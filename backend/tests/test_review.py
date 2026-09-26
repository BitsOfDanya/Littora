import csv
import io
import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.review.seed import import_audit
from app.review.service import REVIEWS_DIR, ReviewFilters, ReviewService

ANALYSIS_ID = "0123456789abcdef"
SCENE_ID = "S2B_37TDK_20250904_0_L2A"
FINGERPRINT = "raunet-test@abc123"
AUDIT_COLUMNS = (
    "zone_id,aoi,scene_id,date,lon,lat,pixels,probability_max,scl_at_centroid,"
    "stratum,crop,class,confidence,comment"
)


def square(lon: float, lat: float, side: float = 0.0002) -> dict:
    ring = [[lon, lat], [lon + side, lat], [lon + side, lat + side], [lon, lat + side], [lon, lat]]
    return {"type": "Polygon", "coordinates": [ring]}


def zone(rank: int, lon: float, lat: float, probability: float) -> dict:
    return {
        "id": f"zone-{rank}",
        "geometry": square(lon, lat),
        "pixels": 4,
        "area_km2": 0.0004,
        "probability_max": probability,
        "probability_mean": probability - 0.1,
        "centroid": [lon + 0.0001, lat + 0.0001],
        "status_label": "обнаружено",
    }


def analysis_result() -> dict:
    return {
        "id": ANALYSIS_ID,
        "pipeline_version": "2",
        "retryable": False,
        "models": {"detector": FINGERPRINT, "concentration": None},
        "computed_at": "2026-09-26T10:00:00+00:00",
        "request": {
            "aoi_id": "novorossiysk",
            "aoi_name": "Новороссийск",
            "bbox": [37.7, 44.6, 37.9, 44.8],
            "date": "2025-09-04",
            "window_days": 3,
            "scene_id": None,
            "target": "macroplastic",
        },
        "area": square(37.7, 44.6, 0.2),
        "scene": {"id": SCENE_ID, "acquired_at": "2025-09-04T08:46:01.024Z"},
        "detection": {
            "status": "detected",
            "label": "обнаружено",
            "reason": "",
            "model": "raunet",
            "threshold": 0.9,
            "zones": [
                zone(1, 37.75, 44.70, 0.99),
                zone(2, 37.80, 44.71, 0.95),
                zone(3, 37.85, 44.72, 0.93),
            ],
        },
        "concentration": {"status": "concentration_unavailable"},
        "observations": [],
        "messages": [],
    }


def write_audit(path: Path, rows: list[str]) -> Path:
    path.write_text("\n".join([AUDIT_COLUMNS, *rows]) + "\n", encoding="utf-8")
    return path


AUDIT_ROWS = [
    f"novorossiysk-001,novorossiysk,{SCENE_ID},2025-09-04,37.7501,44.7001,4,0.99,вода,"
    "крупная,crops/a.png,likely_debris,2,красновато-коричневое пятно",
    f"novorossiysk-002,novorossiysk,{SCENE_ID},2025-09-04,37.9,44.9,2,0.97,вода,"
    "мелкая,crops/b.png,ship,3,малое судно",
    "anapa-005,anapa,S2B_37TCK_20250904_0_L2A,2025-09-04,37.28,44.91,2,0.99,вода,"
    "мелкая,crops/c.png,water,3,",
]


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    folder = tmp_path / ANALYSIS_ID
    folder.mkdir()
    (folder / "result.json").write_text(json.dumps(analysis_result()), encoding="utf-8")
    audit = write_audit(tmp_path / "audit.csv", AUDIT_ROWS)
    app = create_app(Settings(_env_file=None, storage_dir=tmp_path))
    app.state.review = ReviewService(tmp_path / REVIEWS_DIR, audit)
    with TestClient(app) as test_client:
        yield test_client


