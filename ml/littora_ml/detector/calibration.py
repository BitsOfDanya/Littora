from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
from scipy.special import expit
from sklearn.isotonic import IsotonicRegression

from littora_ml.common.io import read_json, write_json
from littora_ml.common.paths import MODELS, REPORTS
from littora_ml.detector.dataset import PatchSet
from littora_ml.detector.evaluation import (
    code_fingerprint,
    scene_bootstrap,
    score_patches,
    unlabeled_alarms,
    usable_labels,
)
from littora_ml.detector.metrics import best_threshold, confusion, rates
from littora_ml.detector.postprocess import SEA_GROW, SEA_MAX_HOLE, remove_small, sea_mask

EPS = 1e-15
BINS = 15
SERVICE = MODELS / "detector" / "service"
PARTS = ("val", "test")


def logit(probability: np.ndarray) -> np.ndarray:
    clipped = np.clip(np.asarray(probability, dtype=np.float64), EPS, 1 - EPS)
    return np.log(clipped) - np.log1p(-clipped)


def log_loss(probability: np.ndarray, truth: np.ndarray) -> float:
    clipped = np.clip(np.asarray(probability, dtype=np.float64), EPS, 1 - EPS)
    truth = np.asarray(truth, dtype=bool)
    return float(-np.mean(np.where(truth, np.log(clipped), np.log1p(-clipped))))


def brier(probability: np.ndarray, truth: np.ndarray) -> float:
    return float(np.mean((np.asarray(probability, dtype=np.float64) - truth) ** 2))


def _bin_sums(probability: np.ndarray, truth: np.ndarray, bins: int):
    probability = np.asarray(probability, dtype=np.float64)
    index = np.clip((probability * bins).astype(np.int64), 0, bins - 1)
    count = np.bincount(index, minlength=bins)
    confidence = np.bincount(index, weights=probability, minlength=bins)
    hits = np.bincount(index, weights=np.asarray(truth, dtype=np.float64), minlength=bins)
    return count, confidence, hits


def expected_calibration_error(
    probability: np.ndarray, truth: np.ndarray, bins: int = BINS
) -> float:
    count, confidence, hits = _bin_sums(probability, truth, bins)
    return float(np.abs(confidence - hits).sum() / max(int(count.sum()), 1))


def reliability_bins(
    probability: np.ndarray, truth: np.ndarray, bins: int = BINS
) -> list[dict[str, Any]]:
    count, confidence, hits = _bin_sums(probability, truth, bins)
    return [
        {
            "lower": index / bins,
            "upper": (index + 1) / bins,
            "pixels": int(count[index]),
            "mean_probability": confidence[index] / count[index] if count[index] else None,
            "frequency": hits[index] / count[index] if count[index] else None,
        }
        for index in range(bins)
    ]


def reliability(
    probability: np.ndarray, truth: np.ndarray, with_bins: bool = False
) -> dict[str, Any]:
    probability = np.asarray(probability, dtype=np.float64)
    truth = np.asarray(truth, dtype=bool)
    result: dict[str, Any] = {
        "pixels": len(truth),
        "positives": int(truth.sum()),
        "frequency": float(truth.mean()) if len(truth) else None,
        "mean_probability": float(probability.mean()) if len(truth) else None,
        "ece": expected_calibration_error(probability, truth),
        "brier": brier(probability, truth) if len(truth) else None,
        "log_loss": log_loss(probability, truth) if len(truth) else None,
    }
    if with_bins:
        result["bins"] = reliability_bins(probability, truth)
    return result


class Temperature:
    method = "temperature"

    def __init__(self, temperature: float = 1.0) -> None:
        self.temperature = float(temperature)

    def fit(self, probability: np.ndarray, truth: np.ndarray) -> Temperature:
        logits = logit(probability)
        truth = np.asarray(truth, dtype=bool)

        def loss(log_temperature: float) -> float:
            scaled = logits / np.exp(log_temperature)
            return float(np.mean(np.logaddexp(0.0, np.where(truth, -scaled, scaled))))

        result = minimize_scalar(
            loss, bounds=(-4.0, 4.0), method="bounded", options={"xatol": 1e-7}
        )
        self.temperature = float(np.exp(result.x))
        return self

    def __call__(self, probability: np.ndarray) -> np.ndarray:
        return expit(logit(probability) / self.temperature)

    def params(self) -> dict[str, Any]:
        return {"method": self.method, "temperature": self.temperature}


