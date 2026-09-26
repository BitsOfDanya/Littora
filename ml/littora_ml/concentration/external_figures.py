from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

from typing import Any

import matplotlib.pyplot as plt
import numpy as np

from littora_ml.common.paths import REPORTS

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
SECONDARY = "#52514e"
MUTED = "#8a8985"
GRID = "#e6e5e1"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]
LABELS = {
    "median": "медиана",
    "site_climatology": "климатология трансекты",
    "idw_k5": "idw_k5",
    "nested": "вложенный выбор",
}


def _axes(axis) -> None:
    axis.set_facecolor(SURFACE)
    for side in ("top", "right"):
        axis.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        axis.spines[side].set_color(GRID)
    axis.tick_params(colors=SECONDARY, labelsize=8)
    axis.grid(color=GRID, linewidth=0.8)
    axis.set_axisbelow(True)


def _figure(columns: int, width: float, height: float):
    figure, axes = plt.subplots(1, columns, figsize=(width, height), squeeze=False)
    figure.patch.set_facecolor(SURFACE)
    for axis in axes[0]:
        _axes(axis)
    return figure, axes[0]


def campaigns_figure(outcome, out) -> str:
    design = outcome.design
    frame = design.frame.iloc[outcome.rows].copy()
    frame["nested"] = outcome.nested[outcome.rows]
    for label in ("median", "site_climatology"):
        frame[label] = outcome.predictions[label][outcome.rows]
    means = frame.groupby("campaign")[["concentration", "median", "site_climatology", "nested"]]
    table = means.mean()
    x = np.arange(len(table))
    figure, (axis,) = _figure(1, 9.5, 4.2)
    axis.plot(
        x,
        table["concentration"],
        color=INK,
        linewidth=2,
        marker="o",
        markersize=6,
        markeredgecolor=SURFACE,
        markeredgewidth=1.5,
        label="измерено",
        zorder=4,
    )
    for color, label in zip(SERIES, ("median", "site_climatology", "nested"), strict=True):
        axis.plot(
            x,
            table[label],
            color=color,
            linewidth=2,
            marker="o",
            markersize=5,
            markeredgecolor=SURFACE,
            markeredgewidth=1.5,
            label=LABELS[label],
            zorder=3,
        )
    axis.set_xticks(x, table.index, rotation=0, fontsize=8)
    axis.set_ylabel("среднее по кампании, шт./км²", color=SECONDARY, fontsize=9)
    axis.legend(frameon=False, fontsize=8, labelcolor=SECONDARY, loc="upper left")
    axis.set_title(
        "Бургас, V1: одна кампания отложена — среднее измеренное и предсказанное",
        color=INK,
        fontsize=10,
        loc="left",
    )
    figure.tight_layout()
    path = out / "v1_campaigns.png"
    figure.savefig(path, dpi=110, facecolor=SURFACE)
    plt.close(figure)
    return str(path)


def mae_figure(results: dict[str, dict[str, Any]], out) -> str:
    names = [name for name in results]
    columns = 4
    rows = int(np.ceil(len(names) / columns))
    figure, axes = plt.subplots(rows, columns, figsize=(13, 2.6 * rows), squeeze=False)
    figure.patch.set_facecolor(SURFACE)
    for axis, name in zip(axes.flat, names, strict=False):
        _axes(axis)
        result = results[name]
        labels = [*result["baselines"], "nested"]
        entries = [*result["baselines"].values(), result["nested"]]
        y = np.arange(len(labels))[::-1]
        for position, label, entry in zip(y, labels, entries, strict=True):
            low, high = entry["ci95"]["mae"]
            color = SERIES[0] if label == "nested" else MUTED
            axis.hlines(position, low, high, color=color, linewidth=2)
            axis.plot(
                entry["mae"],
                position,
                "o",
                color=color,
                markersize=7,
                markeredgecolor=SURFACE,
                markeredgewidth=1.5,
            )
        axis.set_yticks(y, [LABELS.get(label, label) for label in labels], fontsize=8)
        axis.grid(axis="y", visible=False)
        axis.set_title(
            f"{name}\nтест {result['test_rows']}, групп {result['test_groups']}",
            color=INK,
            fontsize=8.5,
            loc="left",
        )
        axis.set_xlabel("MAE, шт./км² (95 % ДИ)", color=SECONDARY, fontsize=8)
    for axis in list(axes.flat)[len(names) :]:
        axis.set_visible(False)
    figure.tight_layout()
    path = out / "designs_mae.png"
    figure.savefig(path, dpi=110, facecolor=SURFACE)
    plt.close(figure)
    return str(path)


def transfer_figure(outcomes: dict[str, Any], results: dict[str, Any], out) -> str | None:
    names = [name for name in outcomes if name.startswith("v3_")]
    if not names:
        return None
    figure, axes = _figure(len(names), 4.2 * len(names), 4.2)
    for axis, name in zip(axes, names, strict=True):
        outcome = outcomes[name]
        rows = outcome.rows
        truth = outcome.design.frame["concentration"].to_numpy(dtype=float)[rows]
        prediction = outcome.pools["models_only"][rows]
        top = max(truth.max(), prediction.max()) * 1.5 + 10
        axis.plot([0, top], [0, top], color=MUTED, linewidth=1)
        axis.plot(
            truth,
            prediction,
            "o",
            color=SERIES[0],
            markersize=6,
            markeredgecolor=SURFACE,
            markeredgewidth=1.2,
            alpha=0.9,
        )
        axis.set_xscale("symlog", linthresh=10)
        axis.set_yscale("symlog", linthresh=10)
        axis.set_xlim(0, top)
        axis.set_ylim(0, top)
        entry = results[name]["pools"]["models_only"]
        rho = entry["spearman"]
        ci = entry["ci95"]["spearman"]
        rho_text = "—" if rho is None else f"{rho:+.2f}"
        ci_text = "" if ci is None else f" [{ci[0]:+.2f}; {ci[1]:+.2f}]"
        ratio = entry["level"]["geometric_ratio"]
        axis.set_title(
            f"{name}\nSpearman {rho_text}{ci_text}, уровень ×{ratio:.2f}",
            color=INK,
            fontsize=8.5,
            loc="left",
        )
        axis.set_xlabel("измерено, шт./км²", color=SECONDARY, fontsize=8)
        axis.set_ylabel("предсказано (выбор среди моделей), шт./км²", color=SECONDARY, fontsize=8)
    figure.tight_layout()
    path = out / "v3_transfer.png"
    figure.savefig(path, dpi=110, facecolor=SURFACE)
    plt.close(figure)
    return str(path)


def external_figures(run: dict[str, Any], config: dict[str, Any]) -> list[str]:
    out = REPORTS / "figures" / "concentration" / config["report_name"]
    out.mkdir(parents=True, exist_ok=True)
    paths = [
        campaigns_figure(run["outcomes"]["v1_burgas"], out),
        mae_figure(run["results"], out),
        transfer_figure(run["outcomes"], run["results"], out),
    ]
    return [path for path in paths if path]
