"""MADOS binary experiment with scene splits and explicit cross-source limitations."""

import hashlib
import json
import sys
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import rasterio
from rasterio.enums import Resampling
from rasterio.errors import NotGeoreferencedWarning
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import average_precision_score

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml"))
from marida.dataset import BANDS
from marida.models import choose_threshold, confusion, scores_from_counts

OUT = ROOT / "reports/expansion/tables"
CACHE = ROOT / "data/processed/expansion"
CLASSES = {
    1: "Marine Debris",
    2: "Dense Sargassum",
    3: "Sparse Floating Algae",
    4: "Natural Organic Material",
    5: "Ship",
    6: "Oil Spill",
    7: "Marine Water",
    8: "Sediment-Laden Water",
    9: "Foam",
    10: "Turbid Water",
    11: "Shallow Water",
    12: "Waves and Wakes",
    13: "Oil Platform",
    14: "Jellyfish",
    15: "Sea Snot",
}
EXPECTED_WAVES = [
    {442, 443},
    {492},
    {559, 560},
    {665},
    {704},
    {739, 740},
    {780, 783},
    {833},
    {864, 865},
    {1610, 1614},
    {2186, 2202},
]


def row_tokens(x):
    x = np.array(x, dtype="<f4", order="C", copy=True)
    x[x == 0] = 0  # canonicalize negative zero
    return x.view("V44").reshape(-1)


def exact_spectrum_matches(x, reference):
    keys = np.unique(row_tokens(reference))
    q = row_tokens(x)
    pos = np.searchsorted(keys, q)
    valid = pos < len(keys)
    found = np.zeros(len(q), dtype=bool)
    found[valid] = keys[pos[valid]] == q[valid]
    return found & (np.ptp(x, axis=1) > 1e-8)


