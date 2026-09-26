import csv
import datetime as dt
import io
import json
import threading
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from shapely.geometry import box

from app.analysis.models import DetectionOutcome
from app.analysis.service import AnalysisService
from app.analysis.statuses import ResultStatus
from app.core.config import Settings
from app.earth.raster import RasterReadError
from app.main import create_app
from tests.fakes import FakeCatalog, FakeDetector, blank_layer, clear_quality, make_scene

T1_DAY = dt.date(2024, 6, 2)
T1_AREA = [29.45, 43.50, 29.80, 43.72]
REQUEST = {"bbox": T1_AREA, "date": T1_DAY.isoformat(), "window_days": 3, "aoi_name": "T1"}


def build_client(tmp_path, catalog: FakeCatalog, detector=None) -> TestClient:
    settings = Settings(_env_file=None, storage_dir=tmp_path)
    app = create_app(settings)
    app.state.analysis = AnalysisService(
        app.state.repository,
        catalog,
        tmp_path,
        detector=detector,
        quality_reader=clear_quality,
        true_color=blank_layer,
        quality_mask=blank_layer,
    )
    return TestClient(app)


@pytest.fixture
def client(tmp_path) -> Iterator[TestClient]:
    with build_client(tmp_path, FakeCatalog([make_scene("S2A_T1", T1_DAY)])) as test_client:
        yield test_client


def test_analysis_reports_honest_statuses(client: TestClient) -> None:
    body = client.post("/api/v1/analyses", json=REQUEST).json()
    assert body["scene"]["id"] == "S2A_T1"
    assert body["quality"]["usable"] is True
    assert body["status"] == {"status": "insufficient_data", "label": "недостаточно данных"}
    assert body["detection"]["reason"] == "модель детектора не подключена"
    assert body["concentration"]["status"] == "concentration_unavailable"
    assert body["concentration"]["unit"] == "шт./км²"
    samples = {o["properties"]["sample_id"]: o["properties"] for o in body["observations"]}
    assert samples["MPL-0904"]["synchronous"] is True
    assert samples["MPL-0904"]["value_kind"] == "measurement"


def test_same_request_returns_the_saved_result(client: TestClient) -> None:
    first = client.post("/api/v1/analyses", json=REQUEST).json()
    second = client.post("/api/v1/analyses", json=REQUEST).json()
    assert first == second
    assert client.get(f"/api/v1/analyses/{first['id']}").json() == first
    history = client.get("/api/v1/analyses").json()["items"]
    assert [item["id"] for item in history] == [first["id"]]


def test_layers_and_exports_agree_with_the_result(client: TestClient) -> None:
    result = client.post("/api/v1/analyses", json=REQUEST).json()
    image = client.get(f"/api/v1/analyses/{result['id']}/image.png")
    assert image.status_code == 200
    assert image.content.startswith(b"\x89PNG")
    assert client.get(f"/api/v1/analyses/{result['id']}/mask.png").status_code == 200
    geojson = client.get(f"/api/v1/analyses/{result['id']}/export.geojson").json()
    area = geojson["features"][0]["properties"]
    assert area["status"] == result["status"]["status"]
    assert area["unit"] == "шт./км²"
    assert len(geojson["features"]) == 1 + len(result["observations"])
    csv_text = client.get(f"/api/v1/analyses/{result['id']}/export.csv").text
    lines = csv_text.lstrip("﻿").splitlines()
    assert lines[0].startswith("feature,id,value_kind,status,estimate_status,value,unit")
    assert any(line.startswith("field_observation,MPL-0904,measurement") for line in lines)


def test_no_scene_means_insufficient_data(tmp_path) -> None:
    with build_client(tmp_path, FakeCatalog([])) as client:
        body = client.post("/api/v1/analyses", json=REQUEST).json()
        assert body["scene"] is None
        assert body["status"]["status"] == "insufficient_data"
        assert body["detection"]["reason"].startswith("нет снимков Sentinel-2")
        assert body["layers"] == {}
        assert client.get(f"/api/v1/analyses/{body['id']}/image.png").status_code == 404


