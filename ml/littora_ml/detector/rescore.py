from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from littora_ml.common.io import read_json
from littora_ml.common.paths import REPORTS
from littora_ml.detector.dataset import PatchSet
from littora_ml.detector.evaluation import usable_labels
from littora_ml.detector.metrics import rates

PREDICTIONS = REPORTS / "predictions" / "detector"
REFERENCE = PREDICTIONS / "reference"
PARTS = ("val", "test")


def write_reference(patches: PatchSet, split: pd.Series, max_confidence_code: int = 3) -> dict:
    REFERENCE.mkdir(parents=True, exist_ok=True)
    values = split.to_numpy()
    names = patches.table["name"].to_numpy()
    out = {}
    for part in PARTS:
        index = np.flatnonzero(values == part)
        labels = usable_labels(patches, index, max_confidence_code).astype(np.uint8)
        np.savez_compressed(
            REFERENCE / f"{part}.npz",
            labels=labels,
            patches=np.array(names[index], dtype=str),
            scenes=np.array(patches.table["scene"].to_numpy()[index], dtype=str),
        )
        out[part] = {
            "patches": len(index),
            "labeled_pixels": int((labels > 0).sum()),
            "debris_pixels": int((labels == 1).sum()),
        }
    return out


def rescore(run: str) -> dict[str, Any]:
    predictions = np.load(PREDICTIONS / run / "test.npz")
    reference = np.load(REFERENCE / "test.npz")
    order = {name: position for position, name in enumerate(reference["patches"])}
    missing = [name for name in predictions["patches"] if name not in order]
    if missing:
        raise SystemExit(f"{len(missing)} патчей прогона нет в эталоне")
    labels = reference["labels"][[order[name] for name in predictions["patches"]]]
    mask = predictions["mask"].astype(bool)
    labeled = labels > 0
    truth = labels == 1
    counts = {
        "tp": int((mask & truth & labeled).sum()),
        "fp": int((mask & ~truth & labeled).sum()),
        "fn": int((~mask & truth & labeled).sum()),
    }
    recomputed = {**counts, **rates(counts)}
    stored = read_json(REPORTS / "metrics" / "detector" / f"{run}.json")["test"]
    return {
        "run": run,
        "patches": len(labels),
        "recomputed": recomputed,
        "stored": {key: stored.get(key) for key in ("precision", "recall", "f1", "iou")},
    }
