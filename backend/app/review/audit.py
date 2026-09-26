from __future__ import annotations

import csv
import threading
from pathlib import Path
from typing import Any

from app.review.labels import ReviewLabel, ReviewSource

AUDIT_FILE = Path("validation") / "black_sea_zone_audit.csv"
AUDIT_REVIEWER = "team"
PIXEL_KM2 = 1e-4
REQUIRED = (
    "zone_id",
    "aoi",
    "scene_id",
    "date",
    "lon",
    "lat",
    "pixels",
    "probability_max",
    "class",
    "confidence",
)
LABELS = {label.value for label in ReviewLabel}


def audit_record(row: dict[str, str]) -> dict[str, Any] | None:
    try:
        lon, lat = round(float(row["lon"]), 6), round(float(row["lat"]), 6)
        confidence = int(row["confidence"])
        pixels = int(row["pixels"])
        probability = float(row["probability_max"])
    except (KeyError, TypeError, ValueError):
        return None
    label = (row.get("class") or "").strip()
    if label not in LABELS or not 1 <= confidence <= 3 or not row.get("zone_id"):
        return None
    return {
        "id": f"audit-{row['scene_id']}-{row['zone_id']}",
        "source": ReviewSource.AUDIT.value,
        "created_at": None,
        "analysis_id": None,
        "zone_id": row["zone_id"],
        "reviewer": (row.get("reviewer") or "").strip() or AUDIT_REVIEWER,
        "label": label,
        "confidence": confidence,
        "comment": (row.get("comment") or "").strip() or None,
        "aoi_id": row.get("aoi") or None,
        "aoi_name": None,
        "scene_id": row.get("scene_id") or None,
        "acquired_at": None,
        "date": row.get("date") or None,
        "model_fingerprint": None,
        "threshold": None,
        "probability_max": probability,
        "probability_mean": None,
        "pixels": pixels,
        "area_km2": round(pixels * PIXEL_KM2, 4),
        "centroid": [lon, lat],
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
    }


class AuditSource:
    def __init__(self, path: Path | None) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._cache: tuple[float, list[dict[str, Any]]] | None = None

    @property
    def available(self) -> bool:
        return self.path is not None and self.path.is_file()

    def records(self) -> list[dict[str, Any]]:
        if not self.available or self.path is None:
            return []
        stamp = self.path.stat().st_mtime
        with self._lock:
            if self._cache and self._cache[0] == stamp:
                return self._cache[1]
            with self.path.open(encoding="utf-8-sig", newline="") as handle:
                rows = [audit_record(row) for row in csv.DictReader(handle)]
            records = [row for row in rows if row is not None]
            self._cache = (stamp, records)
            return records