def test_catalog_outage_is_an_explicit_error(tmp_path) -> None:
    with build_client(tmp_path, FakeCatalog(fail=True)) as client:
        response = client.post("/api/v1/analyses", json=REQUEST)
        assert response.status_code == 502
        assert response.json()["error"]["code"] == "catalog_unavailable"


def test_plugged_detector_changes_status_and_meta(tmp_path) -> None:
    catalog = FakeCatalog([make_scene("S2A_T1", T1_DAY)])
    with build_client(tmp_path, catalog, FakeDetector()) as client:
        body = client.post("/api/v1/analyses", json=REQUEST).json()
        assert body["status"]["status"] == "detected"
        assert body["detection"]["model"] == "fake-detector-1"
        features = client.get(f"/api/v1/analyses/{body['id']}/export.geojson").json()["features"]
        assert any(f["properties"]["feature"] == "zone" for f in features)
        capabilities = client.get("/api/v1/meta").json()["capabilities"]
        assert {c["key"]: c["status"] for c in capabilities}["debris_detection"] == "available"


@pytest.mark.parametrize(
    ("patch", "status"),
    [
        ({"bbox": [29.8, 43.5, 29.4, 43.7]}, 400),
        ({"bbox": [20, 40, 30, 45]}, 400),
        ({"date": "2099-01-01"}, 400),
        ({"target": "unknown"}, 400),
        ({"window_days": 40}, 422),
        ({"scene_id": "../etc"}, 422),
    ],
)
def test_invalid_requests_are_rejected(client: TestClient, patch: dict, status: int) -> None:
    response = client.post("/api/v1/analyses", json={**REQUEST, **patch})
    assert response.status_code == status
    assert response.json()["error"]["message"]


def test_area_larger_than_the_detector_takes_is_rejected_before_reading(tmp_path) -> None:
    detector = FakeDetector()
    detector.max_pixels = 1_000_000
    catalog = FakeCatalog([make_scene("S2A_T1", T1_DAY)])
    with build_client(tmp_path, catalog, detector) as client:
        response = client.post("/api/v1/analyses", json=REQUEST)
        small = client.post("/api/v1/analyses", json={**REQUEST, "bbox": [29.5, 43.5, 29.6, 43.58]})
    assert response.status_code == 400
    assert "10×10 км" in response.json()["error"]["message"]
    assert small.json()["status"]["status"] == "detected"


def test_unknown_analysis_is_not_found(client: TestClient) -> None:
    assert client.get("/api/v1/analyses/0123456789abcdef").status_code == 404
    assert client.get("/api/v1/analyses/not-an-id").status_code == 404


def test_history_filters_by_status_area_and_date(client: TestClient) -> None:
    result = client.post("/api/v1/analyses", json={**REQUEST, "aoi_id": "doors-west"}).json()

    def listed(**params) -> list[str]:
        response = client.get("/api/v1/analyses", params=params)
        assert response.status_code == 200
        return [item["id"] for item in response.json()["items"]]

    assert listed(status="insufficient_data") == [result["id"]]
    assert listed(status="concentration_unavailable") == [result["id"]]
    assert listed(status="detected") == []
    assert listed(aoi_id="doors-west") == [result["id"]]
    assert listed(aoi_id="neva-bay") == []
    assert listed(date_from="2024-06-02", date_to="2024-06-02") == [result["id"]]
    assert listed(date_from="2024-06-03") == []
    item = client.get("/api/v1/analyses").json()["items"][0]
    assert item["scene_acquired_at"].startswith("2024-06-02")
    assert item["concentration"]["label"] == "концентрация недоступна"
    assert item["observations"] == len(result["observations"])


def test_scene_listing_carries_footprint_and_usability(client: TestClient) -> None:
    response = client.get(
        "/api/v1/scenes",
        params={
            "bbox": ",".join(str(value) for value in T1_AREA),
            "date_from": "2024-05-30",
            "date_to": "2024-06-05",
            "aoi_id": "doors-west",
        },
    )
    assert response.status_code == 200
    [scene] = response.json()["items"]
    assert scene["id"] == "S2A_T1"
    assert scene["aoi_id"] == "doors-west"
    assert scene["usability"] == "usable"
    assert scene["valid_water_fraction"] == 1.0
    assert scene["water_fraction"] == 0.97
    assert scene["sun_glint_risk"] == "high"
    assert scene["geometry"]["type"] == "Polygon"
    assert scene["area_coverage"] == 1.0


