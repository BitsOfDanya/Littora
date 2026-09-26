import datetime as dt
import platform
import re
from dataclasses import dataclass, replace
from pathlib import Path

import pytest
from shapely.geometry import box

from app.case.config import PairingRules
from app.case.data import CaseData, load_case_data
from app.case.pairing import (
    EventInput,
    EventResult,
    PairDecision,
    PairingEngine,
    PairReason,
    SyncKind,
)
from app.case.records import CaseRecord
from app.case.registry import (
    EVENTS_FILE,
    NEVER_LARGER,
    NEVER_SMALLER,
    OBSERVATIONS_FILE,
    PAIRS_FILE,
    SUMMARY_FILE,
    _stats,
    code_fingerprint,
    pair_row,
    read_csv,
    read_json,
    rounded,
    runtime_versions,
    write_pairing,
)
from app.case.solar import daylight_within_utc_day
from app.core.config import Settings
from app.earth.catalog import CatalogError, Scene
from app.earth.raster import QualityShares, RasterError
from tests.fakes import FakeCatalog, clear_quality, make_scene

DAY = dt.date(2024, 6, 2)
LAT = 43.5
POLAR = (15.6, 78.2)
POLAR_DAY = dt.date(2024, 6, 21)
REGISTRY_FILES = (OBSERVATIONS_FILE, PAIRS_FILE, EVENTS_FILE, SUMMARY_FILE)


@pytest.fixture(scope="module")
def case() -> CaseData:
    settings = Settings(_env_file=None)
    return load_case_data(settings.case_config, settings.data_dir)


@pytest.fixture(scope="module")
def rules(case: CaseData) -> PairingRules:
    return case.config.pairing


@dataclass(frozen=True)
class Scenario:
    reason: PairReason
    decision: PairDecision
    event: EventInput
    scenes: tuple[Scene, ...] = ()
    quality: QualityShares | None = None
    read_error: bool = False
    broken: bool = False


def site(index: int) -> tuple[float, float]:
    return 28.0 + 0.5 * index, LAT


def around(position: tuple[float, float], half: float = 0.2):
    lon, lat = position
    return box(lon - half, lat - half, lon + half, lat + half)


def make_event(
    name: str,
    position: tuple[float, float] | None,
    day: dt.date | None = DAY,
    time: str | None = "09:00",
    targets: tuple[str, ...] = ("litter-visual",),
) -> EventInput:
    lon, lat = position if position else ("", "")
    fields = {
        "sample_id": f"{name}-S",
        "event_id": name,
        "source_id": "SYN",
        "record_type": "transect_density",
        "date_utc": day.isoformat() if day else "",
        "time_start_utc": time or "",
        "latitude": str(lat),
        "longitude": str(lon),
    }
    return EventInput(name, "SYN", CaseRecord(fields), (fields["sample_id"],), targets)


def make_pass(
    scene_id: str,
    position: tuple[float, float],
    moment: dt.datetime,
    platform: str = "S2A",
    geometry=None,
    **changes,
) -> Scene:
    base = make_scene(scene_id, moment.date(), geometry or around(position), platform=platform)
    return replace(base, acquired_at=moment, **changes)


def at(day: dt.date, hour: int, minute: int = 0) -> dt.datetime:
    return dt.datetime.combine(day, dt.time(hour, minute), tzinfo=dt.UTC)


def quality(**changes) -> QualityShares:
    return replace(clear_quality(), **changes)


