from __future__ import annotations

import itertools
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shapefile
from matplotlib.lines import Line2D

from littora_ml.common.paths import EXTERNAL, resolve
from littora_ml.drift_check.metrics import finite_median
from littora_ml.drift_check.report import (
    CLASS_LABELS,
    SERVICE,
    counts,
    horizon_part,
    units_text,
    variant_name,
)

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
MUTED = "#52514e"
GRID = "#e4e3df"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"]
METHOD_STYLE = {
    SERVICE: ("ансамбль сервиса, медиана", SERIES[0], "-"),
    "persistence": ("персистентность", SERIES[1], "-"),
    "currents_only": ("только течение", SERIES[2], "-"),
    "stationary": ("неподвижная точка", MUTED, "--"),
}
PERIOD_STYLE = {
    "anchored": ("волочение якоря", SERIES[1]),
    "free": ("свободный дрейф", SERIES[0]),
    "grounding": ("мель", SERIES[2]),
}


def _style(axis) -> None:
    axis.set_facecolor(SURFACE)
    axis.grid(color=GRID, linewidth=0.8)
    axis.tick_params(colors=MUTED, labelsize=8)
    for side in ("top", "right"):
        axis.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        axis.spines[side].set_color(GRID)


def _save(figure, folder: Path, name: str) -> str:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    figure.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(figure)
    return str(path.relative_to(resolve(".")))


def _medians(frame: pd.DataFrame, method: str, horizons: list[int]) -> np.ndarray:
    return np.array([finite_median(frame[f"D{h}:{method}"].to_numpy()) for h in horizons])


def separation_figure(frame: pd.DataFrame, horizons: list[int], folder: Path) -> str:
    classes = [name for name in CLASS_LABELS if name in set(frame["class"])]
    columns = min(3, len(classes))
    rows = int(np.ceil(len(classes) / columns))
    figure, axes = plt.subplots(
        rows, columns, figsize=(4.2 * columns, 3.4 * rows), squeeze=False, facecolor=SURFACE
    )
    for axis, name in zip(axes.flat, classes, strict=False):
        part = frame[frame["class"] == name]
        if name == "blacksea":
            part = part[part["period"] == "free"]
        _style(axis)
        for method, (label, color, dash) in METHOD_STYLE.items():
            values = _medians(part, method, horizons)
            axis.plot(
                horizons, values, dash, color=color, linewidth=2, marker="o", ms=5, label=label
            )
        low = [np.nanquantile(part[f"D{h}:{SERVICE}"], 0.25) for h in horizons]
        high = [np.nanquantile(part[f"D{h}:{SERVICE}"], 0.75) for h in horizons]
        axis.fill_between(horizons, low, high, color=SERIES[0], alpha=0.12, linewidth=0)
        top = max(horizons)
        size = units_text(counts(horizon_part(part, top)))
        axis.set_title(f"{CLASS_LABELS[name]}\n{top} ч: {size}", fontsize=9, color=INK)
        axis.set_xticks(horizons)
        axis.set_xlabel("часы от старта", fontsize=8, color=MUTED)
        axis.set_ylabel("медиана расстояния, км", fontsize=8, color=MUTED)
        axis.set_ylim(bottom=0)
    for axis in axes.flat[len(classes) :]:
        axis.set_visible(False)
    handles, labels = axes.flat[0].get_legend_handles_labels()
    figure.legend(handles, labels, loc="lower center", ncol=4, frameon=False, fontsize=8)
    figure.suptitle(
        "Ошибка положения через 24–72 ч; полоса — межквартильный размах ансамбля сервиса",
        fontsize=10,
        color=INK,
    )
    figure.tight_layout(rect=(0, 0.06, 1, 0.97))
    return _save(figure, folder, "separation.png")


def windage_figure(report: dict[str, Any], frame: pd.DataFrame, folder: Path) -> str | None:
    panels = []
    for name, entry in report.get("calibration", {}).items():
        chosen = entry.get("selection")
        if chosen and chosen.get("best"):
            panels.append((f"подбор «{name}»: {units_text(chosen['sample'])}", chosen))
    fit = report.get("blacksea", {}).get("free_fit")
    if fit and fit.get("best"):
        panels.append(("Чёрное море, свободный дрейф", fit))
    if not panels:
        return None
    windages = sorted({float(value) for value in report["service"]["grid"]["windages"]})
    service = report["service"]["ensemble"]["windages"]
    figure, axes = plt.subplots(
        1, len(panels), figsize=(4.2 * len(panels), 3.4), squeeze=False, facecolor=SURFACE
    )
    for axis, (title, chosen) in zip(axes.flat, panels, strict=True):
        _style(axis)
        axis.axvspan(min(service) * 100, max(service) * 100, color=GRID, alpha=0.6, linewidth=0)
        for stokes, color, label in (
            (False, SERIES[0], "Стокс выкл."),
            (True, SERIES[1], "Стокс вкл."),
        ):
            values = [
                chosen["curve"][variant_name(windage, stokes)]["median_km"] for windage in windages
            ]
            axis.plot(
                [w * 100 for w in windages],
                values,
                color=color,
                linewidth=2,
                marker="o",
                ms=5,
                label=label,
            )
        best = chosen["curve"][chosen["best"]]["median_km"]
        axis.scatter(
            [chosen["windage"] * 100],
            [best],
            s=90,
            facecolor="none",
            edgecolor=INK,
            linewidth=1.5,
            zorder=5,
        )
        axis.set_title(f"{title}\nD через {chosen['horizon_h']} ч", fontsize=9, color=INK)
        axis.set_xlabel("парусность α, % от ветра 10 м", fontsize=8, color=MUTED)
        axis.set_ylabel("медиана расстояния, км", fontsize=8, color=MUTED)
    axes.flat[0].legend(frameon=False, fontsize=8)
    figure.suptitle(
        "Подбор парусности и Стокса; серая полоса — диапазон α ансамбля сервиса, кружок — выбор",
        fontsize=10,
        color=INK,
    )
    figure.tight_layout(rect=(0, 0, 1, 0.93))
    return _save(figure, folder, "windage.png")


