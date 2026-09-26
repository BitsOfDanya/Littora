"""Guard the label boundary, fixed thresholds, pairing and reported deltas."""

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports/score_check"
spec = importlib.util.spec_from_file_location(
    "score_check_run", Path(__file__).with_name("run.py")
)
run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run)


def test_unknown_pixels_are_not_scorable():
    for y in [np.array([0, 1, 7]), np.array([], dtype=int)]:
        with pytest.raises(ValueError):
            run.evaluate(y, np.zeros(len(y)), 0.5)
    result = run.evaluate(np.array([1, 7, 1]), np.array([0.9, 0.8, 0.2]), 0.5)
    assert (result["tp"], result["fp"], result["fn"], result["tn"]) == (1, 1, 1, 0)
    assert result["f1"] == 0.5


def test_paired_metrics_from_same_pixels_not_train_test_pool():
    metrics = pd.read_csv(OUT / "tables/model_metrics.csv")
    pixels = pd.read_csv(OUT / "tables/paired_pixel_scores.csv")
    manifest = json.loads((OUT / "run_manifest.json").read_text())
    for row in metrics[metrics.dataset.str.startswith("paired_")].itertuples():
        p = pixels[(pixels["split"] == row.split) & (pixels["product"] == row.product)]
        if row.confidence_mode == "high_only":
            p = p[p.confidence == 1]
        threshold = manifest["thresholds"][
            row.model if row.threshold_mode == "frozen" else "marida_frozen"
        ]
        assert threshold == row.threshold
        actual = run.evaluate(
            p.reference_class.to_numpy(), p[row.model].to_numpy(), threshold
        )
        assert len(p) == row.pixels and p.patch_id.nunique() == row.groups == 1
        assert all(actual[k] == getattr(row, k) for k in ["tp", "fp", "fn", "tn"])
        assert np.isclose(actual["f1"], row.f1, equal_nan=True)


def test_boost_does_not_claim_new_labels_or_blacksea_accuracy():
    m = json.loads((OUT / "run_manifest.json").read_text())
    assert m["new_training_labels"] == 0 and not m["training_performed"]
    assert not m["new_blacksea_detector_predictions"]
    assert (
        pd.read_csv(OUT / "tables/data_readiness.csv")
        .new_detector_training_labels.eq(0)
        .all()
    )
    checks = pd.read_csv(OUT / "tables/reproduction_checks.csv")
    assert len(checks) == 6 and checks.max_abs_score_difference.le(1e-12).all()
    bootstrap = pd.read_csv(OUT / "tables/paired_bootstrap.csv")
    assert not bootstrap.dataset.str.startswith("paired_").any()


def test_frozen_weights_labels_and_case_unchanged():
    m = json.loads((OUT / "run_manifest.json").read_text())
    assert len(m["protected_input_sha256"]) == 40
    for relative, digest in m["protected_input_sha256"].items():
        assert run.sha(ROOT / relative) == digest
