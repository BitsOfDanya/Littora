import datetime as dt
import math

import numpy as np
import pandas as pd
import pytest
from shapely.geometry import LineString, Point, shape

from app.drift import products
from app.drift.geo import offset, to_local
from app.drift.model import DriftParameters, Trajectories
from app.drift.model import integrate as service_integrate
from littora_ml.drift_check.openmeteo import BlockStore, series_key
from littora_ml.drift_check.simulate import Setup, envelope_polygon
from littora_ml.drift_check.spread import (
    Bootstrap,
    CachedOnlyClient,
    NotCached,
    Spread,
    block_labels,
    candidate_grid,
    coverage_flags,
    effective_diffusivity,
    integrate,
    leave_one_out,
    ou_variance,
    required_core,
    select,
    summarize_set,
)

ORIGIN = (30.0, 43.0)


class SwirlField:
    def velocity(self, lon, lat, hours, windage, stokes):
        east = 0.2 * np.cos(np.radians(lat - ORIGIN[1]) * 40.0) + windage * 6.0 + stokes * 0.03
        north = 0.1 * np.sin(np.radians(lon - ORIGIN[0]) * 40.0 + hours / 5.0) - windage * 2.0
        return east, north

    def inside(self, lon, lat):
        return np.abs(lon - ORIGIN[0]) < 0.3


class StillField:
    def velocity(self, lon, lat, hours, windage, stokes):
        return np.zeros_like(lon), np.zeros_like(lat)

    def inside(self, lon, lat):
        return np.ones(lon.shape, dtype=bool)


class Shore:
    def is_land(self, lon, lat):
        return lat > ORIGIN[1] + 0.02


class Sea:
    def is_land(self, lon, lat):
        return np.zeros(lon.shape, dtype=bool)