def reason_scenarios(rules: PairingRules) -> dict[PairReason, Scenario]:
    limit = int(rules.max_time_shift_hours)
    specs: list[tuple] = [
        (PairReason.ACCEPTED, PairDecision.ACCEPTED, {}, {}, None),
        (PairReason.NO_TARGET, PairDecision.NOT_USED, {"targets": ()}, {}, None),
        (PairReason.NO_DATE, PairDecision.REJECTED, {"day": None}, {}, None),
        (PairReason.NO_POSITION, PairDecision.REJECTED, {"position": None}, {}, None),
        (
            PairReason.BEFORE_MISSION,
            PairDecision.REJECTED,
            {"day": dt.date(2014, 6, 2)},
            None,
            None,
        ),
        (PairReason.NOT_ACQUIRED, PairDecision.REJECTED, {"day": dt.date(2020, 6, 2)}, None, None),
        (
            PairReason.NO_SCENE_IN_WINDOW,
            PairDecision.REJECTED,
            {},
            {"moment": at(DAY + dt.timedelta(days=rules.window_days + 2), 9)},
            None,
        ),
        (
            PairReason.TIME_SHIFT,
            PairDecision.REJECTED,
            {},
            {"moment": at(DAY, 9 + limit + 1)},
            None,
        ),
        (
            PairReason.SYNC_UNCERTAIN,
            PairDecision.REJECTED,
            {"time": None},
            {"moment": at(DAY, 23)},
            None,
        ),
        (PairReason.PARTIAL_COVERAGE, PairDecision.REJECTED, {}, {"partial": True}, None),
        (
            PairReason.TILE_CLOUD,
            PairDecision.REJECTED,
            {},
            {"cloud_cover": rules.max_tile_cloud + 10},
            None,
        ),
        (PairReason.QUALITY_UNVERIFIED, PairDecision.CANDIDATE, {}, {"platform": "L8"}, None),
        (
            PairReason.NODATA,
            PairDecision.REJECTED,
            {},
            {},
            quality(nodata=rules.max_footprint_nodata + 0.1),
        ),
        (
            PairReason.FOOTPRINT_CLOUD,
            PairDecision.REJECTED,
            {},
            {},
            quality(cloud=rules.max_footprint_cloud + 0.1),
        ),
        (
            PairReason.NO_WATER,
            PairDecision.REJECTED,
            {},
            {},
            quality(water=rules.min_footprint_water - 0.1),
        ),
        (
            PairReason.BRIGHT_WATER,
            PairDecision.REJECTED,
            {},
            {},
            quality(bright_water=rules.max_bright_water + 0.1),
        ),
        (PairReason.READ_ERROR, PairDecision.NOT_EVALUATED, {}, {}, None),
        (PairReason.CATALOG_ERROR, PairDecision.NOT_EVALUATED, {}, {}, None),
    ]
    scenarios = {}
    for index, (reason, decision, event_args, scene_args, shares) in enumerate(specs):
        position = site(index)
        event_args = {"position": position} | event_args
        event = make_event(f"E:{reason.value}", **event_args)
        scenes: tuple[Scene, ...] = ()
        if scene_args is not None:
            scene_args = dict(scene_args)
            moment = scene_args.pop("moment", at(DAY, 10))
            if scene_args.pop("partial", False):
                lon, lat = position
                scene_args["geometry"] = box(lon, lat - 0.2, lon + 0.2, lat + 0.2)
            scenes = (make_pass(f"S_{reason.value}", position, moment, **scene_args),)
        scenarios[reason] = Scenario(
            reason,
            decision,
            event,
            scenes,
            shares,
            read_error=reason is PairReason.READ_ERROR,
            broken=reason is PairReason.CATALOG_ERROR,
        )
    return scenarios


def extra_scenarios() -> list[Scenario]:
    daylight = site(40)
    tiles = site(42)
    first = make_pass("S2A_T35TPJ_tiles", tiles, at(DAY, 10), tile="35TPJ")
    second = replace(
        first,
        id="S2A_T35TQJ_tiles",
        tile="35TQJ",
        acquired_at=first.acquired_at + dt.timedelta(seconds=4),
    )
    return [
        Scenario(
            PairReason.ACCEPTED,
            PairDecision.ACCEPTED,
            make_event("E:daylight", daylight, time=None),
            (make_pass("S_daylight", daylight, at(DAY, 9)),),
        ),
        Scenario(
            PairReason.ACCEPTED,
            PairDecision.ACCEPTED,
            make_event("E:polar", POLAR, day=POLAR_DAY, time=None),
            (make_pass("S_polar", POLAR, at(POLAR_DAY, 12), geometry=around(POLAR, 1.0)),),
        ),
        Scenario(
            PairReason.ACCEPTED,
            PairDecision.ACCEPTED,
            make_event("E:tiles", tiles),
            (second, first),
        ),
    ]


