import datetime as dt
from dataclasses import replace

import pytest
from shapely.geometry import box

from app.case.data import CaseData, load_case_data
from app.case.pairing import (
    EventInput,
    PairDecision,
    PairingEngine,
    PairReason,
    SyncKind,
    build_event_inputs,
)
from app.case.records import CaseRecord
from app.case.solar import daylight_shift_bound_hours
from app.core.config import Settings
from tests.fakes import FakeCatalog, clear_quality, cloudy_quality, make_scene

T1_DAY = dt.date(2024, 6, 2)


@pytest.fixture(scope="module")
def case() -> CaseData:
    settings = Settings(_env_file=None)
    return load_case_data(settings.case_config, settings.data_dir)


@pytest.fixture(scope="module")
def events(case: CaseData) -> dict:
    record_type = case.config.selection.record_type
    return {event.event_id: event for event in build_event_inputs(case.selections, record_type)}


def engine(case: CaseData, scenes, quality=clear_quality) -> PairingEngine:
    return PairingEngine(case.config.pairing, FakeCatalog(scenes), quality)


def test_every_event_gets_one_input(events: dict) -> None:
    assert len(events) == 318
    assert events["S4:DOORS3:T1"].target_keys == ("litter-visual",)


def test_same_day_clear_scene_is_accepted(case: CaseData, events: dict) -> None:
    result = engine(case, [make_scene("S2A_T1", T1_DAY)]).pair_event(events["S4:DOORS3:T1"])
    assert result.decision is PairDecision.ACCEPTED
    assert result.best.shift_days == 0
    assert result.best.sync is SyncKind.DAYLIGHT_BOUNDED
    assert 8 < result.best.uncertainty_hours < case.config.pairing.max_time_shift_hours


def test_night_pass_cannot_be_bounded_by_daylight(case: CaseData, events: dict) -> None:
    scene = make_scene("S2A_night", T1_DAY, hour=23)
    result = engine(case, [scene]).pair_event(events["S4:DOORS3:T1"])
    assert result.reason is PairReason.SYNC_UNCERTAIN


def test_fallback_collection_fills_gaps_without_duplicates(case: CaseData, events: dict) -> None:
    rules = case.config.pairing
    primary = make_scene("S2A_T35TPJ_20240602_c1", T1_DAY)
    twin = replace(primary, id="S2A_35TPJ_20240602_0_L2A", collection=rules.sentinel2_fallback)
    only_old = replace(
        make_scene("S2B_35TPJ_20240602_0_L2A", T1_DAY, platform="S2B", hour=10),
        collection=rules.sentinel2_fallback,
    )
    result = engine(case, [primary, twin, only_old]).pair_event(events["S4:DOORS3:T1"])
    assert sorted(row.scene.id for row in result.pairs) == [
        "S2A_T35TPJ_20240602_c1",
        "S2B_35TPJ_20240602_0_L2A",
    ]


def test_next_day_scene_is_rejected_without_known_time(case: CaseData, events: dict) -> None:
    scene = make_scene("S2A_next", T1_DAY + dt.timedelta(days=1))
    result = engine(case, [scene]).pair_event(events["S4:DOORS3:T1"])
    assert result.reason is PairReason.TIME_SHIFT


def test_partial_coverage_is_rejected(case: CaseData, events: dict) -> None:
    lon, lat = events["S4:DOORS3:T1"].record.position
    edge = box(lon - 0.01, lat - 1, lon + 5, lat + 1)
    result = engine(case, [make_scene("S2A_edge", T1_DAY, edge)]).pair_event(events["S4:DOORS3:T1"])
    assert result.reason is PairReason.PARTIAL_COVERAGE


def test_clouds_over_the_footprint_reject_the_pair(case: CaseData, events: dict) -> None:
    result = engine(case, [make_scene("S2A_T1", T1_DAY)], cloudy_quality).pair_event(
        events["S4:DOORS3:T1"]
    )
    assert result.reason is PairReason.FOOTPRINT_CLOUD


def test_landsat_needs_a_manual_quality_check(case: CaseData, events: dict) -> None:
    scene = make_scene("LC08_T1", T1_DAY, platform="L8")
    result = engine(case, [scene]).pair_event(events["S4:DOORS3:T1"])
    assert result.decision is PairDecision.CANDIDATE
    assert result.reason is PairReason.QUALITY_UNVERIFIED


def test_open_ocean_is_reported_as_not_acquired(case: CaseData, events: dict) -> None:
    event = next(e for e in events.values() if e.target_keys == ("plastic-trawl",))
    result = engine(case, []).pair_event(event)
    assert result.reason is PairReason.NOT_ACQUIRED


