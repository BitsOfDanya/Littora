from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.errors import NotImplementedYetError
from app.main import create_app
from tests.conftest import TEST_ORIGIN


def _app_with_failing_routes(settings: Settings) -> FastAPI:
    app = create_app(settings)

    @app.get("/api/v1/_test/crash")
    async def crash() -> None:
        raise RuntimeError("boom")

    @app.get("/api/v1/_test/pending")
    async def pending() -> None:
        raise NotImplementedYetError("Detection is not connected yet")

    @app.get("/api/v1/_test/items/{item_id}")
    async def item(item_id: int) -> dict[str, int]:
        return {"item_id": item_id}

    return app


def test_unknown_route_returns_error_envelope(client: TestClient) -> None:
    response = client.get("/api/v1/missing")

    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "not_found"
    assert error["request_id"] == response.headers["X-Request-ID"]


def test_validation_error_is_structured(settings: Settings) -> None:
    with TestClient(_app_with_failing_routes(settings)) as client:
        response = client.get("/api/v1/_test/items/not-a-number")

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["details"][0]["loc"] == ["path", "item_id"]


def test_app_error_keeps_its_status_and_code(settings: Settings) -> None:
    with TestClient(_app_with_failing_routes(settings)) as client:
        response = client.get("/api/v1/_test/pending")

    assert response.status_code == 501
    assert response.json()["error"] == {
        "code": "not_implemented",
        "message": "Detection is not connected yet",
        "details": None,
        "request_id": response.headers["X-Request-ID"],
    }


def test_unexpected_error_is_hidden_and_keeps_cors(settings: Settings) -> None:
    with TestClient(_app_with_failing_routes(settings)) as client:
        response = client.get("/api/v1/_test/crash", headers={"Origin": TEST_ORIGIN})

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert "boom" not in response.text
    assert response.headers["access-control-allow-origin"] == TEST_ORIGIN
