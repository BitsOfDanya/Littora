from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from scipy.ndimage import binary_dilation

RULE_FILE = "vessels.json"
WATER_SCL = 6
MIN_WATER = 20
VISIBLE = (1, 2, 3)
B04, B08, B11 = 3, 7, 9
STRUCTURE = np.ones((3, 3), dtype=bool)


def load_rule(folder: Path) -> dict[str, Any] | None:
    path = folder / RULE_FILE
    if not path.exists():
        return None
    try:
        rule = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    required = ("window", "swir_peak", "visible_contrast")
    return rule if all(key in rule for key in required) else None


def object_features(
    image: np.ndarray,
    scl: np.ndarray,
    labels: np.ndarray,
    index: int,
    bounds: tuple[slice, slice],
    window: int,
) -> dict[str, float]:
    rows, cols = bounds
    height, width = labels.shape
    top, bottom = max(rows.start - window, 0), min(rows.stop + window, height)
    left, right = max(cols.start - window, 0), min(cols.stop + window, width)
    crop = image[:, top:bottom, left:right]
    mask = labels[top:bottom, left:right] == index
    valid = crop[1] != 0
    near = binary_dilation(mask, STRUCTURE, 1)
    ring = valid & ~binary_dilation(mask, STRUCTURE, 2)
    water = ring & (scl[top:bottom, left:right] == WATER_SCL)
    base = water if water.sum() >= MIN_WATER else ring
    if not base.any():
        base = valid
    visible = crop[list(VISIBLE)].mean(axis=0)
    contrast = visible - float(np.median(visible[base])) if base.any() else visible
    inside = near & valid
    if not inside.any():
        inside = near
    body = mask & valid if (mask & valid).any() else mask
    return {
        "swir_peak": round(float(crop[B11][inside].max()), 4),
        "visible_contrast": round(float(contrast[inside].max()), 4),
        "nir_red": round(float(np.median(crop[B08][body] - crop[B04][body])), 4),
    }


def decimal(value: float) -> str:
    return f"{value:.3f}".replace(".", ",")


def vessel_flag(features: dict[str, float], rule: dict[str, Any]) -> dict[str, Any] | None:
    reasons = []
    if features["swir_peak"] >= rule["swir_peak"]:
        reasons.append(
            f"яркость B11 {decimal(features['swir_peak'])} ≥ {decimal(rule['swir_peak'])}: "
            "мусор так ярок в SWIR редко"
        )
    if features["visible_contrast"] >= rule["visible_contrast"]:
        reasons.append(
            f"видимая яркость выше воды на {decimal(features['visible_contrast'])} "
            f"≥ {decimal(rule['visible_contrast'])}"
        )
    if not reasons:
        return None
    return {"kind": "vessel", "label": "вероятно судно", "evidence": reasons}
