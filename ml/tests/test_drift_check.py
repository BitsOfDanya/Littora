import datetime as dt

import numpy as np
import pandas as pd
from shapely.geometry import shape

from app.drift import products
from app.drift.geo import offset
from app.drift.model import Trajectories
from littora_ml.drift_check.metrics import (
    cluster_resamples,
    haversine_km,
    liu_weisberg,
    persistence_path,
    separation_km,
    share_better,
    significance,
    skill_vs,
    stationary_path,
)
from littora_ml.drift_check.openmeteo import BlockCachedClient, BlockStore, Throttle, call_weight
from littora_ml.drift_check.report import (
    SERVICE,
    Summarizer,
    bootstrap_group,
    class_table,
    units_text,
)
from littora_ml.drift_check.simulate import envelope_polygon
from littora_ml.drift_check.tracks import DROGUE_OFF, DROGUE_ON, make_track, unix_seconds
from littora_ml.drift_check.windows import (
    Period,
    WindowRules,
    extract_windows,
    resample,
    sample_by_split,
    stratified_order,
    window_at,
)

START = unix_seconds("2023-05-01T00:00:00Z")
HOUR = 3600


def eastward_track(hours: int, speed_ms: float = 0.2, drifter: str = "d1", **extra):
    seconds = START + np.arange(hours + 1) * HOUR
    lon, lat = offset(
        np.full(hours + 1, 5.0),
        np.full(hours + 1, 40.0),
        speed_ms * np.arange(hours + 1) * HOUR,
        np.zeros(hours + 1),
    )
    return make_track(drifter, "med", "SVP", seconds, lon, lat, **extra)


def test_resample_interpolates_inside_short_gaps_only() -> None:
    track = make_track(
        "d",
        "med",
        "SVP",
        np.array([0, 3600, 3 * 3600, 10 * 3600]),
        [0.0, 1.0, 3.0, 10.0],
        [0.0, 0.0, 0.0, 0.0],
    )
    positions, valid = resample(track, np.array([0, 1800, 2 * 3600, 5 * 3600, 10 * 3600]), 3 * 3600)
    assert valid.tolist() == [True, True, True, False, True]
    assert np.allclose(positions[[0, 1, 2, 4], 0], [0.0, 0.5, 2.0, 10.0])


def test_window_starts_at_fix_and_needs_persistence_history() -> None:
    track = eastward_track(120)
    rules = WindowRules(start_every_h=24, max_gap_h=3)
    windows = extract_windows([track], rules)
    assert [window.t0 for window in windows] == [START + h * HOUR for h in (24, 48, 72, 96)]
    assert [window.horizon for window in windows] == [72, 72, 48, 24]
    first = windows[0]
    assert np.allclose(first.start, [track.lon[24], track.lat[24]])
    assert np.allclose(first.track[72], [track.lon[96], track.lat[96]])
    assert np.allclose(first.before, [track.lon[21], track.lat[21]])
    assert np.isnan(windows[3].track[25:]).all()


def test_window_horizon_stops_at_gap_drogue_loss_and_period_end() -> None:
    track = eastward_track(100)
    keep = (np.arange(track.size) < 40) | (np.arange(track.size) > 45)
    gapped = make_track("g", "med", "SVP", track.seconds[keep], track.lon[keep], track.lat[keep])
    window = window_at(gapped, START + 5 * HOUR, WindowRules(max_gap_h=3, min_horizon_h=24))
    assert window is not None and window.horizon == 34
    assert np.isnan(window.track[35]).all()
    drogue = np.where(np.arange(track.size) < 60, DROGUE_ON, DROGUE_OFF)
    lost = make_track("l", "med", "SVP", track.seconds, track.lon, track.lat, drogue)
    window = window_at(lost, START + 5 * HOUR, WindowRules(drogue_known=True))
    assert window is not None and window.drogue == "on" and window.horizon == 54
    period = Period("free", START, START + 50 * HOUR)
    window = window_at(track, START + 5 * HOUR, WindowRules(periods=(period,)))
    assert window is not None and window.period == "free" and window.horizon == 44
    assert window_at(track, START + 60 * HOUR, WindowRules(periods=(period,))) is None


def test_window_rejects_start_far_from_a_real_fix() -> None:
    track = make_track(
        "s",
        "swot",
        "CARTHE",
        START + np.arange(80) * HOUR,
        np.linspace(5, 6, 80),
        np.full(80, 40.0),
        anchor=np.arange(80) != 24,
    )
    assert window_at(track, START + 24 * HOUR, WindowRules()) is None
    assert window_at(track, START + 25 * HOUR, WindowRules(min_horizon_h=24)) is not None