class ScenarioCatalog(FakeCatalog):
    def __init__(self, scenes: list[Scene], broken: list) -> None:
        super().__init__(scenes)
        self.broken = broken

    def search(self, collection, geometry, start, end, limit=100):
        if any(area.intersects(geometry) for area in self.broken):
            raise CatalogError("нет связи")
        return super().search(collection, geometry, start, end, limit)


def run(scenarios: list[Scenario], rules: PairingRules, workers: int = 4) -> list[EventResult]:
    shares = {scene.id: item.quality for item in scenarios for scene in item.scenes}
    failing = {scene.id for item in scenarios if item.read_error for scene in item.scenes}

    def reader(scene: Scene, _footprint) -> QualityShares:
        if scene.id in failing:
            raise RasterError("маска SCL не читается")
        return shares.get(scene.id) or clear_quality()

    broken = [around(item.event.record.position) for item in scenarios if item.broken]
    scenes = [scene for item in scenarios for scene in item.scenes]
    engine = PairingEngine(rules, ScenarioCatalog(scenes, broken), reader)
    return engine.pair_events([item.event for item in scenarios], workers)


def single(rules: PairingRules, event: EventInput, scene: Scene, shares=None) -> EventResult:
    return run(
        [Scenario(PairReason.ACCEPTED, PairDecision.ACCEPTED, event, (scene,), shares)], rules
    )[0]


@pytest.mark.parametrize("reason", list(PairReason))
def test_every_reason_code_is_reachable(rules: PairingRules, reason: PairReason) -> None:
    scenario = reason_scenarios(rules)[reason]
    result = run([scenario], rules)[0]
    assert result.reason is reason
    assert result.decision is scenario.decision


def test_event_without_coordinates_does_not_crash(rules: PairingRules) -> None:
    result = run([reason_scenarios(rules)[PairReason.NO_POSITION]], rules)[0]
    assert result.footprint is None
    assert result.pairs == ()


@pytest.mark.parametrize(
    ("field", "rule", "step", "reason"),
    [
        ("nodata", "max_footprint_nodata", 1e-6, PairReason.NODATA),
        ("cloud", "max_footprint_cloud", 1e-6, PairReason.FOOTPRINT_CLOUD),
        ("water", "min_footprint_water", -1e-6, PairReason.NO_WATER),
        ("bright_water", "max_bright_water", 1e-6, PairReason.BRIGHT_WATER),
    ],
)
def test_quality_thresholds_are_inclusive(
    rules: PairingRules, field: str, rule: str, step: float, reason: PairReason
) -> None:
    limit = getattr(rules, rule)
    event = make_event("E:edge", site(0))
    scene = make_pass("S_edge", site(0), at(DAY, 10))
    assert single(rules, event, scene, quality(**{field: limit})).reason is PairReason.ACCEPTED
    assert single(rules, event, scene, quality(**{field: limit + step})).reason is reason


def test_tile_cloud_threshold_is_inclusive(rules: PairingRules) -> None:
    event = make_event("E:edge", site(0))
    limit = rules.max_tile_cloud
    at_limit = make_pass("S_edge", site(0), at(DAY, 10), cloud_cover=limit)
    beyond = make_pass("S_edge", site(0), at(DAY, 10), cloud_cover=limit + 1e-6)
    assert single(rules, event, at_limit).reason is PairReason.ACCEPTED
    assert single(rules, event, beyond).reason is PairReason.TILE_CLOUD


def footprint_of(rules: PairingRules, event: EventInput):
    return PairingEngine(rules, ScenarioCatalog([], []), clear_quality).footprint(event.record)


