import datetime as dt
import math
from collections.abc import Iterator
from itertools import pairwise

import numpy as np
import pytest
from fastapi.testclient import TestClient
from shapely.geometry import box

from app.analysis.service import AnalysisService
from app.core.capabilities import CapabilityKey, CapabilityStatus, capability_status
from app.core.config import Settings
from app.drift.forcing import Domain, OpenMeteoForcing, stokes_drift
from app.drift.geo import METERS_PER_DEGREE
from app.drift.land import LandMask
from app.drift.model import DriftParameters, GridField, Trajectories, integrate
from app.drift.places import Place
from app.drift.products import beached_by_hour, envelopes, median_path, source_estimates
from app.drift.service import DriftService
from app.main import create_app
from tests.fakes import (
    FakeCatalog,
    FakeDetector,
    FakeForcing,
    blank_layer,
    clear_quality,
    make_scene,
    uniform_forcing,
)

T0 = dt.datetime(2024, 6, 2, 9, 0, tzinfo=dt.UTC)
DOMAIN = Domain(29.0, 43.0, 31.0, 45.0)
STILL = DriftParameters(diffusivity_m2s=0.0)
OPEN_SEA = LandMask(29.0, 43.0, 1.0, 1.0, np.zeros((2, 2), dtype=bool), {})
T1_DAY = dt.date(2024, 6, 2)
REQUEST = {"bbox": [29.45, 43.50, 29.80, 43.72], "date": T1_DAY.isoformat(), "window_days": 3}
PORT = Place("west-port", "Западный порт", "port", box(29.05, 43.45, 29.3, 43.75), (29.2, 43.6))


def run(forcing, start, windage, stokes, hours, direction=1, land=OPEN_SEA, parameters=STILL):
    return integrate(
        GridField(forcing, T0),
        land,
        np.array(start, dtype=float),
        np.array(windage, dtype=float),
        np.array(stokes, dtype=float),
        hours,
        direction,
        parameters,
        np.random.default_rng(0),
    )


def window(hours: int = 12):
    return T0 - dt.timedelta(hours=hours), T0 + dt.timedelta(hours=hours)


def east_km(tracks: Trajectories, member: int, hour: int) -> float:
    start, end = tracks.positions[0, member], tracks.positions[hour, member]
    scale = METERS_PER_DEGREE * math.cos(math.radians(start[1]))
    return (end[0] - start[0]) * scale / 1000.0


def test_uniform_current_gives_exact_displacement() -> None:
    forcing = uniform_forcing(DOMAIN, *window(), current=(0.1, 0.0))
    ahead = run(forcing, [[30.0, 44.0]], [0.0], [0.0], 10)
    behind = run(forcing, [[30.0, 44.0]], [0.0], [0.0], 10, direction=-1)
    shift = 0.1 * 36_000 / (METERS_PER_DEGREE * math.cos(math.radians(44.0)))
    assert ahead.positions[-1, 0, 0] == pytest.approx(30.0 + shift, rel=1e-12)
    assert behind.positions[-1, 0, 0] == pytest.approx(30.0 - shift, rel=1e-12)
    assert ahead.positions[-1, 0, 1] == pytest.approx(44.0, abs=1e-12)
    assert ahead.positions.shape == (11, 1, 2)
    assert not ahead.left_domain.any()


def test_zero_noise_keeps_trajectories_bit_identical() -> None:
    field = GridField(uniform_forcing(DOMAIN, *window(30), current=(0.1, 0.0)), T0)
    start = np.array([[30.0, 44.0]] * 4)
    windage, stokes = np.full(4, 0.01), np.ones(4)

    def tracks(*noise: float):
        rng = np.random.default_rng(3)
        return integrate(
            field, OPEN_SEA, start, windage, stokes, 24, 1, DriftParameters(), rng, *noise
        )

    assert np.array_equal(tracks().positions, tracks(0.0, 48.0).positions)
    assert not np.array_equal(tracks().positions, tracks(0.2, 48.0).positions)