def scan(root):
    CACHE.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    split = {}
    for role in ["train", "val", "test"]:
        for patch in (root / "splits" / f"{role}_X.txt").read_text().splitlines():
            assert patch not in split
            split[patch] = role
    rows = []
    chunks = {
        k: [] for k in ["x", "y", "confidence", "report", "patch_index", "row", "col"]
    }
    paths = sorted(root.glob("Scene_*/10/*_cl_*.tif"))
    assert len(paths) == 2803
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", NotGeoreferencedWarning)
        for i, path in enumerate(paths):
            scene = path.parents[1].name
            crop = path.stem.split("_")[-1]
            patch = f"{scene}_{crop}"
            bands = sorted(
                path.parents[1].glob(f"*/*_rhorc_*_{crop}.tif"),
                key=lambda p: int(p.stem.split("_")[-2]),
            )
            waves = [int(p.stem.split("_")[-2]) for p in bands]
            assert len(bands) == 11 and all(
                w in allowed for w, allowed in zip(waves, EXPECTED_WAVES)
            ), (path, waves)
            with rasterio.open(path) as ds:
                yf = ds.read(1)
                assert ds.shape == (240, 240)
                georef = not ds.transform.is_identity
            with rasterio.open(str(path).replace("_cl_", "_conf_")) as ds:
                cf = ds.read(1)
            with rasterio.open(str(path).replace("_cl_", "_rep_")) as ds:
                rf = ds.read(1)
            assert (
                np.isin(yf, range(16)).all()
                and np.isin(cf, range(4)).all()
                and np.isin(rf, range(4)).all()
            )
            y = yf.astype("uint8")
            c = cf.astype("uint8")
            rep = rf.astype("uint8")
            image = []
            masks = []
            for band in bands:
                with rasterio.open(band) as ds:
                    factor = int(band.parent.name) // 10
                    assert (
                        ds.count == 1 and ds.width * factor == ds.height * factor == 240
                    )
                    assert ds.scales == (1.0,) and ds.offsets == (0.0,)
                    image.append(
                        ds.read(1, out_shape=(240, 240), resampling=Resampling.nearest)
                    )
                    masks.append(
                        ds.read_masks(
                            1, out_shape=(240, 240), resampling=Resampling.nearest
                        )
                        > 0
                    )
            x = np.stack(image)
            valid = np.isfinite(x).all(axis=0) & np.stack(masks).all(axis=0)
            use = (y > 0) & (c > 0) & valid
            r, co = np.where(use)
            rows.append(
                dict(
                    patch_index=i,
                    patch_id=patch,
                    scene_id=scene,
                    original_split=split[patch],
                    split=split[patch],
                    georeferenced=georef,
                    acquisition_date_status="not_provided",
                    image_sha256=hashlib.sha256(x.tobytes()).hexdigest(),
                    total_pixels=y.size,
                    annotated_pixels=int((y > 0).sum()),
                    usable_pixels=int(use.sum()),
                    invalid_labelled_pixels=int(((y > 0) & ~valid).sum()),
                    labelled_without_confidence=int(((y > 0) & (c == 0)).sum()),
                    negative_values=int((x < 0).sum()),
                    above_one_values=int((x > 1).sum()),
                    **{f"class_{k}": int((y[use] == k).sum()) for k in CLASSES},
                )
            )
            for k, value in {
                "x": x[:, use].T,
                "y": y[use],
                "confidence": c[use],
                "report": rep[use],
                "patch_index": np.full(len(r), i, dtype="uint16"),
                "row": r.astype("uint16"),
                "col": co.astype("uint16"),
            }.items():
                chunks[k].append(value)
            if (i + 1) % 250 == 0:
                print("MADOS scanned", i + 1, "/", len(paths), flush=True)
    frame = pd.DataFrame(rows)
    assert set(frame.patch_id) == set(split)
    assert frame.groupby("scene_id").split.nunique().max() == 1
    # Unite scene identities linked by any identical complete 11-band patch.
    parent = {s: s for s in frame.scene_id.unique()}

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for _, part in frame.groupby("image_sha256"):
        scenes = part.scene_id.unique()
        for s in scenes[1:]:
            parent[find(s)] = find(scenes[0])
    frame["group"] = frame.scene_id.map(find)
    priority = {"train": 0, "val": 1, "test": 2}
    chosen = frame.groupby("group").original_split.agg(
        lambda s: max(s, key=priority.get)
    )
    frame["split"] = frame.group.map(chosen)
    assert frame.groupby("image_sha256").split.nunique().max() == 1
    pixels = {k: np.concatenate(v) for k, v in chunks.items()}
    np.savez_compressed(CACHE / "mados_pixels.npz", **pixels)
    frame.to_csv(OUT / "mados_inventory.csv", index=False)
    pd.DataFrame(
        {
            "band": BANDS,
            "S2A_wavelength": [max(v) for v in EXPECTED_WAVES],
            "S2B_wavelength": [min(v) for v in EXPECTED_WAVES],
        }
    ).to_csv(OUT / "mados_band_contract.csv", index=False)
    return frame, pixels


def bootstrap(groups, repeats=1000):
    rng = np.random.default_rng(42)
    rows = []
    for dataset, part in groups.groupby("dataset"):
        models = sorted(part.model.unique())
        ids = sorted(part.group.unique())
        arrays = {
            m: part[part.model == m]
            .set_index("group")
            .reindex(ids)[["tp", "fp", "fn", "tn"]]
            .fillna(0)
            .to_numpy()
            for m in models
        }
        draws = rng.integers(0, len(ids), (repeats, len(ids)))
        fs = {}
        for model, a in arrays.items():
            totals = a[draws].sum(axis=1)
            denom = 2 * totals[:, 0] + totals[:, 1] + totals[:, 2]
            f = np.divide(
                2 * totals[:, 0], denom, out=np.full(repeats, np.nan), where=denom > 0
            )
            fs[model] = f
            valid = f[np.isfinite(f)]
            rows.append(
                {
                    "dataset": dataset,
                    "comparison": model,
                    "groups": len(ids),
                    "valid_repeats": len(valid),
                    "low": float(np.quantile(valid, 0.025)),
                    "high": float(np.quantile(valid, 0.975)),
                    "metric": "F1",
                }
            )
        if "marida_frozen" in fs:
            for model in models:
                if model == "marida_frozen":
                    continue
                d = fs[model] - fs["marida_frozen"]
                d = d[np.isfinite(d)]
                rows.append(
                    {
                        "dataset": dataset,
                        "comparison": model + " minus marida_frozen",
                        "groups": len(ids),
                        "valid_repeats": len(d),
                        "low": float(np.quantile(d, 0.025)),
                        "high": float(np.quantile(d, 0.975)),
                        "metric": "paired_delta_F1",
                    }
                )
    return pd.DataFrame(rows)