def test_scene_listing_keeps_the_best_tile_of_each_pass(tmp_path) -> None:
    day = dt.date(2024, 6, 2)
    edge = make_scene("S2A_T35TPJ", day, geometry=box(28.0, 43.0, 29.6, 44.0), cloud=1.0)
    full = make_scene("S2A_T35TQJ", day, geometry=box(29.0, 43.0, 31.0, 44.0), cloud=5.0)
    later = make_scene("S2B_T35TQJ", dt.date(2024, 6, 4), platform="S2B")
    with build_client(tmp_path, FakeCatalog([edge, full, later])) as client:
        response = client.get(
            "/api/v1/scenes",
            params={
                "bbox": "29.45,43.5,29.8,43.72",
                "date_from": "2024-06-01",
                "date_to": "2024-06-05",
            },
        )
        items = response.json()["items"]
        assert [item["id"] for item in items] == ["S2A_T35TQJ", "S2B_T35TQJ"]
        assert items[0]["area_coverage"] == 1.0


def test_scene_listing_marks_partial_coverage(tmp_path) -> None:
    day = dt.date(2024, 6, 2)
    edge = make_scene("S2B_T37TFG", day, geometry=box(41.0, 41.6, 41.1, 41.9), platform="S2B")
    with build_client(tmp_path, FakeCatalog([edge])) as client:
        response = client.get(
            "/api/v1/scenes",
            params={
                "bbox": "40.95,41.68,41.35,41.88",
                "date_from": "2024-06-02",
                "date_to": "2024-06-02",
            },
        )
        [item] = response.json()["items"]
        assert item["area_coverage"] < 0.5
        assert item["usability"] == "unusable"


def test_scene_listing_rejects_long_periods(client: TestClient) -> None:
    response = client.get(
        "/api/v1/scenes",
        params={"bbox": "29,43,30,44", "date_from": "2024-01-01", "date_to": "2024-06-30"},
    )
    assert response.status_code == 400


def test_a_new_model_version_does_not_reuse_saved_results(tmp_path) -> None:
    catalog = FakeCatalog([make_scene("S2A_T1", T1_DAY)])
    first_detector, second_detector = FakeDetector(), FakeDetector()
    first_detector.fingerprint, second_detector.fingerprint = "v1", "v2"
    with build_client(tmp_path, catalog, detector=first_detector) as first:
        old = first.post("/api/v1/analyses", json=REQUEST).json()["id"]
    with build_client(tmp_path, catalog, detector=second_detector) as second:
        new = second.post("/api/v1/analyses", json=REQUEST).json()["id"]
    assert old != new


class FakeWeather:
    def __init__(self, complete: bool = True) -> None:
        self.calls = 0
        self.complete = complete

    def at(self, lon, lat, moment):
        self.calls += 1
        return {
            "at": moment.isoformat().replace("+00:00", "Z"),
            "point": [round(lon, 5), round(lat, 5)],
            "wind": {"speed_ms": 4.2, "from_deg": 310, "source": "fake"},
            "waves": None if not self.complete else {"height_m": 0.4, "source": "fake"},
            "messages": [] if self.complete else ["волнение не получено"],
            "complete": self.complete,
        }


def versioned_detector(fingerprint: str) -> FakeDetector:
    detector = FakeDetector()
    detector.fingerprint = fingerprint
    return detector


def test_results_store_models_and_are_current(client: TestClient) -> None:
    body = client.post("/api/v1/analyses", json=REQUEST).json()
    assert body["models"] == {"detector": None, "concentration": None}
    assert body["pipeline_version"] == "4"
    assert body["stale"] is False
    assert client.get(f"/api/v1/analyses/{body['id']}").json()["stale"] is False


