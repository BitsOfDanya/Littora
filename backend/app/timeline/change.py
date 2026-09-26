from __future__ import annotations

import math
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.errors import NotGeoreferencedWarning, RasterioIOError
from shapely import STRtree, contains_xy
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform

from app.analysis.statuses import ResultStatus
from app.drift.geo import METERS_PER_DEGREE
from app.earth.raster import MASK_COLORS

TOLERANCE_M = 20.0
OBSERVED_SHARE = 0.5
COMPARABLE = frozenset({ResultStatus.DETECTED.value, ResultStatus.NOT_DETECTED.value})
METHOD = (
    f"перекрытие контуров зон с допуском {TOLERANCE_M:.0f} м; мусор дрейфует, поэтому "
    "«на том же месте» не обязательно тот же объект, а «исчезла» — не значит убрана"
)
SEEN_NOTE = (
    "зона без пары, место которой на другой дате закрыто облаками или тенью, без данных "
    f"или вне снимка (открытой воды по SCL меньше {OBSERVED_SHARE:.0%} площади), "
    "считается ненаблюдавшейся, а не исчезнувшей или новой"
)
BLIND_NOTE = (
    "маски SCL нет хотя бы у одной даты — зоны под облаками и вне снимка "
    "не отделены от исчезнувших и новых"
)


