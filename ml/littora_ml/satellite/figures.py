from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np

from littora_ml.common.paths import REPORTS
from littora_ml.detector.figures import rgb
from littora_ml.satellite.pairs import accepted_pairs, footprint_mask, pair_window
from littora_ml.satellite.sliding import sliding_scores


def pairs_figure(scorer, threshold: float, concentration: dict[str, float], name: str) -> str:
    pairs = accepted_pairs()
    figure, axes = plt.subplots(len(pairs), 2, figsize=(8, 3.6 * len(pairs)), squeeze=False)
    for row, pair in enumerate(pairs):
        window = pair_window(pair)
        image, grid = window["image"], window["grid"]
        probability = sliding_scores(image, scorer)
        inside = footprint_mask(pair, grid)
        edge = inside ^ np.roll(inside, 1, axis=0)
        picture = rgb(image)
        picture[edge] = (1.0, 0.85, 0.1)
        value = concentration.get(pair["sample_ids"][0])
        axes[row][0].imshow(picture)
        axes[row][0].set_title(
            f"{pair['event_id']} · {value:.0f} шт./км² · {pair['scene_id'][:24]}", fontsize=8
        )
        axes[row][1].imshow(probability, vmin=0, vmax=1, cmap="magma")
        detected = int((probability[inside] >= threshold).sum())
        axes[row][1].set_title(f"вероятность · выше порога в полосе: {detected} пикс.", fontsize=8)
        for axis in axes[row]:
            axis.axis("off")
    figure.tight_layout()
    out = REPORTS / "figures" / "satellite"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"pairs_{name}.png"
    figure.savefig(path, dpi=80)
    plt.close(figure)
    return str(path)
