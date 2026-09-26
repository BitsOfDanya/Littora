from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import StrEnum

from app.case.config import PairingRules
from app.case.geometry import Footprint, MissingPositionError, build_footprint
from app.case.records import CaseRecord
from app.case.selection import Selection
from app.case.solar import daylight_shift_bound_hours, utc_day_shift_bound_hours
from app.earth.catalog import CatalogError, Scene, SceneCatalog
from app.earth.raster import QualityShares, RasterError


class PairDecision(StrEnum):
    ACCEPTED = "accepted"
    CANDIDATE = "candidate"
    NOT_EVALUATED = "not_evaluated"
    REJECTED = "rejected"
    NOT_USED = "not_used"


class PairReason(StrEnum):
    ACCEPTED = "accepted"
    NO_TARGET = "no_target"
    NO_DATE = "no_date"
    NO_POSITION = "no_position"
    BEFORE_MISSION = "before_mission"
    NOT_ACQUIRED = "not_acquired"
    NO_SCENE_IN_WINDOW = "no_scene_in_window"
    TIME_SHIFT = "time_shift"
    SYNC_UNCERTAIN = "sync_uncertain"
    PARTIAL_COVERAGE = "partial_coverage"
    TILE_CLOUD = "tile_cloud"
    QUALITY_UNVERIFIED = "quality_unverified"
    NODATA = "nodata"
    FOOTPRINT_CLOUD = "footprint_cloud"
    NO_WATER = "no_water"
    BRIGHT_WATER = "bright_water"
    READ_ERROR = "read_error"
    CATALOG_ERROR = "catalog_error"


PAIR_REASON_LABELS: dict[PairReason, str] = {
    PairReason.ACCEPTED: "пара принята",
    PairReason.NO_TARGET: "у события нет записей целевых величин",
    PairReason.NO_DATE: "у наблюдения нет даты",
    PairReason.NO_POSITION: "у наблюдения нет координат",
    PairReason.BEFORE_MISSION: "наблюдение раньше начала съёмки Sentinel-2",
    PairReason.NOT_ACQUIRED: (
        "район не снимается: сцен нет и в широком окне, вероятно открытый океан"
    ),
    PairReason.NO_SCENE_IN_WINDOW: "в окне поиска сцен нет",
    PairReason.TIME_SHIFT: "сдвиг по времени больше допустимого",
    PairReason.SYNC_UNCERTAIN: (
        "время учёта неизвестно, и граница сдвига по светлому времени или суткам больше порога"
    ),
    PairReason.PARTIAL_COVERAGE: "полоса наблюдения не целиком в кадре",
    PairReason.TILE_CLOUD: "облачность тайла выше порога",
    PairReason.QUALITY_UNVERIFIED: "маску качества не прочитать без ключей (requester pays)",
    PairReason.NODATA: "в полосе пиксели без данных",
    PairReason.FOOTPRINT_CLOUD: "облака или тени над полосой",
    PairReason.NO_WATER: "мало пригодной воды в полосе",
    PairReason.BRIGHT_WATER: "яркая вода: вероятны блики или пена",
    PairReason.READ_ERROR: "снимок не читается, пара не оценена",
    PairReason.CATALOG_ERROR: "каталог снимков недоступен, событие не оценено",
}

QualityReader = Callable[[Scene, Footprint], QualityShares]


class SyncKind(StrEnum):
    TIME_KNOWN = "time_known"
    DAYLIGHT_BOUNDED = "daylight_bounded"
    DAY_ONLY = "day_only"


@dataclass(frozen=True)
class EventInput:
    event_id: str
    source_id: str
    record: CaseRecord
    sample_ids: tuple[str, ...]
    target_keys: tuple[str, ...]


@dataclass(frozen=True)
class PairRow:
    event: EventInput
    scene: Scene
    decision: PairDecision
    reason: PairReason
    shift_hours: float | None
    shift_days: int
    uncertainty_hours: float
    drift_km_max: float
    sync: SyncKind = SyncKind.TIME_KNOWN
    coverage_fraction: float | None = None
    quality: QualityShares | None = None
    detail: str = ""


@dataclass(frozen=True)
class EventResult:
    event: EventInput
    footprint: Footprint | None
    decision: PairDecision
    reason: PairReason
    pairs: tuple[PairRow, ...] = field(default_factory=tuple)
    detail: str = ""

    @property
    def best(self) -> PairRow | None:
        duplicates = self.tile_duplicates
        passes = [row for row in self.pairs if row.scene.id not in duplicates]
        return min(passes, key=_event_rank) if passes else None

    @property
    def tile_duplicates(self) -> dict[str, str]:
        first: dict[str, str] = {}
        duplicates: dict[str, str] = {}
        for row in sorted(self.pairs, key=_pair_rank):
            key = pass_key(row.scene)
            if key in first:
                duplicates[row.scene.id] = first[key]
            else:
                first[key] = row.scene.id
        return duplicates


