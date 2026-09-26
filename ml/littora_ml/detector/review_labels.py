from __future__ import annotations

import csv
import json
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from affine import Affine
from rasterio.features import rasterize
from rasterio.transform import rowcol
from rasterio.warp import transform_geom
from shapely import wkt
from shapely.geometry import Point, mapping, shape
from shapely.geometry.base import BaseGeometry

IGNORE = 0
POSITIVE = "likely_debris"
UNDECIDED = "unknown"
LABEL_CODES: dict[str, int] = {
    POSITIVE: 1,
    "ship": 2,
    "structure": 3,
    "wake": 4,
    "foam": 5,
    "slick": 6,
    "plume": 7,
    "land_edge": 8,
    "cloud_edge": 9,
    "water": 10,
}
KNOWN_LABELS = {*LABEL_CODES, UNDECIDED}
LONLAT = "EPSG:4326"


@dataclass(frozen=True)
class ZoneLabel:
    source: str
    anchor: str
    zone_id: str
    scene_id: str | None
    label: str
    confidence: int
    reviewers: int
    geometry: BaseGeometry

    @property
    def code(self) -> int:
        return LABEL_CODES[self.label]


@dataclass(frozen=True)
class Conflict:
    source: str
    anchor: str
    zone_id: str
    labels: tuple[str, ...]


@dataclass(frozen=True)
class Grid:
    transform: Affine
    crs: str
    height: int
    width: int

    @classmethod
    def from_raster(cls, path: Path) -> Grid:
        with rasterio.open(path) as dataset:
            return cls(dataset.transform, dataset.crs.to_string(), dataset.height, dataset.width)

    @property
    def shape(self) -> tuple[int, int]:
        return self.height, self.width


@dataclass(frozen=True)
class ReviewMasks:
    labels: np.ndarray
    confidence: np.ndarray
    zones: int

    @property
    def positive(self) -> np.ndarray:
        return self.labels == LABEL_CODES[POSITIVE]

    @property
    def hard_negative(self) -> np.ndarray:
        return self.labels > LABEL_CODES[POSITIVE]

    @property
    def known(self) -> np.ndarray:
        return self.labels != IGNORE

    def counts(self) -> dict[str, int]:
        values = np.bincount(self.labels.ravel(), minlength=max(LABEL_CODES.values()) + 1)
        return {label: int(values[code]) for label, code in LABEL_CODES.items() if values[code]}


def _geometry(record: dict[str, Any]) -> BaseGeometry | None:
    geometry = record.get("geometry")
    if isinstance(geometry, dict) and geometry.get("type"):
        return shape(geometry)
    if record.get("geometry_wkt"):
        return wkt.loads(record["geometry_wkt"])
    for lon_key, lat_key in (("longitude", "latitude"), ("lon", "lat")):
        if record.get(lon_key) not in (None, "") and record.get(lat_key) not in (None, ""):
            return Point(float(record[lon_key]), float(record[lat_key]))
    return None


def _normalize(record: dict[str, Any], default_source: str) -> dict[str, Any] | None:
    label = (record.get("label") or record.get("class") or "").strip()
    geometry = _geometry(record)
    if label not in KNOWN_LABELS or geometry is None or geometry.is_empty:
        return None
    try:
        confidence = int(record.get("confidence") or 0)
    except (TypeError, ValueError):
        return None
    source = record.get("source") or default_source
    analysis_id = record.get("analysis_id") or None
    scene_id = record.get("scene_id") or None
    zone_id = record.get("audit_zone_id") or record.get("zone_id")
    if not zone_id:
        return None
    return {
        "source": source,
        "anchor": analysis_id or scene_id or "",
        "zone_id": zone_id,
        "scene_id": scene_id,
        "reviewer": (record.get("reviewer") or "").strip().casefold(),
        "label": label,
        "confidence": confidence,
        "created_at": record.get("created_at") or "",
        "geometry": geometry,
    }


def _jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _csv(path: Path) -> tuple[list[dict[str, Any]], str]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        audit = "class" in (reader.fieldnames or [])
    return rows, "audit" if audit else "ui"


