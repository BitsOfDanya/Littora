from __future__ import annotations

import struct
import threading
import warnings
import zlib
from collections import OrderedDict
from dataclasses import dataclass

import numpy as np
import rasterio
from affine import Affine
from rasterio.enums import Resampling
from rasterio.errors import NotGeoreferencedWarning, WindowError
from rasterio.features import geometry_mask
from rasterio.warp import transform as transform_points
from rasterio.warp import transform_geom
from rasterio.windows import Window, from_bounds
from shapely.geometry import mapping, shape
from shapely.geometry.base import BaseGeometry

from app.earth.catalog import Scene

warnings.filterwarnings("ignore", category=NotGeoreferencedWarning, module=r"rasterio\.features")

GDAL_OPTIONS = {
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif,.TIF",
    "GDAL_HTTP_MAX_RETRY": "4",
    "GDAL_HTTP_RETRY_DELAY": "1",
    "GDAL_HTTP_TIMEOUT": "60",
    "GDAL_HTTP_CONNECTTIMEOUT": "20",
    "GDAL_HTTP_MULTIPLEX": "YES",
    "VSI_CACHE": "TRUE",
    "GDAL_PAM_ENABLED": "NO",
}
SCL_GROUPS: dict[str, tuple[int, ...]] = {
    "water": (6,),
    "cloud": (8, 9, 10),
    "shadow": (3,),
    "snow": (11,),
    "land": (4, 5),
    "nodata": (0, 1),
    "other": (2, 7),
}
MASK_COLORS: dict[str, tuple[int, int, int, int]] = {
    "water": (0, 0, 0, 0),
    "cloud": (250, 250, 250, 190),
    "shadow": (30, 34, 52, 170),
    "snow": (170, 225, 250, 190),
    "land": (118, 108, 86, 140),
    "nodata": (40, 40, 40, 200),
    "other": (150, 150, 150, 120),
    "bright_water": (255, 196, 110, 170),
}


class RasterError(RuntimeError):
    pass


class RasterReadError(RasterError):
    pass


@dataclass(frozen=True)
class QualityShares:
    pixels: int
    water: float
    cloud: float
    shadow: float
    snow: float
    land: float
    nodata: float
    other: float
    bright_water: float | None

    @property
    def cloud_or_shadow(self) -> float:
        return self.cloud + self.shadow

    def as_dict(self) -> dict[str, float | int | None]:
        return {
            "pixels": self.pixels,
            "water": self.water,
            "cloud": self.cloud,
            "shadow": self.shadow,
            "snow": self.snow,
            "land": self.land,
            "nodata": self.nodata,
            "other": self.other,
            "bright_water": self.bright_water,
        }


@dataclass(frozen=True)
class RenderedLayer:
    png: bytes
    corners: list[list[float]]
    width: int
    height: int


def encode_png(pixels: np.ndarray) -> bytes:
    if pixels.ndim != 3 or pixels.shape[2] not in (3, 4):
        raise ValueError("expected an H×W×3 or H×W×4 array")
    height, width, channels = pixels.shape
    color_type = 6 if channels == 4 else 2
    rows = pixels.astype(np.uint8).reshape(height, width * channels)
    above = np.vstack([np.zeros((1, width * channels), dtype=np.uint8), rows[:-1]])
    filtered = rows - above
    raw = np.hstack([np.full((height, 1), 2, dtype=np.uint8), filtered]).tobytes()

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        )

    header = struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw, 6))
        + chunk(b"IEND", b"")
    )


def _window(dataset, geometry: BaseGeometry) -> tuple[Window, dict]:
    projected = transform_geom("EPSG:4326", dataset.crs, mapping(geometry))
    bounds = shape(projected).bounds
    full = Window(0, 0, dataset.width, dataset.height)
    try:
        window = from_bounds(*bounds, transform=dataset.transform)
        window = window.round_offsets().round_lengths().intersection(full)
    except WindowError as error:
        raise RasterError("район вне снимка") from error
    if window.width < 1 or window.height < 1:
        raise RasterError("район вне снимка")
    return window, projected


def _output_shape(window: Window, max_size: int | None) -> tuple[int, int]:
    height, width = int(window.height), int(window.width)
    if not max_size or max(height, width) <= max_size:
        return height, width
    scale = max_size / max(height, width)
    return max(1, round(height * scale)), max(1, round(width * scale))


def _read(
    href: str,
    geometry: BaseGeometry,
    max_size: int | None = None,
    shape_hint: tuple[int, int] | None = None,
    indexes: int | list[int] = 1,
) -> tuple[np.ndarray, Affine, object, Window, dict]:
    try:
        with rasterio.Env(**GDAL_OPTIONS), rasterio.open(href) as dataset:
            window, projected = _window(dataset, geometry)
            out_height, out_width = shape_hint or _output_shape(window, max_size)
            bands = len(indexes) if isinstance(indexes, list) else None
            out_shape = (bands, out_height, out_width) if bands else (out_height, out_width)
            data = dataset.read(
                indexes, window=window, out_shape=out_shape, resampling=Resampling.nearest
            )
            scale = Affine.scale(window.width / out_width, window.height / out_height)
            return data, dataset.window_transform(window) * scale, dataset.crs, window, projected
    except rasterio.errors.RasterioIOError as error:
        raise RasterReadError(f"снимок не читается: {error}") from error