def coverage_figure(report: dict[str, Any], horizons: list[int], folder: Path) -> str | None:
    classes = [
        (name, entry)
        for name, entry in report.get("classes", {}).items()
        if entry["all"].get("horizons")
    ]
    if not classes:
        return None
    shares = [float(value) for value in ("0.5", "0.9")]
    figure, axes = plt.subplots(1, 2, figsize=(9.2, 3.6), facecolor=SURFACE)
    for axis, share in zip(axes, shares, strict=True):
        _style(axis)
        axis.axhline(share, color=INK, linewidth=1, linestyle=":")
        for color, (name, entry) in zip(SERIES, classes, strict=False):
            values = [
                entry["all"]["horizons"][str(h)]["envelopes"][f"{share:g}"]["covered"]
                for h in horizons
            ]
            values = [np.nan if value is None else value for value in values]
            axis.plot(
                horizons,
                values,
                color=color,
                linewidth=2,
                marker="o",
                ms=5,
                label=CLASS_LABELS[name],
            )
        axis.set_ylim(0, 1)
        axis.set_xticks(horizons)
        axis.set_title(f"огибающая {share:.0%}: доля реальных точек внутри", fontsize=9, color=INK)
        axis.set_xlabel("часы от старта", fontsize=8, color=MUTED)
    axes[0].set_ylabel("доля окон", fontsize=8, color=MUTED)
    handles, labels = axes[0].get_legend_handles_labels()
    figure.legend(handles, labels, loc="lower center", ncol=3, frameon=False, fontsize=8)
    figure.suptitle(
        "Калибровка огибающих ансамбля сервиса; пунктир — номинал", fontsize=10, color=INK
    )
    figure.tight_layout(rect=(0, 0.1, 1, 0.94))
    return _save(figure, folder, "envelopes.png")


SET_STYLE = {
    "fit": ("подбор 2022–2023", SERIES[0]),
    "test": ("проверка 2024", SERIES[1]),
    "blacksea": ("Чёрное море 2026", SERIES[2]),
}


def _series(summary: dict[str, Any], horizons: list[int], share: str | None) -> list[float]:
    values = []
    for horizon in horizons:
        cell = summary["horizons"].get(str(horizon), {})
        if not cell.get("windows"):
            values.append(np.nan)
        elif share is None:
            values.append(cell["separation_km"]["median"])
        else:
            values.append(cell["coverage"][share]["value"])
    return values


