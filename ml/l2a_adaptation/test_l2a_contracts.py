"""Contracts for the paired target-product experiment."""

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OUT = ROOT / "reports/l2a_adaptation"
CACHE = ROOT / "data/processed/l2a_adaptation"
spec = importlib.util.spec_from_file_location("l2a_train", HERE / "train.py")
train = importlib.util.module_from_spec(spec)
spec.loader.exec_module(train)


def test_reject_cross_split_group_and_unknown_labels():
    patches = pd.DataFrame(
        {
            "patch_id": list("abcdef"),
            "selection_index": range(6),
            "group": list("ABCDEF"),
            "split": ["train", "train", "val", "val", "test", "test"],
        }
    )
    pixels = {
        "patch_index": np.repeat(np.arange(6), 2),
        "y": np.tile([1, 7], 6),
        "confidence": np.ones(12, dtype=int),
        "l2a": np.zeros((12, 11)),
        "rhorc": np.zeros((12, 11)),
    }
    roles, groups = train.split_contract(patches, pixels)
    assert len(roles) == len(groups) == 12
    wrong = patches.copy()
    wrong.loc[2, "group"] = "A"
    with pytest.raises(AssertionError):
        train.split_contract(wrong, pixels)
    wrong_pixels = {**pixels, "y": pixels["y"].copy()}
    wrong_pixels["y"][0] = 0
    with pytest.raises(AssertionError):
        train.split_contract(patches, wrong_pixels)


def test_validation_thresholds_recomputed_without_test():
    f = json.loads((CACHE / "frozen_before_test.json").read_text())
    d = dict(np.load(CACHE / "validation_scores.npz"))
    for variant in f["threshold_variants"]:
        if "current L2A validation" not in variant["selection"]:
            continue
        threshold, _ = train.choose_threshold(d["y"] == 1, d[variant["forest"]])
        assert threshold == variant["threshold"]
    assert train.sha(CACHE / "paired_pixels.npz") == f["paired_pixels_sha256"]
    for key, digest in f["model_sha256"].items():
        assert train.sha(CACHE / f"{key}_rf.joblib") == digest


def test_identical_test_pixels_and_saved_metrics():
    f = json.loads((CACHE / "frozen_before_test.json").read_text())
    d = dict(np.load(CACHE / "test_scores.npz"))
    m = pd.read_csv(OUT / "tables/metrics.csv")
    m = m[(m["split"] == "test") & (m.scope == "all")].set_index("variant")
    for variant in f["threshold_variants"]:
        result = train.measures(d["y"], d[variant["forest"]], variant["threshold"])
        row = m.loc[variant["variant"]]
        assert len(d["y"]) == row.pixels
        assert all(result[k] == row[k] for k in ["tp", "fp", "fn", "tn"])
        assert np.isclose(result["f1"], row.f1, equal_nan=True)
    pixels = pd.read_csv(OUT / "tables/pixel_audit.csv")
    assert pixels.groupby("stac_id")["split"].nunique().max() == 1


def test_blacksea_labels_and_original_models_not_touched():
    m = json.loads((OUT / "run_manifest.json").read_text())
    assert m["training_performed"] and not m["new_blacksea_predictions"]
    for rel, digest in m["protected_sha256"].items():
        assert train.sha(ROOT / rel) == digest
    p = pd.read_csv(OUT / "tables/selected_patches.csv")
    original = pd.read_csv(
        ROOT / "reports/marida/tables/split_membership.csv"
    ).set_index("patch_id")
    assert (p["split"].to_numpy() == original.loc[p.patch_id, "split"].to_numpy()).all()
    assert (p.group.to_numpy() == original.loc[p.patch_id, "group"].to_numpy()).all()