def test_coverage_limit_is_inclusive(rules: PairingRules) -> None:
    event = make_event("E:edge", site(0))
    analysis = footprint_of(rules, event).analysis
    _, south, east, north = analysis.bounds
    sliver = analysis.difference(box(east - 1e-4, south - 1, east + 1, north + 1))
    exact = single(rules, event, make_pass("S_edge", site(0), at(DAY, 10), geometry=analysis))
    short = single(rules, event, make_pass("S_edge", site(0), at(DAY, 10), geometry=sliver))
    assert exact.best.coverage_fraction == 1.0
    assert exact.reason is PairReason.ACCEPTED
    assert 0.9999 < short.best.coverage_fraction < 1.0
    assert short.reason is PairReason.PARTIAL_COVERAGE
    assert pair_row(short.best, short.footprint)["coverage_fraction"] == "0.9999"


def test_known_time_shift_threshold_is_inclusive(rules: PairingRules) -> None:
    event = make_event("E:edge", site(0), time="06:00")
    limit = dt.timedelta(hours=rules.max_time_shift_hours)
    start = at(DAY, 6)
    at_limit = single(rules, event, make_pass("S_edge", site(0), start + limit))
    beyond = single(
        rules, event, make_pass("S_edge", site(0), start + limit + dt.timedelta(minutes=1))
    )
    assert at_limit.best.shift_hours == pytest.approx(rules.max_time_shift_hours)
    assert at_limit.reason is PairReason.ACCEPTED
    assert beyond.reason is PairReason.TIME_SHIFT


def test_daylight_bound_threshold_is_inclusive(rules: PairingRules) -> None:
    position = site(0)
    event = make_event("E:edge", position, time=None)
    sunrise = daylight_within_utc_day(DAY, position[1], position[0])[0][0]
    moment = sunrise + dt.timedelta(hours=rules.max_time_shift_hours)
    at_limit = single(rules, event, make_pass("S_edge", position, moment))
    beyond = single(rules, event, make_pass("S_edge", position, moment + dt.timedelta(minutes=1)))
    assert at_limit.best.sync is SyncKind.DAYLIGHT_BOUNDED
    assert at_limit.best.uncertainty_hours == pytest.approx(rules.max_time_shift_hours)
    assert at_limit.reason is PairReason.ACCEPTED
    assert beyond.reason is PairReason.SYNC_UNCERTAIN


def test_utc_day_bound_threshold_is_inclusive(rules: PairingRules) -> None:
    event = make_event("E:polar", POLAR, day=POLAR_DAY, time=None)
    geometry = around(POLAR, 1.0)
    noon = single(rules, event, make_pass("S_polar", POLAR, at(POLAR_DAY, 12), geometry=geometry))
    late = single(
        rules, event, make_pass("S_polar", POLAR, at(POLAR_DAY, 12, 1), geometry=geometry)
    )
    assert noon.best.sync is SyncKind.DAY_ONLY
    assert noon.reason is PairReason.ACCEPTED
    assert late.reason is PairReason.SYNC_UNCERTAIN


def test_unknown_time_rejects_other_days(rules: PairingRules) -> None:
    event = make_event("E:edge", site(0), time=None)
    scene = make_pass("S_edge", site(0), at(DAY + dt.timedelta(days=1), 9))
    assert single(rules, event, scene).reason is PairReason.TIME_SHIFT


def test_pass_is_represented_by_the_tile_that_got_furthest(rules: PairingRules) -> None:
    position = site(0)
    lon, lat = position
    edge = make_pass("S2A_T37TFG", position, at(DAY, 10), tile="37TFG", cloud_cover=5.0)
    edge = replace(edge, geometry=box(lon, lat - 0.2, lon + 0.2, lat + 0.2))
    full = replace(
        make_pass("S2A_T38TKM", position, at(DAY, 10), tile="38TKM", cloud_cover=30.0),
        acquired_at=at(DAY, 10) + dt.timedelta(seconds=3),
    )
    cloudy = quality(cloud=rules.max_footprint_cloud + 0.05)
    scenario = Scenario(
        PairReason.FOOTPRINT_CLOUD,
        PairDecision.REJECTED,
        make_event("E:pass", position),
        (edge, full),
        cloudy,
    )
    result = run([scenario], rules)[0]
    assert result.reason is PairReason.FOOTPRINT_CLOUD
    assert result.best.scene.id == "S2A_T38TKM"
    assert result.tile_duplicates == {"S2A_T37TFG": "S2A_T38TKM"}