def review(client: TestClient, zone_id: str, **payload) -> dict:
    response = client.post(f"/api/v1/analyses/{ANALYSIS_ID}/zones/{zone_id}/review", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_review_keeps_a_snapshot_of_the_zone(client: TestClient) -> None:
    body = review(client, "zone-1", label="ship", confidence=3, comment="  судно  со следом ")
    assert body["source"] == "ui"
    assert body["label_title"] == "судно"
    assert body["comment"] == "судно со следом"
    assert body["reviewer"] is None
    assert body["scene_id"] == SCENE_ID
    assert body["date"] == "2025-09-04"
    assert body["model_fingerprint"] == FINGERPRINT
    assert body["probability_max"] == 0.99
    assert body["geometry"]["type"] == "Polygon"
    assert body["aoi_id"] == "novorossiysk"


@pytest.mark.parametrize(
    "payload",
    [
        {"label": "plastic", "confidence": 2},
        {"label": "ship", "confidence": 4},
        {"label": "ship", "confidence": 0},
        {"label": "ship", "comment": "x" * 201},
        {"label": "ship", "reviewer": "y" * 41},
    ],
)
def test_invalid_reviews_are_rejected(client: TestClient, payload: dict) -> None:
    url = f"/api/v1/analyses/{ANALYSIS_ID}/zones/zone-1/review"
    assert client.post(url, json=payload).status_code == 422


def test_unknown_zone_or_analysis_is_not_found(client: TestClient) -> None:
    url = f"/api/v1/analyses/{ANALYSIS_ID}/zones/zone-9/review"
    assert client.post(url, json={"label": "ship"}).status_code == 404
    url = "/api/v1/analyses/ffffffffffffffff/zones/zone-1/review"
    assert client.post(url, json={"label": "ship"}).status_code == 404
    assert client.get("/api/v1/analyses/ffffffffffffffff/reviews").status_code == 404


def test_last_review_per_reviewer_wins(client: TestClient) -> None:
    review(client, "zone-1", label="unknown", confidence=1, reviewer="Вадим")
    review(client, "zone-1", label="likely_debris", confidence=2, reviewer="вадим ")
    review(client, "zone-1", label="likely_debris", confidence=3, reviewer="Даня")
    review(client, "zone-2", label="ship", confidence=3, reviewer="Даня")
    review(client, "zone-2", label="wake", confidence=2, reviewer="Вадим")
    body = client.get(f"/api/v1/analyses/{ANALYSIS_ID}/reviews").json()
    assert body["zones_total"] == 3
    assert len(body["items"]) == 5
    zones = {item["zone_id"]: item for item in body["zones"]}
    assert zones["zone-1"]["consensus"] == "likely_debris"
    assert zones["zone-1"]["history"] == 3
    assert len(zones["zone-1"]["reviews"]) == 2
    assert zones["zone-2"]["consensus"] == "ship"
    summary = body["summary"]
    assert summary["zones"] == 2
    assert summary["reviews"] == 4
    assert summary["precision"]["debris"] == 1
    assert summary["precision"]["value"] == 0.5
    low, high = summary["precision"]["interval"]
    assert 0 < low < 0.5 < high < 1
    assert summary["agreement"] == {"zones": 2, "agreed": 1, "value": 0.5}


def test_audit_rows_match_analysis_zones_by_scene_and_place(client: TestClient) -> None:
    body = client.get(f"/api/v1/analyses/{ANALYSIS_ID}/reviews").json()
    assert body["audit"]["available"] is True
    assert body["audit"]["matched"] == 1
    assert body["summary"]["zones"] == 0
    [matched] = body["zones"]
    assert matched["zone_id"] == "zone-1"
    assert matched["reviews"] == []
    [row] = matched["audit"]
    assert row["audit_zone_id"] == "novorossiysk-001"
    assert row["source_title"] == "аудит команды, CSV"
    assert row["reviewer"] == "team"


def test_summary_keeps_sources_apart(client: TestClient) -> None:
    review(client, "zone-1", label="ship", reviewer="a")
    body = client.get("/api/v1/reviews").json()
    assert len(body["items"]) == 4
    sources = {source["source"]: source for source in body["summary"]["sources"]}
    assert sources["ui"]["zones"] == 1
    assert sources["ui"]["precision"]["debris"] == 0
    audit = sources["audit"]
    assert audit["zones"] == 3
    assert audit["precision"]["debris"] == 1
    assert {aoi["aoi_id"]: aoi["zones"] for aoi in audit["by_aoi"]} == {
        "novorossiysk": 2,
        "anapa": 1,
    }
    only_audit = client.get("/api/v1/reviews", params={"source": "audit", "aoi_id": "anapa"})
    assert [item["zone_id"] for item in only_audit.json()["items"]] == ["anapa-005"]
    ships = client.get("/api/v1/reviews", params={"label": "ship"}).json()["items"]
    assert {item["source"] for item in ships} == {"ui", "audit"}


def test_history_flag_returns_superseded_reviews(client: TestClient) -> None:
    review(client, "zone-3", label="foam", reviewer="a")
    review(client, "zone-3", label="slick", reviewer="a")
    latest = client.get("/api/v1/reviews", params={"source": "ui"}).json()["items"]
    assert [item["label"] for item in latest] == ["slick"]
    history = client.get("/api/v1/reviews", params={"source": "ui", "history": True}).json()
    assert [item["label"] for item in history["items"]] == ["slick", "foam"]


def test_exports_carry_geometry_and_model(client: TestClient) -> None:
    review(client, "zone-2", label="structure", confidence=3, comment="=HYPERLINK()")
    geojson = client.get("/api/v1/reviews/export.geojson").json()
    kinds = {
        feature["properties"]["source"]: feature["geometry"]["type"]
        for feature in geojson["features"]
    }
    assert kinds == {"ui": "Polygon", "audit": "Point"}
    response = client.get("/api/v1/reviews/export.csv", params={"source": "ui"})
    assert response.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(response.text.lstrip("﻿"))))
    [row] = rows
    assert row["label"] == "structure"
    assert row["model_fingerprint"] == FINGERPRINT
    assert row["scene_id"] == SCENE_ID
    assert row["probability_max"] == "0.95"
    assert row["geometry_wkt"].startswith("POLYGON")
    assert row["comment"] == "'=HYPERLINK()"


def test_audit_import_adds_team_reviewer(tmp_path: Path) -> None:
    source = write_audit(tmp_path / "source.csv", AUDIT_ROWS)
    target = tmp_path / "out" / "audit.csv"
    assert import_audit(source, target) == 3
    rows = list(csv.DictReader(target.open(encoding="utf-8")))
    assert rows[0]["reviewer"] == "team"
    assert list(rows[0])[:14] == AUDIT_COLUMNS.split(",")
    broken = write_audit(tmp_path / "broken.csv", [AUDIT_ROWS[0].replace("likely_debris", "x")])
    with pytest.raises(ValueError, match="неизвестный класс"):
        import_audit(broken, target)


def test_missing_audit_file_is_reported_as_unavailable(tmp_path: Path) -> None:
    service = ReviewService(tmp_path / REVIEWS_DIR, tmp_path / "absent.csv")
    summary = service.summary(ReviewFilters())
    audit = next(source for source in summary["sources"] if source["source"] == "audit")
    assert audit["available"] is False
    assert audit["zones"] == 0
