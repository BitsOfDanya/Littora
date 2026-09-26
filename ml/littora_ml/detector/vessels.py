from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy.ndimage import binary_dilation
from scipy.ndimage import label as connected

from littora_ml.common.io import read_json, write_json
from littora_ml.common.paths import MODELS, REPORTS
from littora_ml.detector.dataset import PatchSet
from littora_ml.detector.evaluation import code_fingerprint, score_patches
from littora_ml.detector.marida import BANDS
from littora_ml.detector.postprocess import remove_small, sea_mask

DEBRIS = 1
SHIP = 5
WAKE = 14
SHIP_CLASSES = (SHIP, WAKE)
FIT_PARTS = ("train", "val")
CHECK_PART = "test"
QUANTILE = 0.975
WINDOW = 20
MIN_WATER = 20
WATER_SCL = 6
STRUCTURE = np.ones((3, 3), dtype=bool)
VISIBLE = [BANDS.index(name) for name in ("B02", "B03", "B04")]
B04, B08, B11, B12 = (BANDS.index(name) for name in ("B04", "B08", "B11", "B12"))
SERVICE = MODELS / "detector" / "service"
RULE_PATH = SERVICE / "vessels.json"
REPORT_PATH = REPORTS / "metrics" / "detector" / "flags" / "vessels.json"
FEATURES = (
    "pixels",
    "swir_peak",
    "swir22_peak",
    "visible_contrast",
    "nir_red",
    "elongation",
    "fill",
    "trail_pixels",
    "trail_length",
)


def _axes(rows: np.ndarray, cols: np.ndarray) -> tuple[float, float]:
    if len(rows) < 3:
        return float(len(rows)), 1.0
    values = np.linalg.eigvalsh(np.cov(np.vstack([cols, rows]).astype(np.float64)))
    major, minor = max(float(values[-1]), 0.0), max(float(values[0]), 0.0)
    return 4.0 * np.sqrt(major), float(np.sqrt(major / max(minor, 1.0 / 12.0)))


def object_features(
    image: np.ndarray, scl: np.ndarray | None, mask: np.ndarray, trail_contrast: float
) -> dict[str, float]:
    rows, cols = np.nonzero(mask)
    height, width = mask.shape
    top, bottom = max(rows.min() - WINDOW, 0), min(rows.max() + WINDOW + 1, height)
    left, right = max(cols.min() - WINDOW, 0), min(cols.max() + WINDOW + 1, width)
    crop = np.asarray(image[:, top:bottom, left:right], dtype=np.float32)
    zone = mask[top:bottom, left:right]
    valid = crop[1] != 0
    near = binary_dilation(zone, STRUCTURE, 1)
    ring = valid & ~binary_dilation(zone, STRUCTURE, 2)
    water = ring & (scl[top:bottom, left:right] == WATER_SCL) if scl is not None else ring
    base = water if water.sum() >= MIN_WATER else ring
    if not base.any():
        base = valid
    visible = crop[VISIBLE].mean(axis=0)
    contrast = visible - float(np.median(visible[base])) if base.any() else visible
    inside = near & valid
    if not inside.any():
        inside = near
    body = zone & valid if (zone & valid).any() else zone
    bright = valid & (contrast >= trail_contrast)
    groups, _ = connected(bright | near, structure=STRUCTURE)
    touching = np.unique(groups[near])
    trail = np.isin(groups, touching[touching > 0]) & ~near
    trail_rows, trail_cols = np.nonzero(trail)
    trail_length, _ = _axes(trail_rows, trail_cols)
    zone_rows, zone_cols = np.nonzero(zone)
    _, elongation = _axes(zone_rows, zone_cols)
    span = (np.ptp(zone_rows) + 1) * (np.ptp(zone_cols) + 1)
    return {
        "pixels": float(zone.sum()),
        "swir_peak": float(crop[B11][inside].max()),
        "swir22_peak": float(crop[B12][inside].max()),
        "visible_contrast": float(contrast[inside].max()),
        "nir_red": float(np.median(crop[B08][body] - crop[B04][body])),
        "elongation": elongation,
        "fill": float(zone.sum() / span),
        "trail_pixels": float(trail.sum()),
        "trail_length": trail_length if trail.any() else 0.0,
    }