def test_windage_and_stokes_scale_linearly() -> None:
    forcing = uniform_forcing(DOMAIN, *window(), stokes=(0.05, 0.0), wind=(10.0, 0.0))
    tracks = run(forcing, [[30.0, 44.0]] * 4, [0.01, 0.03, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0], 6)
    assert east_km(tracks, 0, 6) == pytest.approx(0.1 * 6 * 3.6, rel=1e-9)
    assert east_km(tracks, 1, 6) == pytest.approx(3 * east_km(tracks, 0, 6), rel=1e-9)
    assert east_km(tracks, 2, 6) == pytest.approx(0.05 * 6 * 3.6, rel=1e-9)
    assert east_km(tracks, 3, 6) == pytest.approx(0.0, abs=1e-9)


def test_stokes_estimate_is_deep_water_monochromatic() -> None:
    east, north = stokes_drift(np.array([1.0, 0.0]), np.array([4.0, 4.0]), np.array([270.0, 0.0]))
    expected = 2 * math.pi**3 / (9.80665 * 4.0**3)
    assert expected == pytest.approx(0.0988, abs=1e-4)
    assert east[0] == pytest.approx(expected)
    assert north[0] == pytest.approx(0.0, abs=1e-12)
    assert east[1] == north[1] == 0.0
    east, north = stokes_drift(np.array([1.0]), np.array([4.0]), np.array([0.0]))
    assert north[0] == pytest.approx(-expected)


def test_particles_stop_on_land() -> None:
    step = 0.001
    lons = 29.9 + (np.arange(300) + 0.5) * step
    land = LandMask(29.9, 43.9, step, step, np.tile(lons >= 30.05, (200, 1)), {})
    forcing = uniform_forcing(DOMAIN, *window(), current=(0.2, 0.0))
    tracks = run(forcing, [[30.0, 44.0], [30.0, 44.0]], [0.0, 0.0], [0.0, 0.0], 12, land=land)
    assert np.isfinite(tracks.beached_at).all()
    assert (tracks.positions[-1, :, 0] < 30.05).all()
    assert (tracks.positions[-1, :, 0] > 30.047).all()
    shares = beached_by_hour(tracks)
    assert shares[0] == 0.0 and shares[-1] == 1.0
    assert all(later >= earlier for earlier, later in pairwise(shares))


def test_envelope_probability_falls_as_particles_beach() -> None:
    rng = np.random.default_rng(3)
    count = 200
    positions = np.empty((73, count, 2))
    for hour in range(73):
        spread = rng.normal(0, 0.001 * (1 + hour), (count, 2))
        positions[hour] = np.array([30.0 + hour * 0.002, 44.0]) + spread
    beached = np.full(count, np.nan)
    beached[:120] = np.linspace(2, 70, 120)
    tracks = Trajectories(positions, beached, np.zeros(count, dtype=bool))
    path = median_path(positions)
    items = envelopes(tracks, path)
    assert [item["horizon_h"] for item in items] == [6, 12, 24, 48, 72]
    probabilities = [item["probability"] for item in items]
    assert all(later <= earlier for earlier, later in pairwise(probabilities))
    assert all(item["probability"] <= item["afloat"] for item in items)
    assert items[0]["probability"] == pytest.approx(0.9 * items[0]["afloat"], abs=0.01)
    ring = items[-1]["polygon"]["coordinates"][0]
    assert ring[0] == ring[-1] and len(ring) > 4


def test_zone_inside_a_source_district_is_not_attributed_to_it() -> None:
    positions = np.tile(np.array([29.2, 43.6]), (49, 20, 1))
    tracks = Trajectories(positions, np.full(20, np.nan), np.zeros(20, dtype=bool))
    assert source_estimates(tracks, [PORT]) == ([], ["Западный порт"])