def test_haversine_and_separation() -> None:
    assert np.isclose(haversine_km([10.0, 40.0], [10.0, 41.0]), 111.195, atol=0.01)
    pair = separation_km(np.array([[0.0, 0.0], [1.0, 0.0]]), np.array([[0.0, 0.0], [0.0, 0.0]]))
    assert np.allclose(pair, [0.0, 111.195], atol=0.01)


def test_liu_weisberg_bounds() -> None:
    track = eastward_track(24)
    observed = np.column_stack([track.lon, track.lat])
    assert np.isclose(liu_weisberg(observed, observed, 24), 1.0)
    stay = stationary_path(observed[0], 24)
    assert np.isclose(liu_weisberg(stay, observed, 24), 0.0, atol=1e-6)
    half = observed[0] + (observed - observed[0]) * 0.5
    assert 0.4 < liu_weisberg(half, observed, 24) < 0.6
    assert np.isnan(liu_weisberg(stay, stationary_path(observed[0], 24), 24))


def test_persistence_extrapolates_recent_velocity() -> None:
    track = eastward_track(80)
    observed = np.column_stack([track.lon, track.lat])
    path = persistence_path(observed[5], observed[8], 72, 3)
    assert np.allclose(path[0], observed[8])
    assert separation_km(path[72], observed[80]) < 0.05
    assert np.allclose(stationary_path(observed[8], 72)[72], observed[8])


def test_skill_and_share_against_reference() -> None:
    model = np.array([1.0, 2.0, 3.0, np.nan])
    reference = np.array([2.0, 4.0, 1.0, 5.0])
    assert np.isclose(skill_vs(model, reference), 1 - 2.0 / 3.0)
    assert np.isclose(share_better(model, reference), 2 / 3)


def test_bootstrap_resamples_whole_drifters() -> None:
    drifters = ["a", "a", "a", "b", "c", "c"]
    for sample in cluster_resamples(drifters, 50, np.random.default_rng(0)):
        picked = [drifters[index] for index in sample]
        for name in set(picked):
            assert picked.count(name) % drifters.count(name) == 0


def test_envelope_replica_matches_service_contour() -> None:
    rng = np.random.default_rng(3)
    cloud = np.column_stack([28.0 + rng.normal(0, 0.05, 80), 42.0 + rng.normal(0, 0.03, 80)])
    positions = np.stack([np.tile([28.0, 42.0], (80, 1)), cloud])
    trajectories = Trajectories(positions, np.full(80, np.nan), np.zeros(80, dtype=bool))
    path = products.median_path(positions)
    service = shape(products.envelopes(trajectories, path, horizons=(1,))[0]["polygon"])
    replica = envelope_polygon(cloud, path[1], 0.9)
    assert service.symmetric_difference(replica).area < 1e-9
    assert envelope_polygon(cloud, path[1], 0.5).area < service.area


def test_stratified_order_rotates_over_strata() -> None:
    tracks = [eastward_track(24 * 12, drifter=name) for name in ("a", "b", "c")]
    windows = extract_windows(tracks, WindowRules())
    chosen = stratified_order(windows, 6, np.random.default_rng(1), lambda w: (w.drifter,))
    assert sorted(window.drifter for window in chosen) == ["a", "a", "b", "b", "c", "c"]
    splits = {window.id: "fit" if window.drifter != "c" else "test" for window in windows}
    merged = sample_by_split(windows, splits, 6, 7)
    assert sum(splits[window.id] == "test" for window in merged) == 3


