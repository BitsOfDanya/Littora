import datetime as dt
import json
import math

import numpy as np
from shapely.geometry import box

from app.analysis.field_models import (
    FieldConcentrationModel,
    ProfileModel,
    calendar_day,
    local_xy,
)
from app.analysis.models import DetectionOutcome, EstimateContext, UnavailableConcentrationModel
from app.analysis.statuses import ResultStatus
from tests.fakes import make_scene

REFERENCE = {"latitude": 43.6, "longitude": 29.7}


def idw_spec() -> dict:
    points = []
    for lat, lon, value in [(43.60, 29.62, 190.0), (43.55, 29.83, 440.0), (43.58, 29.70, 300.0)]:
        x, y = local_xy(lat, lon, REFERENCE)
        points.append([x, y, value])
    return {
        "profile": "S4_visual_GT2_5",
        "target_key": "litter-visual",
        "model": "idw_k5",
        "kind": "idw",
        "features": ["x_km", "y_km"],
        "params": {"k": 5, "power": 2},
        "reference": REFERENCE,
        "domain": {
            "bbox": [29.0, 43.0, 30.5, 44.0],
            "max_distance_km": 60,
            "season": {
                "doy_start": 124,
                "doy_end": 200,
                "margin_days": 30,
                "dates": ["2024-06-02", "2024-06-18"],
                "span": ["02.06", "18.06"],
            },
        },
        "conformal": {"nominal": 0.8, "empirical": 0.7, "log_quantile": 0.5},
        "points": points,
        "reason": "полевая модель профиля S4_visual_GT2_5 (idw_k5, только координаты)",
        "validation": {"nested_mae": 170.0, "baseline_mae": 180.0},
    }


def detection() -> DetectionOutcome:
    return DetectionOutcome(status=ResultStatus.INSUFFICIENT_DATA, reason="нет детектора")


def test_inside_domain_gives_a_research_estimate_with_interval(tmp_path) -> None:
    (tmp_path / "S4.json").write_text(json.dumps(idw_spec()))
    model = FieldConcentrationModel.load(tmp_path)
    context = EstimateContext("litter-visual", dt.date(2024, 6, 2))
    scene = make_scene("S2A_T1", dt.date(2024, 6, 2))
    outcome = model.estimate(scene, box(29.6, 43.55, 29.8, 43.65), detection(), context)
    assert outcome.status is ResultStatus.RESEARCH_ESTIMATE
    assert 190 <= outcome.value <= 440
    assert outcome.lower < outcome.value < outcome.upper
    assert math.isclose(math.log1p(outcome.upper) - math.log1p(outcome.value), 0.5, abs_tol=0.01)
    assert outcome.profile == "S4_visual_GT2_5"
    assert outcome.coverage == 0.7
    assert outcome.reason.startswith("полевая модель профиля S4_visual_GT2_5 (idw_k5")


def test_out_of_season_request_is_unavailable_with_a_reason(tmp_path) -> None:
    (tmp_path / "S4.json").write_text(json.dumps(idw_spec()))
    model = FieldConcentrationModel.load(tmp_path)
    scene = make_scene("S2A_T1", dt.date(2024, 11, 20))
    context = EstimateContext("litter-visual", dt.date(2024, 11, 20))
    outcome = model.estimate(scene, box(29.6, 43.55, 29.8, 43.65), detection(), context)
    assert outcome.status is ResultStatus.CONCENTRATION_UNAVAILABLE
    assert "вне сезона" in outcome.reason
    assert "съёмки 02.06–18.06, допуск ±30 дн." in outcome.reason
    inside = EstimateContext("litter-visual", dt.date(2025, 7, 10))
    assert model.estimate(scene, box(29.6, 43.55, 29.8, 43.65), detection(), inside).status is (
        ResultStatus.RESEARCH_ESTIMATE
    )


def test_season_window_wraps_over_new_year() -> None:
    spec = idw_spec()
    spec["domain"]["season"] |= {"doy_start": 340, "doy_end": 40}
    model = ProfileModel(spec)
    assert model.in_season(dt.date(2024, 12, 20))
    assert model.in_season(dt.date(2025, 1, 15))
    assert not model.in_season(dt.date(2025, 6, 1))


def test_median_without_gain_keeps_research_status_and_says_so(tmp_path) -> None:
    reason = "профиль S4_visual_GT2_5: выигрыша над медианой нет"
    spec = idw_spec() | {"model": "median", "kind": "median", "constant": 250.0, "reason": reason}
    (tmp_path / "S4.json").write_text(json.dumps(spec))
    model = FieldConcentrationModel.load(tmp_path)
    context = EstimateContext("litter-visual", dt.date(2024, 6, 10))
    scene = make_scene("S2A_T1", dt.date(2024, 6, 10))
    outcome = model.estimate(scene, box(29.6, 43.55, 29.8, 43.65), detection(), context)
    assert outcome.status is ResultStatus.RESEARCH_ESTIMATE
    assert outcome.value == 250.0
    assert outcome.lower < 250.0 < outcome.upper
    assert "выигрыша над медианой нет" in outcome.reason


