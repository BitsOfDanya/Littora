import datetime as dt
from pathlib import Path

from fastapi.testclient import TestClient

from app.case.data import load_case_data
from app.case.pairing import PairingEngine, build_event_inputs
from app.case.registry import write_pairing
from app.core.config import Settings
from app.earth.raster import RasterError
from app.main import create_app
from tests.fakes import FakeCatalog, clear_quality, make_scene


def test_targets_expose_the_primary_definition(client: TestClient) -> None:
    body = client.get("/api/v1/case/targets").json()
    assert body["primary"] == "plastic-visual"
    primary = next(target for target in body["targets"] if target["primary"])
    assert primary["unit"] == "шт./км²"
    assert primary["events"] == 63
    litter = next(target for target in body["targets"] if target["key"] == "litter-visual")
    assert litter["events"] == 74


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


def test_not_evaluated_decisions_can_be_filtered(tmp_path: Path, settings: Settings) -> None:
    case = load_case_data(settings.case_config, settings.data_dir)
    rules = case.config.pairing
    record_type = case.config.selection.record_type
    events = {e.event_id: e for e in build_event_inputs(case.selections, record_type)}

    def unreadable(*_args) -> None:
        raise RasterError("маска SCL не читается")

    scene = make_scene("S2A_T1", dt.date(2024, 6, 2))
    read_error = PairingEngine(rules, FakeCatalog([scene]), unreadable)
    offline = PairingEngine(rules, FakeCatalog(fail=True), clear_quality)
    results = [
        read_error.pair_event(events["S4:DOORS3:T1"]),
        offline.pair_event(events["S4:DOORS3:T2"]),
    ]
    write_pairing(tmp_path / "registry", case.config, case.selections, results)
    local = settings.model_copy(update={"reports_dir": tmp_path})
    with TestClient(create_app(local)) as client:
        pairs = client.get("/api/v1/pairs", params={"decision": "not_evaluated"})
        assert pairs.status_code == 200
        assert [item["reason_code"] for item in pairs.json()["items"]] == ["read_error"]
        response = client.get("/api/v1/events", params={"decision": "not_evaluated"})
        assert response.status_code == 200
        reasons = sorted(f["properties"]["reason_code"] for f in response.json()["features"])
        assert reasons == ["catalog_error", "read_error"]
        assert client.get("/api/v1/events", params={"decision": "unknown"}).status_code == 422
