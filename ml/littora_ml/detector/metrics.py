from __future__ import annotations

from typing import Any

import numpy as np
from sklearn.metrics import average_precision_score, precision_recall_curve

from littora_ml.detector.marida import CLASS_NAMES


def confusion(scores: np.ndarray, truth: np.ndarray, threshold: float) -> dict[str, int]:
    predicted = scores >= threshold
    return {
        "tp": int(np.sum(predicted & truth)),
        "fp": int(np.sum(predicted & ~truth)),
        "fn": int(np.sum(~predicted & truth)),
        "tn": int(np.sum(~predicted & ~truth)),
    }


def rates(counts: dict[str, int]) -> dict[str, float]:
    tp, fp, fn = counts["tp"], counts["fp"], counts["fn"]
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    iou = tp / (tp + fp + fn) if tp + fp + fn else 0.0
    return {"precision": precision, "recall": recall, "f1": f1, "iou": iou}


def best_threshold(scores: np.ndarray, truth: np.ndarray) -> tuple[float, float]:
    precision, recall, thresholds = precision_recall_curve(truth, scores)
    f1 = 2 * precision * recall / np.maximum(precision + recall, 1e-12)
    index = int(np.nanargmax(f1[:-1])) if len(thresholds) else 0
    return float(thresholds[index]) if len(thresholds) else 0.5, float(f1[index])


def evaluate(
    scores: np.ndarray,
    labels: np.ndarray,
    threshold: float,
    positive: tuple[int, ...] = (1,),
    groups: np.ndarray | None = None,
) -> dict[str, Any]:
    labeled = labels > 0
    score = scores[labeled]
    classes = labels[labeled]
    truth = np.isin(classes, positive)
    counts = confusion(score, truth, threshold)
    result: dict[str, Any] = {
        "threshold": threshold,
        "pixels": int(labeled.sum()),
        "positives": int(truth.sum()),
        **counts,
        **rates(counts),
        "pr_auc": float(average_precision_score(truth, score)) if truth.any() else None,
    }
    predicted = score >= threshold
    by_class = {}
    for value in np.unique(classes):
        if value in positive:
            continue
        mask = classes == value
        by_class[CLASS_NAMES.get(int(value), str(value))] = {
            "pixels": int(mask.sum()),
            "false_positives": int((predicted & mask).sum()),
            "false_positive_rate": float(predicted[mask].mean()),
        }
    result["false_positives_by_class"] = dict(
        sorted(by_class.items(), key=lambda item: -item[1]["false_positives"])
    )
    if groups is not None:
        group_values = groups[labeled]
        per_group = {}
        for group in np.unique(group_values):
            mask = group_values == group
            group_truth = truth[mask]
            group_counts = confusion(score[mask], group_truth, threshold)
            per_group[str(group)] = {
                "pixels": int(mask.sum()),
                "positives": int(group_truth.sum()),
                **group_counts,
                **rates(group_counts),
            }
        result["by_group"] = per_group
    return result
