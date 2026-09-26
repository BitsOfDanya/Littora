"""Fresh frozen-model inference plus EDA; do not invent labels for optical data."""

import hashlib
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import rasterio
from sklearn.metrics import average_precision_score

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml"))
from expansion.mados import bootstrap
from marida.models import confusion, scores_from_counts

OUT = ROOT / "reports/score_check"
CACHE = ROOT / "data/processed/score_check"
BRIDGE = ROOT / "reports/validation_bridge/tables"
BANDS = ["B01", "B02", "B03", "B04", "B05", "B06", "B07", "B08", "B8A", "B11", "B12"]
MODEL_PATHS = {
    "marida_frozen": ROOT / "data/processed/marida_baseline/spectral_forest.joblib",
    "mados_only": ROOT / "data/processed/expansion/mados_only.joblib",
    "joint": ROOT / "data/processed/expansion/joint.joblib",
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evaluate(y, scores, threshold):
    if not len(y) or (y == 0).any():
        raise ValueError("Only nonempty, known reference classes may be scored")
    binary = y == 1
    counts = confusion(binary, scores >= threshold)
    return dict(
        pixels=len(y),
        positive_pixels=int(binary.sum()),
        threshold=threshold,
        **counts,
        **scores_from_counts(**counts),
        average_precision=float(average_precision_score(binary, scores))
        if np.unique(binary).size == 2
        else np.nan,
    )


def record_metrics(
    dataset,
    product,
    split,
    y,
    confidence,
    groups,
    scores,
    thresholds,
    metrics,
    group_counts,
    errors,
):
    for model, score in scores.items():
        for mode, threshold in [
            ("frozen", thresholds[model]),
            ("common_marida_threshold", thresholds["marida_frozen"]),
        ]:
            for confidence_mode, keep in [
                ("all", np.ones(len(y), dtype=bool)),
                ("high_only", confidence == 1),
            ]:
                if not keep.any():
                    continue
                metrics.append(
                    dict(
                        dataset=dataset,
                        product=product,
                        split=split,
                        model=model,
                        threshold_mode=mode,
                        confidence_mode=confidence_mode,
                        groups=len(np.unique(groups[keep])),
                        **evaluate(y[keep], score[keep], threshold),
                    )
                )
            if mode != "frozen":
                continue
            pred = score >= threshold
            for group in np.unique(groups):
                keep = groups == group
                group_counts.append(
                    dict(
                        dataset=dataset,
                        product=product,
                        split=split,
                        model=model,
                        group=str(group),
                        **confusion(y[keep] == 1, pred[keep]),
                    )
                )
            for cls in np.unique(y):
                keep = y == cls
                errors.append(
                    {
                        "dataset": dataset,
                        "product": product,
                        "split": split,
                        "model": model,
                        "class_id": int(cls),
                        "pixels": int(keep.sum()),
                        "predicted_debris": int(pred[keep].sum()),
                        "predicted_debris_rate": float(pred[keep].mean()),
                    }
                )


def full_benchmarks(models, thresholds, metrics, group_counts, errors):
    checks = []
    specs = [
        (
            "marida_development_test",
            "data/processed/marida/annotated_pixels.npz",
            "reports/marida/tables/split_membership.csv",
        ),
        (
            "mados_test",
            "data/processed/expansion/mados_pixels.npz",
            "reports/expansion/tables/mados_inventory.csv",
        ),
    ]
    for name, pixel_path, inventory_path in specs:
        d = dict(np.load(ROOT / pixel_path))
        inventory = pd.read_csv(ROOT / inventory_path).sort_values("patch_index")
        assert np.array_equal(inventory.patch_index, np.arange(len(inventory)))
        mask = inventory.split.to_numpy()[d["patch_index"]] == "test"
        if "cross_source_screen_pass" in inventory:
            mask &= inventory.cross_source_screen_pass.to_numpy()[d["patch_index"]]
        y = d["y"][mask]
        x = d["x"][mask]
        confidence = d["confidence"][mask]
        groups = inventory.group.to_numpy()[d["patch_index"][mask]].astype(str)
        old = dict(np.load(ROOT / f"data/processed/expansion/{name}_predictions.npz"))
        assert np.array_equal(y, old["y"]) and np.array_equal(groups, old["group"])
        assert np.array_equal(d["patch_index"][mask], old["patch_index"])
        scores = {}
        for model, forest in models.items():
            score = forest.predict_proba(x)[:, 1]
            delta = float(np.max(np.abs(score - old[model + "_score"])))
            assert delta <= 1e-12, (name, model, delta)
            checks.append(
                {
                    "dataset": name,
                    "model": model,
                    "pixels": len(y),
                    "max_abs_score_difference": delta,
                }
            )
            scores[model] = score
            print(name, model, evaluate(y, score, thresholds[model])["f1"], flush=True)
        np.savez_compressed(
            CACHE / f"{name}_scores.npz",
            y=y,
            confidence=confidence,
            group=groups,
            patch_index=d["patch_index"][mask],
            **scores,
        )
        record_metrics(
            name,
            "rhorc",
            "development_test",
            y,
            confidence,
            groups,
            scores,
            thresholds,
            metrics,
            group_counts,
            errors,
        )
    pd.DataFrame(checks).to_csv(OUT / "tables/reproduction_checks.csv", index=False)


def paired_benchmarks(models, thresholds, metrics, group_counts, errors):
    pairs = pd.read_csv(BRIDGE / "radiometry_pairs.csv")
    inventory = pd.read_csv(
        ROOT / "reports/marida/tables/split_membership.csv"
    ).set_index("patch_id")
    flips = []
    predictions = []
    for row in pairs[pairs.match_status == "paired"].itertuples():
        meta = inventory.loc[row.patch_id]
        folder = ROOT / row.paired_folder
        with rasterio.open(folder / "rhorc.tif") as ds:
            rhorc = ds.read()
        with rasterio.open(folder / "l2a.tif") as ds:
            l2a = ds.read()
        with rasterio.open(folder / "reference_labels.tif") as ds:
            y = ds.read(1)
        with rasterio.open(ROOT / "data/external/marida" / meta.confidence_path) as ds:
            confidence = ds.read(1)
        use = (
            np.isfinite(rhorc).all(axis=0)
            & np.isfinite(l2a).all(axis=0)
            & (y > 0)
            & (confidence > 0)
        )
        rr, cc = np.where(use)
        yy = y[use]
        cf = confidence[use]
        groups = np.repeat(meta.group, len(yy))
        dataset = "paired_" + meta["split"]
        for product, x in [("rhorc", rhorc), ("L2A", l2a)]:
            scores = {
                name: model.predict_proba(x[:, use].T)[:, 1]
                for name, model in models.items()
            }
            record_metrics(
                dataset,
                product,
                meta["split"],
                yy,
                cf,
                groups,
                scores,
                thresholds,
                metrics,
                group_counts,
                errors,
            )
            pred = pd.DataFrame(
                dict(
                    patch_id=row.patch_id,
                    split=meta["split"],
                    product=product,
                    row=rr,
                    col=cc,
                    reference_class=yy,
                    confidence=cf,
                    **scores,
                )
            )
            predictions.append(pred)
            base = scores["marida_frozen"] >= thresholds["marida_frozen"]
            target = yy == 1
            for name in ["mados_only", "joint"]:
                p = scores[name] >= thresholds[name]
                flips.append(
                    {
                        "patch_id": row.patch_id,
                        "split": meta["split"],
                        "product": product,
                        "model": name,
                        "corrected_errors": int(
                            ((base != target) & (p == target)).sum()
                        ),
                        "introduced_errors": int(
                            ((base == target) & (p != target)).sum()
                        ),
                        "recovered_debris": int((target & ~base & p).sum()),
                        "lost_debris": int((target & base & ~p).sum()),
                        "removed_false_positives": int((~target & base & ~p).sum()),
                        "added_false_positives": int((~target & ~base & p).sum()),
                    }
                )
    pd.concat(predictions).to_csv(OUT / "tables/paired_pixel_scores.csv", index=False)
    pd.DataFrame(flips).to_csv(OUT / "tables/paired_error_changes.csv", index=False)


def eda():
    coverage = []
    for name, filename in [
        ("EMBLAS", "reports/expansion/tables/emblas_events_pending.csv"),
        (
            "DOORS_litter",
            "reports/validation_bridge/tables/doors_transects_pending_geometry.csv",
        ),
        ("DOORS_TriOS", "reports/validation_bridge/tables/doors_trios_rrs.csv"),
        ("DOORS_MicroPro", "reports/validation_bridge/tables/doors_micropro_aop.csv"),
        (
            "DOORS_water_quality",
            "reports/validation_bridge/tables/doors_water_quality.csv",
        ),
        (
            "Romania_July2024",
            "reports/validation_bridge/tables/romania_july2024_pending.csv",
        ),
        (
            "BlackSea_holdout",
            "reports/validation_bridge/tables/blacksea_holdout_registry.csv",
        ),
    ]:
        d = pd.read_csv(ROOT / filename)
        coverage.append(
            {
                "source": name,
                "rows": len(d),
                "new_detector_training_labels": 0,
                "new_eligible_T3_events": 0,
                "source_table": filename,
            }
        )
        pd.DataFrame(
            {
                "column": d.columns,
                "missing": d.isna().sum().values,
                "missing_fraction": d.isna().mean().values,
            }
        ).to_csv(OUT / f"tables/{name}_missingness.csv", index=False)
    pd.DataFrame(coverage).to_csv(OUT / "tables/data_readiness.csv", index=False)
    rrs = pd.read_csv(BRIDGE / "doors_trios_rrs.csv").copy()
    waves = [f"Rrs_{w}" for w in range(400, 851)]
    summary = []
    for w in waves:
        v = rrs[w].to_numpy()
        summary.append(
            {
                "wavelength_nm": int(w[4:]),
                "n": len(v),
                "mean": v.mean(),
                "std": v.std(ddof=1),
                "minimum": v.min(),
                "p10": np.quantile(v, 0.1),
                "median": np.median(v),
                "p90": np.quantile(v, 0.9),
                "maximum": v.max(),
            }
        )
    pd.DataFrame(summary).to_csv(OUT / "tables/rrs_spectral_summary.csv", index=False)
    rrs["day_utc"] = pd.to_datetime(rrs.datetime_utc, utc=True).dt.date.astype(str)
    accepted = pd.read_csv(BRIDGE / "doors_optical_primary_candidates.csv")
    rrs["has_optical_candidate"] = rrs.record_id.isin(accepted.record_id)
    rrs[
        [
            "record_id",
            "Station",
            "datetime_utc",
            "day_utc",
            "Latitude",
            "Longitude",
            "has_optical_candidate",
        ]
    ].to_csv(OUT / "tables/optical_coverage.csv", index=False)
    hydro = pd.read_csv(BRIDGE / "doors_water_quality.csv")
    hydro[["tsm (mg/l)", "chl (mg/m3)", "secchi disk (m)"]].describe().to_csv(
        OUT / "tables/water_quality_summary.csv"
    )
    registry = pd.read_csv(BRIDGE / "blacksea_holdout_registry.csv")
    assert (
        registry.training_allowed.eq(False).all()
        and registry.model_predictions_computed.eq(False).all()
    )
    pixels = dict(np.load(ROOT / "data/processed/marida/annotated_pixels.npz"))
    inventory = pd.read_csv(ROOT / "reports/marida/tables/split_membership.csv")
    train = inventory.split.to_numpy()[pixels["patch_index"]] == "train"
    water = pixels["x"][train & (pixels["y"] == 7)]
    low, high = np.quantile(water, [0.01, 0.99], axis=0)
    stats = []
    domain = []
    for row in registry.itertuples():
        folder = ROOT / row.folder
        with rasterio.open(folder / "l2a.tif") as ds:
            x = ds.read()
        with rasterio.open(folder / "scl.tif") as ds:
            scl = ds.read(1)
        with rasterio.open(folder / "labels.tif") as ds:
            assert not ds.read().any(), (
                "New labels arrived: revise this protocol before scoring"
            )
        for scope, mask in [
            ("all", np.isfinite(x).all(axis=0)),
            ("SCL_water", scl == 6),
        ]:
            xx = x[:, mask].T
            for b, band in enumerate(BANDS):
                v = xx[:, b]
                stats.append(
                    {
                        "chip_id": row.chip_id,
                        "scope": scope,
                        "band": band,
                        "pixels": len(v),
                        "minimum": float(v.min()),
                        "p01": float(np.quantile(v, 0.01)),
                        "median": float(np.median(v)),
                        "p99": float(np.quantile(v, 0.99)),
                        "maximum": float(v.max()),
                        "negative_fraction": float((v < 0).mean()),
                    }
                )
            outside = (xx < low) | (xx > high)
            domain.append(
                {
                    "chip_id": row.chip_id,
                    "scope": scope,
                    "pixels": len(xx),
                    "outside_any_train_water_marginal_range": float(
                        outside.any(axis=1).mean()
                    ),
                    "mean_bands_outside": float(outside.sum(axis=1).mean()),
                    "interpretation": "L2A versus rhorc description; not classifier OOD or litter accuracy",
                }
            )
    pd.DataFrame(stats).to_csv(OUT / "tables/blacksea_band_statistics.csv", index=False)
    pd.DataFrame(domain).to_csv(
        OUT / "tables/blacksea_radiometry_ranges.csv", index=False
    )
    pd.DataFrame(
        {
            "band": BANDS,
            "train_water_p01": low,
            "train_water_p99": high,
            "train_water_median": np.median(water, axis=0),
            "pixels": len(water),
        }
    ).to_csv(OUT / "tables/marida_train_water_reference.csv", index=False)
    print("EDA complete; Black Sea detector predictions not computed.", flush=True)


def main():
    (OUT / "tables").mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    protected = list(MODEL_PATHS.values()) + [
        ROOT / "data/case/macroplastic_marine_samples.csv"
    ]
    protected += list(
        (ROOT / "data/external/validation-bridge/blacksea_holdout").rglob("labels.tif")
    )
    before = {str(p.relative_to(ROOT)): sha(p) for p in protected}
    meta = json.loads(
        (ROOT / "data/processed/expansion/model_metadata.json").read_text()
    )
    thresholds = {r["model"]: r["threshold"] for r in meta["thresholds"]}
    models = {name: joblib.load(p) for name, p in MODEL_PATHS.items()}
    for model in models.values():
        model.set_params(n_jobs=4)
    metrics = []
    counts = []
    errors = []
    paired_benchmarks(models, thresholds, metrics, counts, errors)
    pd.DataFrame(metrics).to_csv(OUT / "tables/metrics_in_progress.csv", index=False)
    full_benchmarks(models, thresholds, metrics, counts, errors)
    pd.DataFrame(metrics).to_csv(OUT / "tables/model_metrics.csv", index=False)
    group_counts = pd.DataFrame(counts)
    group_counts.to_csv(OUT / "tables/group_counts.csv", index=False)
    pd.DataFrame(errors).to_csv(OUT / "tables/errors_by_class.csv", index=False)
    bootstrap(
        group_counts[
            group_counts.dataset.isin(["mados_test", "marida_development_test"])
        ]
    ).to_csv(OUT / "tables/paired_bootstrap.csv", index=False)
    eda()
    assert before == {str(p.relative_to(ROOT)): sha(p) for p in protected}
    manifest = {
        "status": "completed",
        "new_training_labels": 0,
        "training_performed": False,
        "new_blacksea_detector_predictions": False,
        "protected_input_sha256": before,
        "thresholds": thresholds,
        "protocol_sha256": sha(Path(__file__).with_name("protocol.md")),
    }
    inputs = [
        ROOT / "data/processed/marida/annotated_pixels.npz",
        ROOT / "data/processed/expansion/mados_pixels.npz",
        ROOT / "data/processed/expansion/model_metadata.json",
        ROOT / "reports/marida/tables/split_membership.csv",
        ROOT / "reports/expansion/tables/mados_inventory.csv",
    ]
    inputs += list(BRIDGE.glob("*.csv"))
    inputs += list((ROOT / "data/external/validation-bridge").rglob("*.tif"))
    pd.DataFrame(
        [{"path": str(p.relative_to(ROOT)), "sha256": sha(p)} for p in inputs]
    ).to_csv(OUT / "tables/input_hashes.csv", index=False)
    manifest["run_code_sha256"] = sha(Path(__file__))
    (OUT / "run_manifest.json").write_text(json.dumps(manifest, indent=2))
    print("Frozen-model run complete; all protected hashes unchanged.", flush=True)


if __name__ == "__main__":
    main()