class Coverage:
    def __init__(self, rgba: np.ndarray, corners: list[list[float]]) -> None:
        bright = np.array(MASK_COLORS["bright_water"], dtype=np.uint8)
        self.seen = (rgba[..., 3] == 0) | np.all(rgba == bright, axis=-1)
        self.rows, self.cols = self.seen.shape
        origin, right, _, down = (np.asarray(corner, dtype=float) for corner in corners)
        self.origin = origin
        self.axes = np.column_stack([right - origin, down - origin])
        self.inverse = np.linalg.inv(self.axes)

    @classmethod
    def read(cls, path: Path, corners: list[list[float]]) -> Coverage | None:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", NotGeoreferencedWarning)
                with rasterio.open(path) as source:
                    pixels = source.read()
        except (RasterioIOError, OSError):
            return None
        if pixels.shape[0] != 4:
            return None
        try:
            return cls(np.moveaxis(pixels, 0, -1), corners)
        except np.linalg.LinAlgError:
            return None

    def _cells(self, xs: np.ndarray, ys: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        u, v = self.inverse @ np.vstack([xs - self.origin[0], ys - self.origin[1]])
        return v * self.rows, u * self.cols

    def share(self, geometry: BaseGeometry) -> float:
        west, south, east, north = geometry.bounds
        rows, cols = self._cells(np.array([west, west, east, east]), np.array([south, north] * 2))
        top, bottom = max(math.floor(rows.min()), 0), min(math.ceil(rows.max()), self.rows)
        left, right = max(math.floor(cols.min()), 0), min(math.ceil(cols.max()), self.cols)
        if top < bottom and left < right:
            grid_rows, grid_cols = np.mgrid[top:bottom, left:right]
            lon, lat = self.origin[:, None] + self.axes @ np.vstack(
                [(grid_cols.ravel() + 0.5) / self.cols, (grid_rows.ravel() + 0.5) / self.rows]
            )
            inside = contains_xy(geometry, lon, lat)
            if inside.any():
                return float(self.seen[grid_rows.ravel()[inside], grid_cols.ravel()[inside]].mean())
        point = geometry.representative_point()
        rows, cols = self._cells(np.array([point.x]), np.array([point.y]))
        row, col = math.floor(rows[0]), math.floor(cols[0])
        if 0 <= row < self.rows and 0 <= col < self.cols:
            return float(self.seen[row, col])
        return 0.0

    def observed(self, geometry: BaseGeometry) -> bool:
        return self.share(geometry) >= OBSERVED_SHARE


def _local(geometry: BaseGeometry, origin: tuple[float, float]) -> BaseGeometry:
    scale = METERS_PER_DEGREE * math.cos(math.radians(origin[1]))

    def project(x, y, z=None):
        return (x - origin[0]) * scale, (y - origin[1]) * METERS_PER_DEGREE

    return transform(project, geometry)


def _shapes(zones: list[dict[str, Any]]) -> list[tuple[str, BaseGeometry, float]]:
    items = []
    for index, zone in enumerate(zones, start=1):
        if not zone.get("geometry"):
            continue
        items.append(
            (
                str(zone.get("id") or f"zone-{index}"),
                shape(zone["geometry"]),
                float(zone.get("area_km2") or 0.0),
            )
        )
    return items


def _origin(shapes: list[tuple[str, BaseGeometry, float]]) -> tuple[float, float]:
    xs = [geometry.centroid.x for _, geometry, _ in shapes]
    ys = [geometry.centroid.y for _, geometry, _ in shapes]
    return sum(xs) / len(xs), sum(ys) / len(ys)


def _matches(
    source: list[tuple[str, BaseGeometry, float]],
    other: list[tuple[str, BaseGeometry, float]],
    origin: tuple[float, float],
    tolerance_m: float,
) -> set[str]:
    if not source or not other:
        return set()
    grown = [_local(geometry, origin).buffer(tolerance_m) for _, geometry, _ in other]
    tree = STRtree(grown)
    matched = set()
    for zone_id, geometry, _ in source:
        local = _local(geometry, origin)
        if any(grown[index].intersects(local) for index in tree.query(local)):
            matched.add(zone_id)
    return matched


def _kinds(
    items: list[tuple[str, BaseGeometry, float]],
    kept: set[str],
    unmatched: str,
    other: Coverage | None,
) -> dict[str, str]:
    kinds = {}
    for zone_id, geometry, _ in items:
        if zone_id in kept:
            kinds[zone_id] = "persisting"
        elif other is not None and not other.observed(geometry):
            kinds[zone_id] = "not_observed"
        else:
            kinds[zone_id] = unmatched
    return kinds


def zone_change(
    before: list[dict[str, Any]],
    after: list[dict[str, Any]],
    tolerance_m: float = TOLERANCE_M,
    before_coverage: Coverage | None = None,
    after_coverage: Coverage | None = None,
) -> dict[str, Any]:
    old = _shapes(before)
    new = _shapes(after)
    everything = old + new
    origin = _origin(everything) if everything else (0.0, 0.0)
    after_zones = _kinds(new, _matches(new, old, origin, tolerance_m), "new", before_coverage)
    before_zones = _kinds(
        old, _matches(old, new, origin, tolerance_m), "disappeared", after_coverage
    )

    def count(zones: dict[str, str], kind: str) -> int:
        return sum(1 for value in zones.values() if value == kind)

    def area(items, zones: dict[str, str], kind: str) -> float:
        return round(sum(size for zone_id, _, size in items if zones[zone_id] == kind), 4)

    checked = before_coverage is not None and after_coverage is not None
    return {
        "counts": {
            "new": count(after_zones, "new"),
            "persisting": count(after_zones, "persisting"),
            "disappeared": count(before_zones, "disappeared"),
            "not_observed": count(after_zones, "not_observed")
            + count(before_zones, "not_observed"),
        },
        "area_km2": {
            "new": area(new, after_zones, "new"),
            "persisting": area(new, after_zones, "persisting"),
            "disappeared": area(old, before_zones, "disappeared"),
            "not_observed": round(
                area(new, after_zones, "not_observed") + area(old, before_zones, "not_observed"),
                4,
            ),
        },
        "after_zones": after_zones,
        "before_zones": before_zones,
        "masks_checked": checked,
        "tolerance_m": tolerance_m,
        "method": f"{METHOD}; {SEEN_NOTE if checked else BLIND_NOTE}",
    }


def comparable(result: dict[str, Any]) -> bool:
    return result["detection"]["status"] in COMPARABLE
