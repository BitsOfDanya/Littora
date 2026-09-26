from pathlib import Path

from fastapi.testclient import TestClient

from app.core.capabilities import SERVICE_CAPABILITIES, CapabilityKey
from app.core.config import Settings
from app.main import create_app
from tests.conftest import TEST_ORIGIN


def test_health_reports_ok(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "Littora API"
    assert body["environment"] == "local"
    assert body["timestamp"]


def test_meta_marks_service_capabilities_available_and_models_planned(
    tmp_path: Path, settings: Settings
) -> None:
    local = settings.model_copy(update={"reports_dir": tmp_path})
    with TestClient(create_app(local)) as client:
        response = client.get("/api/v1/meta")

    assert response.status_code == 200
    body = response.json()
    assert body["api_version"] == "v1"
    statuses = {item["key"]: item["status"] for item in body["capabilities"]}
    assert set(statuses) == {key.value for key in CapabilityKey}
    assert {key for key, status in statuses.items() if status == "available"} == {
        key.value
        for key in SERVICE_CAPABILITIES
        | {CapabilityKey.DRIFT_FORECAST, CapabilityKey.SURVEY_PLANNING}
    }
    assert statuses["debris_detection"] == "planned"
    assert statuses["concentration_model"] == "planned"
    assert statuses["model_evaluation"] == "planned"


def test_request_id_is_echoed_or_generated(client: TestClient) -> None:
    echoed = client.get("/api/v1/health", headers={"X-Request-ID": "trace-12345678"})
    generated = client.get("/api/v1/health")

    assert echoed.headers["X-Request-ID"] == "trace-12345678"
    assert len(generated.headers["X-Request-ID"]) == 32


def test_cors_preflight_allows_configured_origin(client: TestClient) -> None:
    response = client.options(
        "/api/v1/health",
        headers={"Origin": TEST_ORIGIN, "Access-Control-Request-Method": "GET"},
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == TEST_ORIGIN


def test_cors_rejects_unknown_origin(client: TestClient) -> None:
    response = client.get("/api/v1/health", headers={"Origin": "https://example.org"})

    assert "access-control-allow-origin" not in response.headers


def test_team_labels_combine_background_polygons_and_audit_points(client) -> None:
    body = client.get("/api/v1/labels").json()
    sources = {feature["properties"]["source"] for feature in body["features"]}
    assert sources == {"negatives", "audit"}
    ship = next(f for f in body["features"] if f["properties"]["class"] == "ship")
    assert ship["properties"]["title"] == "судно"
