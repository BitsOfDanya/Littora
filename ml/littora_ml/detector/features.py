from __future__ import annotations

import numpy as np
from scipy.ndimage import uniform_filter

from littora_ml.detector.marida import BANDS

WAVELENGTH = {"B04": 664.6, "B08": 832.8, "B11": 1613.7}
INDEX_NAMES = ("NDVI", "FDI", "FAI", "NDWI", "NDMI", "PI", "RE_SLOPE", "SWIR_RATIO")
LOCAL_SOURCES = ("B08", "FDI", "NDVI")
EPS = 1e-6


def band(image: np.ndarray, name: str) -> np.ndarray:
    return image[BANDS.index(name)].astype(np.float32)


def _ratio(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return (a - b) / (a + b + EPS)


def spectral_indices(image: np.ndarray) -> np.ndarray:
    red, nir = band(image, "B04"), band(image, "B08")
    green, re1 = band(image, "B03"), band(image, "B05")
    re2, re3 = band(image, "B06"), band(image, "B07")
    swir1, swir2 = band(image, "B11"), band(image, "B12")
    span = (WAVELENGTH["B08"] - WAVELENGTH["B04"]) / (WAVELENGTH["B11"] - WAVELENGTH["B04"])
    fdi = nir - (re2 + (swir1 - re2) * span * 10)
    fai = nir - (red + (swir1 - red) * span)
    return np.stack(
        [
            _ratio(nir, red),
            fdi,
            fai,
            _ratio(green, nir),
            _ratio(nir, swir1),
            nir / (nir + red + EPS),
            re3 - re1,
            swir1 / (swir2 + EPS),
        ]
    ).astype(np.float32)


def local_statistics(stack: np.ndarray, names: list[str], size: int = 3) -> np.ndarray:
    layers = []
    for name in LOCAL_SOURCES:
        values = stack[names.index(name)]
        mean = uniform_filter(values, size=size, mode="reflect")
        square = uniform_filter(values * values, size=size, mode="reflect")
        layers.extend([values - mean, np.sqrt(np.maximum(square - mean * mean, 0))])
    return np.stack(layers).astype(np.float32)


def feature_names(
    indices: bool = True, local: bool = True, bands: list[str] | None = None
) -> list[str]:
    names = list(bands or BANDS)
    if indices:
        names += list(INDEX_NAMES)
    if local:
        names += [f"{source}_{kind}" for source in LOCAL_SOURCES for kind in ("anomaly", "std")]
    return names


def pixel_features(
    image: np.ndarray, indices: bool = True, local: bool = True, bands: list[str] | None = None
) -> np.ndarray:
    full = image.astype(np.float32)
    derived = spectral_indices(image)
    layers = [full[[BANDS.index(name) for name in bands]] if bands else full]
    if indices:
        layers.append(derived)
    if local:
        combined = np.concatenate([full, derived])
        layers.append(local_statistics(combined, list(BANDS) + list(INDEX_NAMES)))
    return np.concatenate(layers)