def vessel_like(features: dict[str, float], rule: dict[str, Any]) -> bool:
    return (
        features["swir_peak"] >= rule["swir_peak"]
        or features["visible_contrast"] >= rule["visible_contrast"]
    )


def label_components(
    patches: PatchSet, indices: np.ndarray, classes: tuple[int, ...], trail_contrast: float
) -> pd.DataFrame:
    scl = np.load(patches.root / "scl.npy", mmap_mode="r")
    rows = []
    for index in indices:
        labels = np.asarray(patches.labels[index])
        if not np.isin(labels, classes).any():
            continue
        image = np.asarray(patches.images[index], dtype=np.float32)
        scene_classes = np.asarray(scl[index])
        for kind in classes:
            groups, count = connected(labels == kind, structure=STRUCTURE)
            for group in range(1, count + 1):
                features = object_features(image, scene_classes, groups == group, trail_contrast)
                rows.append({"patch": int(index), "label": kind, **features})
    return pd.DataFrame(rows, columns=["patch", "label", *FEATURES])


def edge_subsets(
    patches: PatchSet, indices: np.ndarray, trail_contrast: float, size: int = 2
) -> pd.DataFrame:
    scl = np.load(patches.root / "scl.npy", mmap_mode="r")
    rows = []
    for index in indices:
        labels = np.asarray(patches.labels[index])
        if not (labels == SHIP).any():
            continue
        image = np.asarray(patches.images[index], dtype=np.float32)
        visible = image[VISIBLE].mean(axis=0)
        groups, count = connected(labels == SHIP, structure=STRUCTURE)
        for group in range(1, count + 1):
            ship = groups == group
            if ship.sum() <= size:
                continue
            edge = ship & binary_dilation(~ship, STRUCTURE, 1)
            edge_rows, edge_cols = np.nonzero(edge)
            order = np.argsort(visible[edge_rows, edge_cols])[:size]
            subset = np.zeros_like(ship)
            subset[edge_rows[order], edge_cols[order]] = True
            features = object_features(image, np.asarray(scl[index]), subset, trail_contrast)
            rows.append({"patch": int(index), "label": SHIP, **features})
    return pd.DataFrame(rows, columns=["patch", "label", *FEATURES])


def wake_contrast(patches: PatchSet, indices: np.ndarray) -> tuple[float, int]:
    scl = np.load(patches.root / "scl.npy", mmap_mode="r")
    values = []
    for index in indices:
        labels = np.asarray(patches.labels[index])
        if not (labels == WAKE).any():
            continue
        image = np.asarray(patches.images[index], dtype=np.float32)
        visible = image[VISIBLE].mean(axis=0)
        valid = image[1] != 0
        water = valid & (np.asarray(scl[index]) == WATER_SCL) & np.isin(labels, (0, 7))
        base = water if water.sum() >= MIN_WATER else valid
        values.append(visible[labels == WAKE] - float(np.median(visible[base])))
    merged = np.concatenate(values) if values else np.zeros(0)
    return (float(np.median(merged)) if len(merged) else 0.0), len(merged)


def derive_rule(fit: pd.DataFrame, trail_contrast: float, quantile: float) -> dict[str, Any]:
    debris = fit[fit["label"] == DEBRIS]
    return {
        "swir_peak": float(debris["swir_peak"].quantile(quantile)),
        "visible_contrast": float(debris["visible_contrast"].quantile(quantile)),
        "trail_contrast": trail_contrast,
        "trail_pixels": float(debris["trail_pixels"].quantile(quantile)),
    }


