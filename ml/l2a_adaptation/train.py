"""Train target-product RF and isolate validation-only threshold effects."""

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import average_precision_score
from sklearn.neighbors import BallTree

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml"))
from marida.models import choose_threshold, confusion, scores_from_counts

OUT = ROOT / "reports/l2a_adaptation"
CACHE = ROOT / "data/processed/l2a_adaptation"
RF_PARAMS = {
    "n_estimators": 125,
    "max_depth": 20,
    "min_samples_leaf": 2,
    "class_weight": "balanced_subsample",
    "random_state": 42,
    "n_jobs": 4,
}


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def measures(y, score, threshold):
    assert (y > 0).all() and len(y) > 0
    counts = confusion(y == 1, score >= threshold)
    return dict(
        pixels=len(y),
        positive_pixels=int((y == 1).sum()),
        **counts,
        **scores_from_counts(**counts),
        average_precision=float(average_precision_score(y == 1, score))
        if np.unique(y == 1).size == 2
        else np.nan,
    )


def split_contract(patches, pixels):
    assert patches.patch_id.is_unique and np.array_equal(
        patches.selection_index, np.arange(len(patches))
    )
    assert patches.groupby("group")["split"].nunique().max() == 1
    assert np.isin(pixels["y"], range(1, 16)).all()
    assert np.isin(pixels["confidence"], [1, 2, 3]).all()
    assert np.isfinite(pixels["l2a"]).all() and np.isfinite(pixels["rhorc"]).all()
    roles = patches["split"].to_numpy()[pixels["patch_index"]]
    groups = patches.group.to_numpy()[pixels["patch_index"]].astype(str)
    for role in ["train", "val", "test"]:
        m = roles == role
        assert np.unique(pixels["y"][m] == 1).size == 2
        assert len(np.unique(groups[m & (pixels["y"] == 1)])) >= 2, (
            f"Insufficient positive groups: {role}"
        )
    return roles, groups


def bootstrap_counts(group_counts, repeats=1000):
    frame = pd.DataFrame(group_counts)
    groups = sorted(frame.group.unique())
    variants = sorted(frame.variant.unique())
    rng = np.random.default_rng(42)
    draws = rng.integers(0, len(groups), (repeats, len(groups)))
    fs = {}
    rows = []
    for name in variants:
        part = frame[frame.variant == name].set_index("group").reindex(groups)
        assert part[["tp", "fp", "fn", "tn"]].notna().all().all()
        a = part[["tp", "fp", "fn", "tn"]].to_numpy()[draws].sum(axis=1)
        den = 2 * a[:, 0] + a[:, 1] + a[:, 2]
        f = np.divide(2 * a[:, 0], den, out=np.full(repeats, np.nan), where=den > 0)
        fs[name] = f
        v = f[np.isfinite(f)]
        rows.append(
            {
                "comparison": name,
                "metric": "F1",
                "groups": len(groups),
                "valid_repeats": len(v),
                "low": float(np.quantile(v, 0.025)),
                "high": float(np.quantile(v, 0.975)),
            }
        )
    contrasts = [
        ("l2a_rf", "joint_original"),
        ("l2a_rf", "joint_l2a_threshold"),
        ("l2a_rf", "paired_rhorc_l2a_threshold"),
        ("joint_l2a_threshold", "joint_original"),
        ("l2a_rf", "marida_original"),
    ]
    for a, b in contrasts:
        delta = fs[a] - fs[b]
        v = delta[np.isfinite(delta)]
        rows.append(
            {
                "comparison": a + " minus " + b,
                "metric": "paired_delta_F1",
                "groups": len(groups),
                "valid_repeats": len(v),
                "low": float(np.quantile(v, 0.025)),
                "high": float(np.quantile(v, 0.975)),
            }
        )
    return pd.DataFrame(rows)


