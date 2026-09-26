import math

import joblib
import numpy as np
import pandas as pd

from littora_ml.common.io import write_json
from littora_ml.concentration import export
from littora_ml.concentration.export import export_profile, service_reason
from littora_ml.concentration.models import Candidate
from littora_ml.concentration.run import (
    HOLDOUT_OPTIMISTIC,
    _service,
    domain_bbox,
    research_role,
    season_check,
    season_pools,
)
from littora_ml.concentration.validation import RepeatedCV, interval

SERVICE = ["median", "idw_k5", "tweedie_glm|spatial"]


def fake_cv(errors: dict[str, np.ndarray], repetitions: int = 2) -> RepeatedCV:
    days = 20
    target = np.full(2 * days, 100.0)
    target[:2] = 5000.0
    groups = np.repeat([f"d{day:02d}" for day in range(days)], 2)
    shape = (repetitions, len(target))
    oof = {label: np.tile(target + error, (repetitions, 1)) for label, error in errors.items()}
    lower, upper = {}, {}
    for label, rows in oof.items():
        lower[label], upper[label] = interval(rows, 0.4)
    selections = [[{"fold": 0, "selected": "median"}] for _ in range(repetitions)]
    return RepeatedCV(
        target,
        groups,
        np.zeros(shape, dtype=int),
        oof,
        lower,
        upper,
        oof["median"].copy(),
        lower["median"].copy(),
        upper["median"].copy(),
        selections,
    )


def options() -> list:
    return [(label, Candidate(label, "median"), ["x_km", "y_km"]) for label in SERVICE]


def errors(lucky: np.ndarray, steady: np.ndarray) -> dict[str, np.ndarray]:
    median = np.full(40, 50.0)
    median[:2] = 5000.0
    return {"median": median, "idw_k5": lucky, "tweedie_glm|spatial": steady}


def gate_case() -> RepeatedCV:
    lucky = np.full(40, 52.0)
    lucky[:2] = 0.0
    steady = np.full(40, 40.0)
    steady[:2] = 4990.0
    return fake_cv(errors(lucky, steady))


CONFIG = {"seed": 0, "bootstrap": 400, "coverage": 0.8}


def test_gate_tests_each_candidate_with_bonferroni_and_deploys_a_passing_one() -> None:
    cv = gate_case()
    service = _service(cv, options(), CONFIG)
    assert math.isclose(service["confidence"], 0.975)
    lucky, steady = service["candidates"]["idw_k5"], service["candidates"]["tweedie_glm|spatial"]
    assert lucky["mae"]["mean"] < steady["mae"]["mean"]
    assert not lucky["passes"] and lucky["difference_vs_median"]["mae"]["ci"][1] >= 0
    assert steady["passes"] and steady["difference_vs_median"]["mae"]["ci"][1] < 0
    assert lucky["difference_vs_median"]["mae"]["confidence"] == service["confidence"]
    assert service["deployed_model"] == "tweedie_glm|spatial"
    assert service["gain_over_median"]
    own = cv.coverage("tweedie_glm|spatial")
    assert service["coverage"]["model"] == "tweedie_glm|spatial"
    assert math.isclose(service["coverage"]["empirical"], float(own.mean()))
    assert service["deployed"]["mae"] == steady["mae"]
    assert math.isclose(service["log_quantile"], cv.quantile("tweedie_glm|spatial", 0.8))
    assert "selection" in service["nested_procedure"]


def test_gate_keeps_the_median_when_no_candidate_is_significant() -> None:
    worse = np.full(40, 60.0)
    worse[:2] = 5000.0
    cv = fake_cv(errors(worse, worse.copy()))
    service = _service(cv, options(), CONFIG)
    assert service["deployed_model"] == "median"
    assert not service["gain_over_median"]
    assert math.isclose(service["coverage"]["empirical"], float(cv.coverage("median").mean()))
    assert math.isclose(service["log_quantile"], cv.quantile("median", 0.8))
    assert service["deployed"]["mae"] == service["baseline"]["mae"]


def test_reason_names_the_deployed_model_with_its_own_difference() -> None:
    service = _service(gate_case(), options(), CONFIG)
    text = service_reason("S1", service, None)
    own = service["candidates"]["tweedie_glm|spatial"]["difference_vs_median"]["mae"]
    low, high = own["ci"]
    assert text.startswith("полевая модель профиля S1 (tweedie_glm|spatial, только координаты)")
    assert f"разница {own['mean']:+.0f} [{low:+.0f}; {high:+.0f}]" in text
    assert "97,5 % ДИ" in text and "Бонферрони" in text
    assert "idw_k5" not in text


def test_reason_for_the_median_lists_every_candidate_and_no_median_model() -> None:
    worse = np.full(40, 60.0)
    worse[:2] = 5000.0
    service = _service(fake_cv(errors(worse, worse.copy())), options(), CONFIG)
    text = service_reason("S3", service, 30.0)
    assert text.startswith("профиль S3: значимого выигрыша над медианой нет")
    for label in ("idw_k5", "tweedie_glm|spatial"):
        mae = service["candidates"][label]["difference_vs_median"]["mae"]
        low, high = mae["ci"]
        assert f"{label} {mae['mean']:+.0f} [{low:+.0f}; {high:+.0f}]" in text
    assert "(median)" not in text
    assert "выдана медиана полевых данных 30 шт./км²" in text