def spread_figure(report: dict[str, Any], horizons: list[int], path: Path) -> str | None:
    evaluation = report.get("evaluation") or {}
    selection = report["selection"]
    baseline, chosen, recommended = (
        selection["baseline"],
        selection["chosen"],
        selection["recommended"],
    )
    if not chosen or not recommended:
        return None
    figure, axes = plt.subplots(1, 3, figsize=(12.6, 4.1), facecolor=SURFACE)
    panels = [
        ("0.5", "огибающая 50 %: доля точек внутри", ((baseline, "--"), (recommended, "-"))),
        ("0.9", "огибающая 90 %: доля точек внутри", ((baseline, "--"), (recommended, "-"))),
        (
            None,
            "медиана ошибки, км (сплошная — сервис и рекомендация)",
            ((baseline, "-"), (chosen, ":")),
        ),
    ]
    for axis, (share, title, lines) in zip(axes, panels, strict=True):
        _style(axis)
        if share is not None:
            axis.axhline(float(share), color=INK, linewidth=1, linestyle=(0, (1, 2)))
        for name, (_, color) in SET_STYLE.items():
            summaries = evaluation.get(name)
            if not summaries:
                continue
            for variant, dash in lines:
                hollow = dash != "-"
                axis.plot(
                    horizons,
                    _series(summaries[variant], horizons, share),
                    linestyle=dash,
                    color=color,
                    linewidth=1.3 if hollow else 2.2,
                    marker="o",
                    ms=4 if hollow else 5,
                    mfc=SURFACE if hollow else color,
                )
        axis.set_xticks(horizons)
        axis.set_xlabel("часы от старта", fontsize=8, color=MUTED)
        axis.set_title(title, fontsize=9, color=INK)
        if share is None:
            axis.set_ylim(bottom=0)
        else:
            axis.set_ylim(0, 1.02)
    handles = [
        Line2D([], [], color=color, linewidth=2.2, marker="o", ms=5, label=label)
        for label, color in SET_STYLE.values()
    ]
    handles += [
        Line2D([], [], color=MUTED, linestyle="--", marker="o", mfc=SURFACE, label="сервис"),
        Line2D([], [], color=MUTED, linewidth=2.2, label=f"{chosen} только для огибающих"),
        Line2D(
            [],
            [],
            color=MUTED,
            linestyle=":",
            marker="o",
            mfc=SURFACE,
            label=f"{chosen} во всём ансамбле",
        ),
        Line2D([], [], color=INK, linestyle=(0, (1, 2)), label="номинал"),
    ]
    figure.legend(handles=handles, loc="lower center", ncol=7, frameon=False, fontsize=8)
    figure.suptitle(
        "Разброс ансамбля подобран на 2022–2023 и проверен на 2024 и Чёрном море; медиана "
        "у рекомендации совпадает с сервисом",
        fontsize=10,
        color=INK,
    )
    figure.tight_layout(rect=(0, 0.08, 1, 0.96))
    return _save(figure, path.parent, path.name)


def _coastline(bounds: tuple[float, float, float, float]) -> list[np.ndarray]:
    path = EXTERNAL / "natural-earth" / "ne_10m_coastline.zip"
    if not path.exists():
        return []
    archive = zipfile.ZipFile(path)
    reader = shapefile.Reader(
        shp=BytesIO(archive.read("ne_10m_coastline.shp")),
        shx=BytesIO(archive.read("ne_10m_coastline.shx")),
        dbf=BytesIO(archive.read("ne_10m_coastline.dbf")),
    )
    west, south, east, north = bounds
    lines = []
    for shape in reader.shapes():
        box_west, box_south, box_east, box_north = shape.bbox
        if box_east < west or box_west > east or box_north < south or box_south > north:
            continue
        for start, end in itertools.pairwise([*shape.parts, len(shape.points)]):
            lines.append(np.asarray(shape.points[start:end]))
    return lines


def blacksea_figure(frame: pd.DataFrame, track: pd.DataFrame, folder: Path) -> str | None:
    part = frame[frame["source"] == "blacksea"]
    if part.empty or track.empty:
        return None
    figure, (left, right) = plt.subplots(
        1, 2, figsize=(10.5, 4.6), facecolor=SURFACE, gridspec_kw={"width_ratios": [1, 1.4]}
    )
    _style(left)
    bounds = (
        track["lon"].min() - 0.4,
        track["lat"].min() - 0.3,
        track["lon"].max() + 0.4,
        track["lat"].max() + 0.3,
    )
    for line in _coastline(bounds):
        left.plot(line[:, 0], line[:, 1], color=MUTED, linewidth=0.8)
    for period, (label, color) in PERIOD_STYLE.items():
        piece = track[track["period"] == period]
        left.plot(piece["lon"], piece["lat"], color=color, linewidth=2, label=label)
    left.set_xlim(bounds[0], bounds[2])
    left.set_ylim(bounds[1], bounds[3])
    left.set_aspect(1 / np.cos(np.radians(np.mean(bounds[1::2]))))
    left.legend(frameon=False, fontsize=8, loc="lower left")
    left.set_title("трек 4401656, февраль–март 2026", fontsize=9, color=INK)
    _style(right)
    free = part[part["period"] == "free"].sort_values("t0")
    for method in (SERVICE, "persistence", "currents_only"):
        label, color, dash = METHOD_STYLE[method]
        right.plot(
            free["t0"],
            free[f"D72:{method}"],
            dash,
            color=color,
            linewidth=2,
            marker="o",
            ms=3,
            label=label,
        )
    right.set_ylabel("расстояние через 72 ч, км", fontsize=8, color=MUTED)
    right.set_title("свободный дрейф: ошибка по окнам (старт каждые 6 ч)", fontsize=9, color=INK)
    right.legend(frameon=False, fontsize=8)
    right.set_ylim(bottom=0)
    figure.autofmt_xdate()
    figure.tight_layout()
    return _save(figure, folder, "blacksea.png")


def draw_all(
    report: dict[str, Any],
    frame: pd.DataFrame,
    track: pd.DataFrame,
    horizons: list[int],
    folder: Path,
) -> list[str]:
    if frame.empty:
        return []
    paths = [separation_figure(frame, horizons, folder)]
    for path in (
        windage_figure(report, frame, folder),
        coverage_figure(report, horizons, folder),
        blacksea_figure(frame, track, folder),
    ):
        if path:
            paths.append(path)
    return paths
