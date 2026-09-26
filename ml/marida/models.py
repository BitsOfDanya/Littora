"""Small fixed baselines; tune thresholds on validation, evaluate held-out groups."""
from pathlib import Path
import json

import joblib
import numpy as np
import pandas as pd
import rasterio
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import average_precision_score, precision_recall_curve


def confusion(y, pred):
    return dict(tp=int((y & pred).sum()), fp=int((~y & pred).sum()),
                fn=int((y & ~pred).sum()), tn=int((~y & ~pred).sum()))


def scores_from_counts(tp, fp, fn, tn):
    def div(a, b):
        return a / b if b else np.nan
    return dict(precision=div(tp, tp + fp), recall=div(tp, tp + fn),
                f1=div(2 * tp, 2 * tp + fp + fn), iou=div(tp, tp + fp + fn),
                false_positive_rate=div(fp, fp + tn))


def choose_threshold(y, scores):
    assert np.unique(y).size == 2, "Validation must contain positive and negative pixels"
    precision, recall, thresholds = precision_recall_curve(y, scores)
    f1 = 2 * precision[:-1] * recall[:-1] / np.maximum(precision[:-1] + recall[:-1], 1e-15)
    best = np.flatnonzero(np.isclose(f1, f1.max(), rtol=0, atol=1e-12))[-1]
    return float(thresholds[best]), float(f1[best])


def train_evaluate(patches, pixels, config, output):
    output.mkdir(parents=True, exist_ok=True)
    roles = patches.split.to_numpy()[pixels["patch_index"]]
    train, val, test = (roles == split for split in ("train", "val", "test"))
    y = pixels["y"] == config["evaluation"]["positive_class"]
    assert all(np.unique(y[ix]).size == 2 for ix in (train, val, test))
    forest = RandomForestClassifier(**config["forest"], random_state=config["seed"], class_weight="balanced_subsample")
    weights = np.array(config["evaluation"]["confidence_weights"])[pixels["confidence"][train] - 1]
    forest.fit(pixels["x"][train], y[train], sample_weight=weights)
    joblib.dump(forest, output / "spectral_forest.joblib", compress=3)
    model_scores = {"nir_threshold": pixels["x"][:, 7].astype(float)}
    forest_scores = np.full(len(y), np.nan)
    forest_scores[val | test] = forest.predict_proba(pixels["x"][val | test])[:, 1]
    model_scores["spectral_forest"] = forest_scores
    selected_thresholds, metrics, patch_counts, class_errors = [], [], [], []
    predictions = {k: pixels[k][val | test] for k in ("y", "confidence", "patch_index", "row", "col")}
    for name, scores in model_scores.items():
        threshold, val_f1 = choose_threshold(y[val], scores[val])
        selected_thresholds.append(dict(model=name, threshold=threshold, validation_f1=val_f1,
                                        criterion="max validation pixel F1; highest threshold on ties"))
        # Preserve score precision so PR ranking and threshold decisions can be recomputed exactly.
        predictions[name + "_score"] = scores[val | test].copy()
        predictions[name + "_prediction"] = (scores[val | test] >= threshold).astype(np.uint8)
        for split_name, split_mask in (("val", val), ("test", test)):
            for confidence_mode in ("all", "high_only"):
                keep = split_mask & ((pixels["confidence"] == 1) if confidence_mode == "high_only" else True)
                yy, pp = y[keep], scores[keep] >= threshold
                counts = confusion(yy, pp)
                metrics.append(dict(model=name, split=split_name, confidence=confidence_mode, pixels=int(keep.sum()),
                    positive_pixels=int(yy.sum()), threshold=threshold, **counts, **scores_from_counts(**counts),
                    average_precision=average_precision_score(yy, scores[keep]) if np.unique(yy).size == 2 else np.nan))
            for patch_index in np.unique(pixels["patch_index"][split_mask]):
                keep = split_mask & (pixels["patch_index"] == patch_index)
                counts = confusion(y[keep], scores[keep] >= threshold)
                p = patches.iloc[int(patch_index)]
                patch_counts.append(dict(model=name, split=split_name, patch_index=int(patch_index), patch_id=p.patch_id,
                    scene_id=p.scene_id, group=p.group, **counts, **scores_from_counts(**counts)))
            for class_id in range(1, 16):
                keep = split_mask & (pixels["y"] == class_id)
                positive = int((scores[keep] >= threshold).sum())
                class_errors.append(dict(model=name, split=split_name, class_id=class_id, pixels=int(keep.sum()),
                    predicted_debris=positive, predicted_debris_rate=positive / keep.sum() if keep.any() else np.nan))
    # Thresholds are fixed before any test-based analysis; no model/hyperparameter selection follows.
    metadata = dict(config=config, thresholds=selected_thresholds,
                    input="11-band MARIDA ACOLITE Rayleigh reflectance; no /10000 scaling",
                    positive_class="Marine Debris", ignore_class=0,
                    prediction_status="research_detector; not validated on Littora L2A or for concentration")
    (output / "model_metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2))
    np.savez_compressed(output / "heldout_predictions.npz", **predictions)
    return forest, pd.DataFrame(selected_thresholds), pd.DataFrame(metrics), pd.DataFrame(patch_counts), pd.DataFrame(class_errors)


def group_bootstrap(patch_counts, config):
    results = []
    for (model, split), patches in patch_counts.groupby(["model", "split"]):
        groups = patches.groupby("group")[["tp", "fp", "fn", "tn"]].sum()
        values = groups.to_numpy()
        rng = np.random.default_rng(config["seed"])
        boot = []
        for _ in range(config["bootstrap_repeats"]):
            c = values[rng.integers(0, len(values), len(values))].sum(axis=0)
            boot.append(scores_from_counts(*c))
        for metric in ["precision", "recall", "f1", "iou"]:
            vals = np.array([x[metric] for x in boot])
            valid = vals[np.isfinite(vals)]
            results.append(dict(model=model, split=split, metric=metric, groups=len(values),
                ci025=float(np.quantile(valid, .025)) if len(valid) else np.nan,
                ci975=float(np.quantile(valid, .975)) if len(valid) else np.nan,
                valid_bootstrap_replicates=len(valid)))
    return pd.DataFrame(results)


def predict_patch(model, threshold, path, output_prefix):
    with rasterio.open(path) as source:
        assert source.count == 11, "Expected MARIDA band order and radiometry"
        x = source.read()
        valid = np.isfinite(x).all(axis=0) & (source.read_masks() > 0).all(axis=0)
        probability = np.full(source.shape, -9999, dtype=np.float32)
        mask = np.full(source.shape, 255, dtype=np.uint8)
        if valid.any():
            scores = model.predict_proba(x[:, valid].T)[:, 1]
            probability[valid] = scores
            # Classify before float32 export rounding; preserve the evaluation decision rule.
            mask[valid] = (scores >= threshold).astype(np.uint8)
        profile = source.profile.copy()
        for suffix, data, dtype, nodata in [("score", probability, "float32", -9999), ("mask", mask, "uint8", 255)]:
            dest = Path(str(output_prefix) + f"_{suffix}.tif")
            profile.update(count=1, dtype=dtype, nodata=nodata, compress="deflate")
            with rasterio.open(dest, "w", **profile) as out:
                out.write(data, 1)
                out.update_tags(model="MARIDA spectral RF baseline", threshold=str(threshold), status="research_detector")
    return probability, mask
