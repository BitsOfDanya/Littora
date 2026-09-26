from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np
from affine import Affine
from rasterio.crs import CRS
from rasterio.features import shapes
from rasterio.warp import transform_geom
from scipy.ndimage import find_objects
from scipy.ndimage import label as connected
from shapely.geometry import shape
from shapely.ops import unary_union

from app.earth.raster import SCL_GROUPS

PIXEL_KM2 = 1e-4
MAX_ZONES = 300
METERS_PER_DEGREE = 111_320.0


def pixel_km2(transform: Affine, crs: str, shape: tuple[int, int]) -> float:
    area = abs(transform.a * transform.e - transform.b * transform.d)
    try:
        geographic = CRS.from_user_input(crs).is_geographic
    except Exception:
        geographic = False
    if geographic:
        _, lat = transform * (shape[1] / 2, shape[0] / 2)
        area *= METERS_PER_DEGREE**2 * float(np.cos(np.radians(lat)))
    return area / 1e6 if area > 0 else PIXEL_KM2


def _class_counts(labels: np.ndarray, scl: np.ndarray, size: int) -> dict[str, np.ndarray]:
    flat = labels.ravel()
    return {
        name: np.bincount(flat, weights=np.isin(scl, codes).ravel(), minlength=size)
        for name, codes in SCL_GROUPS.items()
    }


def mask_zones(
    mask: np.ndarray,
    probability: np.ndarray,
    transform: Affine,
    crs: str,
    min_pixels: int = 1,
    scl: np.ndarray | None = None,
    describe: Callable[[np.ndarray, int, tuple[slice, slice]], dict[str, Any]] | None = None,
    measure: Callable[[np.ndarray, list[int], list], dict[int, dict[str, Any]]] | None = None,
    stats: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    labels, count = connected(mask, structure=np.ones((3, 3), dtype=bool))
    if not count:
        return []
    cell_km2 = pixel_km2(transform, crs, mask.shape)
    sizes = np.bincount(labels.ravel())
    peaks = np.zeros(count + 1)
    np.maximum.at(peaks, labels.ravel(), probability.ravel())
    sums = np.bincount(labels.ravel(), weights=probability.ravel())
    keep = [index for index in range(1, count + 1) if sizes[index] >= min_pixels]
    if stats is not None:
        stats["total"] = len(keep)
        stats["limit"] = MAX_ZONES
    keep = sorted(keep, key=lambda index: -peaks[index])[:MAX_ZONES]
    selected = np.isin(labels, keep)
    classes = _class_counts(labels, scl, count + 1) if scl is not None else None
    bounds = find_objects(labels) if describe is not None or measure is not None else []
    measured = measure(labels, keep, bounds) if measure is not None else {}
    geometries: dict[int, list] = {}
    for geometry, value in shapes(labels.astype(np.int32), mask=selected, transform=transform):
        geometries.setdefault(int(value), []).append(shape(geometry))
    zones = []
    for rank, index in enumerate(keep, start=1):
        parts = geometries.get(index, [])
        if not parts:
            continue
        merged = unary_union(parts)
        lonlat = transform_geom(crs, "EPSG:4326", merged.__geo_interface__)
        centroid = shape(lonlat).centroid
        zone = {
            "id": f"zone-{rank}",
            "geometry": lonlat,
            "pixels": int(sizes[index]),
            "area_km2": round(float(sizes[index]) * cell_km2, 4),
            "probability_max": round(float(peaks[index]), 4),
            "probability_mean": round(float(sums[index] / sizes[index]), 4),
            "centroid": [round(centroid.x, 6), round(centroid.y, 6)],
            "status_label": "обнаружено",
        }
        if classes is not None:
            zone["scl"] = {
                name: round(float(counts[index] / sizes[index]), 4)
                for name, counts in classes.items()
                if counts[index] > 0
            }
        if describe is not None:
            zone.update(describe(labels, index, bounds[index - 1]))
        for key, value in measured.get(index, {}).items():
            if isinstance(value, list):
                zone.setdefault(key, []).extend(value)
            else:
                zone[key] = value
        zones.append(zone)
    return zones
