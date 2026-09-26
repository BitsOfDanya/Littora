from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy.ndimage import binary_dilation
from scipy.ndimage import label as connected
from sklearn.metrics import roc_auc_score

from littora_ml.common.io import read_json, write_json
from littora_ml.common.paths import MODELS, REPORTS
from littora_ml.detector.dataset import PatchSet
from littora_ml.detector.evaluation import code_fingerprint
from littora_ml.detector.postprocess import remove_small, sea_mask

DEBRIS = 1
SHIP_CLASSES = (5, 14)
STRUCTURE = np.ones((3, 3), dtype=bool)
VIEWS = tuple((turns, mirrored) for turns in range(4) for mirrored in (False, True))
FIT_PART = "val"
CHECK_PART = "test"
FLAG_QUANTILE = 0.05
BOOTSTRAP = 2000
STRATA = 3
SERVICE = MODELS / "detector" / "service"
RULE_PATH = SERVICE / "stability.json"
REPORT_PATH = REPORTS / "metrics" / "detector" / "flags" / "stability.json"
BATCH = 16


def view_scores(scorer, images: np.ndarray) -> np.ndarray:
    out = np.zeros((len(VIEWS), len(images), *images.shape[2:]), dtype=np.float32)
    for position, (turns, mirrored) in enumerate(VIEWS):
        view = np.rot90(images, turns, axes=(2, 3))
        if mirrored:
            view = view[..., ::-1]
        scores = scorer(np.ascontiguousarray(view, dtype=np.float32))
        if mirrored:
            scores = scores[..., ::-1]
        out[position] = np.rot90(scores, -turns, axes=(1, 2))
    return out


def zone_group(labels: np.ndarray, mask: np.ndarray) -> str:
    if (labels[mask] == DEBRIS).any():
        return "debris"
    if np.isin(labels[binary_dilation(mask, STRUCTURE, 1)], SHIP_CLASSES).any():
        return "ship"
    if (labels[mask] > 0).any():
        return "other_labeled"
    return "unlabeled"


def patch_zones(
    views: np.ndarray,
    image: np.ndarray,
    scl: np.ndarray,
    labels: np.ndarray,
    service: dict[str, Any],
) -> list[dict[str, Any]]:
    threshold = float(service["threshold"])
    detected = (views[0] >= threshold) & (image[1] != 0)
    sea = service.get("sea_mask")
    if sea:
        detected &= sea_mask(scl, sea["grow"], sea["max_hole"])
    detected = remove_small(detected[None], int(service.get("min_pixels", 1)))[0]
    zones, count = connected(detected, structure=STRUCTURE)
    votes = (views >= threshold).mean(axis=0)
    rows = []
    for zone in range(1, count + 1):
        mask = zones == zone
        rows.append(
            {
                "group": zone_group(labels, mask),
                "pixels": int(mask.sum()),
                "max_probability": float(views[0][mask].max()),
                "agreement": float(votes[mask].mean()),
                "views_hit": int(((views >= threshold) & mask).any(axis=(1, 2)).sum()),
            }
        )
    return rows


def collect(
    scorer, patches: PatchSet, indices: np.ndarray, service: dict[str, Any]
) -> pd.DataFrame:
    scl = np.load(patches.root / "scl.npy", mmap_mode="r")
    scenes = patches.table["scene"].to_numpy()
    rows = []
    for start in range(0, len(indices), BATCH):
        chunk = indices[start : start + BATCH]
        images = np.asarray(patches.images[chunk], dtype=np.float32)
        views = view_scores(scorer, images)
        for position, index in enumerate(chunk):
            for row in patch_zones(
                views[:, position],
                images[position],
                np.asarray(scl[index]),
                np.asarray(patches.labels[index]),
                service,
            ):
                rows.append({**row, "patch": int(index), "scene": scenes[index]})
    return pd.DataFrame(rows)


def _auc(truth: np.ndarray, score: np.ndarray) -> float | None:
    if truth.all() or not truth.any():
        return None
    return float(roc_auc_score(truth, score))


def stratified_auc(truth: np.ndarray, score: np.ndarray, strata: np.ndarray) -> float | None:
    wins = pairs = 0.0
    for stratum in np.unique(strata):
        inside = strata == stratum
        positive, negative = score[inside & truth], score[inside & ~truth]
        if not len(positive) or not len(negative):
            continue
        difference = positive[:, None] - negative[None, :]
        wins += (difference > 0).sum() + 0.5 * (difference == 0).sum()
        pairs += difference.size
    return float(wins / pairs) if pairs else None


def strata_edges(probability: np.ndarray) -> list[float]:
    return [float(value) for value in np.quantile(probability, np.linspace(0, 1, STRATA + 1)[1:-1])]


def _scene_bootstrap(table: pd.DataFrame, statistic, seed: int = 0) -> list[float] | None:
    scenes = table["scene"].unique()
    groups = {scene: table.index[table["scene"] == scene].to_numpy() for scene in scenes}
    rng = np.random.default_rng(seed)
    values = []
    for _ in range(BOOTSTRAP):
        chosen = rng.choice(scenes, len(scenes))
        value = statistic(table.loc[np.concatenate([groups[scene] for scene in chosen])])
        if value is not None:
            values.append(value)
    if len(values) < BOOTSTRAP // 2:
        return None
    return [float(np.quantile(values, 0.025)), float(np.quantile(values, 0.975))]