def test_block_client_reuses_cached_blocks(tmp_path) -> None:
    calls = []

    class FakeClient(BlockCachedClient):
        def _request(self, url, params):
            calls.append(params)
            start = dt.date.fromisoformat(params["start_date"])
            times = [
                (dt.datetime.combine(start, dt.time()) + dt.timedelta(hours=h)).strftime(
                    "%Y-%m-%dT%H:%M"
                )
                for h in range(14 * 24)
            ]
            return [
                {"hourly": {"time": times, "wind_speed_10m": [float(lat)] * len(times)}}
                for lat in params["latitude"].split(",")
            ]

    throttle = Throttle(per_minute=1e9, per_hour=1e9, budget=1e9)
    client = FakeClient(BlockStore(tmp_path / "cache.sqlite"), throttle, chunk_points=2)
    params = {
        "latitude": "40.0000,40.2500,40.5000",
        "longitude": "5.0000,5.0000,5.0000",
        "start_date": "2023-05-03",
        "end_date": "2023-05-05",
        "hourly": "wind_speed_10m",
    }
    first = client.get("https://example.test/archive", params)
    assert len(first["locations"]) == 3
    assert len(first["locations"][1]["hourly"]["time"]) == 72
    assert first["locations"][1]["hourly"]["time"][0] == "2023-05-03T00:00"
    assert len(calls) == 2
    second = client.get(
        "https://example.test/archive",
        {
            **params,
            "latitude": "40.2500,40.5000",
            "longitude": "5.0000,5.0000",
            "start_date": "2023-05-04",
            "end_date": "2023-05-06",
        },
    )
    assert len(calls) == 2
    assert second["locations"][1]["hourly"]["wind_speed_10m"][0] == 40.5
    assert throttle.spent == call_weight(2, 14, 1) + call_weight(1, 14, 1) == 3


def test_nautilos_items_of_one_mission_share_a_bootstrap_group() -> None:
    assert bootstrap_group("nautilos", "10_20231215:105") == "10_20231215"
    assert bootstrap_group("nautilos", "10_20231215:116") == "10_20231215"
    assert bootstrap_group("med", "6102345") == "6102345"


def test_significance_needs_interval_clear_of_null() -> None:
    assert significance([-0.27, 0.65], 0.0) == "не значимо"
    assert significance([0.34, 0.91], 0.5) == "не значимо"
    assert significance([0.1, 0.4], 0.0) == "значимо лучше"
    assert significance([-0.4, -0.1], 0.0) == "значимо хуже"
    assert significance(None, 0.0) == "интервала нет"


def litter_frame(missions: int, items: int, windows: int) -> pd.DataFrame:
    rng = np.random.default_rng(5)
    rows = []
    for mission in range(missions):
        for item in range(items):
            for index in range(windows):
                rows.append(
                    {
                        "source": "nautilos",
                        "drifter": f"{mission}_2023:{item}",
                        "group": f"{mission}_2023",
                        "kind": "bottle" if item % 2 else "board",
                        "split": "fit" if mission % 2 else "test",
                        "t0": pd.Timestamp("2023-05-01", tz="UTC") + pd.Timedelta(hours=index),
                        f"D72:{SERVICE}": rng.uniform(5, 50),
                        "D72:stationary": rng.uniform(5, 50),
                        "D72:persistence": rng.uniform(5, 50),
                        f"S72:{SERVICE}": rng.uniform(0, 1),
                        "S72:stationary": 0.0,
                        "S72:persistence": rng.uniform(0, 1),
                        "C72:0.9": float(rng.uniform() < 0.5),
                        "spread72": rng.uniform(1, 5),
                    }
                )
    return pd.DataFrame(rows)


def test_intervals_resample_missions_and_need_five_of_them() -> None:
    summarizer = Summarizer(200, 0.95, 1, 5)
    few = summarizer.block(litter_frame(3, 4, 6), [SERVICE], [72], [0.9])
    entry = few["horizons"]["72"]["methods"][SERVICE]
    assert entry["groups"] == 3 and entry["drifters"] == 12
    assert entry["separation_km"]["median_ci"] is None
    assert entry["skill_vs_persistence"]["verdict"] == "интервала нет"
    many = summarizer.block(litter_frame(6, 2, 6), [SERVICE], [72], [0.9])
    entry = many["horizons"]["72"]["methods"][SERVICE]
    assert entry["skill_vs_stationary"]["ci"] is not None
    assert entry["better_than_persistence"]["verdict"] in {
        "не значимо",
        "значимо лучше",
        "значимо хуже",
    }
    assert units_text(entry) == "72 окна, 12 предм., 6 миссий"


def test_class_table_weights_by_item_and_mission() -> None:
    frame = litter_frame(3, 2, 4)
    rows = {row["label"]: row for row in class_table(frame, [72])}
    assert rows["все окна"]["horizons"]["72"]["units"] == 24
    assert rows["все, медиана по предметам"]["horizons"]["72"]["units"] == 6
    assert rows["все, медиана по миссиям"]["horizons"]["72"]["units"] == 3
    assert {"подбор 2023", "проверка 2023", "бутылки", "доски"} <= set(rows)
    assert rows["миссия 1_2023"]["horizons"]["72"]["windows"] == 8