STAGES = [
    PairReason.TIME_SHIFT,
    PairReason.SYNC_UNCERTAIN,
    PairReason.PARTIAL_COVERAGE,
    PairReason.TILE_CLOUD,
    PairReason.QUALITY_UNVERIFIED,
    PairReason.READ_ERROR,
    PairReason.NODATA,
    PairReason.FOOTPRINT_CLOUD,
    PairReason.NO_WATER,
    PairReason.BRIGHT_WATER,
]
PAIR_DECISIONS = {
    PairReason.ACCEPTED: PairDecision.ACCEPTED,
    PairReason.QUALITY_UNVERIFIED: PairDecision.CANDIDATE,
    PairReason.READ_ERROR: PairDecision.NOT_EVALUATED,
}
FIXED_DIGITS = {
    "shift_hours": 2,
    "time_uncertainty_hours": 2,
    "drift_km_max": 2,
    "tile_cloud": 2,
    "sun_elevation": 2,
    "footprint_radius_m": 1,
    "footprint_area_km2": 4,
    "coverage_fraction": 4,
    "water": 4,
    "cloud": 4,
    "shadow": 4,
    "snow": 4,
    "land": 4,
    "nodata": 4,
    "other": 4,
    "bright_water": 4,
}


SHARE_STEP = 1e-4


def _value(row: dict[str, str], name: str) -> float:
    return float(row[name])


def passes(stage: PairReason, row: dict[str, str], rules: PairingRules, slack: float = 0.0) -> bool:
    known = row["time_known"] == "yes"
    limit = rules.max_time_shift_hours
    if stage is PairReason.TIME_SHIFT:
        if known:
            return abs(_value(row, "shift_hours")) <= limit
        return abs(int(row["shift_days"])) <= rules.unknown_time_max_days
    if stage is PairReason.SYNC_UNCERTAIN:
        return known or _value(row, "time_uncertainty_hours") <= limit
    if stage is PairReason.PARTIAL_COVERAGE:
        return _value(row, "coverage_fraction") >= 1.0
    if stage is PairReason.TILE_CLOUD:
        return row["tile_cloud"] == "" or _value(row, "tile_cloud") <= rules.max_tile_cloud
    if stage is PairReason.QUALITY_UNVERIFIED:
        return row["platform"].startswith("S2")
    if stage is PairReason.READ_ERROR:
        return row["pixels"] != ""
    if stage is PairReason.NODATA:
        return _value(row, "nodata") <= rules.max_footprint_nodata
    if stage is PairReason.FOOTPRINT_CLOUD:
        shown = _value(row, "cloud") + _value(row, "shadow")
        return shown <= rules.max_footprint_cloud + slack + 1e-9
    if stage is PairReason.NO_WATER:
        return _value(row, "water") >= rules.min_footprint_water
    return row["bright_water"] == "" or _value(row, "bright_water") <= rules.max_bright_water


def assert_pairs_consistent(rows: list[dict[str, str]], rules: PairingRules) -> None:
    by_scene = {(row["event_id"], row["scene_id"]): row for row in rows}
    for row in rows:
        reason = PairReason(row["reason_code"])
        assert row["decision"] == PAIR_DECISIONS.get(reason, PairDecision.REJECTED).value
        stage = STAGES.index(reason) if reason in STAGES else len(STAGES)
        assert all(passes(earlier, row, rules, SHARE_STEP) for earlier in STAGES[:stage]), row
        if reason in STAGES:
            assert not passes(reason, row, rules), row
        for name, digits in FIXED_DIGITS.items():
            if row[name]:
                assert re.fullmatch(rf"\d+\.\d{{{digits}}}", row[name].lstrip("-")), (name, row)
                assert not row[name].startswith("-0.") or float(row[name]) != 0
        if row["tile_duplicate_of"]:
            original = by_scene[(row["event_id"], row["tile_duplicate_of"])]
            assert original["pass_id"] == row["pass_id"]
            assert not original["tile_duplicate_of"]


