import datetime as dt
from typing import Annotated, Any

from fastapi import APIRouter, Query
from shapely.geometry import box, mapping
from shapely.geometry.base import BaseGeometry

from app.api.dependencies import AnalysisDep
from app.api.v1.params import parse_bbox
from app.case.registry import round_coordinates
from app.core.errors import AppError
from app.earth.catalog import Scene

router = APIRouter(tags=["scenes"])

MAX_RANGE_DAYS = 120


def _glint_risk(sun_elevation: float | None) -> str:
    if sun_elevation is None:
        return "moderate"
    if sun_elevation >= 60:
        return "high"
    if sun_elevation >= 45:
        return "moderate"
    return "low"


def _usability(cloud: float, coverage: float) -> str:
    if cloud >= 0.6 or coverage < 0.5:
        return "unusable"
    if cloud >= 0.2 or coverage < 0.9:
        return "partial"
    return "usable"


def _coverage(scene: Scene, area: BaseGeometry) -> float:
    return round(scene.geometry.intersection(area).area / area.area, 4) if area.area else 0.0


def best_per_pass(scenes: list[Scene], area: BaseGeometry) -> list[Scene]:
    passes: dict[tuple[str, str], list[Scene]] = {}
    for scene in scenes:
        key = (scene.platform, scene.acquired_at.strftime("%Y%m%d%H%M"))
        passes.setdefault(key, []).append(scene)
    best = [
        min(tiles, key=lambda scene: (-_coverage(scene, area), scene.cloud_cover or 0.0, scene.id))
        for tiles in passes.values()
    ]
    return sorted(best, key=lambda scene: (scene.acquired_at, scene.id))


def scene_listing(scene: Scene, aoi_id: str | None, area: BaseGeometry) -> dict[str, Any]:
    cloud = (scene.cloud_cover or 0.0) / 100
    coverage = _coverage(scene, area)
    water = None
    if scene.water_percentage is not None:
        water = round(max(0.0, min(1.0, scene.water_percentage / 100)), 4)
    return {
        "id": scene.id,
        "aoi_id": aoi_id,
        "collection": scene.collection,
        "platform": scene.platform,
        "processing_level": "L2A",
        "acquired_at": scene.acquired_at.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "mgrs_tile": scene.tile,
        "relative_orbit": scene.relative_orbit,
        "footprint": [round(value, 5) for value in scene.footprint_bbox],
        "geometry": round_coordinates(mapping(scene.geometry)),
        "area_coverage": coverage,
        "cloud_cover": round(cloud, 4),
        "valid_water_fraction": round(max(0.0, 1 - cloud), 4),
        "water_fraction": water,
        "sun_glint_risk": _glint_risk(scene.sun_elevation),
        "sun_zenith_deg": 90 - scene.sun_elevation if scene.sun_elevation is not None else None,
        "usability": _usability(cloud, coverage),
    }


@router.get("/scenes")
def read_scenes(
    analysis: AnalysisDep,
    bbox: Annotated[str, Query(max_length=120)],
    date_from: dt.date,
    date_to: dt.date,
    aoi_id: Annotated[str | None, Query(max_length=80)] = None,
) -> dict[str, Any]:
    area = parse_bbox(bbox)
    if date_to < date_from:
        raise AppError("date_to раньше date_from")
    if (date_to - date_from).days > MAX_RANGE_DAYS:
        raise AppError(f"Период не длиннее {MAX_RANGE_DAYS} суток")
    start = dt.datetime.combine(date_from, dt.time.min, tzinfo=dt.UTC)
    end = dt.datetime.combine(date_to, dt.time(23, 59, 59), tzinfo=dt.UTC)
    region = box(*area)
    platforms = {"S2A", "S2B", "S2C"}
    scenes = [s for s in analysis.search_scenes(region, start, end) if s.platform in platforms]
    return {
        "items": [scene_listing(scene, aoi_id, region) for scene in best_per_pass(scenes, region)]
    }