def test_export_takes_quantile_and_coverage_from_the_deployed_model(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(export, "MODELS", tmp_path / "models")
    monkeypatch.setattr(export, "REPORTS", tmp_path / "reports")
    cv = gate_case()
    service = _service(cv, options(), CONFIG)
    table = pd.DataFrame(
        {
            "measurement_profile": "S1",
            "x_km": np.linspace(-20, 20, 40),
            "y_km": np.linspace(5, -5, 40),
            "concentration": cv.target,
        }
    )
    folder = tmp_path / "models" / "concentration" / "compact" / "S1"
    folder.mkdir(parents=True)
    model = Candidate("tweedie_glm", "tweedie", {"power": 1.5, "alpha": 0.3})
    joblib.dump(model.fit(table[["x_km", "y_km"]], cv.target), folder / "service.joblib")
    domain = {"reference": {"latitude": 54.5, "longitude": 20.0}, "max_distance_km": 60}
    meta = {
        "target_key": "litter",
        "service": {"model": "tweedie_glm|spatial", "features": ["x_km", "y_km"]},
        "domain": domain,
    }
    write_json(folder / "meta.json", meta)
    metrics = {
        "events": 40,
        "survey_days": 20,
        "validation": {"outer": "схема"},
        "service": service,
    }
    write_json(tmp_path / "reports" / "metrics" / "concentration" / "compact" / "S1.json", metrics)
    payload = export_profile("compact", "S1", table)
    assert payload["model"] == "tweedie_glm|spatial"
    assert payload["conformal"]["model"] == "tweedie_glm|spatial"
    own = cv.coverage("tweedie_glm|spatial")
    assert math.isclose(payload["conformal"]["empirical"], float(own.mean()))
    assert math.isclose(payload["conformal"]["log_quantile"], cv.quantile(payload["model"], 0.8))
    assert payload["domain"]["max_distance_km"] == 60
    assert payload["validation"]["model_mae"] == service["deployed"]["mae"]["mean"]
    assert (tmp_path / "models" / "concentration" / "service" / "S1.json").exists()


def test_domain_bbox_is_never_narrower_than_the_distance() -> None:
    west, south, east, north = domain_bbox([54.3, 54.8], [19.6, 20.6], 60)
    assert north - 54.8 >= 60 / 110.57 and 54.3 - south >= 60 / 110.57
    widest = 60 / (111.32 * math.cos(math.radians(north)))
    assert east - 20.6 >= widest and 19.6 - west >= widest
    forty_east = 20.6 + 40 / (111.32 * math.cos(math.radians(54.8)))
    assert forty_east <= east


def survey_with_season() -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(2)
    days = 12
    dates = [f"2024-06-{day + 1:02d}" for day in range(days) for _ in range(3)]
    x = rng.normal(0, 20, len(dates))
    angle = 2 * np.pi * (pd.to_datetime(pd.Series(dates)).dt.dayofyear - 1) / 365.25
    table = pd.DataFrame(
        {
            "x_km": x,
            "y_km": rng.normal(0, 5, len(dates)),
            "doy_sin": np.sin(angle),
            "doy_cos": np.cos(angle),
            "date": dates,
        }
    )
    target = np.exp(3 + x / 40) + rng.gamma(2, 2, len(dates))
    return table, target, np.array(dates)


def test_season_check_selects_inside_the_early_days_and_scores_one_option_each() -> None:
    table, target, groups = survey_with_season()
    tweedie = Candidate("tweedie_glm", "tweedie", {"power": 1.5, "alpha": 0.3})
    candidates = [
        ("median", Candidate("median", "median"), ["x_km", "y_km"]),
        ("idw_k5", Candidate("idw_k5", "idw", {"k": 5, "power": 2}), ["x_km", "y_km"]),
        ("tweedie_glm|spatial_season", tweedie, ["x_km", "y_km", "doy_sin", "doy_cos"]),
    ]
    with_season, without_season = season_pools(candidates)
    assert [label for label, _, _ in with_season] == ["tweedie_glm|spatial_season"]
    assert [label for label, _, _ in without_season] == [
        "median",
        "idw_k5",
        "tweedie_glm|spatial_season-season",
    ]
    config = {"seed": 1, "inner_splits": 3, "jobs": 1, "service": {"season_holdout": 0.7}}
    result = season_check(candidates, table, target, groups, config)
    scores = result["options"]
    plain = [label for label, row in scores.items() if not row["season"]]
    assert result["without_season"]["selected"] == min(plain, key=lambda k: scores[k]["inner_mae"])
    assert result["with_season"]["selected"] == "tweedie_glm|spatial_season"
    for side in ("with_season", "without_season"):
        chosen = result[side]
        assert chosen["holdout_mae"] == scores[chosen["selected"]]["holdout_mae"]
    assert result["season_holds_up"] == (
        result["with_season"]["holdout_mae"] < result["without_season"]["holdout_mae"]
    )
    assert result["holdout_minimum"]["selection"] == HOLDOUT_OPTIMISTIC
    assert result["train_days"][1] < result["test_days"][0]


def test_shortlist_is_labelled_optimistic_and_full_zoo_is_primary() -> None:
    assert research_role({"search": {"options": ["idw_k5"]}})["role"] == "shortlist"
    assert "оптимистично" in research_role({"search": {"options": []}})["selection"]
    assert research_role({})["role"] == "primary"


def test_reason_keeps_one_decimal_for_small_concentrations() -> None:
    difference = {"mean": -1.04, "ci": [-4.4, -0.2], "confidence": 0.975}
    row = {"difference_vs_median": {"mae": difference}}
    service = {
        "baseline": {"mae": {"mean": 20.2, "sd": 1.35}},
        "candidates": {"idw_k5": row, "tweedie_glm|spatial": row},
        "confidence": 0.975,
        "repetitions": 10,
        "deployed_model": "median",
    }
    text = service_reason("S3", service, 30.0)
    assert "idw_k5 -1.0 [-4.4; -0.2]" in text
    assert "MAE медианы 20.2 ± 1.4" in text
