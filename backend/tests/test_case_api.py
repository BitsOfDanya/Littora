from fastapi.testclient import TestClient


def test_targets_expose_the_primary_definition(client: TestClient) -> None:
    body = client.get("/api/v1/case/targets").json()
    assert body["primary"] == "litter-visual"
    primary = next(target for target in body["targets"] if target["primary"])
    assert primary["unit"] == "шт./км²"
    assert primary["events"] == 74


def test_observations_are_filtered(client: TestClient) -> None:
    features = client.get("/api/v1/observations", params={"target": "litter-visual"}).json()[
        "features"
    ]
    assert len(features) == 74
    assert {f["properties"]["value_kind"] for f in features} == {"measurement"}
    black_sea = client.get("/api/v1/observations", params={"bbox": "27,40,42,47"}).json()
    assert len(black_sea["features"]) == 33
    dated = client.get(
        "/api/v1/observations", params={"date_from": "2024-06-02", "date_to": "2024-06-02"}
    ).json()
    assert {f["properties"]["date"] for f in dated["features"]} == {"2024-06-02"}


def test_bad_bbox_is_explained(client: TestClient) -> None:
    response = client.get("/api/v1/observations", params={"bbox": "30,44,29,43"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "bad_request"


def test_registry_files_are_served(client: TestClient) -> None:
    pairs = client.get("/api/v1/pairs", params={"decision": "accepted"}).json()
    assert pairs["total"] >= 1
    assert all(item["decision"] == "accepted" for item in pairs["items"])
    events = client.get("/api/v1/events", params={"target": "litter-visual"}).json()
    assert len(events["features"]) == 74
