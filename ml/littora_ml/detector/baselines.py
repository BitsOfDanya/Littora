from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import joblib
import lightgbm as lgb
import numpy as np
from sklearn.ensemble import ExtraTreesClassifier, RandomForestClassifier

from littora_ml.common.io import read_json
from littora_ml.common.paths import MODELS, REPORTS
from littora_ml.detector.dataset import PatchSet, load_patch_set
from littora_ml.detector.evaluation import score_patches, usable_labels
from littora_ml.detector.features import feature_names, pixel_features, spectral_indices


def labeled_pixels(
    patches: PatchSet,
    indices: np.ndarray,
    indices_on: bool,
    local_on: bool,
    max_confidence_code: int,
    bands: list[str] | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    features, classes, owners = [], [], []
    labels = usable_labels(patches, indices, max_confidence_code)
    for position, index in enumerate(indices):
        mask = labels[position] > 0
        if not mask.any():
            continue
        stack = pixel_features(
            np.asarray(patches.images[index], dtype=np.float32), indices_on, local_on, bands
        )
        features.append(stack[:, mask].T)
        classes.append(labels[position][mask])
        owners.append(np.full(mask.sum(), index))
    return np.concatenate(features), np.concatenate(classes), np.concatenate(owners)


def fdi_scorer(images: np.ndarray) -> np.ndarray:
    return np.stack([spectral_indices(image)[1] for image in images])


def fdi_probability(scale: float = 0.02):
    def scorer(images: np.ndarray) -> np.ndarray:
        return 1 / (1 + np.exp(-fdi_scorer(images) / scale))

    return scorer


def rule_scorer(ndvi_max: float, blue_max: float):
    def scorer(images: np.ndarray) -> np.ndarray:
        out = []
        for image in images:
            derived = spectral_indices(image)
            allowed = (derived[0] <= ndvi_max) & (image[1] <= blue_max)
            out.append(np.where(allowed, 1 / (1 + np.exp(-derived[1] / 0.02)), 0.0))
        return np.stack(out)

    return scorer


def tune_rule(
    patches: PatchSet, val_index: np.ndarray, max_confidence_code: int
) -> dict[str, float]:
    from littora_ml.detector.evaluation import choose_threshold

    labels = usable_labels(patches, val_index, max_confidence_code)
    best = {"f1": -1.0}
    for ndvi_max in (0.1, 0.2, 0.3, 0.4, 0.5, 1.0):
        for blue_max in (0.05, 0.08, 0.12, 0.2, 1.0):
            scores = score_patches(rule_scorer(ndvi_max, blue_max), patches, val_index)
            threshold, f1 = choose_threshold(scores, labels)
            if f1 > best["f1"]:
                best = {
                    "f1": f1,
                    "ndvi_max": ndvi_max,
                    "blue_max": blue_max,
                    "threshold": threshold,
                }
    return best


def fit_tree_model(
    kind: str,
    features: np.ndarray,
    target: np.ndarray,
    params: dict[str, Any],
    seed: int,
    eval_set: tuple[np.ndarray, np.ndarray] | None = None,
):
    started = time.time()
    positives = max(int(target.sum()), 1)
    weight = (len(target) - positives) / positives
    if kind == "lightgbm":
        model = lgb.LGBMClassifier(
            random_state=seed,
            scale_pos_weight=params.get("scale_pos_weight", weight),
            verbose=-1,
            **{k: v for k, v in params.items() if k != "scale_pos_weight"},
        )
        callbacks = [lgb.early_stopping(100, verbose=False)] if eval_set else None
        model.fit(
            features,
            target,
            eval_X=(eval_set[0],) if eval_set else None,
            eval_y=(eval_set[1],) if eval_set else None,
            eval_metric="average_precision",
            callbacks=callbacks,
        )
    elif kind in ("random_forest", "extra_trees"):
        estimator = RandomForestClassifier if kind == "random_forest" else ExtraTreesClassifier
        model = estimator(random_state=seed, n_jobs=-1, class_weight="balanced_subsample", **params)
        model.fit(features, target)
    else:
        raise ValueError(f"unknown model {kind}")
    return model, time.time() - started


def tree_scorer(model, indices_on: bool, local_on: bool, bands: list[str] | None = None):
    def scorer(images: np.ndarray) -> np.ndarray:
        out = []
        for image in images:
            stack = pixel_features(image, indices_on, local_on, bands)
            flat = stack.reshape(stack.shape[0], -1).T
            probability = model.predict_proba(flat)[:, 1]
            out.append(probability.reshape(image.shape[1:]))
        return np.stack(out)

    return scorer


def run_tree_baseline(patches: PatchSet, split, config: dict[str, Any]):
    model_config = config["model"]
    features_config = config.get("features", {})
    indices_on = features_config.get("indices", True)
    local_on = features_config.get("local", True)
    bands = features_config.get("bands")
    max_confidence_code = config.get("labels", {}).get("max_confidence_code", 3)
    seed = config.get("seed", 42)
    values = split.to_numpy()
    train_index = np.flatnonzero(values == "train")
    val_index = np.flatnonzero(values == "val")
    test_index = np.flatnonzero(values == "test")
    x_train, c_train, _ = labeled_pixels(
        patches, train_index, indices_on, local_on, max_confidence_code, bands
    )
    x_val, c_val, _ = labeled_pixels(
        patches, val_index, indices_on, local_on, max_confidence_code, bands
    )
    y_train, y_val = (c_train == 1).astype(np.int8), (c_val == 1).astype(np.int8)
    kind = model_config["kind"]
    params = {k: v for k, v in model_config.items() if k != "kind"}
    model, seconds = fit_tree_model(
        kind, x_train, y_train, params, seed, (x_val, y_val) if kind == "lightgbm" else None
    )
    scorer = tree_scorer(model, indices_on, local_on, bands)
    val_scores = score_patches(scorer, patches, val_index)
    test_scores = score_patches(scorer, patches, test_index)
    names = feature_names(indices_on, local_on, bands)
    importances = getattr(model, "feature_importances_", None)
    extra = {
        "train_pixels": len(y_train),
        "train_positives": int(y_train.sum()),
        "fit_seconds": round(seconds, 1),
        "features": names,
        "feature_importance": dict(
            sorted(
                zip(names, (importances.tolist() if importances is not None else []), strict=False),
                key=lambda item: -item[1],
            )
        ),
        "best_iteration": getattr(model, "best_iteration_", None),
    }
    return extra, val_scores, test_scores, model


def score_tree_run(root: str, run: str, indices: np.ndarray) -> np.ndarray:
    report = read_json(REPORTS / "metrics" / "detector" / f"{run}.json")
    features = report["config"].get("features", {})
    model = joblib.load(MODELS / "detector" / run / "model.joblib")
    scorer = tree_scorer(
        model, features.get("indices", True), features.get("local", True), features.get("bands")
    )
    return score_patches(scorer, load_patch_set(Path(root)), indices)
