from __future__ import annotations

from typing import Any

import numpy as np
from scipy.ndimage import uniform_filter

from app.earth.raster import encode_png

B03, B04, B06, B08, B11 = 2, 3, 5, 7, 9
WAVELENGTH_NM = {"red": 664.6, "nir": 832.8, "swir": 1613.7}
FDI_FACTOR = (
    (WAVELENGTH_NM["nir"] - WAVELENGTH_NM["red"])
    / (WAVELENGTH_NM["swir"] - WAVELENGTH_NM["red"])
    * 10
)
FALSE_COLOR_MAX = 0.3
GAMMA = 1 / 2.2
FDI_RANGE = (-0.02, 0.06)
NDVI_RANGE = (-0.3, 0.5)
PLASTIC_NIR = 0.15
PLASTIC_NIR_RANGE = (0.08, 0.30)
BACKGROUND_WINDOW = 21
PIXEL_M2 = 100.0
COVERAGE_STOPS = (0.01, 0.03, 0.06, 0.1, 0.15, 0.2)
COVERAGE_COLORS = ("#1F2F4A", "#3B4A6B", "#6F7470", "#A69C5E", "#DCC24F", "#FDEB6E")
INDEX_COLORS = ((49, 54, 149), (116, 173, 209), (255, 255, 191), (244, 109, 67), (165, 0, 38))


def fdi(image: np.ndarray) -> np.ndarray:
    nir, re2, swir = image[B08], image[B06], image[B11]
    return nir - (re2 + (swir - re2) * FDI_FACTOR)


def ndvi(image: np.ndarray) -> np.ndarray:
    nir, red = image[B08], image[B04]
    return (nir - red) / np.maximum(nir + red, 1e-6)


def _hex(color: str) -> tuple[int, int, int]:
    return tuple(int(color[index : index + 2], 16) for index in (1, 3, 5))


def false_color_png(image: np.ndarray, valid: np.ndarray) -> bytes:
    rgb = np.stack([image[B08], image[B04], image[B03]], axis=-1)
    scaled = np.clip(rgb / FALSE_COLOR_MAX, 0, 1) ** GAMMA * 255
    alpha = np.where(valid, 255, 0)[..., None]
    return encode_png(np.concatenate([scaled, alpha], axis=-1).astype(np.uint8))


def index_png(values: np.ndarray, valid: np.ndarray, low: float, high: float) -> bytes:
    colors = np.array(INDEX_COLORS, dtype=np.float32)
    position = np.clip((values - low) / (high - low), 0, 1) * (len(colors) - 1)
    lower = np.floor(position).astype(int)
    upper = np.minimum(lower + 1, len(colors) - 1)
    fraction = (position - lower)[..., None]
    rgb = colors[lower] * (1 - fraction) + colors[upper] * fraction
    alpha = np.where(valid, 230, 0)[..., None]
    return encode_png(np.concatenate([rgb, alpha], axis=-1).astype(np.uint8))


def water_background(nir: np.ndarray, sea: np.ndarray) -> np.ndarray:
    weight = uniform_filter(sea.astype(np.float32), BACKGROUND_WINDOW)
    total = uniform_filter(np.where(sea, nir, 0).astype(np.float32), BACKGROUND_WINDOW)
    return np.where(weight > 0.05, total / np.maximum(weight, 1e-6), np.nan)


def coverage_fraction(nir: np.ndarray, background: np.ndarray, endmember: float) -> np.ndarray:
    span = endmember - background
    fraction = np.where(span > 0.01, (nir - background) / np.maximum(span, 1e-6), np.nan)
    return np.clip(fraction, 0, 1)


def coverage_png(fraction: np.ndarray, shown: np.ndarray) -> bytes:
    colors = np.array([_hex(color) for color in COVERAGE_COLORS], dtype=np.uint8)
    index = np.clip(
        np.searchsorted(COVERAGE_STOPS, np.nan_to_num(fraction), side="right") - 1, 0, 5
    )
    rgb = colors[index]
    alpha = np.where(shown & np.isfinite(fraction), 235, 0).astype(np.uint8)[..., None]
    return encode_png(np.concatenate([rgb, alpha], axis=-1))


class Coverage:
    def __init__(self, image: np.ndarray, sea: np.ndarray) -> None:
        nir = image[B08]
        background = water_background(nir, sea)
        self.central = coverage_fraction(nir, background, PLASTIC_NIR)
        self.high = coverage_fraction(nir, background, PLASTIC_NIR_RANGE[0])
        self.low = coverage_fraction(nir, background, PLASTIC_NIR_RANGE[1])

    def zone(self, inside: np.ndarray) -> dict[str, Any] | None:
        central = self.central[inside]
        if not np.isfinite(central).any():
            return None
        low, high = self.low[inside], self.high[inside]
        return {
            "mean": round(float(np.nanmean(central)), 4),
            "low": round(float(np.nanmean(low)), 4),
            "high": round(float(np.nanmean(high)), 4),
            "area_m2": round(float(np.nansum(central) * PIXEL_M2), 1),
            "area_m2_low": round(float(np.nansum(low) * PIXEL_M2), 1),
            "area_m2_high": round(float(np.nansum(high) * PIXEL_M2), 1),
            "endmember_nir": PLASTIC_NIR,
            "endmember_nir_range": list(PLASTIC_NIR_RANGE),
        }
