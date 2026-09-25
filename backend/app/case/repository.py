from __future__ import annotations

import datetime as dt
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from shapely.geometry import LineString, Point, box, mapping

from app.analysis.statuses import ValueKind
from app.case.concentration import UNIT
from app.case.data import CaseData, load_case_data
from app.case.registry import (
    EVENTS_FILE,
    PAIRS_FILE,
    SUMMARY_FILE,
    read_csv,
    read_json,
)
from app.case.selection import Selection
from app.core.config import Settings


@dataclass(frozen=True)
class ObservationFilter:
    target: str | None = None
    decision: str | None = None
    source: str | None = None
    date_from: dt.date | None = None
    date_to: dt.date | None = None
    bbox: tuple[float, float, float, float] | None = None


def _mtime(path: Path) -> float:
    return path.stat().st_mtime if path.exists() else 0.0


class CaseRepository:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._lock = threading.Lock()
        self._data: CaseData | None = None
        self._data_stamp: tuple[float, float] | None = None
        self._registry: dict[str, Any] = {}
        self._registry_stamp: tuple[float, ...] | None = None

    def data(self) -> CaseData:
        config_path = self.settings.case_config
        with self._lock:
            csv_guess = self._data.csv_path if self._data else self.settings.data_dir
            stamp = (_mtime(config_path), _mtime(csv_guess))
            if self._data is None or stamp != self._data_stamp:
                self._data = load_case_data(config_path, self.settings.data_dir)
                self._data_stamp = (_mtime(config_path), _mtime(self._data.csv_path))
            return self._data

    def _registry_files(self) -> dict[str, Path]:
        folder = self.settings.registry_dir
        return {name: folder / name for name in (SUMMARY_FILE, PAIRS_FILE, EVENTS_FILE)}

    def registry(self) -> dict[str, Any]:
        files = self._registry_files()
        stamp = tuple(_mtime(path) for path in files.values())
        with self._lock:
            if stamp != self._registry_stamp:
                events = read_json(files[EVENTS_FILE]) or {
                    "type": "FeatureCollection",
                    "features": [],
                }
                self._registry = {
                    "summary": read_json(files[SUMMARY_FILE]),
                    "pairs": read_csv(files[PAIRS_FILE]),
                    "events": events,
                    "event_index": {
                        feature["properties"]["event_id"]: feature["properties"]
                        for feature in events.get("features", [])
                    },
                }
                self._registry_stamp = stamp
            return self._registry

    def targets(self) -> list[dict[str, Any]]:
        data = self.data()
        accepted = [s for s in data.selections if s.accepted]
        return [
            {
                "key": target.key,
                "primary": target.primary,
                "title": target.title,
                "material": target.material,
                "size_class": target.size_class,
                "unit": target.unit,
                "profiles": list(target.profiles),
                "target_scope": list(target.target_scope),
                "rationale": target.rationale,
                "records": sum(1 for s in accepted if s.target_key == target.key),
                "events": len({s.record.event_id for s in accepted if s.target_key == target.key}),
            }
            for target in data.config.targets
        ]

    def _geometry(self, selection: Selection) -> dict[str, Any] | None:
        record = selection.record
        if record.segment is not None:
            return mapping(LineString(record.segment))
        if record.position is not None:
            return mapping(Point(record.position))
        return None

    def observation_feature(self, selection: Selection) -> dict[str, Any] | None:
        geometry = self._geometry(selection)
        if geometry is None:
            return None
        record, check = selection.record, selection.check
        event = self.registry()["event_index"].get(record.event_id, {})
        return {
            "type": "Feature",
            "id": record.sample_id,
            "geometry": geometry,
            "properties": {
                "sample_id": record.sample_id,
                "event_id": record.event_id,
                "source_id": record.source_id,
                "source_short": record.text("source_short"),
                "source_doi": record.text("source_doi"),
                "source_license": record.text("source_license"),
                "region": record.text("region"),
                "sea_area": record.text("sea_area"),
                "sampling_method": record.text("sampling_method"),
                "platform": record.text("platform"),
                "measurement_profile": record.profile,
                "target_scope": record.scope,
                "material": record.text("material"),
                "size_class": record.text("size_class"),
                "date": record.text("date_utc"),
                "time_start": record.text("time_start_utc") or None,
                "time_end": record.text("time_end_utc") or None,
                "position_role": record.text("position_role"),
                "value_kind": ValueKind.MEASUREMENT.value,
                "concentration": check.published,
                "recomputed": check.recomputed,
                "unit": UNIT,
                "items": record.items,
                "area_km2": record.area_km2,
                "check": check.status.value,
                "check_label": check.label,
                "target_key": selection.target_key,
                "decision": "accepted" if selection.accepted else "rejected",
                "reason_code": selection.reason.value,
                "reason": selection.label,
                "quality_flags": list(record.flags),
                "pair_decision": event.get("decision"),
                "pair_reason": event.get("reason"),
                "pair_scene_id": event.get("best_scene_id"),
            },
        }

    def observations(self, filters: ObservationFilter) -> list[dict[str, Any]]:
        data = self.data()
        area = box(*filters.bbox) if filters.bbox else None
        features = []
        for selection in data.selections:
            record = selection.record
            if record.record_type != data.config.selection.record_type:
                continue
            if filters.target and selection.target_key != filters.target:
                continue
            if filters.decision == "accepted" and not selection.accepted:
                continue
            if filters.decision == "rejected" and selection.accepted:
                continue
            if filters.source and record.source_id != filters.source:
                continue
            day = record.date
            if filters.date_from and (day is None or day < filters.date_from):
                continue
            if filters.date_to and (day is None or day > filters.date_to):
                continue
            feature = self.observation_feature(selection)
            if feature is None:
                continue
            if area is not None:
                position = record.position
                if position is None or not area.intersects(Point(position)):
                    continue
            features.append(feature)
        return features
