from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from littora_ml.common.io import read_json
from littora_ml.common.paths import REPORTS


def _band(values: dict) -> str:
    return f"{values['mean']:.1f} ± {values['sd']:.1f}"


def profile_figure(report: str, profile: str) -> str:
    frame = pd.read_csv(REPORTS / "predictions" / "concentration" / report / f"{profile}.csv")
    metrics = read_json(REPORTS / "metrics" / "concentration" / report / f"{profile}.json")
    events = frame.groupby("sample_id", sort=False)
    truth = events["concentration"].first().to_numpy()
    figure, axes = plt.subplots(1, 2, figsize=(11, 4.6))
    limits = [max(1.0, truth.min() * 0.5), truth.max() * 2]
    for axis, column, block, title in [
        (axes[0], "median_baseline", metrics["baseline"], "медиана обучающих фолдов"),
        (axes[1], "nested_prediction", metrics["nested"], "модель, вложенная CV"),
    ]:
        logs = np.log1p(frame[column].clip(lower=0))
        center = np.expm1(logs.groupby(frame["sample_id"], sort=False).mean()).to_numpy()
        low = events[column].min().to_numpy()
        high = events[column].max().to_numpy()
        axis.vlines(truth, np.maximum(low, limits[0]), high, color="0.75", linewidth=1, zorder=1)
        axis.scatter(truth, np.maximum(center, limits[0]), s=18, color="#0B3C5D", zorder=2)
        axis.plot(limits, limits, color="#C0392B", linewidth=1)
        axis.set_xscale("log")
        axis.set_yscale("log")
        axis.set_xlim(limits)
        axis.set_ylim(limits)
        scores = f"MAE {_band(block['mae'])}, RMSE {_band(block['rmse'])}"
        axis.set_title(f"{title}: {scores}", fontsize=9)
        axis.set_xlabel("измерено, шт./км²")
        axis.set_ylabel("предсказано, шт./км²; линии — разброс повторов")
    coverage = metrics["nested"]["coverage"]
    difference = metrics["difference_vs_median"]["mae"]
    low, high = difference["ci"]
    role = metrics["research"]
    note = "" if role["role"] == "primary" else f"\n{role['selection']}"
    figure.suptitle(
        f"{profile}: {metrics['events']} событий, {metrics['validation']['repetitions']} повторов "
        f"вложенной CV по дням съёмки\nразница MAE с медианой {difference['mean']:+.1f} "
        f"[{low:+.1f}; {high:+.1f}] ({difference['confidence']:.0%} ДИ); покрытие "
        f"{metrics['nested']['target_coverage']:.0%} интервалов {coverage['mean']:.2f} ± "
        f"{coverage['sd']:.2f}{note}",
        fontsize=10,
    )
    figure.tight_layout()
    out = REPORTS / "figures" / "concentration" / report
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{profile}.png"
    figure.savefig(path, dpi=90)
    plt.close(figure)
    return str(path)
