from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np
import rasterio
from affine import Affine
from rasterio.enums import Resampling
from rasterio.errors import WindowError
from rasterio.warp import transform as transform_points
from rasterio.warp import transform_bounds
from rasterio.windows import Window, from_bounds
from scipy.ndimage import label as connected

from app.drift.forcing import Domain, Forcing
from app.drift.geo import METERS_PER_DEGREE
from app.earth.catalog import Scene
from app.earth.raster import GDAL_OPTIONS, RasterError

SCL_LAND = (4, 5)
SCL_WATER = (6,)
MASK_CELL_M = 160.0
MAX_MASK_CELLS = 4_000_000
MIN_LAND_CELLS = 16

ClassSampler = Callable[[np.ndarray, np.ndarray], np.ndarray]
SceneClassReader = Callable[[Scene, Domain, float], ClassSampler]


@dataclass(frozen=True)
class LandMask:
    west: float
    south: float
    lon_step: float
    lat_step: float
    land: np.ndarray
    provenance: dict[str, Any]

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        rows, cols = self.land.shape
        return (
            self.west,
            self.south,
            self.west + cols * self.lon_step,
            self.south + rows * self.lat_step,
        )

    def cells(self, lon: np.ndarray, lat: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        rows, cols = self.land.shape
        col = np.floor((np.asarray(lon) - self.west) / self.lon_step).astype(int)
        row = np.floor((np.asarray(lat) - self.south) / self.lat_step).astype(int)
        inside = (row >= 0) & (row < rows) & (col >= 0) & (col < cols)
        return row, col, inside

    def is_land(self, lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
        row, col, inside = self.cells(lon, lat)
        result = np.zeros(np.shape(lon), dtype=bool)
        result[inside] = self.land[row[inside], col[inside]]
        return result


@dataclass(frozen=True)
class NestedLand:
    inner: LandMask
    outer: LandMask

    def is_land(self, lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
        _, _, near = self.inner.cells(lon, lat)
        return np.where(near, self.inner.is_land(lon, lat), self.outer.is_land(lon, lat))


def scene_class_sampler(scene: Scene, domain: Domain, cell_m: float) -> ClassSampler:
    if "scl" not in scene.assets:
        raise RasterError("у сцены нет маски классов SCL")
    try:
        with rasterio.Env(**GDAL_OPTIONS), rasterio.open(scene.assets["scl"]) as dataset:
            crs = dataset.crs
            left, bottom, right, top = transform_bounds("EPSG:4326", crs, *domain.bounds)
            full = Window(0, 0, dataset.width, dataset.height)
            window = from_bounds(left, bottom, right, top, transform=dataset.transform)
            window = window.round_offsets().round_lengths().intersection(full)
            factor = max(1.0, cell_m / abs(dataset.res[0]))
            height = max(1, round(window.height / factor))
            width = max(1, round(window.width / factor))
            classes = dataset.read(
                1, window=window, out_shape=(height, width), resampling=Resampling.nearest
            )
            affine = dataset.window_transform(window) * Affine.scale(
                window.width / width, window.height / height
            )
    except WindowError as error:
        raise RasterError("снимок не покрывает область дрейфа") from error
    except rasterio.errors.RasterioIOError as error:
        raise RasterError(f"маска SCL не читается: {error}") from error

    def sample(lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
        xs, ys = transform_points("EPSG:4326", crs, lon.ravel().tolist(), lat.ravel().tolist())
        cols, rows = ~affine * (np.asarray(xs), np.asarray(ys))
        cols, rows = np.floor(cols).astype(int), np.floor(rows).astype(int)
        inside = (rows >= 0) & (rows < height) & (cols >= 0) & (cols < width)
        result = np.zeros(lon.size, dtype=np.uint8)
        result[inside] = classes[rows[inside], cols[inside]]
        return result.reshape(lon.shape)

    return sample


def _drop_specks(land: np.ndarray, min_cells: int) -> np.ndarray:
    labels, count = connected(land, structure=np.ones((3, 3), dtype=bool))
    if not count:
        return land
    sizes = np.bincount(labels.ravel())
    keep = sizes >= min_cells
    keep[0] = False
    return keep[labels]


def build_land_mask(
    domain: Domain,
    forcing: Forcing,
    sampler: ClassSampler | None,
    keep_water: np.ndarray,
    scene_id: str | None = None,
    cell_m: float = MASK_CELL_M,
) -> LandMask:
    middle = math.radians((domain.south + domain.north) / 2)
    lat_step = cell_m / METERS_PER_DEGREE
    lon_step = lat_step / max(math.cos(middle), 0.1)
    rows = math.ceil((domain.north - domain.south) / lat_step)
    cols = math.ceil((domain.east - domain.west) / lon_step)
    if rows * cols > MAX_MASK_CELLS:
        scale = math.sqrt(rows * cols / MAX_MASK_CELLS)
        lat_step, lon_step = lat_step * scale, lon_step * scale
        rows = math.ceil((domain.north - domain.south) / lat_step)
        cols = math.ceil((domain.east - domain.west) / lon_step)
    lats = domain.south + (np.arange(rows) + 0.5) * lat_step
    lons = domain.west + (np.arange(cols) + 0.5) * lon_step
    near_row = np.rint(np.interp(lats, forcing.lats, np.arange(forcing.lats.size))).astype(int)
    near_col = np.rint(np.interp(lons, forcing.lons, np.arange(forcing.lons.size))).astype(int)
    land = ~forcing.water[np.ix_(near_row, near_col)]
    scene_share = 0.0
    if sampler is not None:
        lon_grid, lat_grid = np.meshgrid(lons, lats)
        classes = sampler(lon_grid, lat_grid)
        scene_land = np.isin(classes, SCL_LAND)
        scene_water = np.isin(classes, SCL_WATER)
        land = np.where(scene_land, True, np.where(scene_water, False, land))
        scene_share = float((scene_land | scene_water).mean())
    land = _drop_specks(land, MIN_LAND_CELLS)
    mask = LandMask(domain.west, domain.south, lon_step, lat_step, land, {})
    if keep_water.size:
        row, col, inside = mask.cells(keep_water[:, 0], keep_water[:, 1])
        land[row[inside], col[inside]] = False
    source = (
        f"SCL снимка {scene_id}: классы 4–5 — суша, 6 — вода; прочее — сетка Open-Meteo Marine"
        if sampler is not None
        else "сетка Open-Meteo Marine: узел без данных о море — суша"
    )
    provenance = {
        "source": source,
        "cell_m": round(lat_step * METERS_PER_DEGREE, 1),
        "scene_share": round(scene_share, 3),
        "land_share": round(float(land.mean()), 3),
        "min_land_cells": MIN_LAND_CELLS,
        "outside": "за пределами области — открытая вода",
    }
    return LandMask(domain.west, domain.south, lon_step, lat_step, land, provenance)