def test_source_counts_only_arrivals_after_t0() -> None:
    lons = np.empty((49, 20))
    lons[:, :10] = 29.605 - 0.01 * np.arange(49)[:, None]
    lons[:, 10:] = 29.6
    positions = np.stack([lons, np.full((49, 20), 43.6)], axis=-1)
    tracks = Trajectories(positions, np.full(20, np.nan), np.zeros(20, dtype=bool))
    items, enclosing = source_estimates(tracks, [PORT])
    assert enclosing == []
    assert [item["id"] for item in items] == ["west-port", "open-sea"]
    assert items[0]["members"] == 10 and items[0]["hours_back"] == 31


class ScriptedClient:
    def __init__(self) -> None:
        self.urls: list[str] = []

    def get(self, url: str, params: dict[str, str]) -> dict:
        self.urls.append(url)
        lats = [float(value) for value in params["latitude"].split(",")]
        start = dt.date.fromisoformat(params["start_date"])
        days = (dt.date.fromisoformat(params["end_date"]) - start).days + 1
        stamps = [
            (dt.datetime.combine(start, dt.time()) + dt.timedelta(hours=h)).strftime(
                "%Y-%m-%dT%H:%M"
            )
            for h in range(days * 24)
        ]
        locations = []
        for lat in lats:
            if "marine" in url:
                land = lat > 43.9
                last_day = 24 * (days - 1)
                current = [None if land or h >= last_day else 0.3 for h in range(len(stamps))]
                series = {
                    "wave_height_meteofrance_wave": [None if land else 1.0] * len(stamps),
                    "wave_period_meteofrance_wave": [None if land else 4.0] * len(stamps),
                    "wave_direction_meteofrance_wave": [None if land else 270.0] * len(stamps),
                    "ocean_current_velocity_meteofrance_currents": current,
                    "ocean_current_direction_meteofrance_currents": [90.0] * len(stamps),
                }
            else:
                series = {
                    "wind_speed_10m": [10.0] * len(stamps),
                    "wind_direction_10m": [270.0] * len(stamps),
                }
            locations.append({"hourly": {"time": stamps, **series}})
        return {"url": url, "fetched_at": "2024-06-20T00:00:00+00:00", "locations": locations}


def test_open_meteo_forcing_is_assembled_without_double_counting_stokes() -> None:
    client = ScriptedClient()
    source = OpenMeteoForcing(None, today=lambda: dt.date(2024, 7, 1), client=client)
    domain = Domain.around((29.6, 43.6, 29.6, 43.6), 50.0)
    forcing = source.load(domain, T0 - dt.timedelta(hours=49), T0 + dt.timedelta(hours=74))
    stokes = 2 * math.pi**3 / (9.80665 * 64.0)
    water = forcing.water
    assert water.any() and not water.all()
    assert np.allclose(forcing.stokes[..., 0][:, water], stokes)
    assert np.allclose(forcing.current[..., 0][:, water], 0.3 - stokes)
    assert np.allclose(forcing.current[..., 1], 0.0, atol=1e-9)
    assert np.allclose(forcing.wind[..., 0], 10.0) and np.allclose(forcing.wind[..., 1], 0.0)
    provenance = forcing.provenance
    assert provenance["currents"]["available"] and provenance["waves"]["available"]
    assert provenance["currents"]["filled_hours"] > 0
    assert provenance["currents"]["quantum_ms"] == 0.05
    assert provenance["wind"]["source"].endswith("ERA5 0,25°")
    assert any("archive" in url for url in client.urls)
    recent = OpenMeteoForcing(None, today=lambda: dt.date(2024, 6, 3), client=ScriptedClient())
    later = recent.load(domain, T0, T0 + dt.timedelta(hours=24))
    assert later.provenance["wind"]["source"].startswith("Open-Meteo Forecast")


def east_land(scene, domain, cell_m):
    return lambda lon, lat: np.where(lon > 29.9, 4, 6).astype(np.uint8)