def experiment(frame, pixels):
    marida = dict(np.load(ROOT / "data/processed/marida/annotated_pixels.npz"))
    mf = pd.read_csv(ROOT / "reports/marida/tables/split_membership.csv")
    mr = mf.split.to_numpy()[marida["patch_index"]]
    matches = exact_spectrum_matches(pixels["x"], marida["x"])
    matched_counts = np.bincount(
        pixels["patch_index"], weights=matches, minlength=len(frame)
    ).astype(int)
    frame["marida_exact_spectral_matches"] = matched_counts
    excluded = set(frame.loc[matched_counts > 0, "group"])
    frame["cross_source_screen_pass"] = ~frame.group.isin(excluded)
    frame.to_csv(OUT / "mados_inventory.csv", index=False)
    # Conservative: screen ALL original MARIDA splits; do not promote excluded pixels to another split.
    roles = frame.split.to_numpy()[pixels["patch_index"]]
    eligible = frame.cross_source_screen_pass.to_numpy()[pixels["patch_index"]]
    masks = {s: (roles == s) & eligible for s in ["train", "val", "test"]}
    summaries = []
    for s, m in masks.items():
        summaries.append(
            {
                "split": s,
                "pixels": int(m.sum()),
                "positive_pixels": int((pixels["y"][m] == 1).sum()),
                "patches": len(np.unique(pixels["patch_index"][m])),
                "scenes": frame.loc[
                    (frame.split == s) & frame.cross_source_screen_pass, "scene_id"
                ].nunique(),
            }
        )
        assert np.unique(pixels["y"][m] == 1).size == 2, (
            s,
            "insufficient binary classes",
        )
    pd.DataFrame(summaries).to_csv(OUT / "mados_split_summary.csv", index=False)
    print(
        "Exact cross-source matches",
        int(matches.sum()),
        "excluded groups",
        len(excluded),
        flush=True,
    )
    print(pd.DataFrame(summaries).to_string(index=False), flush=True)
    frozen = joblib.load(ROOT / "data/processed/marida_baseline/spectral_forest.joblib")
    meta = json.loads(
        (ROOT / "data/processed/marida_baseline/model_metadata.json").read_text()
    )
    threshold = next(
        t["threshold"] for t in meta["thresholds"] if t["model"] == "spectral_forest"
    )
    models = {"marida_frozen": (frozen, threshold)}
    thresholds = [
        {
            "model": "marida_frozen",
            "threshold": threshold,
            "selection": "previous MARIDA validation",
        }
    ]
    for name, include_marida in [("mados_only", False), ("joint", True)]:
        xx = [pixels["x"][masks["train"]]]
        yy = [pixels["y"][masks["train"]] == 1]
        cc = [pixels["confidence"][masks["train"]]]
        if include_marida:
            xx.append(marida["x"][mr == "train"])
            yy.append(marida["y"][mr == "train"] == 1)
            cc.append(marida["confidence"][mr == "train"])
        model = RandomForestClassifier(
            n_estimators=125,
            max_depth=20,
            min_samples_leaf=2,
            n_jobs=4,
            random_state=42,
            class_weight="balanced_subsample",
        )
        print("Training", name, "pixels", sum(map(len, yy)), flush=True)
        model.fit(
            np.concatenate(xx),
            np.concatenate(yy),
            sample_weight=np.array([1, 2 / 3, 1 / 3])[np.concatenate(cc) - 1],
        )
        threshold, valf1 = choose_threshold(
            pixels["y"][masks["val"]] == 1,
            model.predict_proba(pixels["x"][masks["val"]])[:, 1],
        )
        thresholds.append(
            {
                "model": name,
                "threshold": threshold,
                "validation_f1": valf1,
                "selection": "MADOS validation max F1",
            }
        )
        joblib.dump(model, CACHE / f"{name}.joblib", compress=3)
        models[name] = (model, threshold)
        print(name, "validation F1", valf1, flush=True)
    pd.DataFrame(thresholds).to_csv(OUT / "detector_thresholds.csv", index=False)
    metrics = []
    group_counts = []
    errors = []
    for dataset, d, mask, patches in [
        ("mados_test", pixels, masks["test"], frame),
        ("marida_development_test", marida, mr == "test", mf),
    ]:
        y = d["y"][mask]
        xx = d["x"][mask]
        patch_index = d["patch_index"][mask]
        groups = patches.group.to_numpy()[patch_index]
        predictions = {
            "y": y,
            "patch_index": patch_index,
            "group": groups.astype(str),
            "confidence": d["confidence"][mask],
        }
        for name, (model, threshold) in models.items():
            score = model.predict_proba(xx)[:, 1]
            pred = score >= threshold
            binary = y == 1
            predictions[name + "_score"] = score
            count = confusion(binary, pred)
            metrics.append(
                dict(
                    dataset=dataset,
                    model=name,
                    pixels=len(y),
                    positive_pixels=int(binary.sum()),
                    threshold=threshold,
                    **count,
                    **scores_from_counts(**count),
                    average_precision=average_precision_score(binary, score),
                )
            )
            for group in np.unique(groups):
                ix = groups == group
                group_counts.append(
                    dict(
                        dataset=dataset,
                        model=name,
                        group=group,
                        **confusion(binary[ix], pred[ix]),
                    )
                )
            for cls in np.unique(y):
                ix = y == cls
                errors.append(
                    {
                        "dataset": dataset,
                        "model": name,
                        "class_id": int(cls),
                        "pixels": int(ix.sum()),
                        "predicted_debris": int(pred[ix].sum()),
                        "predicted_debris_rate": float(pred[ix].mean()),
                    }
                )
        np.savez_compressed(CACHE / f"{dataset}_predictions.npz", **predictions)
    for name, data in [
        ("detector_metrics", metrics),
        ("detector_group_counts", group_counts),
        ("detector_errors_by_class", errors),
    ]:
        pd.DataFrame(data).to_csv(OUT / f"{name}.csv", index=False)
    bootstrap(pd.DataFrame(group_counts)).to_csv(
        OUT / "detector_bootstrap.csv", index=False
    )
    print(pd.DataFrame(metrics).to_string(index=False), flush=True)
    (CACHE / "model_metadata.json").write_text(
        json.dumps(
            {
                "bands": BANDS,
                "product": "ACOLITE rhorc",
                "positive_class": 1,
                "ignore_class": 0,
                "thresholds": thresholds,
                "status": "research_only; cross-source spatial-temporal independence unresolved",
                "production_ready": False,
                "random_seed": 42,
            },
            indent=2,
        )
    )


def main():
    if (CACHE / "mados_pixels.npz").exists() and (OUT / "mados_inventory.csv").exists():
        frame = pd.read_csv(OUT / "mados_inventory.csv")
        pixels = dict(np.load(CACHE / "mados_pixels.npz"))
    else:
        frame, pixels = scan(ROOT / "data/external/mados/MADOS")
    experiment(frame, pixels)


if __name__ == "__main__":
    main()