def test_observations_before_sentinel2_are_marked(case: CaseData, events: dict) -> None:
    event = next(e for e in events.values() if e.target_keys == ("plastic-visual",))
    result = engine(case, []).pair_event(event)
    assert result.reason is PairReason.BEFORE_MISSION


def test_events_without_targets_are_not_paired(case: CaseData, events: dict) -> None:
    unused = [e for e in events.values() if not e.target_keys]
    result = engine(case, [make_scene("S2A_T1", T1_DAY)]).pair_event(unused[0])
    assert result.decision is PairDecision.NOT_USED


POLAR_DAY = dt.date(2024, 6, 21)


def polar_event() -> EventInput:
    record = CaseRecord(
        {
            "sample_id": "POLAR-1",
            "event_id": "POLAR:1",
            "source_id": "POLAR",
            "record_type": "transect_density",
            "date_utc": POLAR_DAY.isoformat(),
            "latitude": "78.2",
            "longitude": "15.6",
        }
    )
    return EventInput("POLAR:1", "POLAR", record, ("POLAR-1",), ("litter-visual",))


def polar_scene(hour: int, minute: int = 0):
    scene = make_scene("S2A_polar", POLAR_DAY, box(0, 70, 40, 85))
    moment = dt.datetime.combine(POLAR_DAY, dt.time(hour, minute), tzinfo=dt.UTC)
    return replace(scene, acquired_at=moment)


def test_polar_day_falls_back_to_the_utc_day_bound(case: CaseData) -> None:
    result = engine(case, [polar_scene(10)]).pair_event(polar_event())
    assert result.best.sync is SyncKind.DAY_ONLY
    assert result.best.uncertainty_hours == pytest.approx(14.0)
    assert result.reason is PairReason.SYNC_UNCERTAIN


def test_polar_day_bound_at_noon_is_exactly_the_limit(case: CaseData) -> None:
    result = engine(case, [polar_scene(12)]).pair_event(polar_event())
    assert result.best.uncertainty_hours == pytest.approx(case.config.pairing.max_time_shift_hours)
    assert result.decision is PairDecision.ACCEPTED


def test_unknown_time_bound_is_monotonic_in_information(case: CaseData, events: dict) -> None:
    daylight = engine(case, [make_scene("S2A_T1", T1_DAY, hour=10)]).pair_event(
        events["S4:DOORS3:T1"]
    )
    polar = engine(case, [polar_scene(10)]).pair_event(polar_event())
    assert daylight.best.sync is SyncKind.DAYLIGHT_BOUNDED
    assert daylight.best.uncertainty_hours < polar.best.uncertainty_hours


def test_point_footprint_uses_the_unknown_extent_buffer(case: CaseData, events: dict) -> None:
    result = engine(case, [make_scene("S2A_T1", T1_DAY)]).pair_event(events["S4:DOORS3:T1"])
    assert result.footprint.radius_m == case.config.pairing.unknown_extent_buffer_m
    assert result.best.coverage_fraction == 1.0


def test_event_inputs_follow_the_configured_record_type(case: CaseData) -> None:
    events = build_event_inputs(case.selections, "no_such_record_type")
    assert len(events) == 318
    assert all(event.target_keys == () for event in events)


@pytest.mark.parametrize("reverse", [False, True])
def test_duplicate_scenes_do_not_depend_on_catalog_order(
    case: CaseData, events: dict, reverse: bool
) -> None:
    rules = case.config.pairing
    later = make_scene("S2A_T35TPJ_20240602_1_L2A", T1_DAY)
    earlier = replace(later, id="S2A_T35TPJ_20240602_0_L2A")
    fallback = replace(later, id="S2A_35TPJ_20240602_0_L2A", collection=rules.sentinel2_fallback)
    scenes = [later, fallback, earlier]
    if reverse:
        scenes.reverse()
    result = engine(case, scenes).pair_event(events["S4:DOORS3:T1"])
    assert [row.scene.id for row in result.pairs] == ["S2A_T35TPJ_20240602_0_L2A"]


def test_pass_is_represented_by_the_tile_that_covers_the_footprint_best(
    case: CaseData, events: dict
) -> None:
    lon, lat = events["S4:DOORS3:T1"].record.position
    moment = dt.datetime.combine(T1_DAY, dt.time(9), tzinfo=dt.UTC)
    wide = replace(
        make_scene("S2A_T35TQJ", T1_DAY, box(lon - 0.05, lat - 1, lon + 5, lat + 1), cloud=30.0),
        tile="35TQJ",
    )
    narrow = replace(
        make_scene("S2A_T35TPJ", T1_DAY, box(lon, lat - 1, lon + 5, lat + 1), cloud=0.0),
        acquired_at=moment + dt.timedelta(seconds=4),
    )
    result = engine(case, [wide, narrow]).pair_event(events["S4:DOORS3:T1"])
    rows = {row.scene.id: row for row in result.pairs}
    assert {row.reason for row in rows.values()} == {PairReason.PARTIAL_COVERAGE}
    assert rows["S2A_T35TPJ"].uncertainty_hours < rows["S2A_T35TQJ"].uncertainty_hours
    assert rows["S2A_T35TPJ"].coverage_fraction < rows["S2A_T35TQJ"].coverage_fraction
    assert result.best.scene.id == "S2A_T35TQJ"
    assert result.tile_duplicates == {"S2A_T35TPJ": "S2A_T35TQJ"}