def _share(flags: pd.Series) -> dict[str, Any]:
    count = len(flags)
    flagged = int(flags.sum())
    return {"objects": count, "flagged": flagged, "share": flagged / count if count else None}


def flag_rates(table: pd.DataFrame, rule: dict[str, Any]) -> dict[str, Any]:
    if table.empty:
        return {}
    swir = table["swir_peak"] >= rule["swir_peak"]
    visible = table["visible_contrast"] >= rule["visible_contrast"]
    trail = table["trail_pixels"] >= rule["trail_pixels"]
    flagged = swir | visible
    result = {}
    for kind, name in ((SHIP, "ship"), (DEBRIS, "debris")):
        chosen = table["label"] == kind
        if not chosen.any():
            continue
        result[name] = {
            **_share(flagged[chosen]),
            "by_criterion": {
                "swir_peak": _share(swir[chosen])["share"],
                "visible_contrast": _share(visible[chosen])["share"],
                "trail_pixels": _share(trail[chosen])["share"],
                "trail_adds": _share((trail & ~flagged)[chosen])["share"],
            },
        }
    return result


def _quantiles(table: pd.DataFrame) -> dict[str, Any]:
    levels = (0.05, 0.25, 0.5, 0.75, 0.95)
    return {
        name: {
            feature: [float(table.loc[table["label"] == kind, feature].quantile(q)) for q in levels]
            for feature in FEATURES
        }
        for kind, name in ((SHIP, "ship"), (DEBRIS, "debris"))
        if (table["label"] == kind).any()
    }


def service_zones(
    scores: np.ndarray,
    patches: PatchSet,
    indices: np.ndarray,
    rule: dict[str, Any],
    service: dict[str, Any],
) -> dict[str, Any]:
    scl = np.load(patches.root / "scl.npy", mmap_mode="r")
    sea = service.get("sea_mask") or {}
    groups: dict[str, list[bool]] = {"debris": [], "ship": [], "other_labeled": [], "unlabeled": []}
    for position, index in enumerate(indices):
        image = np.asarray(patches.images[index], dtype=np.float32)
        scene_classes = np.asarray(scl[index])
        detected = (scores[position] >= service["threshold"]) & (image[1] != 0)
        if sea:
            detected &= sea_mask(scene_classes, sea["grow"], sea["max_hole"])
        detected = remove_small(detected[None], int(service.get("min_pixels", 1)))[0]
        zones, count = connected(detected, structure=STRUCTURE)
        labels = np.asarray(patches.labels[index])
        for zone in range(1, count + 1):
            mask = zones == zone
            around = labels[binary_dilation(mask, STRUCTURE, 1)]
            if (labels[mask] == DEBRIS).any():
                group = "debris"
            elif np.isin(around, SHIP_CLASSES).any():
                group = "ship"
            elif (labels[mask] > 0).any():
                group = "other_labeled"
            else:
                group = "unlabeled"
            features = object_features(image, scene_classes, mask, rule["trail_contrast"])
            groups[group].append(vessel_like(features, rule))
    return {name: _share(pd.Series(values, dtype=bool)) for name, values in groups.items()}


def _percent(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.1f}".replace(".", ",") + " %"


def rule_text(rates: dict[str, Any]) -> str:
    ship, debris = rates["ship"], rates["debris"]
    return (
        "«вероятно судно», если максимум B11 в зоне и кольце 1 пикс. не ниже swir_peak или "
        "видимая яркость выше фона воды не меньше чем на visible_contrast; на train+val так "
        f"отмечено {_percent(ship['share'])} судов и {_percent(debris['share'])} обломков. "
        "Яркий след и B08 − B04 показываются как свидетельства и в правило не входят: след "
        f"отмечает {_percent(ship['by_criterion']['trail_pixels'])} судов и "
        f"{_percent(debris['by_criterion']['trail_pixels'])} обломков, сверх яркости добавляет "
        f"{_percent(ship['by_criterion']['trail_adds'])} судов"
    )


