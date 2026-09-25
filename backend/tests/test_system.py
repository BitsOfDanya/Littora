from fastapi.testclient import TestClient

from app.core.capabilities import SERVICE_CAPABILITIES, CapabilityKey
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
    client: TestClient,
) -> None:
    response = client.get("/api/v1/meta")

    assert response.status_code == 200
    body = response.json()
    assert body["api_version"] == "v1"
    statuses = {item["key"]: item["status"] for item in body["capabilities"]}
    assert set(statuses) == {key.value for key in CapabilityKey}
    assert {key for key, status in statuses.items() if status == "available"} == {
        key.value for key in SERVICE_CAPABILITIES
    }
    assert statuses["debris_detection"] == "planned"
    assert statuses["concentration_model"] == "planned"


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
