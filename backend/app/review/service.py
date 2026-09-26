from __future__ import annotations

import datetime as dt
import secrets
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from shapely.geometry import Point, shape
from shapely.geometry.base import BaseGeometry

from app.core.errors import NotFoundError
from app.review.audit import AuditSource
from app.review.labels import LABEL_TITLES, SOURCE_TITLES, ReviewLabel, ReviewSource
from app.review.stats import by_zone, consensus, latest, per_aoi, reviewer_key, statistics
from app.review.store import ReviewStore

REVIEWS_DIR = "reviews"
MATCH_TOLERANCE_DEG = 0.00015


@dataclass(frozen=True)
class ReviewFilters:
    source: ReviewSource | None = None
    analysis_id: str | None = None
    aoi_id: str | None = None
    scene_id: str | None = None
    label: ReviewLabel | None = None
    reviewer: str | None = None
    history: bool = False


def _zone_ids(analysis: dict[str, Any]) -> dict[str, dict[str, Any]]:
    zones = analysis["detection"].get("zones") or []
    return {zone.get("id", f"zone-{index}"): zone for index, zone in enumerate(zones, start=1)}


def _now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def present(record: dict[str, Any]) -> dict[str, Any]:
    source = ReviewSource(record["source"])
    return {
        **record,
        "label_title": LABEL_TITLES[ReviewLabel(record["label"])],
        "source_title": SOURCE_TITLES[source],
    }


def _newest_first(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(records, key=lambda record: record.get("created_at") or "", reverse=True)


class ReviewService:
    def __init__(self, folder: Path, audit_path: Path | None = None) -> None:
        self.store = ReviewStore(folder)
        self.audit = AuditSource(audit_path)

    def add(self, analysis: dict[str, Any], zone_id: str, review: dict[str, Any]) -> dict[str, Any]:
        zone = _zone_ids(analysis).get(zone_id)
        if zone is None:
            raise NotFoundError("Нет такой зоны в этом анализе")
        scene = analysis.get("scene") or {}
        request = analysis.get("request") or {}
        acquired = scene.get("acquired_at")
        models = analysis.get("models") or {}
        record = {
            "id": secrets.token_hex(6),
            "source": ReviewSource.UI.value,
            "created_at": _now(),
            "analysis_id": analysis["id"],
            "zone_id": zone_id,
            "reviewer": review.get("reviewer"),
            "label": ReviewLabel(review["label"]).value,
            "confidence": int(review["confidence"]),
            "comment": review.get("comment"),
            "aoi_id": request.get("aoi_id"),
            "aoi_name": request.get("aoi_name"),
            "scene_id": scene.get("id"),
            "acquired_at": acquired,
            "date": acquired[:10] if acquired else request.get("date"),
            "model_fingerprint": models.get("detector") or analysis["detection"].get("model"),
            "threshold": analysis["detection"].get("threshold"),
            "probability_max": zone.get("probability_max"),
            "probability_mean": zone.get("probability_mean"),
            "pixels": zone.get("pixels"),
            "area_km2": zone.get("area_km2"),
            "centroid": zone.get("centroid"),
            "geometry": zone.get("geometry"),
        }
        self.store.append(record)
        return present(record)

    def audit_matches(self, analysis: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
        scene = (analysis.get("scene") or {}).get("id")
        rows = [row for row in self.audit.records() if scene and row["scene_id"] == scene]
        if not rows:
            return {}
        shapes: list[tuple[str, BaseGeometry]] = [
            (zone_id, shape(zone["geometry"]))
            for zone_id, zone in _zone_ids(analysis).items()
            if zone.get("geometry")
        ]
        matches: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            point = Point(row["centroid"])
            near = [
                (geometry.distance(point), zone_id)
                for zone_id, geometry in shapes
                if geometry.distance(point) <= MATCH_TOLERANCE_DEG
            ]
            if near:
                zone_id = min(near)[1]
                matches.setdefault(zone_id, []).append(
                    present({**row, "audit_zone_id": row["zone_id"], "zone_id": zone_id})
                )
        return matches

    def for_analysis(self, analysis: dict[str, Any]) -> dict[str, Any]:
        zones = _zone_ids(analysis)
        history = [
            record for record in self.store.read(analysis["id"]) if record["zone_id"] in zones
        ]
        effective = latest(history)
        grouped = {key[2]: group for key, group in by_zone(effective).items()}
        counts = Counter(record["zone_id"] for record in history)
        audit = self.audit_matches(analysis)
        audit_effective = [row for rows in audit.values() for row in rows]
        items = []
        for zone_id in zones:
            reviews = grouped.get(zone_id, [])
            if not reviews and zone_id not in audit:
                continue
            items.append(
                {
                    "zone_id": zone_id,
                    "consensus": consensus(reviews),
                    "reviews": [present(record) for record in _newest_first(reviews)],
                    "history": counts.get(zone_id, 0),
                    "audit": audit.get(zone_id, []),
                }
            )
        return {
            "analysis_id": analysis["id"],
            "zones_total": len(zones),
            "zones": items,
            "items": [present(record) for record in _newest_first(history)],
            "summary": {"zones_total": len(zones), **statistics(effective)},
            "audit": {
                "source": ReviewSource.AUDIT.value,
                "title": SOURCE_TITLES[ReviewSource.AUDIT],
                "available": self.audit.available,
                "matched": len(audit_effective),
                **statistics([{**row, "zone_id": row["audit_zone_id"]} for row in audit_effective]),
            },
        }

    def _source_records(self, source: ReviewSource, history: bool) -> list[dict[str, Any]]:
        if source is ReviewSource.AUDIT:
            return self.audit.records()
        records = self.store.read_all()
        return records if history else latest(records)

    @staticmethod
    def _matches(record: dict[str, Any], filters: ReviewFilters, with_label: bool) -> bool:
        if filters.analysis_id and record.get("analysis_id") != filters.analysis_id:
            return False
        if filters.aoi_id and record.get("aoi_id") != filters.aoi_id:
            return False
        if filters.scene_id and record.get("scene_id") != filters.scene_id:
            return False
        if filters.reviewer and reviewer_key(record.get("reviewer")) != reviewer_key(
            filters.reviewer
        ):
            return False
        return not (with_label and filters.label and record["label"] != filters.label.value)

    def _sources(self, filters: ReviewFilters) -> list[ReviewSource]:
        return [filters.source] if filters.source else list(ReviewSource)

    def records(self, filters: ReviewFilters) -> list[dict[str, Any]]:
        items = [
            record
            for source in self._sources(filters)
            for record in self._source_records(source, filters.history)
            if self._matches(record, filters, with_label=True)
        ]
        return [present(record) for record in _newest_first(items)]

    def summary(self, filters: ReviewFilters) -> dict[str, Any]:
        sources = []
        for source in self._sources(filters):
            effective = [
                record
                for record in self._source_records(source, history=False)
                if self._matches(record, filters, with_label=False)
            ]
            sources.append(
                {
                    "source": source.value,
                    "title": SOURCE_TITLES[source],
                    "available": source is ReviewSource.UI or self.audit.available,
                    **statistics(effective),
                    "by_aoi": per_aoi(effective),
                }
            )
        return {"sources": sources}
