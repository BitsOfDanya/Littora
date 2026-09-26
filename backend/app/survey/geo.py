from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
from shapely.geometry import Polygon

from app.drift.geo import EARTH_RADIUS_M, to_local

EARTH_RADIUS_KM = EARTH_RADIUS_M / 1000.0

Point = Sequence[float]


def distance_km(a: Point, b: Point) -> float:
    lat1, lat2 = math.radians(a[1]), math.radians(b[1])
    d_lat = lat2 - lat1
    d_lon = math.radians(b[0] - a[0])
    h = math.sin(d_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(d_lon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(h)))


def bearing_deg(a: Point, b: Point) -> float:
    east, north = to_local(a, [b[0]], [b[1]])[0]
    return (math.degrees(math.atan2(east, north)) + 360.0) % 360.0


def along(track: Sequence[Point], hours: float) -> list[float]:
    if not track:
        raise ValueError("пустой трек")
    last = len(track) - 1
    hours = min(max(hours, 0.0), float(last))
    low = min(math.floor(hours), last)
    high = min(low + 1, last)
    t = hours - low
    return [
        track[low][0] + (track[high][0] - track[low][0]) * t,
        track[low][1] + (track[high][1] - track[low][1]) * t,
    ]


def equivalent_radius_km(ring: Sequence[Point]) -> float:
    points = np.asarray(ring, dtype=float)
    if len(points) < 4:
        return 0.0
    center = points.mean(axis=0)
    area = Polygon(to_local(center, points[:, 0], points[:, 1])).area
    return math.sqrt(area / math.pi) / 1000.0


def centroid(points: Sequence[Point], weights: Sequence[float]) -> list[float]:
    total = sum(weights)
    if total <= 0:
        weights = [1.0] * len(points)
        total = float(len(points))
    return [
        sum(point[0] * weight for point, weight in zip(points, weights, strict=True)) / total,
        sum(point[1] * weight for point, weight in zip(points, weights, strict=True)) / total,
    ]
