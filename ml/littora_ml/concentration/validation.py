from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from joblib import Parallel, delayed
from scipy.stats import spearmanr
from sklearn.cluster import KMeans

from littora_ml.concentration.models import Candidate, to_log

Split = tuple[np.ndarray, np.ndarray]
Option = tuple[str, Candidate, list[str]]


def metrics(truth: np.ndarray, prediction: np.ndarray) -> dict[str, float]:
    error = prediction - truth
    rho = spearmanr(truth, prediction).statistic if np.ptp(prediction) > 0 else np.nan
    return {
        "n": len(truth),
        "mae": float(np.mean(np.abs(error))),
        "rmse": float(np.sqrt(np.mean(error**2))),
        "medae": float(np.median(np.abs(error))),
        "bias": float(np.mean(error)),
        "mae_log1p": float(np.mean(np.abs(to_log(prediction) - to_log(truth)))),
        "spearman": float(rho) if rho == rho else None,
    }


def spread(values) -> dict[str, float]:
    array = np.asarray(values, dtype=float)
    return {
        "mean": float(array.mean()),
        "sd": float(array.std(ddof=1)) if len(array) > 1 else 0.0,
    }


def folds(groups: np.ndarray, n_splits: int, seed: int | list[int] = 0) -> list[Split]:
    unique = np.unique(groups)
    splits = min(n_splits, len(unique))
    order = np.random.default_rng(seed).permutation(len(unique))
    fold_of = dict(zip(unique[order], np.arange(len(unique)) % splits, strict=True))
    assignment = np.array([fold_of[group] for group in groups])
    return [
        (np.flatnonzero(assignment != k), np.flatnonzero(assignment == k)) for k in range(splits)
    ]


def spatial_groups(xy: np.ndarray, clusters: int, seed: int) -> np.ndarray:
    model = KMeans(n_clusters=clusters, n_init=10, random_state=seed)
    return model.fit_predict(xy)


def out_of_fold(
    candidate: Candidate,
    features: pd.DataFrame,
    target: np.ndarray,
    splits: list[Split],
) -> np.ndarray:
    prediction = np.zeros(len(target))
    for train, test in splits:
        model = copy.deepcopy(candidate).fit(features.iloc[train], target[train])
        prediction[test] = model.predict(features.iloc[test])
    return prediction


def conformal_rank(size: int, coverage: float) -> int:
    return min(size, math.ceil((size + 1) * coverage - 1e-9))


def conformal_quantile(truth: np.ndarray, prediction: np.ndarray, coverage: float) -> float:
    residual = np.sort(np.abs(to_log(truth) - to_log(prediction)))
    return float(residual[conformal_rank(len(residual), coverage) - 1])


def interval(prediction: np.ndarray, quantile: float) -> tuple[np.ndarray, np.ndarray]:
    log = to_log(prediction)
    return np.maximum(np.expm1(log - quantile), 0), np.expm1(log + quantile)


def _fold_task(
    options: list[Option],
    table: pd.DataFrame,
    target: np.ndarray,
    groups: np.ndarray,
    split: Split,
    inner_splits: int,
    inner_seed: list[int],
    coverage: float,
) -> dict[str, dict[str, Any]]:
    train, test = split
    inner = folds(groups[train], inner_splits, inner_seed)
    fit_frame, test_frame = table.iloc[train], table.iloc[test]
    result: dict[str, dict[str, Any]] = {"score": {}, "quantile": {}, "prediction": {}}
    for label, candidate, columns in options:
        oof = out_of_fold(candidate, fit_frame[columns], target[train], inner)
        result["score"][label] = float(np.mean(np.abs(oof - target[train])))
        result["quantile"][label] = conformal_quantile(target[train], oof, coverage)
        model = copy.deepcopy(candidate).fit(fit_frame[columns], target[train])
        result["prediction"][label] = model.predict(test_frame[columns])
    return result


@dataclass
class RepeatedCV:
    target: np.ndarray
    groups: np.ndarray
    assignments: np.ndarray
    oof: dict[str, np.ndarray]
    lower: dict[str, np.ndarray]
    upper: dict[str, np.ndarray]
    nested: np.ndarray
    nested_lower: np.ndarray
    nested_upper: np.ndarray
    selections: list[list[dict[str, Any]]] = field(default_factory=list)

    @property
    def repetitions(self) -> int:
        return len(self.assignments)

    def option_metrics(self, label: str) -> list[dict[str, float]]:
        return [metrics(self.target, row) for row in self.oof[label]]

    def nested_metrics(self) -> list[dict[str, float]]:
        return [metrics(self.target, row) for row in self.nested]

    def coverage(self, label: str | None = None) -> np.ndarray:
        lower = self.nested_lower if label is None else self.lower[label]
        upper = self.nested_upper if label is None else self.upper[label]
        return ((self.target >= lower) & (self.target <= upper)).mean(axis=1)

    def width(self, label: str | None = None) -> np.ndarray:
        lower = self.nested_lower if label is None else self.lower[label]
        upper = self.nested_upper if label is None else self.upper[label]
        return np.median(upper - lower, axis=1)

    def rank(self) -> list[str]:
        means = {
            label: float(np.mean(np.abs(rows - self.target))) for label, rows in self.oof.items()
        }
        return sorted(means, key=means.get)

    def quantile(self, label: str, coverage: float) -> float:
        return float(
            np.median([conformal_quantile(self.target, row, coverage) for row in self.oof[label]])
        )


