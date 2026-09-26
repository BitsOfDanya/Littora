from __future__ import annotations

import itertools
import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from typing import Any

import numpy as np

from littora_ml.detector.dataset import PatchSet
from littora_ml.detector.evaluation import choose_threshold, score_patches, usable_labels
from littora_ml.detector.inference import TrainedDetector, model_folder, run_threshold
from littora_ml.detector.tree_worker import score_tree_member

STEP = 0.1


def member_scores(runs: list[str], patches: PatchSet, indices: np.ndarray) -> list[np.ndarray]:
    scores = []
    for run in runs:
        if (model_folder(run) / "model.joblib").exists():
            context = multiprocessing.get_context("spawn")
            with ProcessPoolExecutor(1, mp_context=context) as pool:
                job = pool.submit(score_tree_member, str(patches.root), run, indices)
                scores.append(job.result())
            continue
        _, tta = run_threshold(run)
        scores.append(score_patches(TrainedDetector(run).scorer(tta), patches, indices))
    return scores


def weight_grid(count: int) -> list[tuple[float, ...]]:
    steps = np.round(np.arange(0, 1 + 1e-9, STEP), 2)
    return [w for w in itertools.product(steps, repeat=count) if abs(sum(w) - 1) < 1e-6]


def search_weights(val_members: list[np.ndarray], val_labels: np.ndarray) -> list[dict[str, Any]]:
    rows = []
    for weights in weight_grid(len(val_members)):
        combined = sum(w * s for w, s in zip(weights, val_members, strict=True))
        threshold, f1 = choose_threshold(combined, val_labels)
        rows.append({"weights": [float(w) for w in weights], "threshold": threshold, "val_f1": f1})
    return sorted(rows, key=lambda row: -row["val_f1"])


def run_ensemble(runs: list[str], patches: PatchSet, split, max_confidence_code: int = 3):
    values = split.to_numpy()
    val_index = np.flatnonzero(values == "val")
    test_index = np.flatnonzero(values == "test")
    val_labels = usable_labels(patches, val_index, max_confidence_code)
    val_members = member_scores(runs, patches, val_index)
    search = search_weights(val_members, val_labels)
    best = search[0]
    test_members = member_scores(runs, patches, test_index)

    def combine(members: list[np.ndarray]) -> np.ndarray:
        return sum(w * s for w, s in zip(best["weights"], members, strict=True))

    return combine(val_members), combine(test_members), best, search[:10]
