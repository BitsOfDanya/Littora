from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from littora_ml.common.io import write_json
from littora_ml.common.paths import REPORTS
from littora_ml.detector.baselines import run_tree_baseline
from littora_ml.detector.dataset import PatchSet
from littora_ml.detector.evaluation import choose_threshold, score_patches, usable_labels
from littora_ml.detector.metrics import evaluate
from littora_ml.detector.splits import with_regions


def region_split(table: pd.DataFrame, region: str, base: pd.Series) -> pd.Series:
    regions = with_regions(table)["region"]
    split = base.where(base.isin(["train", "val"]), "val")
    split = split.where(base != "none", "none")
    split = split.where(regions != region, "test")
    return split.where(~((regions == region) & (base == "none")), "none")


def leave_region_out(patches: PatchSet, base: pd.Series, config: dict[str, Any]) -> dict:
    regions = with_regions(patches.table)["region"]
    labels_all = patches.labels
    results = {}
    pooled_scores, pooled_labels = [], []
    for region in sorted(regions.unique()):
        split = region_split(patches.table, region, base)
        test_index = np.flatnonzero(split.to_numpy() == "test")
        debris = int((labels_all[test_index] == 1).sum())
        if debris < 20:
            continue
        _, val_scores, test_scores, _ = run_tree_baseline(patches, split, config)
        val_index = np.flatnonzero(split.to_numpy() == "val")
        val_labels = usable_labels(patches, val_index, 3)
        threshold, _ = choose_threshold(val_scores, val_labels)
        test_labels = usable_labels(patches, test_index, 3)
        metrics = evaluate(test_scores, test_labels, threshold)
        results[region] = {
            key: metrics[key]
            for key in ("positives", "precision", "recall", "f1", "iou", "pr_auc", "threshold")
        }
        pooled_scores.append(test_scores[test_labels > 0] >= threshold)
        pooled_labels.append(test_labels[test_labels > 0] == 1)
    predicted = np.concatenate(pooled_scores)
    truth = np.concatenate(pooled_labels)
    tp = int((predicted & truth).sum())
    fp = int((predicted & ~truth).sum())
    fn = int((~predicted & truth).sum())
    precision, recall = tp / max(tp + fp, 1), tp / max(tp + fn, 1)
    pooled = {
        "precision": precision,
        "recall": recall,
        "f1": 2 * precision * recall / max(precision + recall, 1e-12),
        "iou": tp / max(tp + fp + fn, 1),
    }
    return {"regions": results, "pooled": pooled}


def run_regions(patches: PatchSet, base: pd.Series, config: dict[str, Any], name: str) -> dict:
    result = leave_region_out(patches, base, config)
    result["name"] = name
    result["protocol"] = (
        "регион целиком в тесте; обучение на train остальных регионов, порог по их val"
    )
    write_json(REPORTS / "metrics" / "detector" / "regions" / f"{name}.json", result)
    return result


__all__ = ["run_regions", "score_patches"]