def _classes(scl: np.ndarray) -> dict[str, np.ndarray]:
    return {name: np.isin(scl, codes) for name, codes in SCL_GROUPS.items()}


@dataclass(frozen=True)
class ClassRaster:
    scl: np.ndarray
    affine: Affine
    crs: object
    projected: dict
    reflectance: np.ndarray | None


_CLASS_CACHE: OrderedDict[tuple, ClassRaster] = OrderedDict()
_CLASS_CACHE_SIZE = 4
_CLASS_CACHE_LOCK = threading.Lock()


def _class_raster(scene: Scene, geometry: BaseGeometry, max_size: int | None) -> ClassRaster:
    if "scl" not in scene.assets:
        raise RasterError("у сцены нет маски классов SCL")
    key = (scene.id, scene.assets["scl"], geometry.wkb, max_size)
    with _CLASS_CACHE_LOCK:
        cached = _CLASS_CACHE.get(key)
        if cached is not None:
            _CLASS_CACHE.move_to_end(key)
            return cached
    try:
        scl, affine, crs, _, projected = _read(scene.assets["scl"], geometry, max_size)
        reflectance = None
        if "nir" in scene.assets:
            nir, *_ = _read(scene.assets["nir"], geometry, shape_hint=scl.shape)
            reflectance = nir.astype("float32") * scene.reflectance_scale + scene.reflectance_offset
    except RasterReadError as error:
        raise RasterReadError(f"маска SCL не читается: {error.__cause__}") from error
    result = ClassRaster(scl, affine, crs, projected, reflectance)
    with _CLASS_CACHE_LOCK:
        _CLASS_CACHE[key] = result
        while len(_CLASS_CACHE) > _CLASS_CACHE_SIZE:
            _CLASS_CACHE.popitem(last=False)
    return result


def quality_shares(
    scene: Scene,
    geometry: BaseGeometry,
    bright_reflectance: float | None = None,
    max_size: int | None = 1024,
) -> QualityShares:
    raster = _class_raster(scene, geometry, max_size)
    scl = raster.scl
    inside = geometry_mask(
        [raster.projected], out_shape=scl.shape, transform=raster.affine, invert=True
    )
    total = int(inside.sum())
    if total == 0:
        raise RasterError("в полосе нет ни одного пикселя маски")
    classes = _classes(scl)
    shares = {name: float((mask & inside).sum()) / total for name, mask in classes.items()}
    bright = None
    if bright_reflectance is not None and raster.reflectance is not None:
        water = classes["water"] & inside
        water_count = int(water.sum())
        if water_count:
            bright = float(((raster.reflectance > bright_reflectance) & water).sum()) / water_count
    return QualityShares(pixels=total, bright_water=bright, **shares)


def layer_corners(affine: Affine, crs, height: int, width: int) -> list[list[float]]:
    pixel_corners = [(0, 0), (width, 0), (width, height), (0, height)]
    xs, ys = zip(*(affine @ corner for corner in pixel_corners), strict=True)
    lons, lats = transform_points(crs, "EPSG:4326", list(xs), list(ys))
    return [[round(lon, 7), round(lat, 7)] for lon, lat in zip(lons, lats, strict=True)]


def render_true_color(scene: Scene, geometry: BaseGeometry, max_size: int = 1600) -> RenderedLayer:
    if "visual" not in scene.assets:
        raise RasterError("у сцены нет цветного снимка")
    rgb, affine, crs, _, _ = _read(scene.assets["visual"], geometry, max_size, indexes=[1, 2, 3])
    pixels = np.moveaxis(rgb, 0, -1)
    alpha = np.where(pixels.max(axis=2) > 0, 255, 0).astype(np.uint8)
    rgba = np.dstack([pixels, alpha])
    height, width = alpha.shape
    return RenderedLayer(encode_png(rgba), layer_corners(affine, crs, height, width), width, height)


def render_quality_mask(
    scene: Scene,
    geometry: BaseGeometry,
    bright_reflectance: float | None,
    max_size: int = 1600,
) -> RenderedLayer:
    raster = _class_raster(scene, geometry, max_size)
    scl = raster.scl
    rgba = np.zeros((*scl.shape, 4), dtype=np.uint8)
    classes = _classes(scl)
    for name, mask in classes.items():
        rgba[mask] = MASK_COLORS[name]
    if bright_reflectance is not None and raster.reflectance is not None:
        rgba[(raster.reflectance > bright_reflectance) & classes["water"]] = MASK_COLORS[
            "bright_water"
        ]
    height, width = scl.shape
    corners = layer_corners(raster.affine, raster.crs, height, width)
    return RenderedLayer(encode_png(rgba), corners, width, height)