def _start(count: int, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    lon, lat = offset(
        np.full(count, ORIGIN[0]),
        np.full(count, ORIGIN[1]),
        rng.normal(0, 300, count),
        rng.normal(0, 300, count),
    )
    return np.column_stack([lon, lat])


@pytest.mark.parametrize("direction", [1, -1])
def test_integrate_without_velocity_noise_reproduces_the_service(direction: int) -> None:
    parameters = DriftParameters(diffusivity_m2s=20.0)
    start = _start(64)
    windage = np.repeat([0.005, 0.03], 32)
    stokes = np.tile([1.0, 0.0], 32)
    expected = service_integrate(
        SwirlField(),
        Shore(),
        start,
        windage,
        stokes,
        30,
        direction,
        parameters,
        np.random.default_rng(11),
    )
    actual = integrate(
        SwirlField(),
        Shore(),
        start,
        windage,
        stokes,
        30,
        direction,
        parameters,
        np.random.default_rng(11),
    )
    assert np.isfinite(expected.beached_at).any()
    assert np.array_equal(expected.positions, actual.positions)
    assert np.array_equal(expected.beached_at, actual.beached_at, equal_nan=True)
    assert np.array_equal(expected.left_domain, actual.left_domain)


def test_velocity_random_walk_spreads_like_ornstein_uhlenbeck() -> None:
    parameters = DriftParameters(diffusivity_m2s=0.0)
    count, hours, sigma, tau = 4000, 48, 0.2, 12.0
    start = np.tile(ORIGIN, (count, 1))
    trajectories = integrate(
        StillField(),
        Sea(),
        start,
        np.zeros(count),
        np.zeros(count),
        hours,
        1,
        parameters,
        np.random.default_rng(5),
        sigma,
        tau,
    )
    for hour in (6, 24, 48):
        xy = to_local(
            ORIGIN, trajectories.positions[hour, :, 0], trajectories.positions[hour, :, 1]
        )
        expected = ou_variance(sigma, tau, hour)
        assert np.var(xy[:, 0]) == pytest.approx(expected, rel=0.1)
        assert np.var(xy[:, 1]) == pytest.approx(expected, rel=0.1)
    assert ou_variance(sigma, tau, 1000) == pytest.approx(
        2 * sigma**2 * tau * 3600 * (1000 - tau) * 3600, rel=1e-9
    )


def test_velocity_random_walk_needs_a_decorrelation_time() -> None:
    with pytest.raises(ValueError):
        integrate(
            StillField(),
            Sea(),
            np.tile(ORIGIN, (4, 1)),
            np.zeros(4),
            np.zeros(4),
            2,
            1,
            DriftParameters(),
            np.random.default_rng(0),
            0.1,
            0.0,
        )


def test_required_core_reproduces_service_envelopes() -> None:
    rng = np.random.default_rng(7)
    count = 320
    cloud = np.column_stack(
        offset(
            np.full(count, ORIGIN[0]),
            np.full(count, ORIGIN[1]),
            rng.normal(0, 6000, count),
            rng.normal(0, 2500, count),
        )
    )
    positions = np.stack([np.tile(ORIGIN, (count, 1)), cloud])
    trajectories = Trajectories(positions, np.full(count, np.nan), np.zeros(count, dtype=bool))
    path = products.median_path(positions)
    outer = shape(products.envelopes(trajectories, path, horizons=(1,))[0]["polygon"])
    inner = envelope_polygon(cloud, path[1], 0.5)
    targets = np.column_stack(
        offset(
            np.full(200, ORIGIN[0]),
            np.full(200, ORIGIN[1]),
            rng.normal(0, 9000, 200),
            rng.normal(0, 4000, 200),
        )
    )
    checked = 0
    for target in targets:
        core = np.array([required_core(cloud, path[1], target)])
        for share, polygon in ((0.9, outer), (0.5, inner)):
            border = LineString(to_local(target, *np.asarray(polygon.exterior.coords).T))
            if border.distance(Point(0.0, 0.0)) < 10:
                continue
            flag = coverage_flags(core, np.array([count]), share)[0]
            assert bool(flag) == polygon.covers(Point(*target))
            checked += 1
    assert checked > 300


def test_required_core_is_minimal_and_handles_no_afloat_particles() -> None:
    points = np.column_stack(
        offset(
            np.full(5, ORIGIN[0]),
            np.full(5, ORIGIN[1]),
            np.array([0.0, 1000.0, -1000.0, 0.0, 0.0]),
            np.array([0.0, 0.0, 0.0, 3000.0, -3000.0]),
        )
    )
    near = offset(np.array([ORIGIN[0]]), np.array([ORIGIN[1]]), np.array([900.0]), np.array([0.0]))
    far = offset(np.array([ORIGIN[0]]), np.array([ORIGIN[1]]), np.array([0.0]), np.array([9e4]))
    assert required_core(points, ORIGIN, (near[0][0], near[1][0])) == 2.0
    assert math.isinf(required_core(points, ORIGIN, (far[0][0], far[1][0])))
    empty = np.empty((0, 2))
    assert required_core(empty, ORIGIN, ORIGIN) == 0.0
    assert math.isinf(required_core(empty, ORIGIN, (near[0][0], near[1][0])))


def test_coverage_flags_follow_service_rounding_and_skip_missing_points() -> None:
    core = np.array([288.0, 289.0, math.inf, np.nan, 0.0, 160.0])
    afloat = np.array([320.0, 320.0, 320.0, 320.0, 0.0, 320.0])
    assert np.array_equal(
        coverage_flags(core, afloat, 0.9), [1.0, 0.0, 0.0, np.nan, 1.0, 1.0], equal_nan=True
    )
    assert np.array_equal(
        coverage_flags(core, afloat, 0.5), [0.0, 0.0, 0.0, np.nan, 1.0, 1.0], equal_nan=True
    )


def test_selection_keeps_separation_within_tolerance_and_prefers_simple() -> None:
    table = {
        "service": {
            "error": 0.6,
            "separation": {24: 10.0, 72: 40.0},
            "complexity": 0,
            "family": "service",
        },
        "sharp": {
            "error": 0.02,
            "separation": {24: 10.6, 72: 30.0},
            "complexity": 2,
            "family": "random_walk",
        },
        "walk": {
            "error": 0.1,
            "separation": {24: 10.4, 72: 39.0},
            "complexity": 2,
            "family": "random_walk",
        },
        "diffuse": {
            "error": 0.1,
            "separation": {24: 10.0, 72: 41.0},
            "complexity": 1,
            "family": "diffusivity",
        },
        "partial": {
            "error": 0.01,
            "separation": {24: 9.0},
            "complexity": 1,
            "family": "diffusivity",
        },
    }
    assert select(table, 0.05) == "diffuse"
    assert select(table, 0.05, families=("random_walk",)) == "walk"
    assert select(table, 0.0, families=("service", "diffusivity")) == "service"


def test_candidate_grid_starts_with_service_and_names_are_unique() -> None:
    service = DriftParameters()
    grid = {
        "diffusivity_m2s": [50.0, 500.0],
        "velocity_noise_ms": [0.1, 0.2],
        "velocity_decorrelation_h": [12.0, 24.0],
        "wide_windages": [0.0, 0.01, 0.03],
    }
    spreads = candidate_grid(grid, service)
    names = [spread.name for spread in spreads]
    assert names[0] == "service" and len(set(names)) == len(names) == 1 + 2 + 4 + 1 + 4
    base = spreads[0]
    assert base.parameters(service) == service
    assert base.complexity(service) == 0
    walk = next(spread for spread in spreads if spread.name == "rw0.2_24h")
    assert walk.velocity_noise_ms == 0.2 and walk.velocity_decorrelation_h == 24.0
    assert walk.complexity(service) == 2
    assert effective_diffusivity(walk) == pytest.approx(5.0 + 0.04 * 24 * 3600, abs=0.1)
    assert len({spread.key(_setup(service)) for spread in spreads}) == len(spreads)
    assert isinstance(base, Spread)


def _setup(service: DriftParameters) -> Setup:
    return Setup(72, 48, 50.0, (24, 48, 72), (0.5, 0.9), service, service)


def test_black_sea_blocks_group_overlapping_windows_by_start_time() -> None:
    moments = [1_700_000_000 + hour * 3600 for hour in range(0, 24 * 7, 6)]
    labels = block_labels(moments, 72)
    assert labels[0] == "block0" and labels[11] == "block0" and labels[12] == "block1"
    assert sorted(set(labels)) == ["block0", "block1", "block2"]
    assert block_labels([], 72) == []


def test_set_summary_uses_items_when_missions_are_few() -> None:
    rows = []
    for group, items, covered in (
        ("m1", ("a", "b"), 1.0),
        ("m2", ("c", "d"), 0.0),
        ("m3", ("e",), 1.0),
    ):
        for item in items:
            for index in range(4):
                rows.append(
                    {
                        "group": group,
                        "item": item,
                        "beached": 0.0,
                        "core24": 10.0 if covered else math.inf,
                        "afloat24": 320.0,
                        "sep24": 5.0 + index,
                        "spread24": 2.0,
                    }
                )
    frame = pd.DataFrame(rows)
    summary = summarize_set(frame, [24], [0.5, 0.9], [0.5], Bootstrap(200, 0.95, 1, 5))
    assert summary["bootstrap_unit"] == "item"
    cell = summary["horizons"]["24"]
    assert cell["coverage"]["0.9"]["value"] == pytest.approx(12 / 20)
    assert cell["coverage"]["0.9"]["group_weighted"] == pytest.approx(2 / 3)
    assert cell["coverage"]["0.9"]["ci"] is not None
    assert cell["coverage"]["0.9"]["leave_one_group_out"] == pytest.approx([1 / 3, 1.0])
    assert summary["calibration_error"] == pytest.approx((abs(0.6 - 0.5) + abs(0.6 - 0.9)) / 2)
    few = Bootstrap(200, 0.95, 1, 6)
    assert (
        summarize_set(frame, [24], [0.9], [0.5], few)["horizons"]["24"]["coverage"]["0.9"]["ci"]
        is None
    )
    assert leave_one_out(frame.iloc[:8], np.ones(8)) is None


def test_cached_only_client_reads_cache_and_never_downloads(tmp_path) -> None:
    store = BlockStore(tmp_path / "cache.sqlite")
    client = CachedOnlyClient(store, None, block_days=14, epoch=dt.date(2021, 12, 27))
    params = {
        "latitude": "40.0000",
        "longitude": "5.0000",
        "start_date": "2023-05-03",
        "end_date": "2023-05-04",
        "hourly": "wind_speed_10m",
    }
    with pytest.raises(NotCached):
        client.get("https://example.test/archive", params)
    times = [
        (dt.datetime(2023, 5, 1) + dt.timedelta(hours=hour)).strftime("%Y-%m-%dT%H:%M")
        for hour in range(14 * 24)
    ]
    signature = "hourly=wind_speed_10m"
    key = series_key(
        "https://example.test/archive", signature, dt.date(2023, 5, 1), "40.0000", "5.0000"
    )
    store.put_many(
        [
            (
                key,
                "2026-01-01T00:00:00+00:00",
                {"hourly": {"time": times, "wind_speed_10m": [3.0] * len(times)}},
            )
        ]
    )
    reply = client.get("https://example.test/archive", params)
    assert len(reply["locations"][0]["hourly"]["time"]) == 48