def write_twice(tmp_path: Path, case: CaseData, scenarios: list[Scenario]) -> list[Path]:
    rules = case.config.pairing
    folders = [tmp_path / "first", tmp_path / "second"]
    provenance = {"code_fingerprint": code_fingerprint()}
    write_pairing(folders[0], case.config, case.selections, run(scenarios, rules), provenance)
    shuffled = list(reversed(run(scenarios, rules, workers=1)))
    write_pairing(folders[1], case.config, case.selections, shuffled, dict(provenance))
    return folders


def test_write_pairing_is_consistent_and_deterministic(tmp_path: Path, case: CaseData) -> None:
    rules = case.config.pairing
    scenarios = list(reason_scenarios(rules).values()) + extra_scenarios()
    first, second = write_twice(tmp_path, case, scenarios)
    for name in REGISTRY_FILES:
        assert (first / name).read_bytes() == (second / name).read_bytes(), name

    rows = read_csv(first / PAIRS_FILE)
    assert_pairs_consistent(rows, rules)
    assert {PairReason(row["reason_code"]) for row in rows} == set(STAGES) | {PairReason.ACCEPTED}

    events = {
        feature["id"]: feature["properties"]
        for feature in read_json(first / EVENTS_FILE)["features"]
    }
    for scenario in scenarios:
        properties = events[scenario.event.event_id]
        assert properties["decision"] == scenario.decision.value
        assert properties["reason_code"] == scenario.reason.value
    assert events["E:no_position"]["footprint_kind"] is None
    assert events["E:accepted"]["footprint_kind"] == "point"
    assert events["E:accepted"]["footprint_radius_m"] == rules.unknown_extent_buffer_m
    assert events["E:tiles"]["candidates"] == 2
    assert events["E:tiles"]["accepted_passes"] == 1

    summary = read_json(first / SUMMARY_FILE)
    duplicates = [row for row in rows if row["tile_duplicate_of"]]
    assert [row["scene_id"] for row in duplicates] == ["S2A_T35TQJ_tiles"]
    assert summary["scene_candidates"] == len(rows)
    assert summary["tile_duplicates"] == len(duplicates)
    assert summary["scene_passes"] == len(rows) - len(duplicates)
    assert sum(summary["pairs"].values()) == summary["scene_passes"]
    assert sum(summary["pair_reasons"].values()) == summary["scene_passes"]
    assert summary["events"]["not_evaluated"] == 2
    assert summary["sync_accepted_events"] == {
        "daylight_bounded": 1,
        "day_only": 1,
        "time_known": 2,
    }


def test_summary_keeps_shifts_and_bounds_apart(tmp_path: Path, case: CaseData) -> None:
    rules = case.config.pairing
    scenarios = list(reason_scenarios(rules).values()) + extra_scenarios()
    first, _ = write_twice(tmp_path, case, scenarios)
    offsets = read_json(first / SUMMARY_FILE)["time_offset_hours"]
    assert set(offsets) == {kind.value for kind in SyncKind}
    assert offsets["time_known"]["measure"] == "abs_shift"
    assert offsets["daylight_bounded"]["measure"] == "upper_bound"
    assert offsets["day_only"]["measure"] == "upper_bound"
    assert offsets["time_known"]["accepted_pairs"]["max"] == pytest.approx(1.0)
    assert offsets["day_only"]["accepted_pairs"]["max"] == pytest.approx(12.0)
    daylight = offsets["daylight_bounded"]["accepted_pairs"]
    assert daylight["n"] == 1
    assert 6.0 < daylight["max"] < rules.max_time_shift_hours