def test_event_is_represented_by_the_nearest_pass(case: CaseData, events: dict) -> None:
    lon, lat = events["S4:DOORS3:T1"].record.position
    near = make_scene(
        "S2A_near", T1_DAY + dt.timedelta(days=1), box(lon, lat - 1, lon + 5, lat + 1)
    )
    far = make_scene("S2B_far", T1_DAY + dt.timedelta(days=2), platform="S2B")
    result = engine(case, [near, far]).pair_event(events["S4:DOORS3:T1"])
    rows = {row.scene.id: row for row in result.pairs}
    assert {row.reason for row in rows.values()} == {PairReason.TIME_SHIFT}
    assert rows["S2A_near"].coverage_fraction < rows["S2B_far"].coverage_fraction
    assert result.best.scene.id == "S2A_near"
    assert result.tile_duplicates == {}


def edge_moment(day: dt.date, days: int, direction: int, inside: bool) -> dt.datetime:
    edge = day + dt.timedelta(days=direction * (days if inside else days + 1))
    clock = dt.time(23, 59, 59) if (direction > 0) == inside else dt.time.min
    return dt.datetime.combine(edge, clock, tzinfo=dt.UTC)


@pytest.mark.parametrize(
    ("window", "direction", "inside", "reason"),
    [
        ("window_days", 1, True, PairReason.TIME_SHIFT),
        ("window_days", 1, False, PairReason.NO_SCENE_IN_WINDOW),
        ("window_days", -1, True, PairReason.TIME_SHIFT),
        ("window_days", -1, False, PairReason.NO_SCENE_IN_WINDOW),
        ("wide_window_days", 1, True, PairReason.NO_SCENE_IN_WINDOW),
        ("wide_window_days", 1, False, PairReason.NOT_ACQUIRED),
        ("wide_window_days", -1, True, PairReason.NO_SCENE_IN_WINDOW),
        ("wide_window_days", -1, False, PairReason.NOT_ACQUIRED),
    ],
)
def test_search_windows_include_whole_edge_days(
    case: CaseData, events: dict, window: str, direction: int, inside: bool, reason: PairReason
) -> None:
    days = getattr(case.config.pairing, window)
    moment = edge_moment(T1_DAY, days, direction, inside)
    scene = replace(make_scene("S2A_edge", T1_DAY), acquired_at=moment)
    result = engine(case, [scene]).pair_event(events["S4:DOORS3:T1"])
    assert result.reason is reason
    assert len(result.pairs) == (1 if reason is PairReason.TIME_SHIFT else 0)


@pytest.mark.parametrize(
    ("offset", "reason"), [(0, PairReason.NOT_ACQUIRED), (-1, PairReason.BEFORE_MISSION)]
)
def test_mission_start_day_counts_as_covered(
    case: CaseData, events: dict, offset: int, reason: PairReason
) -> None:
    day = case.config.pairing.sentinel2_start + dt.timedelta(days=offset)
    event = events["S4:DOORS3:T1"]
    record = CaseRecord({**event.record.fields, "date_utc": day.isoformat()})
    result = engine(case, []).pair_event(replace(event, record=record))
    assert result.reason is reason


def test_strip_without_centre_uses_the_segment_midpoint_for_the_daylight_bound(
    case: CaseData,
) -> None:
    record = CaseRecord(
        {
            "sample_id": "STRIP-1",
            "event_id": "STRIP:1",
            "source_id": "STRIP",
            "record_type": "transect_density",
            "date_utc": T1_DAY.isoformat(),
            "lon_start": "30.0",
            "lat_start": "43.4",
            "lon_end": "30.2",
            "lat_end": "43.6",
            "transect_width_m": "50",
        }
    )
    event = EventInput("STRIP:1", "STRIP", record, ("STRIP-1",), ("litter-visual",))
    scene = make_scene("S2A_strip", T1_DAY, box(29, 43, 31, 44))
    result = engine(case, [scene]).pair_event(event)
    assert record.position is None
    assert result.best.sync is SyncKind.DAYLIGHT_BOUNDED
    expected = daylight_shift_bound_hours(scene.acquired_at, T1_DAY, 43.5, 30.1)
    assert result.best.uncertainty_hours == pytest.approx(expected)
    assert result.decision is PairDecision.ACCEPTED