class Isotonic:
    method = "isotonic"

    def __init__(self, x: list[float] | None = None, y: list[float] | None = None) -> None:
        self.x = np.asarray(x if x is not None else [0.0, 1.0], dtype=np.float64)
        self.y = np.asarray(y if y is not None else [0.0, 1.0], dtype=np.float64)

    def fit(self, probability: np.ndarray, truth: np.ndarray) -> Isotonic:
        model = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
        model.fit(np.asarray(probability, dtype=np.float64), np.asarray(truth, dtype=np.float64))
        self.x = np.asarray(model.X_thresholds_, dtype=np.float64)
        self.y = np.asarray(model.y_thresholds_, dtype=np.float64)
        return self

    def __call__(self, probability: np.ndarray) -> np.ndarray:
        return np.interp(np.asarray(probability, dtype=np.float64), self.x, self.y)

    def params(self) -> dict[str, Any]:
        return {"method": self.method, "x": self.x.tolist(), "y": self.y.tolist()}


CALIBRATORS = {"temperature": Temperature, "isotonic": Isotonic}


def from_params(params: dict[str, Any]) -> Temperature | Isotonic:
    if params["method"] == "temperature":
        return Temperature(params["temperature"])
    if params["method"] == "isotonic":
        return Isotonic(params["x"], params["y"])
    raise ValueError(f"неизвестный калибратор {params['method']}")


def out_of_fold(
    method: str, probability: np.ndarray, truth: np.ndarray, groups: np.ndarray
) -> np.ndarray:
    predicted = np.empty(len(probability), dtype=np.float64)
    for group in np.unique(groups):
        held = groups == group
        calibrator = CALIBRATORS[method]().fit(probability[~held], truth[~held])
        predicted[held] = calibrator(probability[held])
    return predicted


def decision_metrics(mask: np.ndarray, labels: np.ndarray) -> dict[str, Any]:
    labeled = labels > 0
    counts = confusion(mask[labeled].astype(np.float32), labels[labeled] == 1, 0.5)
    return {**counts, **rates(counts)}


def service_rule(run: str) -> dict[str, Any]:
    path = SERVICE / "detector.json"
    manifest = read_json(path) if path.exists() else {}
    if manifest.get("name") == run:
        sea = manifest.get("sea_mask") or {}
        return {
            "source": "models/detector/service/detector.json",
            "in_service": True,
            "threshold": float(manifest["threshold"]),
            "min_pixels": int(manifest.get("min_pixels", 1)),
            "sea_mask": {"grow": sea["grow"], "max_hole": sea["max_hole"]} if sea else None,
        }
    from littora_ml.detector.inference import run_postprocessing

    chosen = run_postprocessing(run)
    return {
        "source": f"reports/metrics/detector/{run}.json",
        "in_service": False,
        "threshold": float(chosen["threshold"]),
        "min_pixels": int(chosen.get("min_pixels", 1)),
        "sea_mask": {"grow": SEA_GROW, "max_hole": SEA_MAX_HOLE},
    }


def service_area(patches: PatchSet, indices: np.ndarray, rule: dict[str, Any]) -> np.ndarray:
    keep = np.stack([np.asarray(patches.images[index, 1]) != 0 for index in indices])
    scl_path = patches.root / "scl.npy"
    if rule["sea_mask"] is None or not scl_path.exists():
        return keep
    scl = np.load(scl_path, mmap_mode="r")
    sea = np.stack(
        [
            sea_mask(np.asarray(scl[index]), rule["sea_mask"]["grow"], rule["sea_mask"]["max_hole"])
            for index in indices
        ]
    )
    return keep & sea