def read_reviews(path: Path) -> list[dict[str, Any]]:
    paths = sorted(path.glob("*.jsonl")) if path.is_dir() else [path]
    records: list[dict[str, Any]] = []
    for item in paths:
        suffix = item.suffix.lower()
        default_source = "ui"
        if suffix == ".jsonl":
            rows = _jsonl(item)
        elif suffix in {".geojson", ".json"}:
            collection = json.loads(item.read_text(encoding="utf-8"))
            rows = [
                {**feature.get("properties", {}), "geometry": feature.get("geometry")}
                for feature in collection.get("features", [])
            ]
        elif suffix == ".csv":
            rows, default_source = _csv(item)
        else:
            raise ValueError(f"unsupported review file: {item.name}")
        records.extend(
            record for row in rows if (record := _normalize(row, default_source)) is not None
        )
    return records


def resolve(
    records: Iterable[dict[str, Any]], min_confidence: int = 2
) -> tuple[list[ZoneLabel], list[Conflict]]:
    effective: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for record in sorted(records, key=lambda item: item["created_at"]):
        key = (record["source"], record["anchor"], record["zone_id"], record["reviewer"])
        effective[key] = record
    zones: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for (source, anchor, zone_id, _), record in effective.items():
        zones[(source, anchor, zone_id)].append(record)
    labels, conflicts = [], []
    for (source, anchor, zone_id), reviews in sorted(zones.items()):
        names = tuple(sorted({review["label"] for review in reviews}))
        if len(names) > 1:
            conflicts.append(Conflict(source, anchor, zone_id, names))
            continue
        confidence = min(review["confidence"] for review in reviews)
        if names[0] == UNDECIDED or confidence < min_confidence:
            continue
        labels.append(
            ZoneLabel(
                source,
                anchor,
                zone_id,
                reviews[-1]["scene_id"],
                names[0],
                confidence,
                len(reviews),
                reviews[-1]["geometry"],
            )
        )
    return labels, conflicts


def _point_window(point: Point, grid: Grid, radius: int) -> tuple[slice, slice] | None:
    row, col = rowcol(grid.transform, point.x, point.y)
    if not (0 <= row < grid.height and 0 <= col < grid.width):
        return None
    return (
        slice(max(row - radius, 0), min(row + radius + 1, grid.height)),
        slice(max(col - radius, 0), min(col + radius + 1, grid.width)),
    )


def _footprint(zone: ZoneLabel, grid: Grid, point_radius: int) -> np.ndarray:
    projected = shape(transform_geom(LONLAT, grid.crs, mapping(zone.geometry)))
    inside = np.zeros(grid.shape, dtype=bool)
    if isinstance(projected, Point):
        window = _point_window(projected, grid, point_radius)
        if window is not None:
            inside[window] = True
        return inside
    return rasterize(
        [(projected, 1)],
        out_shape=grid.shape,
        transform=grid.transform,
        fill=0,
        dtype="uint8",
    ).astype(bool)


def rasterize_reviews(
    zones: Iterable[ZoneLabel],
    grid: Grid,
    scene_id: str | None = None,
    point_radius: int = 0,
) -> ReviewMasks:
    labels = np.full(grid.shape, IGNORE, dtype=np.uint8)
    confidence = np.zeros(grid.shape, dtype=np.uint8)
    positive = np.zeros(grid.shape, dtype=bool)
    negative = np.zeros(grid.shape, dtype=bool)
    burned = 0
    selected = [zone for zone in zones if scene_id is None or zone.scene_id == scene_id]
    for zone in sorted(selected, key=lambda item: item.confidence):
        inside = _footprint(zone, grid, point_radius)
        if not inside.any():
            continue
        burned += 1
        labels[inside] = zone.code
        confidence[inside] = zone.confidence
        if zone.label == POSITIVE:
            positive |= inside
        else:
            negative |= inside
    contested = positive & negative
    labels[contested] = IGNORE
    confidence[contested] = 0
    return ReviewMasks(labels, confidence, burned)


def review_masks(
    path: Path,
    grid: Grid,
    scene_id: str | None = None,
    min_confidence: int = 2,
    point_radius: int = 0,
) -> tuple[ReviewMasks, list[Conflict]]:
    zones, conflicts = resolve(read_reviews(path), min_confidence)
    return rasterize_reviews(zones, grid, scene_id, point_radius), conflicts
