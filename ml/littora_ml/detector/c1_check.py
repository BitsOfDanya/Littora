from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy.ndimage import binary_dilation
from scipy.ndimage import label as connected

from littora_ml.common.io import read_json, write_json
from littora_ml.common.paths import REPORTS
from littora_ml.detector.calibration import service_area, service_rule
from littora_ml.detector.dataset import PatchSet
from littora_ml.detector.evaluation import code_fingerprint, score_patches, usable_labels
from littora_ml.detector.metrics import rates
from littora_ml.detector.postprocess import remove_small

PARTS = ("val", "test")
BOOTSTRAP = 2000
TOLERANT_CORR = 0.8
TOLERANCE_PX = 1
MIN_PRESENT = 0.5
STRUCTURE = np.ones((3, 3), dtype=bool)
REPORT_PATH = REPORTS / "metrics" / "detector" / "c1_check.json"
RULE = (
    "кандидат заменяет сервисную модель, если у него выше объектный F1 с допуском 1 пикс. на "
    "объединённой val: те же патчи val в старой обработке L2A и в C1, счётчики объектов "
    "складываются; test в выборе не участвует и оценён один раз"
)


def pixel_counts(
    decisions: np.ndarray, labels: np.ndarray, scenes: np.ndarray
) -> dict[str, np.ndarray]:
    out: dict[str, np.ndarray] = {}
    labeled = labels > 0
    truth = labels == 1
    for scene in np.unique(scenes):
        inside = (scenes == scene)[:, None, None] & labeled
        out[scene] = np.array(
            [
                int((decisions & truth & inside).sum()),
                int((decisions & ~truth & inside).sum()),
                int((~decisions & truth & inside).sum()),
            ]
        )
    return out


def patch_objects(decision: np.ndarray, labels: np.ndarray) -> np.ndarray:
    debris = labels == 1
    near_debris = binary_dilation(debris, STRUCTURE, TOLERANCE_PX)
    near_labeled = binary_dilation(labels > 0, STRUCTURE, TOLERANCE_PX)
    zones, count = connected(decision, structure=STRUCTURE)
    hits = misses = 0
    for zone in range(1, count + 1):
        mask = zones == zone
        if (mask & near_debris).any():
            hits += 1
        elif (mask & near_labeled).any():
            misses += 1
    objects, total = connected(debris, structure=STRUCTURE)
    reached = binary_dilation(decision, STRUCTURE, TOLERANCE_PX)
    found = sum(1 for item in range(1, total + 1) if (reached & (objects == item)).any())
    return np.array([hits, misses, found, total])


def object_counts(
    decisions: np.ndarray, labels: np.ndarray, scenes: np.ndarray
) -> dict[str, np.ndarray]:
    out: dict[str, np.ndarray] = {}
    for position, scene in enumerate(scenes):
        counts = patch_objects(decisions[position], labels[position])
        out[scene] = out.get(scene, np.zeros(4, dtype=np.int64)) + counts
    return out


def pixel_metrics(counts: np.ndarray) -> dict[str, float]:
    return rates({"tp": int(counts[0]), "fp": int(counts[1]), "fn": int(counts[2])})


def object_metrics(counts: np.ndarray) -> dict[str, float]:
    hits, misses, found, total = (int(value) for value in counts)
    precision = hits / (hits + misses) if hits + misses else 0.0
    recall = found / total if total else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "zones_on_debris": hits,
        "zones_on_other_labels": misses,
        "objects_found": found,
        "objects": total,
    }


def bootstrap(counts: list[dict[str, np.ndarray]], statistic, seed: int = 0) -> list[float] | None:
    scenes = sorted(set().union(*counts))
    if len(scenes) < 2:
        return None
    width = len(next(iter(counts[0].values())))
    rng = np.random.default_rng(seed)
    values = []
    for _ in range(BOOTSTRAP):
        chosen = rng.choice(scenes, len(scenes))
        sums = [
            np.sum([block.get(scene, np.zeros(width)) for scene in chosen], axis=0)
            for block in counts
        ]
        values.append(statistic(*sums))
    return [float(np.quantile(values, 0.025)), float(np.quantile(values, 0.975))]


def decisions_for(
    scorer, patches: PatchSet, indices: np.ndarray, rule: dict[str, Any]
) -> np.ndarray:
    scores = score_patches(scorer, patches, indices)
    area = service_area(patches, indices, rule)
    return remove_small((scores >= rule["threshold"]) & area, rule["min_pixels"])


def tolerant_scenes(c1: PatchSet) -> set[str]:
    alignment = read_json(c1.root / "source.json").get("alignment", {})
    return {
        scene
        for scene, value in alignment.items()
        if value.get("corr_best") is not None and value["corr_best"] >= TOLERANT_CORR
    }


def present(patches: PatchSet) -> np.ndarray:
    return np.array(
        [
            (np.asarray(patches.images[index, 1]) != 0).mean() >= MIN_PRESENT
            for index in range(len(patches.table))
        ]
    )


def selections(c1: PatchSet, l2a: PatchSet, split: pd.Series) -> dict[str, dict[str, np.ndarray]]:
    in_l2a = l2a.table["l2a_found"].to_numpy()
    aligned = c1.table["l2a_found"].to_numpy()
    tolerant = c1.table["scene"].isin(tolerant_scenes(c1)).to_numpy() & present(c1)
    values = split.to_numpy()
    return {
        part: {
            "strict": np.flatnonzero(in_l2a & aligned & (values == part)),
            "tolerant": np.flatnonzero(in_l2a & tolerant & (values == part)),
        }
        for part in PARTS
    }