def _labeled(scores: np.ndarray, labels: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    labeled = labels > 0
    return scores[labeled].astype(np.float64), labels[labeled] == 1


def _pixel_groups(labels: np.ndarray, scenes: np.ndarray) -> np.ndarray:
    return np.repeat(scenes, (labels > 0).reshape(len(labels), -1).sum(axis=1))


def _summary(block: dict[str, Any]) -> dict[str, Any]:
    return {key: block[key] for key in ("ece", "brier", "log_loss", "mean_probability")}


def calibrate_mode(
    scores: dict[str, np.ndarray],
    labels: dict[str, np.ndarray],
    scenes: dict[str, np.ndarray],
    areas: dict[str, np.ndarray],
    rule: dict[str, Any],
    patches: PatchSet,
    test_index: np.ndarray,
) -> tuple[dict[str, Any], Temperature | Isotonic]:
    pixels = {part: _labeled(scores[part], labels[part]) for part in PARTS}
    val_p, val_y = pixels["val"]
    groups = _pixel_groups(labels["val"], scenes["val"])
    fitted = {name: kind().fit(val_p, val_y) for name, kind in CALIBRATORS.items()}
    folds = {
        name: reliability(out_of_fold(name, val_p, val_y, groups), val_y) for name in CALIBRATORS
    }
    folds["raw"] = reliability(val_p, val_y)
    chosen = min(CALIBRATORS, key=lambda name: (folds[name]["log_loss"], folds[name]["brier"]))
    calibrator = fitted[chosen]
    service_threshold = rule["threshold"]
    curves = {}
    for part in PARTS:
        probability, truth = pixels[part]
        detected = probability >= service_threshold
        variants = {"raw": probability, **{name: fitted[name](probability) for name in fitted}}
        curves[part] = {
            name: {
                **reliability(values, truth, with_bins=True),
                "above_service_threshold": reliability(values[detected], truth[detected]),
            }
            for name, values in variants.items()
        }
    raw_threshold, raw_f1 = best_threshold(val_p, val_y)
    calibrated_threshold, calibrated_f1 = best_threshold(calibrator(val_p), val_y)
    mapped = {
        "val_max_f1": float(calibrator(np.array([raw_threshold]))[0]),
        "service": float(calibrator(np.array([service_threshold]))[0]),
    }
    mismatches = {"val_max_f1": 0, "service": 0}
    for part in PARTS:
        calibrated = calibrator(scores[part])
        mismatches["val_max_f1"] += int(
            ((calibrated >= calibrated_threshold) != (scores[part] >= raw_threshold)).sum()
        )
        mismatches["service"] += int(
            ((calibrated >= mapped["service"]) != (scores[part] >= service_threshold)).sum()
        )
    zero = float(calibrator(np.array([0.0]))[0])
    thresholds = {
        "raw_val_max_f1": raw_threshold,
        "raw_val_max_f1_f1": raw_f1,
        "calibrated_val_max_f1": calibrated_threshold,
        "calibrated_val_max_f1_f1": calibrated_f1,
        "calibrated_of_raw_val_max_f1": mapped["val_max_f1"],
        "same_operating_point": bool(np.isclose(calibrated_threshold, mapped["val_max_f1"]))
        and mismatches["val_max_f1"] == 0,
        "service_raw": service_threshold,
        "service_calibrated": mapped["service"],
        "calibrated_zero": zero,
        "decision_mismatches_all_pixels": mismatches,
        "monotonic": bool(np.all(np.diff(calibrator(np.linspace(0, 1, 2001))) >= 0)),
    }
    operating = {"service": service_threshold, "val_max_f1": raw_threshold}
    metrics: dict[str, Any] = {}
    for option, threshold in operating.items():
        block = {"raw_threshold": threshold}
        for part in PARTS:
            pixel = scores[part] >= threshold
            final = remove_small(pixel & areas[part], rule["min_pixels"])
            entry = {"pixel": decision_metrics(pixel, labels[part])}
            entry["service"] = decision_metrics(final, labels[part])
            if part == "test":
                entry["pixel_ci95_scene_bootstrap"] = scene_bootstrap(
                    pixel.astype(np.float32), labels[part], scenes[part], 0.5
                )
                entry["service_ci95_scene_bootstrap"] = scene_bootstrap(
                    final.astype(np.float32), labels[part], scenes[part], 0.5
                )
                entry["service_unlabeled_alarms"] = unlabeled_alarms(
                    final.astype(np.float32), patches, test_index, 0.5
                )
            block[part] = entry
        metrics[option] = block
    result = {
        "calibrators": {name: model.params() for name, model in fitted.items()},
        "selection": {
            "criterion": (
                "log-loss (затем Brier) вне фолда на val: калибратор обучается на остальных "
                "сценах val и применяется к отложенной сцене; тест в выборе не участвует"
            ),
            "folds": len(np.unique(groups)),
            "out_of_fold_val": {name: _summary(block) for name, block in folds.items()},
            "chosen": chosen,
        },
        "reliability": curves,
        "threshold": thresholds,
        "metrics": metrics,
    }
    return result, calibrator


def reliability_figure(run: str, mode: dict[str, Any], out: Path) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    chosen = mode["selection"]["chosen"]
    series = (("raw", "до калибровки", "#2a78d6"), (chosen, f"после: {chosen}", "#eb6834"))
    figure, axes = plt.subplots(
        2, 2, figsize=(10, 6.4), sharex=True, gridspec_kw={"height_ratios": [3, 1]}
    )
    for column, part in enumerate(PARTS):
        top, bottom = axes[0][column], axes[1][column]
        top.plot([0, 1], [0, 1], color="#9a9893", linewidth=1, linestyle="--")
        width = 1 / BINS / 2.4
        for offset, (key, label, color) in enumerate(series):
            block = mode["reliability"][part][key]
            used = [row for row in block["bins"] if row["pixels"]]
            x = [row["mean_probability"] for row in used]
            y = [row["frequency"] for row in used]
            top.plot(x, y, color=color, linewidth=2, marker="o", markersize=5, label=label)
            centers = [(row["lower"] + row["upper"]) / 2 for row in used]
            shift = (offset - 0.5) * width
            bottom.bar(
                [value + shift for value in centers],
                [row["pixels"] for row in used],
                width=width,
                color=color,
            )
            detected = block["above_service_threshold"]
            top.text(
                0.02,
                0.95 - 0.07 * offset,
                f"{label}: ECE {block['ece']:.5f} · выше порога {detected['ece']:.3f}",
                transform=top.transAxes,
                fontsize=8,
                color="#0b0b0b",
            )
        info = mode["reliability"][part]["raw"]
        count = f"{info['pixels']:,}".replace(",", " ")
        top.set_title(f"{part}: {count} размеченных пикс., мусор {info['positives']}", fontsize=10)
        top.set_xlim(0, 1)
        top.set_ylim(0, 1.02)
        top.grid(color="#e4e3df", linewidth=0.6)
        top.set_ylabel("доля мусора")
        bottom.set_yscale("log")
        bottom.set_xlabel("предсказанная вероятность (среднее в корзине, 15 корзин)")
        bottom.set_ylabel("пикселей")
        bottom.grid(axis="y", color="#e4e3df", linewidth=0.6)
        for axis in (top, bottom):
            axis.spines[["top", "right"]].set_visible(False)
    axes[0][0].legend(loc="lower right", fontsize=8, frameon=False)
    figure.suptitle(f"{run}: надёжность вероятности без TTA, как в сервисе", fontsize=11)
    figure.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(out, dpi=110)
    plt.close(figure)
    return out


def _rates(block: dict[str, Any]) -> dict[str, Any]:
    keys = ("precision", "recall", "f1", "iou")
    return {part: {key: block[part]["service"][key] for key in keys} for part in PARTS}


def service_candidate(
    run: str,
    mode: dict[str, Any],
    calibrator: Temperature | Isotonic,
    rule: dict[str, Any],
    fitted_on: str,
) -> dict[str, Any]:
    thresholds = mode["threshold"]
    operating = mode["metrics"]["val_max_f1"]
    current = mode["metrics"]["service"]
    chosen = mode["selection"]["chosen"]
    test = mode["reliability"]["test"]
    return {
        "name": run,
        "applies_to": (
            "вероятность detector.onnx без TTA до масок; калибровка монотонна, порог "
            "threshold на калиброванной шкале даёт то же решение, что raw_threshold на исходной"
        ),
        **calibrator.params(),
        "method_choice": (
            "температура выбрана по log-loss вне фолда по сценам val: изотоническая регрессия "
            "даёт p = 0 части размеченного мусора; по Brier и ECE без TTA изотоническая чуть лучше"
        ),
        "threshold": thresholds["service_calibrated"],
        "raw_threshold": thresholds["service_raw"],
        "threshold_rule": (
            "на val порог манифеста и максимум F1 без TTA различаются на один пиксель; оставлен "
            "порог манифеста, выбранный ранее на val, решения сервиса не меняются"
        ),
        "alternative_threshold": thresholds["calibrated_val_max_f1"],
        "alternative_raw_threshold": thresholds["raw_val_max_f1"],
        "min_pixels": rule["min_pixels"],
        "fitted_on": fitted_on,
        "val_pixel_f1": {
            "threshold": current["val"]["pixel"]["f1"],
            "alternative_threshold": operating["val"]["pixel"]["f1"],
        },
        "service_metrics": _rates(current),
        "alternative_metrics": _rates(operating),
        "test_reliability": {
            "before": _summary(test["raw"]),
            "after": _summary(test[chosen]),
        },
    }


def run_calibration(
    run: str, patches: PatchSet, split: pd.Series, data: str, split_name: str
) -> dict[str, Any]:
    from littora_ml.detector.inference import TrainedDetector

    detector = TrainedDetector(run)
    max_confidence_code = 3
    if detector.kind == "network":
        max_confidence_code = detector.config.get("labels", {}).get("max_confidence_code", 3)
    rule = service_rule(run)
    values = split.to_numpy()
    index = {part: np.flatnonzero(values == part) for part in PARTS}
    labels = {part: usable_labels(patches, index[part], max_confidence_code) for part in PARTS}
    scenes = {part: patches.table["scene"].to_numpy()[index[part]] for part in PARTS}
    areas = {part: service_area(patches, index[part], rule) for part in PARTS}
    modes = {"plain": False, "tta": True} if detector.kind == "network" else {"plain": False}
    report: dict[str, Any] = {
        "name": f"calibration__{run}",
        "run": run,
        "code_sha256": code_fingerprint(),
        "data_variant": data,
        "split_name": split_name,
        "service_rule": rule,
        "sea_mask_applied": (patches.root / "scl.npy").exists() and rule["sea_mask"] is not None,
        "protocol": (
            "оценки пересчитаны моделью прогона на val и test; калибраторы обучены только на "
            "размеченных пикселях val (протокол MARIDA, класс 1 — мусор), тест оценён один раз; "
            f"ECE — {BINS} равных корзин; service — порог, затем обнуление вне B02 != 0 и маски "
            "моря по SCL патча, затем удаление компонент меньше min_pixels (8-связность), "
            "как в сервисе; above_service_threshold — пиксели с исходной вероятностью не ниже "
            "порога сервиса, это вероятности, которые видит пользователь в зонах"
        ),
        "patches": {part: len(index[part]) for part in PARTS},
        "modes": {},
    }
    candidate = None
    for mode_name, tta in modes.items():
        scorer = detector.scorer(tta)
        scores = {part: score_patches(scorer, patches, index[part]) for part in PARTS}
        mode, calibrator = calibrate_mode(
            scores, labels, scenes, areas, rule, patches, index["test"]
        )
        report["modes"][mode_name] = {"tta": tta, **mode}
        if mode_name == "plain":
            val = mode["reliability"]["val"]["raw"]
            fitted_on = (
                f"{data}, разбиение {split_name}, val: {val['pixels']} размеченных пикселей, "
                f"{val['positives']} мусор; выбор по log-loss вне фолда по сценам val"
            )
            candidate = service_candidate(run, mode, calibrator, rule, fitted_on)
    out = REPORTS / "metrics" / "detector" / f"calibration__{run}.json"
    write_json(out, report)
    reliability_figure(
        run,
        report["modes"]["plain"],
        REPORTS / "figures" / "detector" / run / "reliability.png",
    )
    if candidate is not None and rule["in_service"]:
        write_json(SERVICE / "calibration.json", candidate)
    return report