DECISION_ORDER = {
    PairDecision.ACCEPTED: 0,
    PairDecision.CANDIDATE: 1,
    PairDecision.NOT_EVALUATED: 2,
    PairDecision.REJECTED: 3,
}
PAIR_CHECKS = (
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
    PairReason.ACCEPTED,
)


def _pair_rank(row: PairRow) -> tuple:
    shift = abs(row.shift_hours) if row.shift_hours is not None else row.uncertainty_hours
    progress = PAIR_CHECKS.index(row.reason)
    return (
        DECISION_ORDER[row.decision],
        -progress,
        -(row.coverage_fraction or 0.0),
        shift,
        row.scene.cloud_cover or 0.0,
        row.scene.id,
    )


def _event_rank(row: PairRow) -> tuple:
    decision, progress, coverage, shift, *rest = _pair_rank(row)
    return (decision, progress, shift, coverage, *rest)


def pass_key(scene: Scene) -> str:
    if scene.relative_orbit is None:
        return scene.id
    return f"{scene.platform}_R{scene.relative_orbit:03d}_{scene.acquired_at:%Y%m%d}"


def build_event_inputs(selections: Iterable[Selection], record_type: str) -> list[EventInput]:
    by_event: dict[str, list[Selection]] = {}
    for selection in selections:
        by_event.setdefault(selection.record.event_id, []).append(selection)
    events = []
    for event_id, items in sorted(by_event.items()):
        density_rows = [s for s in items if s.record.record_type == record_type]
        accepted = [s for s in density_rows if s.accepted]
        representative = (accepted or density_rows or items)[0].record
        events.append(
            EventInput(
                event_id=event_id,
                source_id=representative.source_id,
                record=representative,
                sample_ids=tuple(s.record.sample_id for s in (accepted or density_rows)),
                target_keys=tuple(sorted({s.target_key for s in accepted if s.target_key})),
            )
        )
    return events


def _solar_position(record: CaseRecord) -> tuple[float, float] | None:
    if record.position is not None:
        return record.position
    segment = record.segment
    if segment is None:
        return None
    (lon_a, lat_a), (lon_b, lat_b) = segment
    return (lon_a + lon_b) / 2, (lat_a + lat_b) / 2


def _day_range(day: dt.date, days: int) -> tuple[dt.datetime, dt.datetime]:
    start = dt.datetime.combine(day - dt.timedelta(days=days), dt.time.min, tzinfo=dt.UTC)
    end = dt.datetime.combine(day + dt.timedelta(days=days), dt.time.max, tzinfo=dt.UTC)
    return start, end.replace(microsecond=0)