def build_client(tmp_path, forcing: FakeForcing, detector=None) -> TestClient:
    settings = Settings(_env_file=None, storage_dir=tmp_path)
    app = create_app(settings)
    app.state.analysis = AnalysisService(
        app.state.repository,
        FakeCatalog([make_scene("S2A_T1", T1_DAY)]),
        tmp_path,
        detector=detector,
        quality_reader=clear_quality,
        true_color=blank_layer,
        quality_mask=blank_layer,
    )
    app.state.drift = DriftService(forcing, places=[PORT], scene_classes=east_land)
    return TestClient(app)


@pytest.fixture
def forcing() -> FakeForcing:
    return FakeForcing()


@pytest.fixture
def client(tmp_path, forcing: FakeForcing) -> Iterator[TestClient]:
    with build_client(tmp_path, forcing, FakeDetector()) as test_client:
        yield test_client


def analysis_id(client: TestClient) -> str:
    return client.post("/api/v1/analyses", json=REQUEST).json()["id"]


def test_drift_scenario_matches_the_forecast_contract(
    client: TestClient, forcing: FakeForcing
) -> None:
    identifier = analysis_id(client)
    response = client.post(f"/api/v1/analyses/{identifier}/drift")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == {"status": "scenario", "label": "сценарий дрейфа"}
    assert body["value_kind"] == "scenario"
    assert "не проверенный прогноз" in body["reason"]
    assert body["zones"] == {"total": 1, "computed": 1, "limit": 25}
    assert body["run"]["ensemble_size"] == 320
    assert body["run"]["windage_ratio"] == 0.015
    assert body["run"]["wind_from_deg"] == 270
    assert body["run"]["t0"] == "2024-06-02T09:00:00.000Z"
    assert body["forcing"]["land"]["scene_share"] > 0.9
    [forecast] = body["forecasts"]
    assert forecast["candidate_id"] == "zone-1"
    assert forecast["origin"] == [29.6, 43.6]
    assert len(forecast["median_path"]) == 73
    assert [item["horizon_h"] for item in forecast["envelopes"]] == [6, 12, 24, 48, 72]
    assert len(forecast["hindcast_path"]) == 49
    assert forecast["hindcast_path"][-1] == forecast["median_path"][0]
    assert forecast["hindcast_path"][0][0] < forecast["median_path"][0][0]
    assert forecast["median_path"][24][0] > forecast["median_path"][0][0]
    assert len(forecast["beached_by_hour"]) == 73
    assert forecast["beached_by_hour"][-1] == forecast["beaching_any"]["value"] > 0
    assert forecast["beaching"][0]["path"][0][0] <= 29.9
    assert sum(item["members"] for item in forecast["beaching"]) <= 320
    sources = forecast["sources"]
    assert sources[0]["id"] == "west-port" and sources[0]["position"] == [29.2, 43.6]
    assert sum(item["members"] for item in sources) == 320
    assert len(forecast["variants"]) == 8
    field = body["current_field"]
    assert field["typical_speed_ms"] == pytest.approx(0.12)
    assert len(field["mask"]["data"]) == field["mask"]["rows"]
    assert client.get(f"/api/v1/analyses/{identifier}/drift").json() == body
    assert client.post(f"/api/v1/analyses/{identifier}/drift").json() == body
    assert forcing.calls == 2
    narrow, wide = forcing.domains
    assert wide.bounds[0] < narrow.bounds[0] and wide.bounds[2] > narrow.bounds[2]
    assert all(0.0 <= item["outside_domain"] <= 1.0 for item in forecast["envelopes"])


def test_zone_inside_a_port_district_is_reported_not_attributed(tmp_path) -> None:
    district = Place(
        "east-port", "Восточный порт", "port", box(29.5, 43.5, 29.7, 43.7), (29.6, 43.6)
    )
    with build_client(tmp_path, FakeForcing(), FakeDetector()) as client:
        client.app.state.drift.places = [PORT, district]
        body = client.post(f"/api/v1/analyses/{analysis_id(client)}/drift").json()
    [forecast] = body["forecasts"]
    assert forecast["sources"][0]["id"] == "west-port"
    assert all(item["id"] != "east-port" for item in forecast["sources"])
    assert all(item["hours_back"] is None or item["hours_back"] > 0 for item in forecast["sources"])
    assert any("«Восточный порт»" in message for message in body["messages"])