def test_results_of_an_older_model_are_marked_stale(tmp_path) -> None:
    catalog = FakeCatalog([make_scene("S2A_T1", T1_DAY)])
    with build_client(tmp_path, catalog) as before:
        blind = before.post("/api/v1/analyses", json=REQUEST).json()
    with build_client(tmp_path, catalog, detector=versioned_detector("v1")) as first:
        old = first.post("/api/v1/analyses", json=REQUEST).json()
    with build_client(tmp_path, catalog, detector=versioned_detector("v2")) as second:
        assert second.get(f"/api/v1/analyses/{old['id']}").json()["stale"] is True
        stored = second.get(f"/api/v1/analyses/{blind['id']}").json()
        assert stored["stale"] is True
        assert stored["detection"]["reason"] == "модель детектора не подключена"
        fresh = second.post("/api/v1/analyses", json=REQUEST).json()
        assert fresh["id"] not in {old["id"], blind["id"]}
        assert fresh["stale"] is False
        assert fresh["models"]["detector"] == "v2"
        items = second.get("/api/v1/analyses").json()["items"]
        assert items[0]["id"] == fresh["id"]
        assert [item["stale"] for item in items] == [False, True, True]
        assert items[0]["zones"] == 1


def test_results_of_an_older_pipeline_are_marked_stale(tmp_path) -> None:
    catalog = FakeCatalog([make_scene("S2A_T1", T1_DAY)])
    with build_client(tmp_path, catalog) as client:
        body = client.post("/api/v1/analyses", json=REQUEST).json()
        legacy = "00000000000000aa"
        (tmp_path / legacy).mkdir()
        saved = json.loads((tmp_path / body["id"] / "result.json").read_text(encoding="utf-8"))
        saved.update(id=legacy, pipeline_version="1")
        saved.pop("models")
        (tmp_path / legacy / "result.json").write_text(json.dumps(saved), encoding="utf-8")
        assert client.get(f"/api/v1/analyses/{legacy}").json()["stale"] is True
        items = client.get("/api/v1/analyses").json()["items"]
        assert [(item["id"], item["stale"]) for item in items] == [
            (body["id"], False),
            (legacy, True),
        ]


def test_scene_conditions_come_from_the_weather_source_and_are_cached(tmp_path) -> None:
    catalog = FakeCatalog([make_scene("S2A_T1", T1_DAY)])
    weather = FakeWeather()
    with build_client(tmp_path, catalog) as client:
        client.app.state.analysis.weather = weather
        body = client.post("/api/v1/analyses", json=REQUEST).json()
        first = client.get(f"/api/v1/analyses/{body['id']}/conditions").json()
        second = client.get(f"/api/v1/analyses/{body['id']}/conditions").json()
    assert first == second
    assert weather.calls == 1
    assert first["wind"]["speed_ms"] == 4.2
    assert first["acquired_at"].startswith("2024-06-02T09:00")
    assert "complete" not in first


def test_partial_conditions_are_not_cached(tmp_path) -> None:
    catalog = FakeCatalog([make_scene("S2A_T1", T1_DAY)])
    weather = FakeWeather(complete=False)
    with build_client(tmp_path, catalog) as client:
        client.app.state.analysis.weather = weather
        body = client.post("/api/v1/analyses", json=REQUEST).json()
        partial = client.get(f"/api/v1/analyses/{body['id']}/conditions").json()
        client.get(f"/api/v1/analyses/{body['id']}/conditions")
    assert partial["waves"] is None
    assert partial["messages"] == ["волнение не получено"]
    assert weather.calls == 2


def test_conditions_need_a_scene_and_a_weather_source(tmp_path) -> None:
    with build_client(tmp_path, FakeCatalog([])) as client:
        body = client.post("/api/v1/analyses", json=REQUEST).json()
        assert client.get(f"/api/v1/analyses/{body['id']}/conditions").status_code == 404
    with build_client(tmp_path, FakeCatalog([make_scene("S2A_T1", T1_DAY)])) as client:
        client.app.state.analysis.weather = None
        body = client.post("/api/v1/analyses", json=REQUEST).json()
        assert client.get(f"/api/v1/analyses/{body['id']}/conditions").status_code == 501


