from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

from shapely.geometry import LineString, Point, mapping
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform

from app.case.records import CaseRecord

EARTH_RADIUS_M = 6_371_008.8
APPROXIMATE_FLAGS = ("interrupted_transect_summary_area",)


class FootprintKind(StrEnum):
    STRIP = "strip"
    POINT = "point"


FOOTPRINT_LABELS: dict[FootprintKind, str] = {
    FootprintKind.STRIP: "полоса по концам трансекты",
    FootprintKind.POINT: "только центр наблюдения: протяжённость неизвестна, круг неопределённости",
}


@dataclass(frozen=True)
class LocalProjection:
    lon0: float
    lat0: float

    def forward(self, lon: float, lat: float, z: float | None = None) -> tuple[float, float]:
        x = math.radians(lon - self.lon0) * EARTH_RADIUS_M * math.cos(math.radians(self.lat0))
        y = math.radians(lat - self.lat0) * EARTH_RADIUS_M
        return x, y

    def inverse(self, x: float, y: float, z: float | None = None) -> tuple[float, float]:
        lat = self.lat0 + math.degrees(y / EARTH_RADIUS_M)
        lon = self.lon0 + math.degrees(x / (EARTH_RADIUS_M * math.cos(math.radians(self.lat0))))
        return lon, lat


@dataclass(frozen=True)
class Footprint:
    kind: FootprintKind
    observed: BaseGeometry
    analysis: BaseGeometry
    radius_m: float
    width_m: float | None
    length_km: float | None
    approximate: bool

    @property
    def label(self) -> str:
        return FOOTPRINT_LABELS[self.kind]

    @property
    def analysis_area_km2(self) -> float:
        return area_km2(self.analysis)

    def geojson(self) -> dict:
        return mapping(self.observed)

    def covered_by(self, cover: BaseGeometry) -> float:
        if cover.contains(self.analysis):
            return 1.0
        overlap = cover.intersection(self.analysis)
        if overlap.is_empty:
            return 0.0
        center = self.analysis.centroid
        projection = LocalProjection(center.x, center.y)
        inside = transform(projection.forward, overlap).area
        return min(inside / transform(projection.forward, self.analysis).area, 1.0)


def area_km2(geometry: BaseGeometry) -> float:
    center = geometry.centroid
    projection = LocalProjection(center.x, center.y)
    return transform(projection.forward, geometry).area / 1e6


def distance_km(first: tuple[float, float], second: tuple[float, float]) -> float:
    projection = LocalProjection(*first)
    x, y = projection.forward(*second)
    return math.hypot(x, y) / 1000.0


def _buffered(geometry: BaseGeometry, projection: LocalProjection, radius_m: float) -> BaseGeometry:
    metric = transform(projection.forward, geometry).buffer(radius_m, quad_segs=8)
    return transform(projection.inverse, metric)


class MissingPositionError(ValueError):
    pass


def build_footprint(
    record: CaseRecord, unknown_extent_buffer_m: float, min_strip_width_m: float
) -> Footprint:
    approximate = any(flag in APPROXIMATE_FLAGS for flag in record.flags)
    segment = record.segment
    width = record.number("transect_width_m")
    length = record.number("transect_length_km")
    if segment is not None:
        (lon_a, lat_a), (lon_b, lat_b) = segment
        projection = LocalProjection((lon_a + lon_b) / 2, (lat_a + lat_b) / 2)
        line = LineString(segment)
        radius = max(width or 0, min_strip_width_m) / 2
        observed = _buffered(line, projection, (width or 0) / 2) if width else line
        analysis = _buffered(line, projection, radius)
        return Footprint(
            FootprintKind.STRIP, observed, analysis, radius, width, length, approximate
        )
    position = record.position
    if position is None:
        raise MissingPositionError(f"{record.sample_id}: no coordinates")
    projection = LocalProjection(*position)
    point = Point(position)
    analysis = _buffered(point, projection, unknown_extent_buffer_m)
    return Footprint(
        FootprintKind.POINT, point, analysis, unknown_extent_buffer_m, width, length, approximate
    )