def _block(per: dict[str, dict[str, np.ndarray]], metrics) -> dict[str, Any]:
    totals = {name: np.sum(list(block.values()), axis=0) for name, block in per.items()}
    return {
        "c1": metrics(totals["c1"]),
        "c1_f1_ci95": bootstrap([per["c1"]], lambda counts: metrics(counts)["f1"]),
        "l2a": metrics(totals["l2a"]),
        "l2a_f1_ci95": bootstrap([per["l2a"]], lambda counts: metrics(counts)["f1"]),
        "c1_minus_l2a_f1": metrics(totals["c1"])["f1"] - metrics(totals["l2a"])["f1"],
        "c1_minus_l2a_f1_ci95": bootstrap(
            [per["c1"], per["l2a"]],
            lambda first, second: metrics(first)["f1"] - metrics(second)["f1"],
        ),
        "pooled": metrics(totals["c1"] + totals["l2a"]),
        "counts": {name: [int(value) for value in total] for name, total in totals.items()},
    }


def evaluate_run(
    run: str,
    c1: PatchSet,
    l2a: PatchSet,
    chosen: dict[str, dict[str, np.ndarray]],
    max_confidence: int = 3,
) -> dict[str, Any]:
    from littora_ml.detector.inference import TrainedDetector

    rule = service_rule(run)
    scorer = TrainedDetector(run).scorer(tta=False)
    scenes = c1.table["scene"].to_numpy()
    out: dict[str, Any] = {"rule": rule}
    for part in PARTS:
        indices = chosen[part]["tolerant"]
        strict = np.isin(indices, chosen[part]["strict"])
        labels = usable_labels(l2a, indices, max_confidence)
        c1_valid = np.stack([np.asarray(c1.images[index, 1]) != 0 for index in indices])
        labels = np.where(c1_valid, labels, 0)
        decisions = {
            name: decisions_for(scorer, patches, indices, rule)
            for name, patches in (("c1", c1), ("l2a", l2a))
        }
        objects = {
            name: object_counts(value, labels, scenes[indices]) for name, value in decisions.items()
        }
        pixels = {
            name: pixel_counts(value[strict], labels[strict], scenes[indices][strict])
            for name, value in decisions.items()
        }
        out[part] = {
            "tolerant": {
                "patches": len(indices),
                "scenes": len(np.unique(scenes[indices])),
                **_block(objects, object_metrics),
            },
            "strict": {
                "patches": int(strict.sum()),
                "scenes": len(np.unique(scenes[indices][strict])),
                **(_block(pixels, pixel_metrics) if strict.any() else {}),
            },
        }
    return out


def alignment_summary(c1: PatchSet) -> dict[str, Any]:
    source = read_json(c1.root / "source.json")
    rows = [value for value in source.get("alignment", {}).values() if value.get("corr0")]
    shifts = [value["subpixel_shift"] for value in rows if value.get("subpixel_shift")]
    magnitude = [float(np.hypot(*shift)) for shift in shifts]
    return {
        "scenes_with_data": len(rows),
        "scenes_aligned": sum(1 for value in rows if value.get("aligned")),
        "scenes_tolerant": sum(
            1 for value in rows if (value.get("corr_best") or 0) >= TOLERANT_CORR
        ),
        "corr0_median": float(np.median([value["corr0"] for value in rows])) if rows else None,
        "subpixel_shift_median_px": float(np.median(magnitude)) if magnitude else None,
        "subpixel_shift_max_px": float(max(magnitude)) if magnitude else None,
        "min_alignment": source.get("min_alignment"),
        "tolerant_corr": TOLERANT_CORR,
        "tolerance_px": TOLERANCE_PX,
        "patches_aligned": source.get("patches_found"),
    }


def run_c1_check(
    service: str, candidates: list[str], c1: PatchSet, l2a: PatchSet, split: pd.Series
) -> dict[str, Any]:
    chosen = selections(c1, l2a, split)
    runs = {name: evaluate_run(name, c1, l2a, chosen) for name in [service, *candidates]}

    def score(name: str) -> float:
        return runs[name]["val"]["tolerant"]["pooled"]["f1"]

    best = max(runs, key=score)
    report = {
        "name": "c1_check",
        "code_sha256": code_fingerprint(),
        "protocol": (
            "одни и те же патчи MARIDA в старой обработке L2A и в C1 (sentinel-2-c1-l2a, "
            "смещение −0,1 и нижняя граница 1e-4, как в сервисе); режим сервиса — без TTA, "
            "порог, маска моря и минимум пикселей из правила прогона. Совмещение C1 с разметкой "
            "проверяется корреляцией деталей B02, B03, B04, B08 со снимком MARIDA при сдвигах "
            "до 1 пикс.: пиксельные метрики — только на сценах с корреляцией не ниже "
            "min_alignment при нулевом сдвиге; объектные — на сценах с корреляцией после лучшего "
            "сдвига не ниже tolerant_corr, зона засчитывается, если касается мусора с допуском "
            "1 пикс., объект найден, если зона в пределах 1 пикс.; зоны на неразмеченной воде "
            "не оцениваются; ДИ — бутстреп по сценам"
        ),
        "alignment": alignment_summary(c1),
        "selection_rule": RULE,
        "service": service,
        "chosen": best if score(best) > score(service) else service,
        "runs": runs,
    }
    write_json(REPORT_PATH, report)
    return report
