import datetime as dt
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from shapely.geometry import box

from app.analysis.service import AnalysisService
from app.core.config import Settings
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
    assert lines[0].startswith("feature,id,value_kind,status,value,unit")
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
