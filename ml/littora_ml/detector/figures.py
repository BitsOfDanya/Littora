from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np

from littora_ml.common.io import read_json
from littora_ml.common.paths import REPORTS
from littora_ml.detector.dataset import PatchSet
from littora_ml.detector.evaluation import usable_labels

CLASS_COLORS = {
    1: (0.86, 0.1, 0.2),
    2: (0.2, 0.6, 0.2),
    3: (0.4, 0.75, 0.3),
    4: (0.55, 0.45, 0.2),
    5: (0.95, 0.95, 0.95),
    9: (0.6, 0.9, 1.0),
    12: (0.3, 0.5, 0.9),
    14: (0.5, 0.3, 0.8),
}


def rgb(image: np.ndarray) -> np.ndarray:
    stack = np.stack([image[3], image[2], image[1]], axis=-1).astype(np.float32)
    valid = stack[stack > 0]
    high = np.quantile(valid, 0.99) if valid.size else 1.0
    return np.clip(stack / max(high, 1e-6), 0, 1)


def label_rgb(labels: np.ndarray) -> np.ndarray:
    out = np.zeros((*labels.shape, 3), dtype=np.float32) + 0.12
    out[labels > 0] = (0.45, 0.45, 0.45)
    for value, color in CLASS_COLORS.items():
        out[labels == value] = color
    return out


def outcome_rgb(labels: np.ndarray, mask: np.ndarray) -> np.ndarray:
    out = np.zeros((*labels.shape, 3), dtype=np.float32) + 0.12
    labeled = labels > 0
    debris = labels == 1
    out[mask & debris] = (0.1, 0.8, 0.3)
    out[mask & labeled & ~debris] = (0.95, 0.3, 0.2)
    out[~mask & debris] = (1.0, 0.85, 0.1)
    out[mask & ~labeled] = (0.5, 0.5, 0.8)
    return out


def examples(run: str, patches: PatchSet, split, count: int = 4) -> list:
    report = read_json(REPORTS / "metrics" / "detector" / f"{run}.json")
    data = np.load(REPORTS / "predictions" / "detector" / run / "test.npz")
    probability = data["probability"].astype(np.float32) / 255
    names = list(data["patches"])
    index = {name: position for position, name in enumerate(patches.table["name"])}
    rows = [index[name] for name in names]
    labels = usable_labels(
        patches, np.array(rows), report.get("config", {}).get("max_confidence_code", 3)
    )
    mask = probability >= report["threshold"]
    scored = []
    for position in range(len(rows)):
        truth = labels[position] == 1
        labeled = labels[position] > 0
        tp = int((mask[position] & truth).sum())
        fp = int((mask[position] & labeled & ~truth).sum())
        fn = int((~mask[position] & truth).sum())
        scored.append((position, tp, fp, fn))
    with_debris = [row for row in scored if row[1] + row[3] > 0]
    best = sorted(with_debris, key=lambda r: (-(2 * r[1]) / (2 * r[1] + r[2] + r[3]), -r[1]))
    worst = sorted(with_debris, key=lambda r: ((2 * r[1]) / (2 * r[1] + r[2] + r[3]), -r[3]))
    false_alarms = sorted(scored, key=lambda r: -r[2])
    groups = {
        "best": ("лучшие", best[:count]),
        "worst": ("худшие", worst[:count]),
        "false_alarms": (
            "ложные срабатывания",
            [row for row in false_alarms if row[2] > 0][:count],
        ),
    }
    out_dir = REPORTS / "figures" / "detector" / run
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for slug, (title, chosen) in groups.items():
        if not chosen:
            continue
        figure, axes = plt.subplots(len(chosen), 4, figsize=(12, 3 * len(chosen)), squeeze=False)
        for row, (position, tp, fp, fn) in enumerate(chosen):
            image = np.asarray(patches.images[rows[position]], dtype=np.float32)
            panels = [
                (rgb(image), f"{names[position]} · RGB"),
                (label_rgb(labels[position]), "разметка MARIDA"),
                (probability[position], "вероятность"),
                (outcome_rgb(labels[position], mask[position]), f"TP {tp} · FP {fp} · FN {fn}"),
            ]
            for column, (panel, caption) in enumerate(panels):
                axis = axes[row][column]
                axis.imshow(panel, vmin=0, vmax=1, cmap="magma" if panel.ndim == 2 else None)
                axis.set_title(caption, fontsize=8)
                axis.axis("off")
        figure.suptitle(f"{run}: {title}", fontsize=10)
        figure.tight_layout()
        path = out_dir / f"{slug}.png"
        figure.savefig(path, dpi=90)
        plt.close(figure)
        written.append(path)
    return written
