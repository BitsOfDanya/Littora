import datetime as dt
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from shapely.geometry import box, mapping, shape

from app.analysis.models import DetectionOutcome
from app.analysis.service import AnalysisService
from app.analysis.statuses import ResultStatus
from app.core.config import Settings
from app.earth.raster import MASK_COLORS, RenderedLayer, encode_png
from app.main import create_app
from app.timeline.change import Coverage, zone_change
from app.timeline.service import TimelineService
from tests.fakes import FakeCatalog, blank_layer, clear_quality, make_scene

AREA = [29.45, 43.50, 29.80, 43.72]
DAYS = [dt.date(2024, 6, 2), dt.date(2024, 6, 7), dt.date(2024, 6, 12), dt.date(2024, 6, 17)]
PERIOD = {"date_from": "2024-05-30", "date_to": "2024-06-20"}
QUERY = {"bbox": ",".join(str(value) for value in AREA), **PERIOD, "aoi_id": "doors-west"}
RUN = {"bbox": AREA, **PERIOD, "aoi_id": "doors-west", "aoi_name": "T1–T2"}


def zone(zone_id: str, west: float, south: float, peak: float = 0.5) -> dict:
    return {
        "id": zone_id,
        "geometry": mapping(box(west, south, west + 0.001, south + 0.001)),
        "pixels": 60,
        "area_km2": 0.006,
        "probability_max": peak,
    }


HERE = zone("zone-1", 29.60, 43.60, 0.7)
THERE = zone("zone-2", 29.70, 43.65, 0.4)


class ScriptedDetector:
    def __init__(self, name: str = "scripted-1") -> None:
        self.name = name
        self.calls: list[str] = []
        self.script = {
            "S2A_D1": [HERE],
            "S2B_D2": [HERE, {**THERE, "id": "zone-2"}],
            "S2A_D3": [{**THERE, "id": "zone-1"}],
        }

    def detect(self, scene, area):
        self.calls.append(scene.id)
        if scene.id == "S2B_D4":
            return DetectionOutcome(ResultStatus.INSUFFICIENT_DATA, "снимок не читается", self.name)
        zones = self.script.get(scene.id, [])
        status = ResultStatus.DETECTED if zones else ResultStatus.NOT_DETECTED
        return DetectionOutcome(status, f"зон: {len(zones)}", self.name, zones=zones)


def scenes() -> list:
    return [
        make_scene("S2A_D1", DAYS[0]),
        make_scene("S2B_D2", DAYS[1], platform="S2B"),
        make_scene("S2A_D3", DAYS[2]),
        make_scene("S2B_D4", DAYS[3], platform="S2B", cloud=40.0),
        make_scene("S2A_CLOUD", dt.date(2024, 6, 10), cloud=90.0),
    ]


def build(tmp_path: Path, detector=None, catalog: FakeCatalog | None = None) -> TestClient:
    settings = Settings(
        _env_file=None, storage_dir=tmp_path, models_dir=Path("/nonexistent-littora-models")
    )
    app = create_app(settings)
    app.state.analysis = AnalysisService(
        app.state.repository,
        catalog or FakeCatalog(scenes()),
        tmp_path,
        detector=detector,
        quality_reader=clear_quality,
        true_color=blank_layer,
        quality_mask=blank_layer,
    )
    app.state.timeline = TimelineService(submit=lambda job: job())
    return TestClient(app)


@pytest.fixture
def detector() -> ScriptedDetector:
    return ScriptedDetector()


@pytest.fixture
def client(tmp_path, detector) -> TestClient:
    with build(tmp_path, detector) as test_client:
        yield test_client


def test_lists_passes_before_any_analysis(client: TestClient) -> None:
    body = client.get("/api/v1/timeline", params=QUERY).json()
    ids = [item["scene"]["id"] for item in body["passes"]]
    assert ids == ["S2A_D1", "S2B_D2", "S2A_CLOUD", "S2A_D3", "S2B_D4"]
    assert all(item["analysis"] is None and item["change"] is None for item in body["passes"])
    assert body["summary"] == {"passes": 5, "usable": 3, "analysed": 0, "comparable": 0}
    assert body["value_kind"] == "detections"
    assert "не динамика концентрации" in body["note"]
    assert body["run"] is None
    assert body["limits"]["default_passes"] == 6