def test_drift_honours_shorter_horizons(client: TestClient) -> None:
    identifier = analysis_id(client)
    body = client.post(
        f"/api/v1/analyses/{identifier}/drift", json={"hours": 24, "hindcast_hours": 12}
    ).json()
    [forecast] = body["forecasts"]
    assert len(forecast["median_path"]) == 25
    assert len(forecast["hindcast_path"]) == 13
    assert [item["horizon_h"] for item in forecast["envelopes"]] == [6, 12, 24]
    assert body["method"]["horizons_h"] == [6, 12, 24]


def test_drift_is_deterministic(tmp_path) -> None:
    bodies = []
    for folder in ("a", "b"):
        with build_client(tmp_path / folder, FakeForcing(), FakeDetector()) as client:
            identifier = analysis_id(client)
            bodies.append(client.post(f"/api/v1/analyses/{identifier}/drift").json())
    assert bodies[0]["forecasts"][0]["envelopes"] == bodies[1]["forecasts"][0]["envelopes"]
    assert bodies[0]["forecasts"][0]["sources"] == bodies[1]["forecasts"][0]["sources"]


def test_analysis_without_zones_gives_a_valid_empty_drift(tmp_path) -> None:
    with build_client(tmp_path, FakeForcing()) as client:
        identifier = analysis_id(client)
        body = client.post(f"/api/v1/analyses/{identifier}/drift").json()
        assert body["status"] == {"status": "no_zones", "label": "нет зон для дрейфа"}
        assert body["forecasts"] == [] and body["run"] is None
        assert client.get(f"/api/v1/analyses/{identifier}/drift").json() == body


def test_forcing_failure_is_insufficient_data_and_not_cached(tmp_path) -> None:
    with build_client(tmp_path, FakeForcing(fail=True), FakeDetector()) as client:
        identifier = analysis_id(client)
        body = client.post(f"/api/v1/analyses/{identifier}/drift").json()
        assert body["status"] == {"status": "insufficient_data", "label": "недостаточно данных"}
        assert body["reason"].endswith("нет связи")
        missing = client.get(f"/api/v1/analyses/{identifier}/drift")
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "not_found"


@pytest.mark.parametrize("patch", [{"hours": 100}, {"hours": 0}, {"hindcast_hours": 49}])
def test_drift_rejects_out_of_range_horizons(client: TestClient, patch: dict) -> None:
    identifier = analysis_id(client)
    response = client.post(f"/api/v1/analyses/{identifier}/drift", json=patch)
    assert response.status_code == 422


def test_drift_for_unknown_analysis_is_not_found(client: TestClient) -> None:
    for method in (client.get, client.post):
        response = method("/api/v1/analyses/0123456789abcdef/drift")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"


def test_drift_capability_follows_wiring(client: TestClient) -> None:
    statuses = {c["key"]: c["status"] for c in client.get("/api/v1/meta").json()["capabilities"]}
    assert statuses["drift_forecast"] == "available"
    assert capability_status()[CapabilityKey.DRIFT_FORECAST] == CapabilityStatus.PLANNED
    del client.app.state.drift
    statuses = {c["key"]: c["status"] for c in client.get("/api/v1/meta").json()["capabilities"]}
    assert statuses["drift_forecast"] == "planned"
    response = client.post("/api/v1/analyses/0123456789abcdef/drift")
    assert response.status_code == 501


def test_cloud_falls_back_to_the_base_domain_when_wide_forcing_fails(tmp_path) -> None:
    forcing = FakeForcing(fail_wide=True)
    with build_client(tmp_path, forcing, FakeDetector()) as client:
        body = client.post(f"/api/v1/analyses/{analysis_id(client)}/drift").json()
    assert body["status"]["status"] == "scenario"
    assert any("расширенной области" in message for message in body["messages"])
    assert [item["horizon_h"] for item in body["forecasts"][0]["envelopes"]] == [6, 12, 24, 48, 72]