def run_vessels(
    run: str, patches: PatchSet, split: pd.Series, data: str, split_name: str, zones: bool = True
) -> dict[str, Any]:
    values = split.to_numpy()
    fit_index = np.flatnonzero(np.isin(values, FIT_PARTS))
    check_index = np.flatnonzero(values == CHECK_PART)
    trail_contrast, wake_pixels = wake_contrast(patches, fit_index)
    fit = label_components(patches, fit_index, (SHIP, DEBRIS), trail_contrast)
    rule = derive_rule(fit, trail_contrast, QUANTILE)
    check = label_components(patches, check_index, (SHIP, DEBRIS), trail_contrast)
    report: dict[str, Any] = {
        "name": f"vessels__{run}",
        "run": run,
        "code_sha256": code_fingerprint(),
        "data_variant": data,
        "split_name": split_name,
        "protocol": (
            "признаки считаются по объекту и кольцу вокруг него (окно 20 пикс.): максимум B11 "
            "и B12 в зоне и кольце 1 пикс., превышение видимой яркости (B02–B04) над медианой "
            "воды SCL 6 вне кольца 2 пикс., медиана B08 − B04 в зоне, вытянутость и заполнение "
            "зоны, яркий след — пиксели с превышением не ниже медианы размеченных следов, "
            "связанные с объектом; пороги — квантиль 0,975 обломков MARIDA (класс 1) train+val, "
            "то есть каждый признак отмечает не более 2,5 % обломков train+val; суда — класс 5; "
            "test в выборе не участвует и оценён один раз"
        ),
        "rule": {**rule, "quantile": QUANTILE, "wake_pixels": wake_pixels},
        "fit": {
            "parts": list(FIT_PARTS),
            "objects": {
                "ship": int((fit["label"] == SHIP).sum()),
                "debris": int((fit["label"] == DEBRIS).sum()),
            },
            "rates": flag_rates(fit, rule),
            "quantiles": _quantiles(fit),
        },
        "test": {
            "objects": {
                "ship": int((check["label"] == SHIP).sum()),
                "debris": int((check["label"] == DEBRIS).sum()),
            },
            "rates": flag_rates(check, rule),
            "ship_edge_subsets": flag_rates(
                edge_subsets(patches, check_index, trail_contrast), rule
            ),
        },
    }
    report["fit"]["ship_edge_subsets"] = flag_rates(
        edge_subsets(patches, fit_index, trail_contrast), rule
    )
    manifest_path = SERVICE / "detector.json"
    manifest = read_json(manifest_path) if manifest_path.exists() else {}
    if zones and manifest.get("name") == run and (SERVICE / manifest["file"]).exists():
        from littora_ml.detector.inference import OnnxDetector

        scorer = OnnxDetector(SERVICE / manifest["file"]).scorer()
        scores = score_patches(scorer, patches, check_index)
        report["test"]["service_zones"] = service_zones(
            scores, patches, check_index, rule, manifest
        )
    write_json(REPORT_PATH, report)
    service_rule = {
        "name": report["name"],
        "window": WINDOW,
        "min_water": MIN_WATER,
        "swir_peak": rule["swir_peak"],
        "visible_contrast": rule["visible_contrast"],
        "trail_contrast": rule["trail_contrast"],
        "trail_pixels": rule["trail_pixels"],
        "rule": rule_text(report["fit"]["rates"]),
        "fitted_on": (
            f"{data}, разбиение {split_name}, train+val: {report['fit']['objects']['ship']} судов "
            f"и {report['fit']['objects']['debris']} обломков по разметке MARIDA; квантиль "
            f"{QUANTILE} обломков"
        ),
        "report": "reports/metrics/detector/flags/vessels.json",
    }
    write_json(RULE_PATH, service_rule)
    return report