def test_run_analyses_usable_passes_and_tracks_zone_changes(
    client: TestClient, detector: ScriptedDetector
) -> None:
    run = client.post("/api/v1/timeline/runs", json=RUN).json()
    assert run["status"] == "done"
    assert [item["scene_id"] for item in run["items"]] == ["S2A_D1", "S2B_D2", "S2A_D3", "S2B_D4"]
    assert run["completed"] == run["total"] == 4
    assert detector.calls == ["S2A_D1", "S2B_D2", "S2A_D3", "S2B_D4"]

    body = client.get("/api/v1/timeline", params=QUERY).json()
    passes = {item["scene"]["id"]: item for item in body["passes"]}
    assert body["summary"]["analysed"] == 4
    assert body["summary"]["comparable"] == 3
    assert passes["S2A_CLOUD"]["analysis"] is None
    first = passes["S2A_D1"]["analysis"]
    assert first["status"]["status"] == "detected"
    assert first["zone_count"] == 1
    assert first["area_km2"] == 0.006
    assert first["probability_max"] == 0.7
    assert first["concentration"]["status"] == "concentration_unavailable"
    assert passes["S2A_D1"]["change"] is None
    assert passes["S2B_D2"]["change"]["counts"] == {
        "new": 1,
        "persisting": 1,
        "disappeared": 0,
        "not_observed": 0,
    }
    assert passes["S2B_D2"]["change"]["before"]["scene_id"] == "S2A_D1"
    assert passes["S2A_D3"]["change"]["counts"] == {
        "new": 0,
        "persisting": 1,
        "disappeared": 1,
        "not_observed": 0,
    }
    last = passes["S2B_D4"]
    assert last["analysis"]["zone_count"] is None
    assert last["analysis"]["area_km2"] is None
    assert last["change"] is None
    assert body["run"]["id"] == run["id"]


def test_saved_results_are_reused_not_recomputed(
    client: TestClient, detector: ScriptedDetector
) -> None:
    client.post("/api/v1/timeline/runs", json=RUN)
    again = client.post("/api/v1/timeline/runs", json=RUN).json()
    assert again["total"] == 0
    assert again["status"] == "done"
    assert again["message"] == "все пригодные пролёты периода уже проанализированы"
    assert len(detector.calls) == 4
    explicit = client.post("/api/v1/timeline/runs", json={**RUN, "scene_ids": ["S2A_D1"]}).json()
    assert explicit["items"][0]["state"] == "cached"
    assert len(detector.calls) == 4


class FlakyScriptedDetector(ScriptedDetector):
    def detect(self, scene, area):
        if scene.id == "S2A_D3" and "S2A_D3" not in self.calls:
            self.calls.append(scene.id)
            return DetectionOutcome(
                ResultStatus.INSUFFICIENT_DATA,
                "каналы снимка не читаются: Read failed",
                self.name,
                retryable=True,
            )
        return super().detect(scene, area)


def test_a_pass_with_a_read_failure_is_analysed_again(tmp_path: Path) -> None:
    detector = FlakyScriptedDetector()
    with build(tmp_path, detector) as client:
        client.post("/api/v1/timeline/runs", json=RUN)
        failed = client.get("/api/v1/timeline", params=QUERY).json()
        again = client.post("/api/v1/timeline/runs", json=RUN).json()
        body = client.get("/api/v1/timeline", params=QUERY).json()
    passes = {item["scene"]["id"]: item["analysis"] for item in failed["passes"]}
    assert passes["S2A_D3"]["retryable"] is True
    assert passes["S2A_D1"]["retryable"] is False
    assert [item["scene_id"] for item in again["items"]] == ["S2A_D3"]
    assert again["items"][0]["state"] == "done"
    fixed = {item["scene"]["id"]: item["analysis"] for item in body["passes"]}["S2A_D3"]
    assert fixed["retryable"] is False
    assert fixed["zone_count"] == 1
    assert detector.calls.count("S2A_D3") == 2


