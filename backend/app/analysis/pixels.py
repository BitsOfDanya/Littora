from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import numpy as np
from affine import Affine
from rasterio.warp import transform as warp_transform
from shapely.geometry import Point, shape

from app.analysis.composites import B03, B04, B08, B11, fdi, ndvi

PIXELS_FILE = "pixels.npz"
MAX_PIXELS = 4_000_000
B02 = 1
REFLECTANCE_BANDS = {"B02": B02, "B03": B03, "B04": B04, "B08": B08, "B11": B11}
SCL_NAMES = {
    0: "нет данных",
    1: "дефектный пиксель",
    2: "тень рельефа",
    3: "тень облака",
    4: "растительность",
    5: "суша без растительности",
    6: "вода",
    7: "не классифицировано",
    8: "облако, средняя вероятность",
    9: "облако, высокая вероятность",
    10: "перистые облака",
    11: "снег или лёд",
}


def pack(
    image: np.ndarray,
    scl: np.ndarray,
    probability: np.ndarray,
    coverage: np.ndarray,
    transform: Affine,
    crs: str,
    threshold: float,
) -> bytes | None:
    if scl.size > MAX_PIXELS:
        return None
    arrays = {
        "probability": probability.astype(np.float16),
        "fdi": fdi(image).astype(np.float16),
        "ndvi": ndvi(image).astype(np.float16),
        "coverage": np.nan_to_num(coverage, nan=-1).astype(np.float16),
        "scl": scl.astype(np.uint8),
        **{name: image[index].astype(np.float16) for name, index in REFLECTANCE_BANDS.items()},
        "transform": np.array(tuple(transform)[:6], dtype=np.float64),
        "crs": np.array(crs),
        "threshold": np.array(threshold, dtype=np.float64),
    }
    buffer = io.BytesIO()
    np.savez_compressed(buffer, **arrays)
    return buffer.getvalue()


def _value(array: np.ndarray, row: int, col: int, digits: int = 4) -> float | None:
    value = float(array[row, col])
    return round(value, digits) if np.isfinite(value) else None


def read_pixel(path: Path, zones: list[dict[str, Any]], lon: float, lat: float) -> dict[str, Any]:
    with np.load(path, allow_pickle=False) as data:
        transform = Affine(*data["transform"].tolist())
        crs = str(data["crs"])
        xs, ys = warp_transform("EPSG:4326", crs, [lon], [lat])
        col, row = (~transform) * (xs[0], ys[0])
        row, col = int(np.floor(row)), int(np.floor(col))
        height, width = data["scl"].shape
        if not (0 <= row < height and 0 <= col < width):
            return {"inside": False, "lon": lon, "lat": lat}
        threshold = float(data["threshold"])
        probability = _value(data["probability"], row, col)
        coverage = _value(data["coverage"], row, col)
        scl = int(data["scl"][row, col])
        payload = {
            "inside": True,
            "lon": lon,
            "lat": lat,
            "row": row,
            "col": col,
            "probability": probability,
            "threshold": round(threshold, 4),
            "above_threshold": probability is not None and probability >= threshold,
            "fdi": _value(data["fdi"], row, col),
            "ndvi": _value(data["ndvi"], row, col, 3),
            "coverage": coverage if coverage is not None and coverage >= 0 else None,
            "scl": {"code": scl, "label": SCL_NAMES.get(scl, "неизвестно")},
            "reflectance": {name: _value(data[name], row, col) for name in REFLECTANCE_BANDS},
        }
    point = Point(lon, lat)
    payload["zone_id"] = next(
        (
            zone.get("id")
            for zone in zones
            if zone.get("geometry") and shape(zone["geometry"]).buffer(1e-5).contains(point)
        ),
        None,
    )
    return payload
