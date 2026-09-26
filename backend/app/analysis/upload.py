from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np
import rasterio
from affine import Affine
from rasterio.errors import RasterioIOError
from rasterio.io import MemoryFile
from rasterio.transform import from_bounds
from rasterio.warp import transform_bounds
from scipy.ndimage import binary_fill_holes
from scipy.ndimage import label as connected

from app.core.errors import AppError
from app.earth.bands import BandStack

MAX_BYTES = 150 * 1024 * 1024
BANDS = ("B01", "B02", "B03", "B04", "B05", "B06", "B07", "B08", "B8A", "B11", "B12")
ORDERS = {
    11: list(range(11)),
    12: [0, 1, 2, 3, 4, 5, 6, 7, 8, 10, 11],
    13: [0, 1, 2, 3, 4, 5, 6, 7, 8, 11, 12],
}
REFLECTANCE_FLOOR = 0.0001
DN_SCALE = 10000.0
BOA_OFFSET = 0.1
OFFSET_B02 = 0.1
WATER_NDWI = 0.0
MAX_HOLE = 100
PIXEL_RANGE_M = (5.0, 20.0)
METERS_PER_DEGREE = 111_320.0
BAND_NAME = re.compile(r"B0?(\d{1,2}A?)", re.IGNORECASE)


class UploadError(AppError):
    pass


@dataclass
class Upload:
    stack: BandStack | None
    rgb: np.ndarray
    valid: np.ndarray
    scl: np.ndarray
    crs: str
    transform: Affine
    bounds: tuple[float, float, float, float]
    bands: int
    notes: list[str] = field(default_factory=list)
    visible: np.ndarray | None = None


def _band_key(description: str | None) -> str | None:
    if not description:
        return None
    match = BAND_NAME.search(description)
    if not match:
        return None
    number = match.group(1).upper()
    return "B8A" if number == "8A" else f"B{int(number):02d}"


def _order(descriptions: tuple[str | None, ...], count: int) -> list[int] | None:
    keys = [_band_key(description) for description in descriptions]
    if all(name in keys for name in BANDS):
        return [keys.index(name) for name in BANDS]
    return ORDERS.get(count)


def _scale(raw: np.ndarray, valid: np.ndarray, notes: list[str]) -> np.ndarray:
    values = raw[:, valid] if valid.any() else raw.reshape(raw.shape[0], -1)
    if values.size and float(np.nanmax(values)) > 1.5:
        raw = raw / DN_SCALE
        notes.append("значения приняты за цифровые отсчёты L2A и поделены на 10 000")
        blue = raw[1][valid]
        if blue.size and float(np.percentile(blue, 5)) > OFFSET_B02:
            raw = raw - BOA_OFFSET
            notes.append("обнаружено смещение L2A baseline 04.00+: вычтено 0,1")
    return np.where(valid, np.maximum(raw, REFLECTANCE_FLOOR), 0.0).astype(np.float32)


def _declared(scales, offsets, count: int) -> tuple[np.ndarray, np.ndarray] | None:
    scale = np.array(scales if scales and len(scales) == count else [1.0] * count, dtype=np.float32)
    offset = np.array(
        offsets if offsets and len(offsets) == count else [0.0] * count, dtype=np.float32
    )
    if np.allclose(scale, 1.0) and np.allclose(offset, 0.0):
        return None
    return scale, offset


def water_scl(image: np.ndarray, valid: np.ndarray) -> np.ndarray:
    green, nir = image[2], image[7]
    water = valid & ((green - nir) / np.maximum(green + nir, 1e-6) > WATER_NDWI)
    holes, count = connected(binary_fill_holes(water) & ~water)
    if count:
        sizes = np.bincount(holes.ravel())
        small = np.flatnonzero(sizes <= MAX_HOLE)
        water |= np.isin(holes, small[small > 0])
    return np.where(valid, np.where(water, 6, 5), 0).astype(np.uint8)


def _stretch(rgb: np.ndarray, valid: np.ndarray) -> np.ndarray:
    values = rgb[:, valid] if valid.any() else rgb.reshape(3, -1)
    high = float(np.percentile(values, 99)) if values.size else 1.0
    scaled = np.clip(rgb / max(high, 1e-6), 0, 1) ** (1 / 2.2) * 255
    alpha = np.where(valid, 255, 0)[None]
    return np.moveaxis(np.concatenate([scaled, alpha]), 0, -1).astype(np.uint8)


def _display(rgb: np.ndarray, valid: np.ndarray) -> np.ndarray:
    if float(rgb.max()) <= 255 and np.all(np.mod(rgb, 1) == 0):
        alpha = np.where(valid, 255, 0)[None]
        return np.moveaxis(np.concatenate([rgb, alpha]), 0, -1).astype(np.uint8)
    return _stretch(rgb, valid)


def _georeference(dataset, bbox: tuple[float, float, float, float] | None, notes: list[str]):
    if dataset.crs is not None:
        crs = dataset.crs.to_string()
        transform = dataset.transform
        size_x = abs(transform.a)
        if dataset.crs.is_geographic:
            size_x *= METERS_PER_DEGREE * np.cos(np.radians(dataset.bounds.bottom))
        if not PIXEL_RANGE_M[0] <= size_x <= PIXEL_RANGE_M[1]:
            notes.append(f"пиксель ≈{size_x:.0f} м, модель обучена на 10 м — результат ненадёжен")
        bounds = transform_bounds(dataset.crs, "EPSG:4326", *dataset.bounds)
        return crs, transform, bounds
    if bbox is None:
        raise UploadError(
            "У файла нет привязки к карте: загрузите GeoTIFF или откройте нужный район"
        )
    notes.append("привязки в файле нет: снимок растянут на видимую часть карты")
    return "EPSG:4326", from_bounds(*bbox, dataset.width, dataset.height), bbox