def repeated_nested_cv(
    options: list[Option],
    table: pd.DataFrame,
    target: np.ndarray,
    groups: np.ndarray,
    config: dict[str, Any],
) -> RepeatedCV:
    seed, repetitions = config["seed"], config.get("repetitions", 10)
    outer_splits, inner_splits = config["outer_splits"], config["inner_splits"]
    tasks = [
        (repetition, fold, split)
        for repetition in range(repetitions)
        for fold, split in enumerate(folds(groups, outer_splits, [seed, repetition]))
    ]
    results = Parallel(n_jobs=config.get("jobs", -1))(
        delayed(_fold_task)(
            options,
            table,
            target,
            groups,
            split,
            inner_splits,
            [seed, repetition, fold],
            config["coverage"],
        )
        for repetition, fold, split in tasks
    )
    shape = (repetitions, len(target))
    labels = [label for label, _, _ in options]
    assignments = np.full(shape, -1)
    oof = {label: np.zeros(shape) for label in labels}
    lower = {label: np.zeros(shape) for label in labels}
    upper = {label: np.zeros(shape) for label in labels}
    nested, nested_lower, nested_upper = np.zeros(shape), np.zeros(shape), np.zeros(shape)
    selections: list[list[dict[str, Any]]] = [[] for _ in range(repetitions)]
    for (repetition, fold, (_, test)), result in zip(tasks, results, strict=True):
        assignments[repetition, test] = fold
        for label in labels:
            prediction = result["prediction"][label]
            oof[label][repetition, test] = prediction
            low, high = interval(prediction, result["quantile"][label])
            lower[label][repetition, test], upper[label][repetition, test] = low, high
        best = min(result["score"], key=result["score"].get)
        nested[repetition, test] = oof[best][repetition, test]
        nested_lower[repetition, test] = lower[best][repetition, test]
        nested_upper[repetition, test] = upper[best][repetition, test]
        selections[repetition].append(
            {
                "fold": fold,
                "selected": best,
                "inner_mae": round(result["score"][best], 3),
                "test_events": len(test),
                "log_quantile": round(result["quantile"][best], 4),
            }
        )
    return RepeatedCV(
        target,
        groups,
        assignments,
        oof,
        lower,
        upper,
        nested,
        nested_lower,
        nested_upper,
        selections,
    )


def paired_difference(
    target: np.ndarray,
    model: np.ndarray,
    baseline: np.ndarray,
    groups: np.ndarray,
    draws: int,
    seed: int,
    confidence: float = 0.95,
) -> dict[str, dict[str, Any]]:
    unique, index = np.unique(groups, return_inverse=True)
    rng = np.random.default_rng(seed)
    picks = rng.integers(0, len(unique), size=(draws, len(unique)))
    counts = np.stack([np.bincount(row, minlength=len(unique)) for row in picks])
    weights = np.vstack([np.ones(len(target)), counts[:, index]])
    total = weights.sum(axis=1)
    model_abs = np.abs(model - target).mean(axis=0)
    base_abs = np.abs(baseline - target).mean(axis=0)
    model_mae, base_mae = weights @ model_abs / total, weights @ base_abs / total
    model_rmse = np.sqrt(weights @ ((model - target) ** 2).T / total[:, None]).mean(axis=1)
    base_rmse = np.sqrt(weights @ ((baseline - target) ** 2).T / total[:, None]).mean(axis=1)

    tails = [50 * (1 - confidence), 100 - 50 * (1 - confidence)]

    def summary(model_value: np.ndarray, base_value: np.ndarray) -> dict[str, Any]:
        difference = model_value - base_value
        relative = difference / base_value
        return {
            "mean": float(difference[0]),
            "confidence": confidence,
            "ci": [float(v) for v in np.percentile(difference[1:], tails)],
            "relative": float(relative[0]),
            "relative_ci": [float(v) for v in np.percentile(relative[1:], tails)],
        }

    return {"mae": summary(model_mae, base_mae), "rmse": summary(model_rmse, base_rmse)}


def date_block_split(dates: pd.Series, fraction: float) -> Split:
    days = np.sort(dates.unique())
    cut = min(len(days) - 1, max(1, round(len(days) * fraction)))
    train = dates.isin(days[:cut]).to_numpy()
    return np.flatnonzero(train), np.flatnonzero(~train)


def confidence_label(confidence: float) -> str:
    return f"{confidence * 100:.1f}".rstrip("0").rstrip(".").replace(".", ",") + " %"
