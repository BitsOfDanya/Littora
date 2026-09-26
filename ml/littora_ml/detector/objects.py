from __future__ import annotations

import itertools
from typing import Any

import numpy as np
from scipy.ndimage import label as connected

from littora_ml.detector.features import spectral_indices
from littora_ml.detector.marida import BANDS

VISIBLE = [BANDS.index(name) for name in ("B02", "B03", "B04")]
SWIR = BANDS.index("B11")
STRUCTURE = np.ones((3, 3), dtype=bool)
BRIGHT_ANOMALY = 0.05
BRIGHT_SWIR = 0.05
NDVI_MAX = 0.05
SHIP_GRID = {"min_area": (6, 8, 10), "min_swir": (0.05, 0.06, 0.08)}


def bright_objects(image: np.ndarray) -> tuple[np.ndarray, int]:
    valid = image[1] != 0
    visible = image[VISIBLE].mean(axis=0)
    background = float(np.median(visible[valid])) if valid.any() else 0.0
    bright = valid & ((visible - background > BRIGHT_ANOMALY) | (image[SWIR] > BRIGHT_SWIR))
    return connected(bright, structure=STRUCTURE)


def ship_like(image: np.ndarray, rule: dict[str, Any]) -> np.ndarray:
    labels, count = bright_objects(image)
    if not count:
        return np.zeros(image.shape[1:], dtype=bool)
    index = np.arange(1, count + 1)
    area = np.bincount(labels.ravel(), minlength=count + 1)[1:]
    swir_max = np.zeros(count + 1)
    np.maximum.at(swir_max, labels.ravel(), image[SWIR].ravel())
    ndvi = spectral_indices(image)[0]
    ndvi_median = np.array([np.median(ndvi[labels == i]) for i in index])
    veto = (
        (area >= rule["min_area"]) & (swir_max[1:] >= rule["min_swir"]) & (ndvi_median < NDVI_MAX)
    )
    return np.concatenate([[False], veto])[labels]


def apply_ship_veto(
    scores: np.ndarray, images: np.ndarray, threshold: float, rule: dict[str, Any] | None
) -> np.ndarray:
    if not rule:
        return scores
    out = scores.copy()
    for position in range(len(scores)):
        predicted = scores[position] >= threshold
        if not predicted.any():
            continue
        image = np.asarray(images[position], dtype=np.float32)
        components, _ = connected(predicted, structure=STRUCTURE)
        vetoed_area = ship_like(image, rule)
        touched = np.unique(components[vetoed_area & predicted])
        drop = np.isin(components, touched[touched > 0])
        out[position][drop] = np.minimum(out[position][drop], threshold * 0.999)
    return out


def ship_rules() -> list[dict[str, Any] | None]:
    grid = [
        {"min_area": area, "min_swir": swir}
        for area, swir in itertools.product(SHIP_GRID["min_area"], SHIP_GRID["min_swir"])
    ]
    return [None, *grid]
