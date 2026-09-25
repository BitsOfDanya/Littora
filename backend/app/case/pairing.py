from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import StrEnum

from app.case.config import PairingRules
from app.case.geometry import Footprint, build_footprint
from app.case.records import CaseRecord
from app.case.selection import Selection
from app.earth.catalog import CatalogError, Scene, SceneCatalog
from app.earth.raster import QualityShares, RasterError


class PairDecision(StrEnum):
    ACCEPTED = "accepted"
    CANDIDATE = "candidate"
    REJECTED = "rejected"
    NOT_USED = "not_used"


class PairReason(StrEnum):
    ACCEPTED = "accepted"
    NO_TARGET = "no_target"
    BEFORE_MISSION = "before_mission"
    NOT_ACQUIRED = "not_acquired"
    NO_SCENE_IN_WINDOW = "no_scene_in_window"
    TIME_SHIFT = "time_shift"
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
    PairReason.BEFORE_MISSION: "наблюдение раньше начала съёмки Sentinel-2",
    PairReason.NOT_ACQUIRED: (
        "район не снимается: сцен нет и в широком окне, вероятно открытый океан"
    ),
    PairReason.NO_SCENE_IN_WINDOW: "в окне поиска сцен нет",
    PairReason.TIME_SHIFT: "сдвиг по времени больше допустимого",
    PairReason.PARTIAL_COVERAGE: "полоса наблюдения не целиком в кадре",
    PairReason.TILE_CLOUD: "облачность тайла выше порога",
    PairReason.QUALITY_UNVERIFIED: "маску качества не прочитать без ключей (requester pays)",
    PairReason.NODATA: "в полосе пиксели без данных",
    PairReason.FOOTPRINT_CLOUD: "облака или тени над полосой",
    PairReason.NO_WATER: "мало пригодной воды в полосе",
    PairReason.BRIGHT_WATER: "яркая вода: вероятны блики или пена",
    PairReason.READ_ERROR: "снимок не читается",
    PairReason.CATALOG_ERROR: "каталог снимков недоступен",
}

QualityReader = Callable[[Scene, Footprint], QualityShares]


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
        ranked = sorted(self.pairs, key=_pair_rank)
        return ranked[0] if ranked else None


def _pair_rank(row: PairRow) -> tuple:
    order = {PairDecision.ACCEPTED: 0, PairDecision.CANDIDATE: 1, PairDecision.REJECTED: 2}
    shift = abs(row.shift_hours) if row.shift_hours is not None else abs(row.shift_days) * 24
    return (order[row.decision], shift, row.scene.cloud_cover or 0.0, row.scene.id)


def build_event_inputs(selections: Iterable[Selection]) -> list[EventInput]:
    by_event: dict[str, list[Selection]] = {}
    for selection in selections:
        by_event.setdefault(selection.record.event_id, []).append(selection)
    events = []
    for event_id, items in sorted(by_event.items()):
        density_rows = [s for s in items if s.record.record_type == "transect_density"]
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
            collections.insert(0, self.rules.sentinel2)
        return collections

    def _search(self, footprint: Footprint, day: dt.date, window: int) -> list[Scene]:
        start, end = _day_range(day, window)
        scenes: list[Scene] = []
        for collection in self._collections(day, window):
            scenes.extend(self.catalog.search(collection, footprint.analysis, start, end))
        return scenes

    def _timing(self, event: EventInput, scene: Scene) -> tuple[float | None, int, float, float]:
        observed = event.record.observed_at
        day = event.record.date
        shift_days = (scene.acquired_at.date() - day).days if day else 0
        if observed is not None:
            shift_hours = (scene.acquired_at - observed).total_seconds() / 3600
            uncertainty = 0.0
            span = abs(shift_hours)
        else:
            shift_hours = None
            uncertainty = self.rules.unknown_time_uncertainty_hours
            span = abs(shift_days) * 24 + uncertainty
        drift = self.rules.drift_speed_ms * span * 3.6
        return shift_hours, shift_days, uncertainty, drift

    def evaluate(self, event: EventInput, footprint: Footprint, scene: Scene) -> PairRow:
        shift_hours, shift_days, uncertainty, drift = self._timing(event, scene)

        def row(decision: PairDecision, reason: PairReason, **extra) -> PairRow:
            return PairRow(
                event, scene, decision, reason, shift_hours, shift_days, uncertainty, drift, **extra
            )

        if shift_hours is not None and abs(shift_hours) > self.rules.max_time_shift_hours:
            return row(PairDecision.REJECTED, PairReason.TIME_SHIFT)
        if shift_hours is None and abs(shift_days) > self.rules.unknown_time_max_days:
            return row(PairDecision.REJECTED, PairReason.TIME_SHIFT)
        if not scene.geometry.contains(footprint.analysis):
            return row(PairDecision.REJECTED, PairReason.PARTIAL_COVERAGE)
        if scene.cloud_cover is not None and scene.cloud_cover > self.rules.max_tile_cloud:
            return row(PairDecision.REJECTED, PairReason.TILE_CLOUD)
        if not scene.is_sentinel2 or "scl" not in scene.assets:
            return row(PairDecision.CANDIDATE, PairReason.QUALITY_UNVERIFIED)
        try:
            quality = self.quality_reader(scene, footprint)
        except RasterError as error:
            return row(PairDecision.REJECTED, PairReason.READ_ERROR, detail=str(error))
        rules = self.rules
        if quality.nodata > rules.max_footprint_nodata:
            return row(PairDecision.REJECTED, PairReason.NODATA, quality=quality)
        if quality.cloud_or_shadow > rules.max_footprint_cloud:
            return row(PairDecision.REJECTED, PairReason.FOOTPRINT_CLOUD, quality=quality)
        if quality.water < rules.min_footprint_water:
            return row(PairDecision.REJECTED, PairReason.NO_WATER, quality=quality)
        if quality.bright_water is not None and quality.bright_water > rules.max_bright_water:
            return row(PairDecision.REJECTED, PairReason.BRIGHT_WATER, quality=quality)
        return row(PairDecision.ACCEPTED, PairReason.ACCEPTED, quality=quality)

    def pair_event(self, event: EventInput) -> EventResult:
        rules = self.rules
        footprint = build_footprint(event.record, rules.point_buffer_m, rules.min_strip_width_m)
        if not event.target_keys:
            return EventResult(event, footprint, PairDecision.NOT_USED, PairReason.NO_TARGET)
        day = event.record.date
        if day is None:
            return EventResult(
                event, footprint, PairDecision.REJECTED, PairReason.NO_SCENE_IN_WINDOW
            )
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
                event, footprint, PairDecision.REJECTED, PairReason.CATALOG_ERROR, detail=str(error)
            )
        rows = tuple(sorted((self.evaluate(event, footprint, s) for s in scenes), key=_pair_rank))
        best = rows[0]
        return EventResult(event, footprint, best.decision, best.reason, rows)

    def pair_events(self, events: list[EventInput], workers: int = 8) -> list[EventResult]:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            return list(pool.map(self.pair_event, events))