def discrimination(table: pd.DataFrame, edges: list[float]) -> dict[str, Any]:
    judged = table[table["group"] != "unlabeled"].reset_index(drop=True)

    def agreement_auc(frame: pd.DataFrame) -> float | None:
        return _auc(frame["group"].eq("debris").to_numpy(), frame["agreement"].to_numpy())

    def probability_auc(frame: pd.DataFrame) -> float | None:
        return _auc(frame["group"].eq("debris").to_numpy(), frame["max_probability"].to_numpy())

    def within_auc(frame: pd.DataFrame) -> float | None:
        return stratified_auc(
            frame["group"].eq("debris").to_numpy(),
            frame["agreement"].to_numpy(),
            np.digitize(frame["max_probability"].to_numpy(), edges),
        )

    return {
        "zones": {name: int(count) for name, count in table["group"].value_counts().items()},
        "agreement_auc": agreement_auc(judged),
        "agreement_auc_ci95": _scene_bootstrap(judged, agreement_auc),
        "probability_auc": probability_auc(judged),
        "probability_auc_ci95": _scene_bootstrap(judged, probability_auc),
        "agreement_auc_within_probability": within_auc(judged),
        "agreement_auc_within_probability_ci95": _scene_bootstrap(judged, within_auc),
    }


def flag_shares(table: pd.DataFrame, cutoff: float) -> dict[str, Any]:
    out = {}
    for name in ("debris", "ship", "other_labeled", "unlabeled"):
        values = table.loc[table["group"] == name, "agreement"]
        flagged = int((values < cutoff).sum())
        out[name] = {
            "zones": len(values),
            "flagged": flagged,
            "share": flagged / len(values) if len(values) else None,
        }
    return out


def gate(block: dict[str, Any], shares: dict[str, Any]) -> dict[str, Any]:
    within = block["agreement_auc_within_probability_ci95"]
    debris = shares["debris"]["share"] or 0.0
    false = [shares[name] for name in ("ship", "other_labeled") if shares[name]["zones"]]
    false_share = sum(item["flagged"] for item in false) / max(
        sum(item["zones"] for item in false), 1
    )
    passed = bool(within and within[0] > 0.5 and false_share >= 2 * max(debris, 1e-9))
    return {
        "rule": (
            "флаг включается, если на val нижняя граница 95 % ДИ AUC согласия внутри групп по "
            "вероятности выше 0,5 и флаг отмечает ложные зоны хотя бы вдвое чаще, чем обломки"
        ),
        "false_share": false_share,
        "debris_share": debris,
        "passed": passed,
    }


def service_manifest(run: str) -> dict[str, Any] | None:
    path = SERVICE / "detector.json"
    manifest = read_json(path) if path.exists() else {}
    if manifest.get("name") != run or not (SERVICE / manifest["file"]).exists():
        return None
    return manifest


def run_stability(
    run: str, patches: PatchSet, split: pd.Series, data: str, split_name: str
) -> dict[str, Any]:
    from littora_ml.detector.inference import OnnxDetector

    manifest = service_manifest(run)
    if manifest is None:
        raise SystemExit(f"{run} не выгружен в models/detector/service")
    scorer = OnnxDetector(SERVICE / manifest["file"]).scorer()
    values = split.to_numpy()
    fit = collect(scorer, patches, np.flatnonzero(values == FIT_PART), manifest)
    check = collect(scorer, patches, np.flatnonzero(values == CHECK_PART), manifest)
    debris = fit.loc[fit["group"] == "debris", "agreement"]
    cutoff = float(np.quantile(debris, FLAG_QUANTILE))
    edges = strata_edges(fit["max_probability"].to_numpy())
    fit_block = discrimination(fit, edges)
    fit_shares = flag_shares(fit, cutoff)
    decision = gate(fit_block, fit_shares)
    report = {
        "name": f"stability__{run}",
        "run": run,
        "code_sha256": code_fingerprint(),
        "data_variant": data,
        "split_name": split_name,
        "protocol": (
            "каждый патч прогоняется сервисным ONNX в 8 видах (4 поворота × отражение), вид "
            "возвращается в исходную ориентацию; зона — связная область по исходному виду, как в "
            "сервисе (порог манифеста, маска моря, от min_pixels пикселей); согласие — средняя по "
            "пикселям зоны доля видов выше порога; зона считается мусором, если в ней есть пиксель "
            "класса 1, ложной — если в ней или в кольце 1 пикс. судно или след, либо в ней только "
            "другие размеченные классы; неразмеченные зоны в AUC не входят; порог флага — квантиль "
            "0,05 согласия обломков val, группы по вероятности — терцили максимума вероятности "
            "зон val; test в выборе не участвует и оценён один раз; ДИ — бутстреп по сценам"
        ),
        "views": len(VIEWS),
        "rule": {
            "cutoff": cutoff,
            "quantile": FLAG_QUANTILE,
            "views": len(VIEWS),
            "flag": decision["passed"],
        },
        "fit": {
            "part": FIT_PART,
            **fit_block,
            "flag_shares": fit_shares,
            "gate": decision,
            "strata_edges": edges,
        },
        "test": {
            "part": CHECK_PART,
            **discrimination(check, edges),
            "flag_shares": flag_shares(check, cutoff),
        },
    }
    write_json(REPORT_PATH, report)
    write_json(
        RULE_PATH,
        {
            "run": run,
            "cutoff": cutoff,
            "views": len(VIEWS),
            "flag": decision["passed"],
            "source": "reports/metrics/detector/flags/stability.json",
        },
    )
    return report