class GatedDetector(FakeDetector):
    def __init__(self) -> None:
        self.gate = threading.Event()
        self.calls = 0

    def detect(self, scene, area):
        self.calls += 1
        self.gate.wait(5)
        return super().detect(scene, area)


def test_slow_analysis_answers_running_then_the_result(tmp_path) -> None:
    detector = GatedDetector()
    catalog = FakeCatalog([make_scene("S2A_T1", T1_DAY)])
    with build_client(tmp_path, catalog, detector=detector) as client:
        client.app.state.analysis.wait_seconds = 0.05
        first = client.post("/api/v1/analyses", json=REQUEST)
        again = client.post("/api/v1/analyses", json=REQUEST)
        detector.gate.set()
        client.app.state.analysis.wait_seconds = 5
        done = client.post("/api/v1/analyses", json=REQUEST)
    assert first.status_code == 202
    assert first.json()["state"] == "running"
    assert first.json()["scene"]["id"] == "S2A_T1"
    assert again.status_code == 202
    assert again.json()["id"] == first.json()["id"]
    assert done.status_code == 200
    assert done.json()["id"] == first.json()["id"]
    assert done.json()["status"]["status"] == "detected"
    assert detector.calls == 1


class FlakyDetector(FakeDetector):
    def __init__(self) -> None:
        self.calls = 0

    def detect(self, scene, area):
        self.calls += 1
        if self.calls == 1:
            return DetectionOutcome(
                ResultStatus.INSUFFICIENT_DATA,
                "каналы снимка не читаются: Read failed",
                self.name,
                retryable=True,
            )
        return super().detect(scene, area)


def test_a_read_failure_is_saved_but_recomputed_on_the_next_request(tmp_path) -> None:
    detector = FlakyDetector()
    catalog = FakeCatalog([make_scene("S2A_T1", T1_DAY)])
    with build_client(tmp_path, catalog, detector=detector) as client:
        failed = client.post("/api/v1/analyses", json=REQUEST).json()
        stored = client.get(f"/api/v1/analyses/{failed['id']}").json()
        retried = client.post("/api/v1/analyses", json=REQUEST).json()
        again = client.post("/api/v1/analyses", json=REQUEST).json()
    assert failed["retryable"] is True
    assert stored["status"]["status"] == "insufficient_data"
    assert retried["id"] == failed["id"]
    assert retried["retryable"] is False
    assert retried["status"]["status"] == "detected"
    assert again == retried
    assert detector.calls == 2


def test_an_unreadable_scene_mask_is_retryable(tmp_path) -> None:
    calls = []

    def flaky_quality(*args):
        calls.append(1)
        if len(calls) == 1:
            raise RasterReadError("маска SCL не читается: timeout")
        return clear_quality(*args)

    catalog = FakeCatalog([make_scene("S2A_T1", T1_DAY)])
    with build_client(tmp_path, catalog) as client:
        client.app.state.analysis.quality_reader = flaky_quality
        failed = client.post("/api/v1/analyses", json=REQUEST).json()
        retried = client.post("/api/v1/analyses", json=REQUEST).json()
    assert failed["retryable"] is True
    assert failed["messages"] == ["маска SCL не читается: timeout"]
    assert retried["retryable"] is False
    assert retried["quality"]["usable"] is True


def test_csv_keeps_the_concentration_estimate_as_its_own_row(client: TestClient) -> None:
    body = client.post("/api/v1/analyses", json=REQUEST).json()
    rows = list(
        csv.DictReader(
            io.StringIO(
                client.get(f"/api/v1/analyses/{body['id']}/export.csv").text.removeprefix("\ufeff")
            )
        )
    )
    area = next(row for row in rows if row["feature"] == "request_area")
    estimate = next(row for row in rows if row["feature"] == "concentration")
    assert area["value"] == ""
    assert estimate["value_kind"] == "model_estimate"
    assert estimate["status"] == area["status"]
    assert estimate["estimate_status"] == body["concentration"]["label"]
    assert estimate["measurement_profile"] == (
        body["concentration"]["profile"] or "вне области профилей"
    )