def test_limit_spreads_the_chosen_passes_over_the_period(
    client: TestClient, detector: ScriptedDetector
) -> None:
    run = client.post("/api/v1/timeline/runs", json={**RUN, "max_passes": 2}).json()
    assert [item["scene_id"] for item in run["items"]] == ["S2A_D1", "S2A_D3"]
    body = client.get("/api/v1/timeline", params=QUERY).json()
    passes = {item["scene"]["id"]: item for item in body["passes"]}
    assert passes["S2A_D3"]["change"]["before"]["scene_id"] == "S2A_D1"
    assert passes["S2A_D3"]["change"]["counts"] == {
        "new": 1,
        "persisting": 0,
        "disappeared": 1,
        "not_observed": 0,
    }


def test_monitor_analysis_of_the_same_area_joins_the_series(client: TestClient) -> None:
    saved = client.post(
        "/api/v1/analyses",
        json={"bbox": AREA, "date": "2024-06-07", "window_days": 3, "scene_id": "S2B_D2"},
    ).json()
    other_area = client.post(
        "/api/v1/analyses",
        json={"bbox": [29.5, 43.5, 29.7, 43.7], "date": "2024-06-02", "scene_id": "S2A_D1"},
    ).json()
    assert other_area["status"]["status"] == "detected"
    body = client.get("/api/v1/timeline", params=QUERY).json()
    passes = {item["scene"]["id"]: item for item in body["passes"]}
    assert passes["S2B_D2"]["analysis"]["id"] == saved["id"]
    assert passes["S2B_D2"]["analysis"]["window_days"] == 3
    assert passes["S2A_D1"]["analysis"] is None


def test_results_of_other_models_are_not_mixed_in(tmp_path: Path) -> None:
    with build(tmp_path, ScriptedDetector("old-model")) as client:
        client.post("/api/v1/timeline/runs", json=RUN)
    with build(tmp_path, ScriptedDetector("new-model")) as client:
        body = client.get("/api/v1/timeline", params=QUERY).json()
        assert body["summary"]["analysed"] == 0


def test_compare_any_two_analysed_passes(client: TestClient) -> None:
    client.post("/api/v1/timeline/runs", json=RUN)
    passes = {
        item["scene"]["id"]: item["analysis"]
        for item in client.get("/api/v1/timeline", params=QUERY).json()["passes"]
    }
    body = client.get(
        "/api/v1/timeline/compare",
        params={"before": passes["S2A_D1"]["id"], "after": passes["S2A_D3"]["id"]},
    ).json()
    assert body["comparable"] is True
    assert body["counts"] == {"new": 1, "persisting": 0, "disappeared": 1, "not_observed": 0}
    assert body["after_zones"] == {"zone-1": "new"}
    assert body["before_zones"] == {"zone-1": "disappeared"}
    blocked = client.get(
        "/api/v1/timeline/compare",
        params={"before": passes["S2A_D3"]["id"], "after": passes["S2B_D4"]["id"]},
    ).json()
    assert blocked["comparable"] is False
    assert blocked["reason"]
    missing = client.get("/api/v1/timeline/compare", params={"before": "x", "after": "y"})
    assert missing.status_code == 404


def test_meta_marks_change_tracking_available_with_a_detector(client: TestClient) -> None:
    capabilities = client.get("/api/v1/meta").json()["capabilities"]
    assert {c["key"]: c["status"] for c in capabilities}["change_tracking"] == "available"


def test_unknown_run_is_not_found(client: TestClient) -> None:
    assert client.get("/api/v1/timeline/runs/abc").status_code == 404


@pytest.mark.parametrize(
    ("patch", "status"),
    [
        ({"date_from": "2024-01-01", "date_to": "2024-06-20"}, 400),
        ({"date_from": "2024-06-20", "date_to": "2024-06-01"}, 400),
        ({"bbox": [20, 40, 30, 45]}, 400),
        ({"scene_ids": ["S2A_UNKNOWN"]}, 400),
        ({"target": "unknown"}, 400),
        ({"max_passes": 40}, 422),
    ],
)
def test_invalid_runs_are_rejected(client: TestClient, patch: dict, status: int) -> None:
    assert client.post("/api/v1/timeline/runs", json={**RUN, **patch}).status_code == status


