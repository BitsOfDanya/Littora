"""Fixed ablations on pixel groups and independent field profiles."""

import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml"))
from l2a_adaptation.train import RF_PARAMS, measures, sha, split_contract
from marida.models import choose_threshold

DATA = ROOT / "data/processed/metocean"
OUT = ROOT / "reports/metocean/tables"
PREFIXES = ["wind_", "wave_", "current_"]


def feature_columns(frame):
    return [
        c
        for c in frame
        if any(c.startswith(p) for p in PREFIXES)
        and (c.endswith(("_instant", "_mean24h", "_mean72h")))
    ]


def make_imputer(train, all_rows, columns):
    usable = [c for c in columns if train[c].notna().any()]
    if not usable:
        return None, np.zeros((len(all_rows), 0)), [], []
    imputer = SimpleImputer(strategy="median", add_indicator=True)
    imputer.fit(train[usable])
    return (
        imputer,
        imputer.transform(all_rows[usable]),
        usable,
        list(imputer.get_feature_names_out(usable)),
    )


def paired_f1(group_metrics):
    names = sorted(group_metrics.variant.unique())
    groups = sorted(group_metrics.group.unique())
    draws = np.random.default_rng(42).integers(0, len(groups), (1000, len(groups)))
    boot = {}
    rows = []
    for n in names:
        p = group_metrics[group_metrics.variant == n].set_index("group").loc[groups]
        a = p[["tp", "fp", "fn", "tn"]].to_numpy()[draws].sum(axis=1)
        boot[n] = np.divide(
            2 * a[:, 0],
            2 * a[:, 0] + a[:, 1] + a[:, 2],
            out=np.zeros(1000, dtype=float),
            where=(2 * a[:, 0] + a[:, 1] + a[:, 2]) > 0,
        )
        rows.append(
            {
                "comparison": n,
                "kind": "F1",
                "groups": len(groups),
                "low": np.quantile(boot[n], 0.025),
                "high": np.quantile(boot[n], 0.975),
            }
        )
    for n in names:
        if n == "spectral":
            continue
        d = boot[n] - boot["spectral"]
        rows.append(
            {
                "comparison": n + " minus spectral",
                "kind": "delta_F1",
                "groups": len(groups),
                "low": np.quantile(d, 0.025),
                "high": np.quantile(d, 0.975),
            }
        )
    return pd.DataFrame(rows)