def test_accepted_summary_rounds_like_the_table(tmp_path: Path, case: CaseData) -> None:
    rules = case.config.pairing
    scenarios = list(reason_scenarios(rules).values()) + extra_scenarios()
    first, _ = write_twice(tmp_path, case, scenarios)
    rows = {(row["event_id"], row["scene_id"]): row for row in read_csv(first / PAIRS_FILE)}
    for item in read_json(first / SUMMARY_FILE)["accepted_pairs"]:
        row = rows[(item["event_id"], item["scene_id"])]
        assert f"{item['time_uncertainty_hours']:.2f}" == row["time_uncertainty_hours"]
        assert f"{item['coverage_fraction']:.4f}" == row["coverage_fraction"]
        assert f"{item['water']:.4f}" == row["water"]
        if item["shift_hours"] is not None:
            assert f"{item['shift_hours']:.2f}" == row["shift_hours"]


def test_code_fingerprint_follows_imports_from_the_entrypoint(tmp_path: Path) -> None:
    sources = {
        "__init__.py": "",
        "case/__init__.py": "",
        "case/__main__.py": "from app.case.cli import main\n",
        "case/cli.py": "import json\nfrom app.earth import catalog\n",
        "case/repository.py": "from app.case.cli import main\n",
        "earth/__init__.py": "",
        "earth/catalog.py": "value = 1\n",
        "earth/bands.py": "from app.earth.catalog import value\n",
    }
    for name, text in sources.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(text)
    first = code_fingerprint(tmp_path)
    assert first == code_fingerprint(tmp_path)
    assert first["files"] == [
        "__init__.py",
        "case/__init__.py",
        "case/__main__.py",
        "case/cli.py",
        "earth/__init__.py",
        "earth/catalog.py",
    ]
    (tmp_path / "earth" / "bands.py").write_text("value = 2\n")
    (tmp_path / "case" / "repository.py").write_text("value = 3\n")
    assert code_fingerprint(tmp_path) == first
    (tmp_path / "earth" / "catalog.py").write_text("value = 4\n")
    assert code_fingerprint(tmp_path)["sha256"] != first["sha256"]


def test_code_fingerprint_covers_only_the_registry_pipeline() -> None:
    files = code_fingerprint()["files"]
    pipeline = {
        "case/cli.py",
        "case/data.py",
        "case/pairing.py",
        "case/registry.py",
        "case/solar.py",
        "earth/catalog.py",
        "earth/raster.py",
    }
    assert pipeline <= set(files)
    assert "case/repository.py" not in files
    assert "earth/bands.py" not in files
    assert not [name for name in files if name.startswith(("api/", "analysis/"))]


def test_runtime_versions_name_the_pairing_stack() -> None:
    versions = runtime_versions()
    assert set(versions) == {"python", "numpy", "shapely", "geos", "rasterio", "gdal"}
    assert versions["python"] == platform.python_version()
    assert all(versions.values())


@pytest.mark.parametrize(
    ("value", "digits", "rounding", "shown"),
    [
        (0.99996, 4, NEVER_LARGER, 0.9999),
        (0.49996, 4, NEVER_LARGER, 0.4999),
        (0.96, 4, NEVER_LARGER, 0.96),
        (1.0, 4, NEVER_LARGER, 1.0),
        (40.004, 2, NEVER_SMALLER, 40.01),
        (12.004, 2, NEVER_SMALLER, 12.01),
        (-12.004, 2, NEVER_SMALLER, -12.01),
        (0.1, 4, NEVER_SMALLER, 0.1),
        (12.0, 2, NEVER_SMALLER, 12.0),
    ],
)
def test_conservative_rounding(value: float, digits: int, rounding: str, shown: float) -> None:
    assert rounded(value, digits, rounding) == shown


