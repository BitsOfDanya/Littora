import datetime as dt
import json
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.analysis.service import AnalysisService
from app.core.capabilities import CapabilityKey, CapabilityStatus, capability_status
from app.core.config import REPOSITORY_DIR, Settings
from app.drift.service import DriftService
from app.main import create_app
from app.survey.geo import distance_km
from app.survey.planner import MAX_TARGETS, SurveyOptions, plan, score_of
from app.survey.ports import Port, load_ports
from app.survey.route import nearest_neighbour, plan_tour, tour_length, two_opt
from app.survey.service import SurveyService
from app.survey.water import MaskWater, Router
from tests.fakes import (
    FakeCatalog,
    FakeDetector,
    FakeForcing,
    blank_layer,
    clear_quality,
    make_scene,
)

T0 = "2024-06-02T09:00:00.000Z"
DAY = dt.date(2024, 6, 2)
NOW = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)
HARBOUR = Port("port-a", "Порт А", "Port A", "Russia", "Чёрное море", "Small", None, (29.5, 43.6))
FAR = Port("port-b", "Порт Б", "Port B", "Russia", "Чёрное море", "Small", None, (35.0, 44.0))
REQUEST = {"bbox": [29.45, 43.50, 29.80, 43.72], "date": DAY.isoformat(), "window_days": 3}


def zone(index: int, lon: float, lat: float, probability: float, pixels: int) -> dict:
    return {
        "id": f"zone-{index}",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "centroid": [lon, lat],
        "pixels": pixels,
        "area_km2": pixels * 1e-4,
        "probability_max": probability,
        "probability_mean": probability - 0.1,
    }


def analysis(zones: list[dict], scene: bool = True) -> dict:
    return {
        "id": "0123456789abcdef",
        "computed_at": "2024-06-02T12:00:00+00:00",
        "request": {"bbox": [29.4, 43.4, 29.9, 43.8]},
        "scene": {
            "id": "S2A_T35TPJ_20240602",
            "platform": "S2A",
            "relative_orbit": 107,
            "acquired_at": T0,
        }
        if scene
        else None,
        "quality": clear_quality().as_dict(),
        "target": {
            "title": "Плавающий макромусор, визуальный учёт с судна",
            "size_class": "от 2,5 см",
            "unit": "шт./км²",
        },
        "detection": {"zones": zones},
    }


def forecast(candidate: str, origin: list[float], east_km_per_h: float, beaching=None) -> dict:
    step = east_km_per_h / (111.195 * 0.724)
    path = [[origin[0] + hour * step, origin[1]] for hour in range(73)]
    return {
        "candidate_id": candidate,
        "origin": origin,
        "median_path": path,
        "envelopes": [
            {
                "horizon_h": 24,
                "median": path[24],
                "polygon": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [path[24][0] - 0.01, path[24][1] - 0.01],
                            [path[24][0] + 0.01, path[24][1] - 0.01],
                            [path[24][0] + 0.01, path[24][1] + 0.01],
                            [path[24][0] - 0.01, path[24][1] + 0.01],
                            [path[24][0] - 0.01, path[24][1] - 0.01],
                        ]
                    ],
                },
                "probability": 0.9,
                "afloat": 1.0,
            }
        ],
        "beaching": beaching or [],
        "beaching_any": {"value": beaching[0]["probability"]["value"] if beaching else 0.0},
    }


def drift(forecasts: list[dict]) -> dict:
    return {
        "status": {"status": "scenario", "label": "сценарий дрейфа"},
        "computed_at": "2024-06-02T13:00:00+00:00",
        "request": {"hours": 72, "hindcast_hours": 48},
        "forecasts": forecasts,
        "current_field": {
            "mask": {
                "bounds": [29.0, 43.0, 30.0, 44.0],
                "rows": 10,
                "cols": 10,
                "row_order": "north_to_south",
                "water": "1",
                "data": ["1111111110"] * 10,
            }
        },
    }


ZONES = [
    zone(1, 29.60, 43.60, 0.95, 60),
    zone(2, 29.602, 43.601, 0.90, 10),
    zone(3, 29.70, 43.65, 0.80, 30),
    zone(4, 29.55, 43.52, 0.55, 8),
]