def pixels():
    p = pd.read_csv(ROOT / "reports/l2a_adaptation/tables/selected_patches.csv")
    d = dict(np.load(ROOT / "data/processed/l2a_adaptation/paired_pixels.npz"))
    roles, groups = split_contract(p, d)
    env = (
        pd.read_csv(DATA / "features.csv")
        .set_index("join_id")
        .loc["patch:" + p.patch_id]
        .reset_index()
    )
    assert (env.selection_index.to_numpy() == p.selection_index.to_numpy()).all()
    cols = feature_columns(env)
    imputer, xpatch, usable, expanded = make_imputer(env[p.split == "train"], env, cols)
    assert imputer is not None
    spec = {
        "spectral": [],
        "spectral_wind": ["wind_"],
        "spectral_waves": ["wave_"],
        "spectral_currents": ["current_"],
        "spectral_all": PREFIXES,
        "environment_only": PREFIXES,
    }
    tr = roles == "train"
    va = roles == "val"
    te = roles == "test"
    weight = np.array([1, 2 / 3, 1 / 3])[d["confidence"][tr].astype(int) - 1]
    forests = {}
    xs = {}
    thresholds = {}
    val_scores = {}
    meta = {}
    for name, prefix in spec.items():
        ec = [
            i
            for i, c in enumerate(expanded)
            if any(c.startswith((s, "missingindicator_" + s)) for s in prefix)
        ]
        e = xpatch[d["patch_index"]][:, ec]
        x = e if name == "environment_only" else np.column_stack([d["l2a"], e])
        if x.shape[1] == 0:
            continue
        forest = RandomForestClassifier(**dict(RF_PARAMS, max_features=3))
        forest.fit(x[tr], d["y"][tr] == 1, sample_weight=weight)
        sv = forest.predict_proba(x[va])[:, 1]
        threshold, _ = choose_threshold(d["y"][va] == 1, sv)
        forests[name] = forest
        xs[name] = x
        thresholds[name] = threshold
        val_scores[name] = sv
        names = (
            []
            if name == "environment_only"
            else [
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
            ]
        ) + [expanded[i] for i in ec]
        joblib.dump(
            {
                "model": forest,
                "imputer": imputer,
                "raw_environment_columns": usable,
                "environment_indices": ec,
                "feature_names": names,
                "threshold": threshold,
            },
            DATA / (name + ".joblib"),
            compress=3,
        )
        meta[name] = {
            "features": names,
            "threshold": threshold,
            "model_sha256": sha(DATA / (name + ".joblib")),
        }
        print("Trained", name, "features", len(names), flush=True)
    frozen = {
        "frozen_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "variants": meta,
        "imputation_fit": "unique TRAIN patches",
        "excluded_all_missing": [c for c in cols if c not in usable],
        "input_sha256": sha(DATA / "features.csv"),
        "protocol_sha256": sha(ROOT / "ml/metocean/protocol.md"),
        "params": dict(RF_PARAMS, max_features=3),
        "threshold_selection": "validation max F1; highest threshold tie",
    }
    (DATA / "frozen_before_test.json").write_text(json.dumps(frozen, indent=2))
    print("Frozen models and validation thresholds; test inference starts.", flush=True)
    tests = {n: m.predict_proba(xs[n][te])[:, 1] for n, m in forests.items()}
    np.savez_compressed(
        DATA / "pixel_test_scores.npz",
        y=d["y"][te],
        group=groups[te],
        patch_index=d["patch_index"][te],
        **tests,
    )
    np.savez_compressed(
        DATA / "pixel_validation_scores.npz",
        y=d["y"][va],
        group=groups[va],
        **val_scores,
    )
    rows = []
    gc = []
    errors = []
    slices = []
    imports = []
    geo = pd.read_csv(ROOT / "reports/l2a_adaptation/tables/geographic_audit.csv")
    far = geo.beyond_100km_from_train.to_numpy()[d["patch_index"][te]]
    for n, forest in forests.items():
        t = thresholds[n]
        for role, mask, sc in [("val", va, val_scores[n]), ("test", te, tests[n])]:
            rows.append(
                dict(
                    variant=n, split=role, threshold=t, **measures(d["y"][mask], sc, t)
                )
            )
        yy = d["y"][te]
        gg = groups[te]
        sc = tests[n]
        for g in np.unique(gg):
            m = gg == g
            gc.append(dict(variant=n, group=g, **measures(yy[m], sc[m], t)))
        for label, m in [
            ("high_confidence", d["confidence"][te] == 1),
            ("beyond_100km", far),
        ]:
            if m.any():
                slices.append(dict(variant=n, slice=label, **measures(yy[m], sc[m], t)))
        for c in np.unique(yy):
            m = yy == c
            pred = sc[m] >= t
            errors.append(
                {
                    "variant": n,
                    "class_id": c,
                    "pixels": m.sum(),
                    "predicted_debris": pred.sum(),
                }
            )
        for name, imp in zip(meta[n]["features"], forest.feature_importances_):
            imports.append({"variant": n, "feature": name, "impurity_importance": imp})
    for name, frame in [
        ("pixel_metrics", rows),
        ("pixel_group_metrics", gc),
        ("pixel_class_errors", errors),
        ("pixel_slices", slices),
        ("pixel_impurity_importance", imports),
    ]:
        pd.DataFrame(frame).to_csv(OUT / (name + ".csv"), index=False)
    paired_f1(pd.DataFrame(gc)).to_csv(OUT / "pixel_bootstrap.csv", index=False)
    print(
        pd.DataFrame(rows)
        .query("split == 'test'")[
            ["variant", "f1", "precision", "recall", "average_precision"]
        ]
        .to_string(index=False),
        flush=True,
    )