def test_other_target_or_far_area_is_unavailable(tmp_path) -> None:
    (tmp_path / "S4.json").write_text(json.dumps(idw_spec()))
    model = FieldConcentrationModel.load(tmp_path)
    scene = make_scene("S2A_T1", dt.date(2024, 6, 2))
    plastic = EstimateContext("plastic-visual", dt.date(2024, 6, 2))
    far = EstimateContext("litter-visual", dt.date(2024, 6, 2))
    near_area = box(29.6, 43.55, 29.8, 43.65)
    assert model.estimate(scene, near_area, detection(), plastic).status is (
        ResultStatus.CONCENTRATION_UNAVAILABLE
    )
    far_area = box(30.4, 43.95, 30.5, 43.99)
    assert model.estimate(scene, far_area, detection(), far).status is (
        ResultStatus.CONCENTRATION_UNAVAILABLE
    )


def test_glm_prediction_uses_the_exported_scaling() -> None:
    spec = idw_spec() | {
        "kind": "tweedie",
        "features": ["x_km", "y_km"],
        "glm": {"mean": [0.0, 0.0], "scale": [10.0, 10.0], "coef": [0.1, -0.2], "intercept": 4.0},
    }
    model = ProfileModel(spec)
    x, y = local_xy(43.65, 29.8, REFERENCE)
    expected = math.exp(4.0 + 0.1 * x / 10 - 0.2 * y / 10)
    assert math.isclose(model.predict(43.65, 29.8, dt.date(2024, 6, 2)), expected, rel_tol=1e-9)


def test_missing_directory_falls_back_to_unavailable(tmp_path) -> None:
    assert isinstance(
        FieldConcentrationModel.load(tmp_path / "none"), UnavailableConcentrationModel
    )


def baltic_spec() -> dict:
    reference = {"latitude": 54.55, "longitude": 20.1}
    survey = [(54.30, 19.60, 12.0), (54.55, 20.10, 30.0), (54.80, 20.60, 45.0)]
    points = [[*local_xy(lat, lon, reference), value] for lat, lon, value in survey]
    tight = 50 / 111
    spec = idw_spec() | {"reference": reference, "points": points}
    spec["domain"] = spec["domain"] | {
        "bbox": [19.6 - tight, 54.3 - tight, 20.6 + tight, 54.8 + tight],
        "max_distance_km": 60,
    }
    return spec


def east_of_edge(km: float) -> float:
    return 20.6 + km / (111.32 * math.cos(math.radians(54.55)))


def test_forty_km_east_of_an_edge_point_at_54_8_north_is_in_the_domain(tmp_path) -> None:
    spec = baltic_spec()
    model = ProfileModel(spec)
    lon = east_of_edge(40)
    assert lon > spec["domain"]["bbox"][2]
    assert model.in_area(54.8, lon)
    assert not model.in_area(54.8, east_of_edge(70))
    (tmp_path / "S4.json").write_text(json.dumps(spec))
    field = FieldConcentrationModel.load(tmp_path)
    context = EstimateContext("litter-visual", dt.date(2024, 6, 10))
    scene = make_scene("S2A_T1", dt.date(2024, 6, 10))
    area = box(lon - 0.01, 54.79, lon + 0.01, 54.81)
    assert field.estimate(scene, area, detection(), context).status is (
        ResultStatus.RESEARCH_ESTIMATE
    )


def test_prefilter_never_rejects_what_the_distance_rule_allows() -> None:
    model = ProfileModel(baltic_spec())
    reference = model.spec["reference"]
    lat0 = reference["latitude"]
    for x, y, _ in model.spec["points"]:
        for angle in np.linspace(0, 2 * math.pi, 48, endpoint=False):
            dx, dy = x + 59.9 * math.cos(angle), y + 59.9 * math.sin(angle)
            lat = lat0 + dy / 110.57
            lon = reference["longitude"] + dx / (111.32 * math.cos(math.radians(lat0)))
            assert model.in_area(lat, lon)


def test_leap_year_days_match_the_training_numbering_around_new_year() -> None:
    assert calendar_day(dt.date(2024, 2, 29)) == calendar_day(dt.date(2023, 2, 28)) == 59
    assert calendar_day(dt.date(2024, 3, 1)) == calendar_day(dt.date(2023, 3, 1)) == 60
    assert calendar_day(dt.date(2024, 12, 31)) == calendar_day(dt.date(2023, 12, 31)) == 365
    assert calendar_day(dt.date(2025, 1, 1)) == 1
    spec = idw_spec()
    spec["domain"]["season"] |= {"doy_start": 300, "doy_end": 365}
    late = ProfileModel(spec)
    assert late.in_season(dt.date(2024, 12, 31))
    assert not late.in_season(dt.date(2025, 1, 1))
    spec = idw_spec()
    spec["domain"]["season"] |= {"doy_start": 356, "doy_end": 10}
    crossing = ProfileModel(spec)
    assert crossing.in_season(dt.date(2024, 12, 31))
    assert crossing.in_season(dt.date(2025, 1, 1))
    assert crossing.in_season(dt.date(2024, 12, 22))
    assert not crossing.in_season(dt.date(2024, 12, 21))
