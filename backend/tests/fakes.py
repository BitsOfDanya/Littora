from __future__ import annotations

import datetime as dt

import numpy as np
from shapely.geometry import box
from shapely.geometry.base import BaseGeometry

from app.analysis.models import DetectionOutcome
from app.analysis.statuses import ResultStatus
from app.drift.forcing import Domain, Forcing, ForcingError, hourly
from app.earth.catalog import CatalogError, Scene
from app.earth.raster import QualityShares, RenderedLayer, encode_png

SENTINEL2 = "sentinel-2-c1-l2a"


def make_scene(
    scene_id: str,
    day: dt.date,
    geometry: BaseGeometry | None = None,
    cloud: float = 0.0,
    platform: str = "S2A",
    hour: int = 9,
) -> Scene:
    sentinel = platform.startswith("S2")
    return Scene(
        id=scene_id,
        collection=SENTINEL2 if sentinel else "landsat-c2-l2",
        platform=platform,
        acquired_at=dt.datetime.combine(day, dt.time(hour, 0), tzinfo=dt.UTC),
        cloud_cover=cloud,
        tile="35TPJ",
        relative_orbit=107,
        sun_elevation=62.0,
        water_percentage=97.0,
        nodata_percentage=0.0,
        geometry=geometry or box(20, 30, 60, 70),
        assets={"scl": "scl.tif", "visual": "tci.tif", "nir": "b08.tif"} if sentinel else {},
    )


class FakeCatalog:
    def __init__(self, scenes: list[Scene] | None = None, fail: bool = False) -> None:
        self.scenes = scenes or []
        self.fail = fail
        self.searches = 0

    def search(self, collection, geometry, start, end, limit=100):
        self.searches += 1
        if self.fail:
            raise CatalogError("нет связи")
        return [
            scene
            for scene in self.scenes
            if scene.collection == collection
            and start <= scene.acquired_at <= end
            and scene.geometry.intersects(geometry)
        ]

    def get(self, collection, scene_id):
        for scene in self.scenes:
            if scene.id == scene_id:
                return scene
        raise CatalogError("нет такой сцены")


def clear_quality(*_args) -> QualityShares:
    return QualityShares(
        pixels=400,
        water=0.96,
        cloud=0.01,
        shadow=0.0,
        snow=0.0,
        land=0.03,
        nodata=0.0,
        other=0.0,
        bright_water=0.0,
    )


def cloudy_quality(*_args) -> QualityShares:
    return QualityShares(
        pixels=400,
        water=0.5,
        cloud=0.45,
        shadow=0.05,
        snow=0.0,
        land=0.0,
        nodata=0.0,
        other=0.0,
        bright_water=None,
    )


def blank_layer(*_args) -> RenderedLayer:
    pixels = np.zeros((2, 2, 4), dtype=np.uint8)
    corners = [[29.0, 44.0], [30.0, 44.0], [30.0, 43.0], [29.0, 43.0]]
    return RenderedLayer(encode_png(pixels), corners, 2, 2)


class FakeDetector:
    name = "fake-detector-1"

    def detect(self, scene, area):
        zone = {
            "id": "zone-1",
            "geometry": {"type": "Point", "coordinates": [29.6, 43.6]},
            "probability": 0.9,
            "area_km2": 0.02,
        }
        return DetectionOutcome(
            status=ResultStatus.DETECTED,
            reason="найдена одна зона",
            model=self.name,
            zones=[zone],
        )


def uniform_forcing(
    domain: Domain,
    start: dt.datetime,
    end: dt.datetime,
    current: tuple[float, float] = (0.0, 0.0),
    stokes: tuple[float, float] = (0.0, 0.0),
    wind: tuple[float, float] = (0.0, 0.0),
    step: float = 0.1,
) -> Forcing:
    lats = np.arange(domain.south, domain.north + step, step)
    lons = np.arange(domain.west, domain.east + step, step)
    shape = (len(hourly(start, end)), lats.size, lons.size, 2)

    def constant(vector: tuple[float, float]) -> np.ndarray:
        return np.broadcast_to(np.array(vector, dtype=float), shape).copy()

    return Forcing(
        start=start,
        lons=lons,
        lats=lats,
        current=constant(current),
        stokes=constant(stokes),
        wind=constant(wind),
        water=np.ones(shape[1:3], dtype=bool),
        provenance={
            "currents": {"available": True, "source": "fake"},
            "waves": {"available": True, "source": "fake"},
            "wind": {"available": True, "source": "fake wind"},
            "fetched_at": "2024-06-10T00:00:00+00:00",
        },
    )


class FakeForcing:
    def __init__(
        self,
        current: tuple[float, float] = (0.1, 0.0),
        stokes: tuple[float, float] = (0.02, 0.0),
        wind: tuple[float, float] = (5.0, 0.0),
        fail: bool = False,
        fail_wide: bool = False,
    ) -> None:
        self.current = current
        self.stokes = stokes
        self.wind = wind
        self.fail = fail
        self.fail_wide = fail_wide
        self.calls = 0
        self.limits: list[dict[str, int]] = []
        self.domains: list[Domain] = []

    def load(self, domain: Domain, start: dt.datetime, end: dt.datetime, **limits: int) -> Forcing:
        self.calls += 1
        self.limits.append(limits)
        self.domains.append(domain)
        if self.fail or (limits and self.fail_wide):
            raise ForcingError("нет связи")
        return uniform_forcing(domain, start, end, self.current, self.stokes, self.wind)