def test_close_zones_merge_and_targets_are_ranked_by_score() -> None:
    body = plan(analysis(ZONES), None, [HARBOUR], SurveyOptions(), now=NOW)
    assert body["status"] == {"status": "estimate", "label": "план обследования — расчётный"}
    assert body["zones"] == {"total": 4, "groups": 3, "planned": 3, "limit": MAX_TARGETS}
    targets = body["targets"]
    assert [target["id"] for target in targets] == ["SV-01", "SV-02", "SV-03"]
    assert targets[0]["zone_ids"] == ["zone-1", "zone-2"]
    assert targets[0]["pixels"] == 70
    scores = [target["score"] for target in targets]
    assert scores == sorted(scores, reverse=True)
    for target in targets:
        assert target["score"] == score_of(target["components"])
        assert target["components"]["persistence"] is None
        assert target["components"]["drift_risk"] is None
        assert target["urgency"]["level"] == "unknown"
        assert target["checks"][-1].startswith("учёт шт./км² по протоколу кейса")
        assert target["nearest_port"]["id"] == "port-a"
    assert body["weights"]["persistence"] == 0.0
    assert body["drift"]["used"] is False
    assert any("рассчитайте дрейф" in message for message in body["messages"])


def test_route_starts_at_nearest_port_and_departs_in_daylight_after_the_image() -> None:
    body = plan(analysis(ZONES), None, [FAR, HARBOUR], SurveyOptions(speed_kn=10), now=NOW)
    route = body["route"]
    assert body["port"]["id"] == "port-a"
    assert route["path"][0] == route["path"][-1] == [29.5, 43.6]
    assert sorted(route["order"]) == ["SV-01", "SV-02", "SV-03"]
    window = body["exit_window"]
    departure = dt.datetime.fromisoformat(window["departure"].replace("Z", "+00:00"))
    ready = dt.datetime(2024, 6, 2, 12, 0, tzinfo=dt.UTC)
    assert departure >= ready and departure.minute % 5 == 0
    sunrise, sunset = (
        dt.datetime.fromisoformat(value.replace("Z", "+00:00")) for value in window["daylight"]
    )
    last = route["legs"][-1]["arrive_h"] + route["dwell_min"] / 60
    assert departure + dt.timedelta(hours=last) <= sunset
    assert sunrise < departure
    assert window["relaxed"] is None
    assert window["beaching_at"] is None and window["scenario_end"] is None
    assert window["past"] is False
    etas = [target["eta"] for target in sorted(body["targets"], key=lambda t: t["visit"])]
    assert etas == sorted(etas)
    assert all(target["method"] == "vessel" for target in body["targets"])
    expected = route["one_way_km"] + distance_km(route["path"][-2], route["path"][-1])
    assert route["distance_km"] == pytest.approx(expected, abs=0.02)


def test_drift_sets_urgency_deadline_and_moves_targets_along_the_track() -> None:
    beach = [
        {
            "name": "Берег у места «Мыс»",
            "severity": "alarm",
            "probability": {"value": 0.6},
            "window_h": [5, 9],
        }
    ]
    scenario = drift(
        [
            forecast("zone-1", [29.6, 43.6], 0.45, beach),
            forecast("zone-3", [29.7, 43.65], 0.1),
        ]
    )
    body = plan(analysis(ZONES), scenario, [HARBOUR], SurveyOptions(), now=NOW)
    targets = {target["lead_zone"]: target for target in body["targets"]}
    fast = targets["zone-1"]
    assert fast["urgency"]["leaves_1km_h"] == 3
    assert fast["urgency"]["leaves_2km_h"] == 5
    assert fast["urgency"]["beaching"]["window_h"] == [5, 9]
    assert fast["urgency"]["level"] == "high"
    assert fast["components"]["drift_risk"] == pytest.approx(0.79)
    assert fast["window"]["to"] == "2024-06-02T14:00:00Z"
    assert fast["spot_until"] == "2024-06-02T14:00:00Z"
    assert fast["drift"]["hours"] == 72 and len(fast["drift"]["track"]) == 73
    assert fast["drift"]["radii"][1]["hour"] == 24
    assert fast["shift_at_eta_km"] > 1.5
    slow = targets["zone-3"]
    assert slow["urgency"]["leaves_2km_h"] == 21
    assert slow["urgency"]["level"] == "medium"
    assert targets["zone-4"]["drift"] is None
    assert targets["zone-4"]["urgency"]["level"] == "unknown"
    window = body["exit_window"]
    assert window["beaching_at"] == "2024-06-02T14:00:00Z"
    assert window["scenario_end"] == "2024-06-05T09:00:00Z"
    assert window["relaxed"] is None
    arrival = fast["eta"]
    assert arrival <= "2024-06-02T14:00:00Z"
    assert fast["shore_km"] is not None and fast["shore_km"] < 40
    assert body["drift"]["used"] is True
    assert any("дрейф не считался" in message for message in body["messages"])


