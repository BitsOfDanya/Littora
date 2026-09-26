import math
from collections import Counter
from dataclasses import replace

import pytest
from shapely.geometry import box

from app.case.concentration import (
    CheckStatus,
    absolute_error,
    density,
    strip_area_km2,
)
from app.case.data import CaseData, load_case_data
from app.case.geometry import (
    FootprintKind,
    MissingPositionError,
    area_km2,
    build_footprint,
    distance_km,
)
from app.case.records import CaseRecord
from app.case.registry import selection_summary
from app.case.selection import SelectionReason, select_record
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
    rules = case.config.pairing
    record = _record(case, "S4:DOORS3:T1")
    footprint = build_footprint(record, rules.unknown_extent_buffer_m, rules.min_strip_width_m)
    radius_km = rules.unknown_extent_buffer_m / 1000
    assert footprint.kind is FootprintKind.POINT
    assert footprint.radius_m == rules.unknown_extent_buffer_m
    assert footprint.analysis_area_km2 == pytest.approx(math.pi * radius_km**2, rel=0.03)


def test_strip_footprint_keeps_the_surveyed_width(case: CaseData) -> None:
    record = _record(case, "S3:HE419_MarLitter_transect01")
    footprint = build_footprint(record, 6000.0, 100.0)
    assert footprint.kind is FootprintKind.STRIP
    assert footprint.radius_m == 50.0
    start, end = record.segment
    expected = distance_km(start, end) * 0.1 + math.pi * 0.05**2
    assert area_km2(footprint.analysis) == pytest.approx(expected, rel=0.02)


def test_footprint_without_coordinates_is_reported() -> None:
    record = CaseRecord({"sample_id": "X-1", "event_id": "X:1"})
    with pytest.raises(MissingPositionError):
        build_footprint(record, 6000.0, 100.0)


def test_footprint_coverage_by_a_scene(case: CaseData) -> None:
    record = _record(case, "S4:DOORS3:T1")
    footprint = build_footprint(record, 6000.0, 100.0)
    lon, lat = record.position
    assert footprint.covered_by(box(lon - 1, lat - 1, lon + 1, lat + 1)) == 1.0
    assert footprint.covered_by(box(lon, lat - 1, lon + 1, lat + 1)) == pytest.approx(0.5, abs=0.01)
    assert footprint.covered_by(box(lon + 1, lat + 1, lon + 2, lat + 2)) == 0.0


def _mismatch_record() -> CaseRecord:
    return CaseRecord(
        {
            "sample_id": "MM-1",
            "event_id": "MM:1",
            "source_id": "MM",
            "record_type": "transect_density",
            "measurement_profile": "S2_visual_GT2",
            "target_scope": "total_plastic",
            "concentration_items_km2": "100",
            "density_numerator_items": "30",
            "sampled_area_km2": "0.2",
        }
    )


def test_mismatch_is_kept_unless_the_flag_is_set(case: CaseData) -> None:
    record = _mismatch_record()
    kept = select_record(record, case.config)
    assert kept.check.status is CheckStatus.MISMATCH
    assert kept.reason is SelectionReason.ACCEPTED
    strict = replace(case.config, selection=replace(case.config.selection, reject_on_mismatch=True))
    rejected = select_record(record, strict)
    assert rejected.reason is SelectionReason.CONCENTRATION_MISMATCH
    assert rejected.target_key == "plastic-visual"
    assert "50.0 %" in rejected.label


def test_summary_reports_verifiable_share_per_target(case: CaseData) -> None:
    targets = {
        item["key"]: item for item in selection_summary(case.config, case.selections)["targets"]
    }
    litter = targets["litter-visual"]
    assert litter["records"] == 74
    assert litter["verifiable_records"] == 41
    assert litter["verifiable_share"] == pytest.approx(41 / 74, abs=1e-4)
    assert litter["concentration_checks"]["published_only"] == 33
    assert sum(litter["concentration_checks"].values()) == litter["records"]