class PairingEngine:
    def __init__(
        self,
        rules: PairingRules,
        catalog: SceneCatalog,
        quality_reader: QualityReader,
    ) -> None:
        self.rules = rules
        self.catalog = catalog
        self.quality_reader = quality_reader

    def _collections(self, day: dt.date, window: int) -> list[str]:
        collections = [self.rules.landsat]
        if day + dt.timedelta(days=window) >= self.rules.sentinel2_start:
            collections[:0] = [self.rules.sentinel2, self.rules.sentinel2_fallback]
        return collections

    def _search(self, footprint: Footprint, day: dt.date, window: int) -> list[Scene]:
        start, end = _day_range(day, window)
        found = [
            (priority, scene)
            for priority, collection in enumerate(self._collections(day, window))
            for scene in self.catalog.search(collection, footprint.analysis, start, end)
        ]
        passes: dict[tuple[str, str, str], Scene] = {}
        for _, scene in sorted(found, key=lambda item: (item[0], item[1].id)):
            key = (scene.platform, scene.tile, scene.acquired_at.strftime("%Y%m%d%H%M"))
            passes.setdefault(key, scene)
        return sorted(passes.values(), key=lambda scene: (scene.acquired_at, scene.id))

    def _timing(
        self, event: EventInput, scene: Scene
    ) -> tuple[float | None, int, float, float, SyncKind]:
        record = event.record
        observed = record.observed_at
        day = record.date
        shift_days = (scene.acquired_at.date() - day).days
        if observed is not None:
            shift_hours = (scene.acquired_at - observed).total_seconds() / 3600
            uncertainty = 0.0
            span = abs(shift_hours)
            sync = SyncKind.TIME_KNOWN
        else:
            shift_hours = None
            bound = None
            position = _solar_position(record)
            if self.rules.daylight_bound and position is not None:
                lon, lat = position
                bound = daylight_shift_bound_hours(scene.acquired_at, day, lat, lon)
            sync = SyncKind.DAYLIGHT_BOUNDED
            if bound is None:
                bound = utc_day_shift_bound_hours(scene.acquired_at, day)
                sync = SyncKind.DAY_ONLY
            uncertainty = bound
            span = bound
        drift = self.rules.drift_speed_ms * span * 3.6
        return shift_hours, shift_days, uncertainty, drift, sync

    def evaluate(self, event: EventInput, footprint: Footprint, scene: Scene) -> PairRow:
        shift_hours, shift_days, uncertainty, drift, sync = self._timing(event, scene)
        coverage = footprint.covered_by(scene.geometry)

        def row(decision: PairDecision, reason: PairReason, **extra) -> PairRow:
            return PairRow(
                event,
                scene,
                decision,
                reason,
                shift_hours,
                shift_days,
                uncertainty,
                drift,
                sync,
                coverage,
                **extra,
            )

        rules = self.rules
        limit = rules.max_time_shift_hours
        if shift_hours is not None and abs(shift_hours) > limit:
            return row(PairDecision.REJECTED, PairReason.TIME_SHIFT)
        if shift_hours is None and abs(shift_days) > rules.unknown_time_max_days:
            return row(PairDecision.REJECTED, PairReason.TIME_SHIFT)
        if shift_hours is None and uncertainty > limit:
            return row(PairDecision.REJECTED, PairReason.SYNC_UNCERTAIN)
        if coverage < 1.0:
            return row(PairDecision.REJECTED, PairReason.PARTIAL_COVERAGE)
        if scene.cloud_cover is not None and scene.cloud_cover > rules.max_tile_cloud:
            return row(PairDecision.REJECTED, PairReason.TILE_CLOUD)
        if not scene.is_sentinel2 or "scl" not in scene.assets:
            return row(PairDecision.CANDIDATE, PairReason.QUALITY_UNVERIFIED)
        try:
            quality = self.quality_reader(scene, footprint)
        except RasterError as error:
            return row(PairDecision.NOT_EVALUATED, PairReason.READ_ERROR, detail=str(error))
        if quality.nodata > rules.max_footprint_nodata:
            return row(PairDecision.REJECTED, PairReason.NODATA, quality=quality)
        if quality.cloud_or_shadow > rules.max_footprint_cloud:
            return row(PairDecision.REJECTED, PairReason.FOOTPRINT_CLOUD, quality=quality)
        if quality.water < rules.min_footprint_water:
            return row(PairDecision.REJECTED, PairReason.NO_WATER, quality=quality)
        if quality.bright_water is not None and quality.bright_water > rules.max_bright_water:
            return row(PairDecision.REJECTED, PairReason.BRIGHT_WATER, quality=quality)
        return row(PairDecision.ACCEPTED, PairReason.ACCEPTED, quality=quality)

    def footprint(self, record: CaseRecord) -> Footprint | None:
        rules = self.rules
        try:
            return build_footprint(record, rules.unknown_extent_buffer_m, rules.min_strip_width_m)
        except MissingPositionError:
            return None

    def pair_event(self, event: EventInput) -> EventResult:
        rules = self.rules
        footprint = self.footprint(event.record)
        if not event.target_keys:
            return EventResult(event, footprint, PairDecision.NOT_USED, PairReason.NO_TARGET)
        if footprint is None:
            return EventResult(event, None, PairDecision.REJECTED, PairReason.NO_POSITION)
        day = event.record.date
        if day is None:
            return EventResult(event, footprint, PairDecision.REJECTED, PairReason.NO_DATE)
        try:
            scenes = self._search(footprint, day, rules.window_days)
            if not scenes:
                wide = self._search(footprint, day, rules.wide_window_days)
                if wide:
                    reason = PairReason.NO_SCENE_IN_WINDOW
                elif day < rules.sentinel2_start:
                    reason = PairReason.BEFORE_MISSION
                else:
                    reason = PairReason.NOT_ACQUIRED
                return EventResult(event, footprint, PairDecision.REJECTED, reason)
        except CatalogError as error:
            return EventResult(
                event,
                footprint,
                PairDecision.NOT_EVALUATED,
                PairReason.CATALOG_ERROR,
                detail=str(error),
            )
        rows = tuple(sorted((self.evaluate(event, footprint, s) for s in scenes), key=_pair_rank))
        best = rows[0]
        return EventResult(event, footprint, best.decision, best.reason, rows)

    def pair_events(self, events: list[EventInput], workers: int = 8) -> list[EventResult]:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            return list(pool.map(self.pair_event, events))