def test_runs_need_a_detector(tmp_path: Path) -> None:
    with build(tmp_path) as client:
        response = client.post("/api/v1/timeline/runs", json=RUN)
        assert response.status_code == 501
        assert client.get("/api/v1/timeline", params=QUERY).status_code == 200


def test_catalog_outage_is_explicit(tmp_path: Path) -> None:
    with build(tmp_path, ScriptedDetector(), FakeCatalog(fail=True)) as client:
        response = client.get("/api/v1/timeline", params=QUERY)
        assert response.status_code == 502


def test_zone_change_tolerates_small_offsets() -> None:
    shifted = zone("zone-1", 29.60 + 0.0012, 43.60, 0.7)
    far = zone("zone-2", 29.60 + 0.01, 43.60)
    result = zone_change([HERE], [shifted, far])
    assert result["after_zones"] == {"zone-1": "persisting", "zone-2": "new"}
    assert result["counts"] == {"new": 1, "persisting": 1, "disappeared": 0, "not_observed": 0}
    assert result["area_km2"] == {
        "new": 0.006,
        "persisting": 0.006,
        "disappeared": 0.0,
        "not_observed": 0.0,
    }
    assert zone_change([], [])["counts"] == {
        "new": 0,
        "persisting": 0,
        "disappeared": 0,
        "not_observed": 0,
    }


CORNERS = [[29.0, 44.0], [30.0, 44.0], [30.0, 43.0], [29.0, 43.0]]


def half_cloudy() -> np.ndarray:
    pixels = np.zeros((4, 4, 4), dtype=np.uint8)
    pixels[:, :2] = MASK_COLORS["cloud"]
    pixels[3, 3] = MASK_COLORS["bright_water"]
    return pixels


def test_zones_hidden_on_the_other_date_are_not_observed() -> None:
    seen = Coverage(half_cloudy(), CORNERS)
    hidden = zone("zone-9", 29.20, 43.60)
    assert not seen.observed(shape(hidden["geometry"]))
    assert seen.observed(shape(HERE["geometry"]))
    assert seen.observed(shape(zone("zone-8", 29.90, 43.10)["geometry"]))
    result = zone_change([HERE, hidden], [], before_coverage=seen, after_coverage=seen)
    assert result["before_zones"] == {"zone-1": "disappeared", "zone-9": "not_observed"}
    assert result["counts"] == {"new": 0, "persisting": 0, "disappeared": 1, "not_observed": 1}
    assert result["area_km2"]["not_observed"] == 0.006
    reverse = zone_change([], [HERE, hidden], before_coverage=seen, after_coverage=seen)
    assert reverse["after_zones"] == {"zone-1": "new", "zone-9": "not_observed"}
    assert result["masks_checked"] is True and "ненаблюдавшейся" in result["method"]
    blind = zone_change([HERE], [])
    assert blind["masks_checked"] is False and "маски SCL нет" in blind["method"]


def test_compare_reads_the_saved_cloud_masks(tmp_path: Path) -> None:
    def mask(scene, *_args) -> RenderedLayer:
        pixels = half_cloudy() if scene.id == "S2A_D3" else np.zeros((4, 4, 4), np.uint8)
        return RenderedLayer(encode_png(pixels), CORNERS, 4, 4)

    detector = ScriptedDetector()
    detector.script["S2A_D3"] = []
    detector.script["S2A_D1"] = [HERE, zone("zone-9", 29.20, 43.60)]
    with build(tmp_path, detector) as client:
        client.app.state.analysis.quality_mask = mask
        client.post("/api/v1/timeline/runs", json=RUN)
        body = client.get("/api/v1/timeline", params=QUERY).json()
        ids = {
            item["scene"]["id"]: item["analysis"]["id"]
            for item in body["passes"]
            if item["analysis"]
        }
        compare = client.get(
            "/api/v1/timeline/compare", params={"before": ids["S2A_D1"], "after": ids["S2A_D3"]}
        ).json()
    assert compare["before_zones"] == {"zone-1": "disappeared", "zone-9": "not_observed"}
    assert compare["counts"]["not_observed"] == 1
    assert compare["masks_checked"] is True
