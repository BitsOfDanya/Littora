import datetime as dt

import pytest
from shapely.geometry import box

from app.case.data import CaseData, load_case_data
from app.case.pairing import PairDecision, PairingEngine, PairReason, build_event_inputs
from app.core.config import Settings
from tests.fakes import FakeCatalog, clear_quality, cloudy_quality, make_scene

T1_DAY = dt.date(2024, 6, 2)


@pytest.fixture(scope="module")
def case() -> CaseData:
    settings = Settings(_env_file=None)
    return load_case_data(settings.case_config, settings.data_dir)


@pytest.fixture(scope="module")
def events(case: CaseData) -> dict:
    return {event.event_id: event for event in build_event_inputs(case.selections)}


def engine(case: CaseData, scenes, quality=clear_quality) -> PairingEngine:
    return PairingEngine(case.config.pairing, FakeCatalog(scenes), quality)


def test_every_event_gets_one_input(events: dict) -> None:
    assert len(events) == 318
    assert events["S4:DOORS3:T1"].target_keys == ("litter-visual",)


def test_same_day_clear_scene_is_accepted(case: CaseData, events: dict) -> None:
    result = engine(case, [make_scene("S2A_T1", T1_DAY)]).pair_event(events["S4:DOORS3:T1"])
    assert result.decision is PairDecision.ACCEPTED
    assert result.best.shift_days == 0
    assert result.best.uncertainty_hours == case.config.pairing.unknown_time_uncertainty_hours


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