def read_upload(
    content: bytes, max_pixels: int, bbox: tuple[float, float, float, float] | None = None
) -> Upload:
    if not content:
        raise UploadError("Файл пустой")
    if len(content) > MAX_BYTES:
        raise UploadError("Файл больше 150 МБ")
    notes: list[str] = []
    try:
        with MemoryFile(content) as memory, memory.open() as dataset:
            if dataset.width * dataset.height > max_pixels:
                raise UploadError(f"Снимок больше {max_pixels:,} пикселей".replace(",", " "))
            crs, transform, bounds = _georeference(dataset, bbox, notes)
            raw = dataset.read().astype(np.float32)
            scales, offsets = dataset.scales, dataset.offsets
            nodata = dataset.nodata
            descriptions = dataset.descriptions
            count = dataset.count
    except RasterioIOError as error:
        raise UploadError("Файл не читается как растр: нужен GeoTIFF, PNG или JPEG") from error
    except rasterio.errors.RasterioError as error:
        raise UploadError(f"Файл не читается: {error}") from error
    raw = np.nan_to_num(raw, nan=0.0)
    if nodata is not None:
        raw = np.where(raw == nodata, 0.0, raw)
    valid = raw.max(axis=0) > 0
    order = _order(descriptions, count)
    if order is None:
        rgb = raw[:3] if count >= 3 else np.repeat(raw[:1], 3, axis=0)
        scl = np.where(valid, 6, 0).astype(np.uint8)
        display = _display(rgb, valid)
        notes.append(
            f"в файле {count} канал(а); детектору нужны 11 каналов Sentinel-2 "
            "(B01–B12 без B09 и B10) — по видимым каналам плавающий мусор не определяется"
        )
        return Upload(None, display, valid, scl, crs, transform, bounds, count, notes, visible=rgb)
    declared = _declared(scales, offsets, count)
    if declared is not None:
        scale, offset = declared
        image = raw * scale[:, None, None] + offset[:, None, None]
        image = np.where(valid, np.maximum(image[order], REFLECTANCE_FLOOR), 0.0).astype(np.float32)
        notes.append("масштаб и смещение взяты из метаданных файла")
    else:
        image = _scale(raw[order], valid, notes)
    scl = water_scl(image, valid)
    stack = BandStack(image, scl, crs, transform)
    rgb = _stretch(image[[3, 2, 1]], valid)
    return Upload(stack, rgb, valid, scl, crs, transform, bounds, count, notes)


ANOMALY_WINDOW = 31
ANOMALY_Z = 4.0
ANOMALY_CONTRAST = 15.0
ANOMALY_MIN_PIXELS = 2
ANOMALY_LIMIT = 200
ANOMALY_COLOR = (230, 60, 200, 230)


def rgb_anomalies(rgb: np.ndarray, valid: np.ndarray) -> tuple[np.ndarray, list[dict]]:
    from scipy.ndimage import center_of_mass, uniform_filter

    rgb = rgb.astype(np.float32)
    luminance = rgb.mean(axis=0)
    if float(luminance.max()) <= 1.5:
        luminance = luminance * 255
    red, green, blue = rgb[0], rgb[1], rgb[2]
    water = valid & (blue >= red) & (blue >= 0.8 * green)
    holes, count = connected(binary_fill_holes(water) & ~water)
    if count:
        sizes = np.bincount(holes.ravel())
        small = np.flatnonzero(sizes <= MAX_HOLE)
        water |= np.isin(holes, small[small > 0])
    valid = valid & water
    weight = uniform_filter(valid.astype(np.float32), ANOMALY_WINDOW)
    mean = uniform_filter(np.where(valid, luminance, 0), ANOMALY_WINDOW) / np.maximum(weight, 1e-6)
    square = uniform_filter(np.where(valid, luminance**2, 0), ANOMALY_WINDOW) / np.maximum(
        weight, 1e-6
    )
    spread = np.sqrt(np.maximum(square - mean**2, 0))
    excess = luminance - mean
    bright = valid & (excess > ANOMALY_CONTRAST) & (excess > ANOMALY_Z * np.maximum(spread, 2.0))
    labels, count = connected(bright, structure=np.ones((3, 3), dtype=bool))
    overlay = np.zeros((*valid.shape, 4), dtype=np.uint8)
    if not count:
        return overlay, []
    sizes = np.bincount(labels.ravel())
    strength = np.bincount(labels.ravel(), weights=np.where(bright, excess, 0).ravel())
    kept = [index for index in range(1, count + 1) if sizes[index] >= ANOMALY_MIN_PIXELS]
    kept = sorted(kept, key=lambda index: -strength[index] / sizes[index])[:ANOMALY_LIMIT]
    overlay[np.isin(labels, kept)] = ANOMALY_COLOR
    centers = center_of_mass(bright, labels, kept)
    return overlay, [
        {
            "pixels": int(sizes[index]),
            "contrast": round(float(strength[index] / sizes[index]), 1),
            "row": float(row),
            "col": float(col),
        }
        for index, (row, col) in zip(kept, centers, strict=True)
    ]