def field():
    case = pd.read_csv(ROOT / "data/case/macroplastic_marine_samples.csv").set_index(
        "sample_id"
    )
    member = pd.read_csv(ROOT / "reports/eda/tables/cv_memberships.csv")
    env = pd.read_csv(DATA / "features.csv").set_index("join_id")
    cols = feature_columns(env)
    # A daily summary is context only for events whose exact start is unknown.
    # Keep separate columns; do not label daily values instantaneous.
    cols += [
        c
        for c in env
        if any(c.startswith(p) for p in PREFIXES) and c.endswith("_daily_mean")
    ]
    selected = member[
        ["sample_id", "event_id", "measurement_profile", "group"]
    ].drop_duplicates("sample_id")
    frame = selected.merge(
        case.reset_index().drop(columns=["event_id", "measurement_profile"]),
        on="sample_id",
        validate="one_to_one",
    )
    frame = frame.merge(
        env[cols], left_on="event_id", right_index=True, validate="many_to_one"
    ).set_index("sample_id")
    day = pd.to_datetime(frame.date_utc).dt.dayofyear
    frame["season_sin"] = np.sin(2 * np.pi * day / 365.25)
    frame["season_cos"] = np.cos(2 * np.pi * day / 365.25)
    base = ["latitude", "longitude", "season_sin", "season_cos"]
    rows = []
    for (profile, fold), mem in member.groupby(["measurement_profile", "fold"]):
        train = frame.loc[mem.loc[mem.role == "train", "sample_id"]]
        test = frame.loc[mem.loc[mem.role == "test", "sample_id"]]
        assert set(train.group).isdisjoint(set(test.group))
        ytrain = train.concentration_items_km2.to_numpy()
        yt = test.concentration_items_km2.to_numpy()
        for name, cc in [
            ("train_median", []),
            ("location_season", base),
            ("location_season_environment", base + cols),
            ("environment_only", cols),
        ]:
            if not cc:
                pred = np.full(len(test), np.median(ytrain))
            else:
                imp, xx, _usable, _ = make_imputer(train, pd.concat([train, test]), cc)
                if imp is None:
                    continue
                model = RandomForestRegressor(
                    n_estimators=125,
                    max_depth=8,
                    min_samples_leaf=3,
                    max_features=1.0,
                    random_state=42,
                    n_jobs=4,
                )
                model.fit(xx[: len(train)], np.log1p(ytrain))
                pred = np.maximum(0, np.expm1(model.predict(xx[len(train) :])))
            for (sid, r), y, pr in zip(test.iterrows(), yt, pred):
                rows.append(
                    {
                        "measurement_profile": profile,
                        "fold": fold,
                        "sample_id": sid,
                        "event_id": r.event_id,
                        "group": r.group,
                        "variant": name,
                        "y_true": y,
                        "y_pred": pr,
                        "abs_error": abs(y - pr),
                    }
                )
    pred = pd.DataFrame(rows)
    pred.to_csv(OUT / "field_oof_predictions.csv", index=False)
    metrics = []
    ci = []
    for (profile, name), g in pred.groupby(["measurement_profile", "variant"]):
        metrics.append(
            {
                "measurement_profile": profile,
                "variant": name,
                "events": len(g),
                "groups": g.group.nunique(),
                "MAE": mean_absolute_error(g.y_true, g.y_pred),
                "RMSE": np.sqrt(mean_squared_error(g.y_true, g.y_pred)),
                "RMSLE": np.sqrt(
                    mean_squared_error(np.log1p(g.y_true), np.log1p(g.y_pred))
                ),
                "R2": r2_score(g.y_true, g.y_pred),
            }
        )
    for profile, g in pred.groupby("measurement_profile"):
        wide = g.pivot(
            index=["event_id", "group"], columns="variant", values="abs_error"
        ).reset_index()
        group_values = [z for _, z in wide.groupby("group")]
        rng = np.random.default_rng(42)
        deltas = []
        for _ in range(1000):
            draw = pd.concat(
                [
                    group_values[i]
                    for i in rng.integers(0, len(group_values), len(group_values))
                ]
            )
            deltas.append(
                (draw.location_season - draw.location_season_environment).mean()
            )
        ci.append(
            {
                "measurement_profile": profile,
                "comparison": "MAE control minus environment (positive improves)",
                "groups": len(group_values),
                "gain": (
                    wide.location_season - wide.location_season_environment
                ).mean(),
                "low": np.quantile(deltas, 0.025),
                "high": np.quantile(deltas, 0.975),
            }
        )
    pd.DataFrame(metrics).to_csv(OUT / "field_metrics.csv", index=False)
    pd.DataFrame(ci).to_csv(OUT / "field_bootstrap.csv", index=False)
    print(pd.DataFrame(metrics).to_string(index=False), flush=True)


def main():
    protected = [
        ROOT / "data/case/macroplastic_marine_samples.csv",
        ROOT / "data/processed/l2a_adaptation/l2a_rf.joblib",
    ]
    protected += list(
        (ROOT / "data/external/validation-bridge/blacksea_holdout").rglob("labels.tif")
    )
    hashes = {str(p): sha(p) for p in protected}
    pixels()
    field()
    assert hashes == {str(p): sha(p) for p in protected}
    (DATA / "protected_hashes.json").write_text(json.dumps(hashes, indent=2))


if __name__ == "__main__":
    main()
