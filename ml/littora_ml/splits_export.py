from __future__ import annotations

import numpy as np
import pandas as pd

from littora_ml.common.paths import REPORTS, resolve
from littora_ml.detector.splits import with_regions


def export_detector_splits() -> pd.DataFrame:
    table = pd.read_parquet(resolve("data/processed/detector/marida_l2a/patches.parquet"))
    labels = np.load(resolve("data/processed/detector/marida/labels.npy"))
    frame = with_regions(table)[["name", "scene", "tile", "region", "date", "official_split"]]
    frame = frame.assign(
        l2a_available=table["l2a_found"].to_numpy(),
        common_split=table["official_split"].where(table["l2a_found"], "none").to_numpy(),
        debris_pixels=(labels == 1).sum(axis=(1, 2)),
        labeled_pixels=(labels > 0).sum(axis=(1, 2)),
    )
    out = REPORTS / "splits"
    out.mkdir(parents=True, exist_ok=True)
    frame.to_csv(out / "detector_marida.csv", index=False)
    return frame


def concentration_splits() -> pd.DataFrame:
    path = REPORTS / "splits" / "concentration.csv"
    if not path.exists():
        raise FileNotFoundError(
            "reports/splits/concentration.csv пишет concentration run: запустите его первым"
        )
    frame = pd.read_csv(path)
    if not {"report", "repetition", "outer_fold"} <= set(frame.columns):
        raise ValueError(
            "reports/splits/concentration.csv без повторов: перезапустите concentration run"
        )
    return frame