def main():
    old_models = [
        ROOT / "data/processed/marida_baseline/spectral_forest.joblib",
        ROOT / "data/processed/expansion/joint.joblib",
    ]
    protected = old_models + [ROOT / "data/case/macroplastic_marine_samples.csv"]
    protected += list(
        (ROOT / "data/external/validation-bridge/blacksea_holdout").rglob("labels.tif")
    )
    before = {str(p.relative_to(ROOT)): sha(p) for p in protected}
    patches = pd.read_csv(OUT / "tables/selected_patches.csv")
    d = dict(np.load(CACHE / "paired_pixels.npz"))
    roles, groups = split_contract(patches, d)
    train = roles == "train"
    val = roles == "val"
    test = roles == "test"
    classes = []
    splits = []
    for role in ["train", "val", "test"]:
        keep = roles == role
        splits.append(
            {
                "split": role,
                "pixels": int(keep.sum()),
                "positive_pixels": int((d["y"][keep] == 1).sum()),
                "patches": len(np.unique(d["patch_index"][keep])),
                "groups": len(np.unique(groups[keep])),
                "positive_groups": len(np.unique(groups[keep & (d["y"] == 1)])),
            }
        )
        for c in np.unique(d["y"][keep]):
            classes.append(
                {
                    "split": role,
                    "class_id": int(c),
                    "pixels": int((keep & (d["y"] == c)).sum()),
                }
            )
    pd.DataFrame(splits).to_csv(OUT / "tables/split_summary.csv", index=False)
    pd.DataFrame(classes).to_csv(OUT / "tables/class_counts.csv", index=False)
    print(pd.DataFrame(splits).to_string(index=False), flush=True)
    # Geographic audit does not reassign splits or tune the model.
    training_coords = np.deg2rad(
        patches.loc[patches["split"] == "train", ["latitude", "longitude"]].to_numpy()
    )
    distances = (
        BallTree(training_coords, metric="haversine").query(
            np.deg2rad(patches[["latitude", "longitude"]].to_numpy()), k=1
        )[0][:, 0]
        * 6371.0088
    )
    geo = patches[
        [
            "patch_id",
            "scene_id",
            "split",
            "group",
            "date",
            "tile",
            "latitude",
            "longitude",
        ]
    ].copy()
    geo["nearest_train_patch_km"] = distances
    geo["beyond_100km_from_train"] = distances > 100
    geo.to_csv(OUT / "tables/geographic_audit.csv", index=False)
    forests = {
        "marida": joblib.load(old_models[0]),
        "joint": joblib.load(old_models[1]),
    }
    for model in forests.values():
        model.set_params(n_jobs=4)
    weights = np.array([1, 2 / 3, 1 / 3])[d["confidence"][train].astype(int) - 1]
    for key, product in [("paired_rhorc", "rhorc"), ("l2a", "l2a")]:
        forest = RandomForestClassifier(**RF_PARAMS)
        forest.fit(d[product][train], d["y"][train] == 1, sample_weight=weights)
        joblib.dump(forest, CACHE / f"{key}_rf.joblib", compress=3)
        forests[key] = forest
        print("Trained", key, "on", int(train.sum()), "pixels", flush=True)
    validation = {
        name: model.predict_proba(d["l2a"][val])[:, 1]
        for name, model in forests.items()
    }
    prior = json.loads(
        (ROOT / "data/processed/expansion/model_metadata.json").read_text()
    )
    old_t = {row["model"]: row["threshold"] for row in prior["thresholds"]}
    specs = [
        (
            "marida_original",
            "marida",
            old_t["marida_frozen"],
            "original MARIDA validation",
        ),
        ("joint_original", "joint", old_t["joint"], "original MADOS validation"),
    ]
    for name, forest in [
        ("marida_l2a_threshold", "marida"),
        ("joint_l2a_threshold", "joint"),
        ("paired_rhorc_l2a_threshold", "paired_rhorc"),
        ("l2a_rf", "l2a"),
    ]:
        t, _ = choose_threshold(d["y"][val] == 1, validation[forest])
        specs.append(
            (
                name,
                forest,
                t,
                "current L2A validation; max F1, highest threshold on ties",
            )
        )
    frozen = {
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "forest_params": RF_PARAMS,
        "input_product": "Sentinel-2 C1 L2A BOA reflectance; scale/offset already applied",
        "bands": [
            "B01",
            "B02",
            "B03",
            "B04",
            "B05",
            "B06",
            "B07",
            "B08",
            "B8A",
            "B11",
            "B12",
        ],
        "ignore_reference_class": 0,
        "positive_reference_class": 1,
        "threshold_variants": [
            {"variant": n, "forest": f, "threshold": t, "selection": s}
            for n, f, t, s in specs
        ],
        "paired_pixels_sha256": sha(CACHE / "paired_pixels.npz"),
        "selected_patches_sha256": sha(OUT / "tables/selected_patches.csv"),
        "model_sha256": {
            k: sha(CACHE / f"{k}_rf.joblib") for k in ["paired_rhorc", "l2a"]
        },
    }
    (CACHE / "frozen_before_test.json").write_text(json.dumps(frozen, indent=2))
    (OUT / "frozen_before_test.json").write_text(json.dumps(frozen, indent=2))
    np.savez_compressed(
        CACHE / "validation_scores.npz",
        y=d["y"][val],
        confidence=d["confidence"][val],
        group=groups[val],
        patch_index=d["patch_index"][val],
        **validation,
    )
    print(
        "Models and validation thresholds frozen; starting test inference.", flush=True
    )
    testing = {
        name: model.predict_proba(d["l2a"][test])[:, 1]
        for name, model in forests.items()
    }
    np.savez_compressed(
        CACHE / "test_scores.npz",
        y=d["y"][test],
        confidence=d["confidence"][test],
        group=groups[test],
        patch_index=d["patch_index"][test],
        **testing,
    )
    metrics = []
    gc = []
    errors = []
    patch_counts = []
    for role, mask, scores in [("val", val, validation), ("test", test, testing)]:
        y = d["y"][mask]
        cf = d["confidence"][mask]
        gg = groups[mask]
        pi = d["patch_index"][mask]
        for variant, forest, t, _ in specs:
            s = scores[forest]
            pred = s >= t
            for scope, keep in [
                ("all", np.ones(len(y), dtype=bool)),
                ("high_confidence", cf == 1),
                ("beyond_100km_train", distances[pi] > 100),
            ]:
                if not keep.any():
                    continue
                metrics.append(
                    dict(
                        split=role,
                        scope=scope,
                        variant=variant,
                        forest=forest,
                        threshold=t,
                        groups=len(np.unique(gg[keep])),
                        **measures(y[keep], s[keep], t),
                    )
                )
            if role != "test":
                continue
            for group in np.unique(gg):
                keep = gg == group
                gc.append(
                    dict(
                        variant=variant,
                        group=group,
                        **confusion(y[keep] == 1, pred[keep]),
                    )
                )
            for cls in np.unique(y):
                keep = y == cls
                errors.append(
                    {
                        "variant": variant,
                        "class_id": int(cls),
                        "pixels": int(keep.sum()),
                        "predicted_debris": int(pred[keep].sum()),
                        "predicted_debris_rate": float(pred[keep].mean()),
                    }
                )
            for index in np.unique(pi):
                keep = pi == index
                patch_counts.append(
                    dict(
                        variant=variant,
                        patch_index=int(index),
                        patch_id=patches.iloc[index].patch_id,
                        group=patches.iloc[index].group,
                        **confusion(y[keep] == 1, pred[keep]),
                    )
                )
    for name, records in [
        ("metrics", metrics),
        ("test_group_counts", gc),
        ("errors_by_class", errors),
        ("test_patch_counts", patch_counts),
    ]:
        pd.DataFrame(records).to_csv(OUT / f"tables/{name}.csv", index=False)
    bootstrap_counts(gc).to_csv(OUT / "tables/bootstrap.csv", index=False)
    assert before == {str(p.relative_to(ROOT)): sha(p) for p in protected}
    manifest = {
        "status": "complete",
        "training_performed": True,
        "training_product": "L2A and paired rhorc control",
        "test_product": "L2A",
        "seed": 42,
        "new_blacksea_predictions": False,
        "protected_sha256": before,
        "protocol_sha256": sha(Path(__file__).with_name("protocol.md")),
        "train_code_sha256": sha(Path(__file__)),
        "frozen_before_test_sha256": sha(CACHE / "frozen_before_test.json"),
    }
    (OUT / "run_manifest.json").write_text(json.dumps(manifest, indent=2))
    print(
        pd.DataFrame(metrics)
        .query("split=='test' and scope=='all'")
        .to_string(index=False),
        flush=True,
    )


if __name__ == "__main__":
    main()