def test_beaching_before_the_image_is_ready_is_explained() -> None:
    beach = [
        {
            "name": "Берег у места «Мыс»",
            "severity": "caution",
            "probability": {"value": 0.2},
            "window_h": [1, 4],
        }
    ]
    scenario = drift([forecast("zone-1", [29.6, 43.6], 0.2, beach)])
    body = plan(analysis(ZONES[:1]), scenario, [HARBOUR], SurveyOptions(), now=NOW)
    [target] = body["targets"]
    assert target["window"] is None
    assert "раньше, чем готовы снимок и анализ" in target["window_note"]
    assert body["exit_window"]["relaxed"] == "beaching"
    assert any(message.startswith("до выноса на берег") for message in body["messages"])


def test_scenario_end_is_not_reported_as_beaching() -> None:
    calm = plan(
        analysis(ZONES[:1]),
        drift([forecast("zone-1", [29.6, 43.6], 0.1)]),
        [HARBOUR],
        SurveyOptions(),
        now=NOW,
    )
    window = calm["exit_window"]
    assert calm["targets"][0]["urgency"]["beaching"] is None
    assert window["beaching_at"] is None
    assert window["scenario_end"] == "2024-06-05T09:00:00Z"
    short = forecast("zone-1", [29.6, 43.6], 0.1)
    short["median_path"] = short["median_path"][:3]
    short["envelopes"] = []
    body = plan(analysis(ZONES[:1]), drift([short]), [HARBOUR], SurveyOptions(), now=NOW)
    window = body["exit_window"]
    assert window["beaching_at"] is None
    assert window["scenario_end"] == "2024-06-02T11:00:00Z"
    assert window["relaxed"] == "scenario_end"
    assert any(message.startswith("до конца сценария дрейфа") for message in body["messages"])
    assert not any("выноса на берег" in message for message in body["messages"])


def test_uav_feasibility_follows_range() -> None:
    near = plan(analysis(ZONES), None, [HARBOUR], SurveyOptions(uav_range_km=50), now=NOW)
    assert all(target["uav"]["feasible"] for target in near["targets"])
    far = plan(
        analysis(ZONES), None, [HARBOUR], SurveyOptions(uav_range_km=1, route_targets=1), now=NOW
    )
    unknown = [target for target in far["targets"] if target["method"] != "vessel"]
    assert unknown and all(target["uav"]["feasible"] is None for target in unknown)
    assert all(target["method"] == "tasking" for target in unknown)


def test_far_port_gives_no_route() -> None:
    body = plan(analysis(ZONES), None, [FAR], SurveyOptions(), now=NOW)
    assert body["route"] is None and body["port"] is None and body["exit_window"] is None
    assert any("маршрут не строится" in message for message in body["messages"])
    assert all(target["components"]["accessibility"] == 0.0 for target in body["targets"])


def test_empty_and_imageless_analyses() -> None:
    passes = [{"id": "S2B-R107-20240605"}]
    empty = plan(analysis([]), None, [HARBOUR], SurveyOptions(), passes, now=NOW)
    assert empty["status"] == {"status": "no_zones", "label": "нет зон для обследования"}
    assert empty["targets"] == [] and empty["route"] is None
    assert empty["passes"] == passes and empty["messages"] == []
    blind = plan(analysis(ZONES, scene=False), None, [HARBOUR], SurveyOptions(), now=NOW)
    assert blind["status"]["status"] == "insufficient_data"


