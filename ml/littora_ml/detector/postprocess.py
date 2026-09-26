from __future__ import annotations

from typing import Any

import numpy as np
from scipy.ndimage import binary_dilation, binary_erosion, binary_fill_holes
from scipy.ndimage import label as connected

from littora_ml.detector.evaluation import choose_threshold
from littora_ml.detector.metrics import evaluate
from littora_ml.detector.objects import apply_ship_veto, ship_rules

SCL_EXCLUDED = (0, 1, 4, 5, 8, 9, 11)
SEA_CLASSES = (6, 10)
SEA_GROW = -2
SEA_MAX_HOLE = 100


def scl_filter(scores: np.ndarray, scl: np.ndarray) -> np.ndarray:
    return np.where(np.isin(scl, SCL_EXCLUDED), 0.0, scores)


def remove_small(mask: np.ndarray, min_pixels: int) -> np.ndarray:
    if min_pixels <= 1:
        return mask
    out = np.zeros_like(mask)
    structure = np.ones((3, 3), dtype=bool)
    for index in range(len(mask)):
        labels, count = connected(mask[index], structure=structure)
        if not count:
            continue
        sizes = np.bincount(labels.ravel())
        keep = sizes >= min_pixels
        keep[0] = False
        out[index] = keep[labels]
    return out


def apply(scores: np.ndarray, scl: np.ndarray | None, options: dict[str, Any]) -> np.ndarray:
    if options.get("scl") and scl is not None:
        scores = scl_filter(scores, scl)
    return scores


def search(
    val_scores: np.ndarray,
    val_labels: np.ndarray,
    val_scl: np.ndarray | None,
    val_images: np.ndarray | None = None,
) -> list[dict[str, Any]]:
    results = []
    rules = ship_rules() if val_images is not None else [None]
    for use_scl in (False, True) if val_scl is not None else (False,):
        base = apply(val_scores, val_scl, {"scl": use_scl})
        threshold, _ = choose_threshold(base, val_labels)
        for rule in rules:
            scores = apply_ship_veto(base, val_images, threshold, rule) if rule else base
            for min_pixels in (1, 2, 3):
                mask = remove_small(scores >= threshold, min_pixels)
                filtered = np.where(mask, np.maximum(scores, threshold), 0.0)
                metrics = evaluate(filtered, val_labels, threshold)
                ships = metrics["false_positives_by_class"].get("ship", {})
                results.append(
                    {
                        "scl": use_scl,
                        "ship_veto": rule,
                        "min_pixels": min_pixels,
                        "threshold": threshold,
                        "val_f1": metrics["f1"],
                        "val_precision": metrics["precision"],
                        "val_recall": metrics["recall"],
                        "val_ship_false_positives": ships.get("false_positives", 0),
                    }
                )
    return sorted(results, key=lambda row: (-round(row["val_f1"], 6), row["ship_veto"] is not None))


def finalize(
    scores: np.ndarray,
    scl: np.ndarray | None,
    choice: dict[str, Any],
    images: np.ndarray | None = None,
) -> np.ndarray:
    scores = apply(scores, scl, choice)
    threshold = choice["threshold"]
    if choice.get("ship_veto") and images is not None:
        scores = apply_ship_veto(scores, images, threshold, choice["ship_veto"])
    mask = remove_small(scores >= threshold, choice["min_pixels"])
    return np.where(mask, np.maximum(scores, threshold), np.minimum(scores, threshold * 0.999))


def postprocessing_report(
    patches, split, val_scores: np.ndarray, test_scores: np.ndarray, max_confidence_code: int
) -> dict[str, Any] | None:
    from littora_ml.detector.evaluation import usable_labels

    scl_path = patches.root / "scl.npy"
    values = split.to_numpy()
    val_index, test_index = np.flatnonzero(values == "val"), np.flatnonzero(values == "test")
    scl = np.load(scl_path) if scl_path.exists() else None
    val_labels = usable_labels(patches, val_index, max_confidence_code)
    test_labels = usable_labels(patches, test_index, max_confidence_code)
    val_images = np.asarray(patches.images[val_index], dtype=np.float32)
    options = search(
        val_scores, val_labels, scl[val_index] if scl is not None else None, val_images
    )
    best = options[0]
    test_images = np.asarray(patches.images[test_index], dtype=np.float32)
    final = finalize(test_scores, scl[test_index] if scl is not None else None, best, test_images)
    return {
        "search": options,
        "chosen": best,
        "test": evaluate(final, test_labels, best["threshold"]),
    }


def sea_mask(scl: np.ndarray, grow: int = SEA_GROW, max_hole: int = SEA_MAX_HOLE) -> np.ndarray:
    water = np.isin(scl, SEA_CLASSES)
    holes, count = connected(binary_fill_holes(water) & ~water)
    if count:
        sizes = np.bincount(holes.ravel())
        small = np.flatnonzero(sizes <= max_hole)
        water |= np.isin(holes, small[small > 0])
    if grow > 0:
        return binary_dilation(water, iterations=grow)
    if grow < 0:
        return binary_erosion(water, iterations=-grow, border_value=1)
    return water
