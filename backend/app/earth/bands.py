from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import rasterio
from affine import Affine
from rasterio.enums import Resampling
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds
from shapely.geometry.base import BaseGeometry

from app.earth.catalog import Scene
from app.earth.raster import GDAL_OPTIONS, RasterError, RasterReadError

BAND_ASSETS = (
    ("B01", "coastal"),
    ("B02", "blue"),
    ("B03", "green"),
    ("B04", "red"),
    ("B05", "rededge1"),
    ("B06", "rededge2"),
    ("B07", "rededge3"),
    ("B08", "nir"),
    ("B8A", "nir08"),
    ("B11", "swir16"),
    ("B12", "swir22"),
)
GRID_M = 10
REFLECTANCE_FLOOR = 0.0001


@dataclass(frozen=True)
class BandStack:
    image: np.ndarray
    scl: np.ndarray
    crs: str
    transform: Affine

    @property
    def shape(self) -> tuple[int, int]:
        return self.scl.shape


def grid_size(scene: Scene, geometry: BaseGeometry) -> tuple[int, int]:
    try:
        with rasterio.Env(**GDAL_OPTIONS), rasterio.open(scene.assets["blue"]) as dataset:
            west, south, east, north = transform_bounds("EPSG:4326", dataset.crs, *geometry.bounds)
    except rasterio.errors.RasterioIOError as error:
        raise RasterReadError(f"каналы снимка не читаются: {error}") from error
    return int(np.ceil((north - south) / GRID_M)), int(np.ceil((east - west) / GRID_M))


def read_band_stack(scene: Scene, geometry: BaseGeometry) -> BandStack:
    missing = [asset for _, asset in BAND_ASSETS if asset not in scene.assets]
    if missing or "scl" not in scene.assets:
        raise RasterError("у сцены нет всех каналов для детектора")
    try:
        with rasterio.Env(**GDAL_OPTIONS), rasterio.open(scene.assets["blue"]) as dataset:
            crs = dataset.crs
            west, south, east, north = transform_bounds("EPSG:4326", crs, *geometry.bounds)
    except rasterio.errors.RasterioIOError as error:
        raise RasterReadError(f"каналы снимка не читаются: {error}") from error
    west, south = np.floor(west / GRID_M) * GRID_M, np.floor(south / GRID_M) * GRID_M
    east, north = np.ceil(east / GRID_M) * GRID_M, np.ceil(north / GRID_M) * GRID_M
    height, width = int((north - south) / GRID_M), int((east - west) / GRID_M)

    def read(asset: str, resampling: Resampling) -> np.ndarray:
        with rasterio.Env(**GDAL_OPTIONS), rasterio.open(scene.assets[asset]) as dataset:
            window = from_bounds(west, south, east, north, transform=dataset.transform)
            return dataset.read(
                1,
                window=window,
                out_shape=(height, width),
                resampling=resampling,
                boundless=True,
                fill_value=0,
            )

    image = np.zeros((len(BAND_ASSETS), height, width), dtype=np.float32)
    try:
        for index, (_, asset) in enumerate(BAND_ASSETS):
            raw = read(asset, Resampling.bilinear).astype(np.float32)
            reflectance = raw * scene.reflectance_scale + scene.reflectance_offset
            image[index] = np.where(raw > 0, np.maximum(reflectance, REFLECTANCE_FLOOR), 0.0)
        scl = read("scl", Resampling.nearest).astype(np.uint8)
    except rasterio.errors.RasterioIOError as error:
        raise RasterReadError(f"каналы снимка не читаются: {error}") from error
    transform = Affine(GRID_M, 0, west, 0, -GRID_M, north)
    return BandStack(image, scl, crs.to_string(), transform)
