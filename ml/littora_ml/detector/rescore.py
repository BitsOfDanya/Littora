from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from littora_ml.common.io import read_json, write_json
from littora_ml.common.paths import REPORTS
from littora_ml.detector.dataset import PatchSet
from littora_ml.detector.evaluation import usable_labels
from littora_ml.detector.metrics import rates

PREDICTIONS = REPORTS / "predictions" / "detector"
REFERENCE = PREDICTIONS / "reference"
METRICS = REPORTS / "metrics" / "detector"
SPLITS = REPORTS / "splits" / "detector_marida.csv"
REGIONS_PREFIX = "regions_service__"
PARTS = ("val", "test")
REGIONS_DESCRIPTION = (
    "Разбивка отложенного test по регионам для сервисной модели: P, R, F1 и IoU посчитаны по "
    "размеченным пикселям каждого региона при рабочем пороге прогона. Модель обучалась на train "
    "всех регионов, поэтому это не проверка на новом регионе, а разброс качества внутри test."
)


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


def _aligned(run: str) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    predictions = np.load(PREDICTIONS / run / "test.npz")
    reference = np.load(REFERENCE / "test.npz")
    order = {name: position for position, name in enumerate(reference["patches"])}
    missing = [name for name in predictions["patches"] if name not in order]
    if missing:
        raise SystemExit(f"{len(missing)} патчей прогона нет в эталоне")
    index = [order[name] for name in predictions["patches"]]
    return (
        predictions["patches"],
        reference["scenes"][index],
        reference["labels"][index],
        predictions["mask"].astype(bool),
    )


def _counts(mask: np.ndarray, labels: np.ndarray) -> dict[str, int]:
    labeled = labels > 0
    truth = labels == 1
    return {
        "tp": int((mask & truth & labeled).sum()),
        "fp": int((mask & ~truth & labeled).sum()),
        "fn": int((~mask & truth & labeled).sum()),
    }


def _block(mask: np.ndarray, labels: np.ndarray, scenes: np.ndarray) -> dict[str, Any]:
    counts = _counts(mask, labels)
    return {
        "patches": len(labels),
        "scenes": len(set(scenes.tolist())),
        "labeled_pixels": int((labels > 0).sum()),
        "debris_pixels": int((labels == 1).sum()),
        **counts,
        **rates(counts),
    }


def rescore(run: str) -> dict[str, Any]:
    _, _, labels, mask = _aligned(run)
    counts = _counts(mask, labels)
    recomputed = {**counts, **rates(counts)}
    stored = read_json(METRICS / f"{run}.json")["test"]
    return {
        "run": run,
        "patches": len(labels),
        "recomputed": recomputed,
        "stored": {key: stored.get(key) for key in ("precision", "recall", "f1", "iou")},
    }


def rescore_by_region(run: str) -> dict[str, Any]:
    names, scenes, labels, mask = _aligned(run)
    table = pd.read_csv(SPLITS, usecols=["name", "region"]).drop_duplicates("name")
    region_of = table.set_index("name")["region"].reindex(names).to_numpy()
    unknown = int(pd.isna(region_of).sum())
    if unknown:
        raise SystemExit(f"{unknown} патчей прогона нет в {SPLITS.name}")
    regions = {}
    for region in sorted(set(region_of.tolist())):
        index = np.flatnonzero(region_of == region)
        regions[region] = _block(mask[index], labels[index], scenes[index])
    config = read_json(METRICS / f"{run}.json").get("config") or {}
    report = {
        "name": f"{REGIONS_PREFIX}{run}",
        "run": run,
        "part": "test",
        "split": config.get("split"),
        "description": REGIONS_DESCRIPTION,
        "regions": dict(sorted(regions.items(), key=lambda item: -item[1]["debris_pixels"])),
        "pooled": _block(mask, labels, scenes),
    }
    write_json(METRICS / f"{REGIONS_PREFIX}{run}.json", report)
    return report
