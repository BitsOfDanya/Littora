import math
from collections import Counter

import pytest

from app.case.concentration import (
    CheckStatus,
    absolute_error,
    density,
    strip_area_km2,
)
from app.case.data import CaseData, load_case_data
from app.case.geometry import FootprintKind, area_km2, build_footprint, distance_km
from app.case.selection import SelectionReason
from app.core.config import Settings


@pytest.fixture(scope="module")
def case() -> CaseData:
    settings = Settings(_env_file=None)
    return load_case_data(settings.case_config, settings.data_dir)


def test_control_examples_from_the_statement() -> None:
    assert density(12, 0.20) == pytest.approx(60.0)
    assert absolute_error(75.0, 60.0) == pytest.approx(15.0)
    assert strip_area_km2(2.0, 10.0) == pytest.approx(0.02)


@pytest.mark.parametrize(("items", "area"), [(-1, 0.2), (3, 0.0), (3, -0.5)])
def test_density_rejects_impossible_inputs(items: float, area: float) -> None:
    with pytest.raises(ValueError):
        density(items, area)


def test_registry_shape(case: CaseData) -> None:
    assert len(case.records) == 935
    assert len({record.event_id for record in case.records}) == 318


def test_selection_reasons(case: CaseData) -> None:
    reasons = Counter(selection.reason for selection in case.selections)
    assert reasons[SelectionReason.ACCEPTED] == 220
    assert reasons[SelectionReason.ITEM_OBSERVATION] == 337
    assert reasons[SelectionReason.CATEGORY] == 362
    assert reasons[SelectionReason.PROFILE_NOT_TARGETED] == 16


def test_targets_do_not_mix_profiles(case: CaseData) -> None:
    for selection in case.selections:
        if not selection.accepted:
            continue
        target = case.config.target(selection.target_key)
        assert selection.record.profile in target.profiles
        assert selection.record.scope in target.target_scope
    primary = [s for s in case.selections if s.accepted and s.target_key == "litter-visual"]
    assert Counter(s.record.source_id for s in primary) == {
        "S3_SE_NORTH_SEA": 41,
        "S4_BLACK_SEA_DOORS3": 33,
    }


def test_recomputed_density_agrees_with_published(case: CaseData) -> None:
    density_rows = [s for s in case.selections if s.record.record_type == "transect_density"]
    statuses = Counter(s.check.status for s in density_rows)
    assert statuses[CheckStatus.MISMATCH] == 0
    black_sea = [s for s in density_rows if s.record.source_id == "S4_BLACK_SEA_DOORS3"]
    assert {s.check.status for s in black_sea} == {CheckStatus.PUBLISHED_ONLY}


def _record(case: CaseData, event_id: str):
    return next(
        record
        for record in case.records
        if record.event_id == event_id and record.record_type == "transect_density"
    )


def test_point_footprint_for_black_sea_transects(case: CaseData) -> None:
    footprint = build_footprint(_record(case, "S4:DOORS3:T1"), 2000.0, 100.0)
    assert footprint.kind is FootprintKind.POINT
    assert footprint.analysis_area_km2 == pytest.approx(math.pi * 4, rel=0.03)


def test_strip_footprint_keeps_the_surveyed_width(case: CaseData) -> None:
    record = _record(case, "S3:HE419_MarLitter_transect01")
    footprint = build_footprint(record, 2000.0, 100.0)
    assert footprint.kind is FootprintKind.STRIP
    start, end = record.segment
    expected = distance_km(start, end) * 0.1 + math.pi * 0.05**2
    assert area_km2(footprint.analysis) == pytest.approx(expected, rel=0.02)