def test_two_opt_untangles_a_crossed_tour() -> None:
    stops = [[0.0, 1.0], [1.0, 1.0], [1.0, 0.0], [0.0, 0.0]]
    start = [0.5, -0.2]
    points = [start, *stops]
    matrix = [[distance_km(a, b) for b in points] for a in points]
    crossed = [0, 4, 2, 1, 3, 0]
    fixed = two_opt(crossed, matrix)
    assert tour_length(fixed, matrix) < tour_length(crossed, matrix)
    order = plan_tour(start, stops)
    assert sorted(order) == [0, 1, 2, 3]
    greedy = nearest_neighbour(matrix)
    tour = [0, *[index + 1 for index in order], 0]
    assert tour_length(tour, matrix) <= tour_length(greedy, matrix) + 1e-9


def test_repository_ports_cover_russian_and_black_sea_harbours(tmp_path: Path) -> None:
    ports = load_ports(REPOSITORY_DIR / "data" / "aoi" / "ports.geojson")
    names = {port.name for port in ports}
    assert {"Новороссийск", "Туапсе", "Сочи", "Ейск", "Батуми", "Варна"} <= names
    assert not any("terminal" in port.name_en.lower() for port in ports)
    assert load_ports(tmp_path / "missing.geojson") == []


def build_client(tmp_path: Path, detector=None) -> TestClient:
    settings = Settings(_env_file=None, storage_dir=tmp_path)
    app = create_app(settings)
    scenes = [
        make_scene("S2A_T1", DAY),
        make_scene("S2B_T1", DAY + dt.timedelta(days=3), platform="S2B"),
    ]
    app.state.analysis = AnalysisService(
        app.state.repository,
        FakeCatalog(scenes),
        tmp_path,
        detector=detector,
        quality_reader=clear_quality,
        true_color=blank_layer,
        quality_mask=blank_layer,
    )
    app.state.drift = DriftService(FakeForcing(), places=[], scene_classes=None)
    app.state.survey = SurveyService([HARBOUR], now=lambda: NOW)
    return TestClient(app)


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    with build_client(tmp_path, FakeDetector()) as test_client:
        yield test_client


def analysis_id(client: TestClient) -> str:
    return client.post("/api/v1/analyses", json=REQUEST).json()["id"]


def test_survey_is_cached_and_refreshed_after_drift(client: TestClient, tmp_path: Path) -> None:
    identifier = analysis_id(client)
    url = f"/api/v1/analyses/{identifier}/survey"
    missing = client.get(url)
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"
    body = client.post(url).json()
    assert body["analysis_id"] == identifier
    assert body["model"] == "littora-survey-3"
    assert body["request"] == SurveyOptions().as_dict()
    assert body["drift"]["used"] is False
    [target] = body["targets"]
    assert target["lead_zone"] == "zone-1"
    assert body["route"]["order"] == ["SV-01"]
    assert [item["id"] for item in body["passes"]] == ["S2B-R107-20240605"]
    assert body["inputs"]["drift_computed_at"] is None
    assert (tmp_path / identifier / "survey.json").exists()
    assert client.get(url).json() == body
    assert client.post(url).json() == body
    client.post(f"/api/v1/analyses/{identifier}/drift")
    refreshed = client.get(url).json()
    assert refreshed["drift"]["used"] is True
    assert refreshed["targets"][0]["drift"] is not None
    assert refreshed["passes"] == body["passes"]
    saved = json.loads((tmp_path / identifier / "survey.json").read_text(encoding="utf-8"))
    assert saved["inputs"] == refreshed["inputs"]
    faster = client.post(url, json={"speed_kn": 20, "route_targets": 3}).json()
    assert faster["request"]["speed_kn"] == 20
    assert faster["route"]["speed_kn"] == 20


def test_past_window_is_judged_when_the_plan_is_read(client: TestClient) -> None:
    identifier = analysis_id(client)
    url = f"/api/v1/analyses/{identifier}/survey"
    fresh = client.post(url).json()
    assert fresh["exit_window"]["past"] is False
    assert not any(message.startswith("окно выхода в прошлом") for message in fresh["messages"])
    client.app.state.survey.now = lambda: NOW + dt.timedelta(days=30)
    for late in (client.get(url).json(), client.post(url).json()):
        assert late["computed_at"] == fresh["computed_at"]
        assert late["exit_window"]["past"] is True
        assert late["messages"][-1].startswith("окно выхода в прошлом: снимок от 02.06.2024")
    client.app.state.survey.now = lambda: NOW
    assert client.get(url).json() == fresh


