from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

EARTH_RADIUS_M = 6_371_008.8
METERS_PER_DEGREE = EARTH_RADIUS_M * math.pi / 180.0


def offset(
    lon: np.ndarray, lat: np.ndarray, east_m: np.ndarray, north_m: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    scale = METERS_PER_DEGREE * np.cos(np.radians(lat))
    return lon + east_m / scale, lat + north_m / METERS_PER_DEGREE


def to_local(origin: Sequence[float], lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    scale = METERS_PER_DEGREE * math.cos(math.radians(origin[1]))
    return np.column_stack(
        [(np.asarray(lon) - origin[0]) * scale, (np.asarray(lat) - origin[1]) * METERS_PER_DEGREE]
    )


def from_local(origin: Sequence[float], xy: np.ndarray) -> np.ndarray:
    scale = METERS_PER_DEGREE * math.cos(math.radians(origin[1]))
    return np.column_stack([origin[0] + xy[:, 0] / scale, origin[1] + xy[:, 1] / METERS_PER_DEGREE])


def rounded(point: Sequence[float], digits: int = 5) -> list[float]:
    return [round(float(point[0]), digits), round(float(point[1]), digits)]
