from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.ndimage import distance_transform_edt

from littora_ml.common.io import write_json
from littora_ml.common.paths import REPORTS
from littora_ml.detector.dataset import PatchSet
from littora_ml.detector.metrics import best_threshold, evaluate, rates

PIXEL_KM2 = 1e-4
FAR_FROM_DEBRIS_PX = 5
BOOTSTRAP = 2000

Scorer = Callable[[np.ndarray], np.ndarray]


def usable_labels(patches: PatchSet, indices: np.ndarray, max_confidence_code: int) -> np.ndarray:
    labels = patches.labels[indices].copy()
    valid = patches.valid[indices]
    confidence = patches.confidence[indices]
    labels[~valid] = 0
    if max_confidence_code < 3:
        labels[(confidence > max_confidence_code) | (confidence == 0)] = 0
    return labels


def score_patches(
    scorer: Scorer, patches: PatchSet, indices: np.ndarray, batch: int = 16
) -> np.ndarray:
    maps = np.zeros((len(indices), *patches.labels.shape[1:]), dtype=np.float32)
    for start in range(0, len(indices), batch):
        chunk = indices[start : start + batch]
        images = np.asarray(patches.images[chunk], dtype=np.float32)
        maps[start : start + len(chunk)] = scorer(images)
    return maps


def scene_groups(patches: PatchSet, indices: np.ndarray) -> np.ndarray:
    scenes = patches.table["scene"].to_numpy()[indices]
    shape = patches.labels.shape[1:]
    return np.broadcast_to(scenes[:, None, None], (len(indices), *shape))


def choose_threshold(scores: np.ndarray, labels: np.ndarray, positive=(1,)) -> tuple[float, float]:
    labeled = labels > 0
    truth = np.isin(labels[labeled], positive)
    return best_threshold(scores[labeled], truth)


def unlabeled_alarms(
    scores: np.ndarray, patches: PatchSet, indices: np.ndarray, threshold: float
) -> dict[str, Any]:
    labels = patches.labels[indices]
    valid = patches.valid[indices]
    far = np.zeros_like(valid)
    for position in range(len(indices)):
        debris = labels[position] == 1
        distance = (
            distance_transform_edt(~debris) if debris.any() else np.full(debris.shape, np.inf)
        )
        far[position] = distance > FAR_FROM_DEBRIS_PX
    candidates = valid & (labels == 0) & far
    alarms = candidates & (scores >= threshold)
    area_km2 = float(candidates.sum()) * PIXEL_KM2
    return {
        "unlabeled_valid_km2": round(area_km2, 3),
        "alarm_pixels": int(alarms.sum()),
        "alarm_share": float(alarms.sum() / max(candidates.sum(), 1)),
        "alarm_pixels_per_100km2": float(alarms.sum() / max(area_km2, 1e-9) * 100),
        "definition": (
            "срабатывания на неразмеченной валидной воде дальше "
            f"{FAR_FROM_DEBRIS_PX} пикс. от размеченного мусора"
        ),
    }


def scene_bootstrap(
    scores: np.ndarray, labels: np.ndarray, scenes: np.ndarray, threshold: float, seed: int = 0
) -> dict[str, list[float]]:
    labeled = labels > 0
    per_scene = {}
    for scene in np.unique(scenes):
        mask = labeled & (scenes[:, None, None] == scene)
        truth = labels[mask] == 1
        predicted = scores[mask] >= threshold
        per_scene[scene] = np.array(
            [(predicted & truth).sum(), (predicted & ~truth).sum(), (~predicted & truth).sum()]
        )
    keys = list(per_scene)
    counts = np.stack([per_scene[key] for key in keys])
    rng = np.random.default_rng(seed)
    samples = {name: [] for name in ("precision", "recall", "f1", "iou")}
    for _ in range(BOOTSTRAP):
        chosen = counts[rng.integers(0, len(keys), len(keys))].sum(axis=0)
        values = rates({"tp": chosen[0], "fp": chosen[1], "fn": chosen[2]})
        for name in samples:
            samples[name].append(values[name])
    return {
        name: [float(np.quantile(values, 0.025)), float(np.quantile(values, 0.975))]
        for name, values in samples.items()
    }


def report(
    name: str,
    config: dict[str, Any],
    patches: PatchSet,
    split: pd.Series,
    val_scores: np.ndarray,
    test_scores: np.ndarray,
    max_confidence_code: int = 3,
    extra: dict[str, Any] | None = None,
    threshold: float | None = None,
) -> dict[str, Any]:
    val_index = np.flatnonzero(split.to_numpy() == "val")
    test_index = np.flatnonzero(split.to_numpy() == "test")
    val_labels = usable_labels(patches, val_index, max_confidence_code)
    test_labels = usable_labels(patches, test_index, max_confidence_code)
    chosen, _ = choose_threshold(val_scores, val_labels)
    if threshold is not None:
        chosen = threshold
    val_scenes = patches.table["scene"].to_numpy()[val_index]
    test_scenes = patches.table["scene"].to_numpy()[test_index]
    result = {
        "name": name,
        "code_sha256": code_fingerprint(),
        "config": {key: value for key, value in config.items() if not key.startswith("_")},
        "config_file": config.get("_path"),
        "config_sha256": config.get("_sha256"),
        "data": patches.root.name,
        "threshold": chosen,
        "threshold_source": "fixed" if threshold is not None else "val_max_f1",
        "val": evaluate(val_scores, val_labels, chosen, groups=scene_groups(patches, val_index)),
        "test": evaluate(
            test_scores, test_labels, chosen, groups=scene_groups(patches, test_index)
        ),
        "test_ci95_scene_bootstrap": scene_bootstrap(test_scores, test_labels, test_scenes, chosen),
        "val_ci95_scene_bootstrap": scene_bootstrap(val_scores, val_labels, val_scenes, chosen),
        "test_unlabeled_alarms": unlabeled_alarms(test_scores, patches, test_index, chosen),
        **(extra or {}),
    }
    return result


def code_fingerprint() -> str:
    import hashlib

    root = Path(__file__).resolve().parents[1]
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*.py")):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def save_run(
    result: dict[str, Any],
    test_scores: np.ndarray,
    patches: PatchSet,
    split: pd.Series,
    val_scores: np.ndarray | None = None,
) -> Path:
    name = result["name"]
    out = REPORTS / "metrics" / "detector" / f"{name}.json"
    write_json(out, result)
    predictions = REPORTS / "predictions" / "detector" / name
    predictions.mkdir(parents=True, exist_ok=True)
    test_index = np.flatnonzero(split.to_numpy() == "test")
    quantized = np.clip(np.round(test_scores * 255), 0, 255).astype(np.uint8)
    np.savez_compressed(
        predictions / "test.npz",
        probability=quantized,
        mask=test_scores >= result["threshold"],
        patches=np.array(patches.table["name"].to_numpy()[test_index], dtype=str),
    )
    if val_scores is not None:
        val_index = np.flatnonzero(split.to_numpy() == "val")
        np.savez_compressed(
            predictions / "val.npz",
            probability=np.clip(np.round(val_scores * 255), 0, 255).astype(np.uint8),
            patches=np.array(patches.table["name"].to_numpy()[val_index], dtype=str),
        )
    return out