def test_survey_without_zones(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        identifier = analysis_id(client)
        body = client.post(f"/api/v1/analyses/{identifier}/survey").json()
    assert body["status"] == {"status": "no_zones", "label": "нет зон для обследования"}
    assert body["targets"] == []
    assert [item["id"] for item in body["passes"]] == ["S2B-R107-20240605"]


@pytest.mark.parametrize(
    "patch", [{"speed_kn": 0}, {"route_targets": 13}, {"uav_range_km": -1}, {"lead_h": 49}]
)
def test_survey_rejects_bad_options(client: TestClient, patch: dict) -> None:
    identifier = analysis_id(client)
    response = client.post(f"/api/v1/analyses/{identifier}/survey", json=patch)
    assert response.status_code == 422


def test_survey_capability_follows_wiring(client: TestClient) -> None:
    for method in (client.get, client.post):
        response = method("/api/v1/analyses/0123456789abcdef/survey")
        assert response.status_code == 404
    statuses = {c["key"]: c["status"] for c in client.get("/api/v1/meta").json()["capabilities"]}
    assert statuses["survey_planning"] == "available"
    assert capability_status()[CapabilityKey.SURVEY_PLANNING] == CapabilityStatus.PLANNED
    del client.app.state.survey
    statuses = {c["key"]: c["status"] for c in client.get("/api/v1/meta").json()["capabilities"]}
    assert statuses["survey_planning"] == "planned"
    assert client.post("/api/v1/analyses/0123456789abcdef/survey").status_code == 501


def land_block_mask() -> dict:
    rows = ["1" * 20 for _ in range(20)]
    for row in range(8, 12):
        rows[row] = "1" * 9 + "00" + "1" * 9
    return {
        "bounds": [29.0, 43.0, 30.0, 44.0],
        "rows": 20,
        "cols": 20,
        "row_order": "north_to_south",
        "water": "1",
        "data": rows,
    }


def test_leg_across_a_land_block_goes_around_it() -> None:
    mask = MaskWater(land_block_mask())
    west, east = [29.3, 43.5], [29.7, 43.5]
    straight_line = np.column_stack([np.linspace(29.3, 29.7, 50), np.full(50, 43.5)])
    assert (mask.sample(straight_line[:, 0], straight_line[:, 1]) == 2).any()
    passage = Router([mask]).leg(west, east)
    assert passage.detour is True
    assert passage.over_land is False
    assert passage.path[0] == west and passage.path[-1] == east
    assert passage.km > distance_km(west, east)
    dense = []
    for a, b in zip(passage.path, passage.path[1:], strict=False):
        t = np.linspace(0.0, 1.0, 200)
        dense.append(np.column_stack([a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]))
    points = np.concatenate(dense)
    assert not (mask.sample(points[:, 0], points[:, 1]) == 2).any()
    open_water = Router([mask]).leg([29.1, 43.1], [29.3, 43.2])
    assert open_water.detour is False and open_water.over_land is False
    assert Router([]).leg(west, east).over_land is None


def test_plan_routes_around_land_and_notes_it() -> None:
    port = Port("port-w", "Порт В", "Port W", "Russia", "Чёрное море", "Small", None, (29.3, 43.5))
    scenario = drift([])
    scenario["current_field"]["mask"] = land_block_mask()
    target = [zone(1, 29.7, 43.5, 0.9, 50)]
    body = plan(analysis(target), scenario, [port], SurveyOptions(), now=NOW)
    route = body["route"]
    [leg] = route["legs"]
    assert leg["detour"] is True and leg["over_land"] is False
    assert route["back"]["detour"] is True
    assert route["over_land"] is False
    assert leg["km"] > distance_km(port.position, [29.7, 43.5])
    assert route["one_way_km"] == leg["km"]
    assert route["path"] == [[29.3, 43.5], [29.7, 43.5], [29.3, 43.5]]
    assert len(route["track"]) > 3
    assert any("обход суши по маске воды" in message for message in body["messages"])
    bare = plan(analysis(target), None, [port], SurveyOptions(), now=NOW)
    assert bare["route"]["over_land"] is None
    assert bare["route"]["legs"][0]["detour"] is False
    assert any("прямые отрезки" in message for message in bare["messages"])