def boundary_cases() -> list:
    limit = dt.timedelta(hours=12)
    extra = dt.timedelta(seconds=14.4)
    position = site(0)
    return [
        (
            "tile_cloud",
            "40.01",
            PairReason.TILE_CLOUD,
            make_event("E:edge", position),
            make_pass("S_edge", position, at(DAY, 10), cloud_cover=40.004),
            None,
        ),
        (
            "shift_hours",
            "12.01",
            PairReason.TIME_SHIFT,
            make_event("E:edge", position, time="06:00"),
            make_pass("S_edge", position, at(DAY, 6) + limit + extra),
            None,
        ),
        (
            "shift_hours",
            "-12.01",
            PairReason.TIME_SHIFT,
            make_event("E:edge", position, time="06:00"),
            make_pass("S_edge", position, at(DAY, 6) - limit - extra),
            None,
        ),
        (
            "time_uncertainty_hours",
            "12.01",
            PairReason.SYNC_UNCERTAIN,
            make_event("E:polar", POLAR, day=POLAR_DAY, time=None),
            make_pass("S_polar", POLAR, at(POLAR_DAY, 12) + extra, geometry=around(POLAR, 1.0)),
            None,
        ),
        (
            "water",
            "0.4999",
            PairReason.NO_WATER,
            make_event("E:edge", position),
            make_pass("S_edge", position, at(DAY, 10)),
            quality(water=0.49996),
        ),
        (
            "cloud",
            "0.1001",
            PairReason.FOOTPRINT_CLOUD,
            make_event("E:edge", position),
            make_pass("S_edge", position, at(DAY, 10)),
            quality(cloud=0.10004, shadow=0.0),
        ),
        (
            "nodata",
            "0.0501",
            PairReason.NODATA,
            make_event("E:edge", position),
            make_pass("S_edge", position, at(DAY, 10)),
            quality(nodata=0.05004),
        ),
        (
            "bright_water",
            "0.3001",
            PairReason.BRIGHT_WATER,
            make_event("E:edge", position),
            make_pass("S_edge", position, at(DAY, 10)),
            quality(bright_water=0.30004),
        ),
    ]


@pytest.mark.parametrize(
    ("column", "shown", "reason", "event", "scene", "shares"),
    boundary_cases(),
)
def test_displayed_value_never_looks_better_than_the_decision(
    rules: PairingRules,
    column: str,
    shown: str,
    reason: PairReason,
    event: EventInput,
    scene: Scene,
    shares: QualityShares | None,
) -> None:
    result = single(rules, event, scene, shares)
    row = pair_row(result.best, result.footprint)
    assert result.reason is reason
    assert row[column] == shown
    assert not passes(reason, row, rules)


def test_quartiles_stay_within_the_range() -> None:
    stats = _stats([1.0, 3.0], 2)
    assert stats == {"n": 2, "min": 1.0, "q1": 1.5, "median": 2.0, "q3": 2.5, "max": 3.0}
    assert _stats([0.12341, 0.5], 4, NEVER_SMALLER)["min"] == 0.1235
    assert _stats([0.12349, 0.5], 4, NEVER_LARGER)["min"] == 0.1234


def test_timestamps_share_one_utc_format(tmp_path: Path, case: CaseData) -> None:
    rules = case.config.pairing
    scenarios = list(reason_scenarios(rules).values()) + extra_scenarios()
    first, _ = write_twice(tmp_path, case, scenarios)
    rows = read_csv(first / PAIRS_FILE)
    events = read_json(first / EVENTS_FILE)["features"]
    accepted = read_json(first / SUMMARY_FILE)["accepted_pairs"]
    stamps = [row["scene_datetime"] for row in rows]
    stamps += [row["event_time"] for row in rows if row["event_time"]]
    stamps += [feature["properties"]["time"] for feature in events if feature["properties"]["time"]]
    stamps += [item["scene_datetime"] for item in accepted]
    assert any(row["event_time"] for row in rows)
    for stamp in stamps:
        assert stamp.endswith("Z"), stamp
        assert "+00:00" not in stamp
        assert dt.datetime.fromisoformat(stamp).utcoffset() == dt.timedelta(0)


def test_published_registry_is_consistent(case: CaseData) -> None:
    folder = Settings(_env_file=None).registry_dir
    rows = read_csv(folder / PAIRS_FILE)
    if not rows:
        pytest.skip("реестр пар не собран")
    assert_pairs_consistent(rows, case.config.pairing)
    summary = read_json(folder / SUMMARY_FILE)
    duplicates = sum(1 for row in rows if row["tile_duplicate_of"])
    assert summary["scene_candidates"] == len(rows)
    assert summary["tile_duplicates"] == duplicates
    assert sum(summary["pairs"].values()) == len(rows) - duplicates
