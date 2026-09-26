from __future__ import annotations

import datetime as dt
from collections import Counter
from collections.abc import Callable, Sequence
from typing import Any

import numpy as np
import pandas as pd

from littora_ml.common.io import write_json
from littora_ml.common.paths import resolve
from littora_ml.concentration.features import coast_distance
from littora_ml.drift_check.metrics import (
    cluster_resamples,
    distribution,
    finite_mean,
    finite_median,
    interval,
    liu_weisberg,
    persistence_path,
    separation_km,
    share_better,
    significance,
    skill_vs,
    stationary_path,
)
from littora_ml.drift_check.run import Queued, read_result, result_path, setup_hash
from littora_ml.drift_check.simulate import Setup

BASELINES = ("stationary", "persistence", "currents_only")
SERVICE = "service_median"
KEY_METHODS = (SERVICE, *BASELINES)
REFERENCES = ("persistence", "stationary")
REFERENCE_LABELS = {"persistence": "персистентность", "stationary": "неподвижная точка"}
REFERENCE_DATIVE = {"persistence": "к персистентности", "stationary": "к неподвижной точке"}
KIND_LABELS = {
    "bottle": "бутылки",
    "bottle_3l": "бутылка 3 л",
    "board": "доски",
    "board_perforated": "доски с отверстиями",
    "ring": "кольца",
}
SPLIT_LABELS = {"fit": "подбор", "test": "проверка"}
GROUP_ROWS_MAX = 20
CLASS_LABELS = {
    "svp_drogued": "SVP с дрогом 15 м (Средиземное)",
    "svp_undrogued": "SVP без дрога (Средиземное)",
    "svp_unknown": "SVP, дрог неизвестен (Средиземное)",
    "near_surface": "CARTHE, HEREON, CODE (SWOT-Med 2023)",
    "litter_items": "предметы мусора NAUTILOS",
    "blacksea": "SVP-B 4401656 (Чёрное море)",
}


def variant_name(windage: float, stokes: bool) -> str:
    return f"a{windage * 100:g}_s{int(stokes)}"


def bootstrap_group(window_source: str, drifter: str) -> str:
    return drifter.split(":")[0] if window_source == "nautilos" else drifter


def plural(count: int, one: str, few: str, many: str) -> str:
    if 11 <= count % 100 <= 14:
        return many
    if count % 10 == 1:
        return one
    if 2 <= count % 10 <= 4:
        return few
    return many


def horizon_part(frame: pd.DataFrame, horizon: int) -> pd.DataFrame:
    column = f"D{horizon}:{SERVICE}"
    if frame.empty or column not in frame:
        return frame.iloc[0:0]
    return frame[frame[column].notna()]


def counts(part: pd.DataFrame) -> dict[str, Any]:
    windows = len(part)
    if not windows:
        return {"windows": 0, "drifters": 0, "groups": 0, "missions": 0}
    return {
        "windows": windows,
        "drifters": int(part["drifter"].nunique()),
        "groups": int(part["group"].nunique()),
        "missions": int(part.loc[part["source"] == "nautilos", "group"].nunique()),
        "largest_drifter_share": float(part["drifter"].value_counts().iloc[0] / windows),
        "largest_group_share": float(part["group"].value_counts().iloc[0] / windows),
    }


def units_text(entry: dict[str, Any]) -> str:
    windows, drifters, groups = entry["windows"], entry["drifters"], entry["groups"]
    text = f"{windows} {plural(windows, 'окно', 'окна', 'окон')}"
    if groups and entry.get("missions") == groups:
        return f"{text}, {drifters} предм., {groups} {plural(groups, 'миссия', 'миссии', 'миссий')}"
    text += f", {drifters} дрифт."
    if groups != drifters:
        text += f", {groups} {plural(groups, 'группа', 'группы', 'групп')}"
    return text


def window_class(window_source: str, drogue: str) -> str:
    if window_source == "med":
        return {"on": "svp_drogued", "off": "svp_undrogued"}.get(drogue, "svp_unknown")
    if window_source == "swot":
        return "near_surface"
    if window_source == "nautilos":
        return "litter_items"
    return "blacksea"


def window_rows(
    queue: Sequence[Queued], setup: Setup, work, persistence_h: float, tolerance: float
) -> tuple[pd.DataFrame, dict[str, Any]]:
    signature = setup_hash(setup)
    variants = [variant_name(w, s) for w, s in setup.grid.variants]
    status: Counter[str] = Counter()
    rows = []
    for item in queue:
        window = item.window
        result = read_result(result_path(work, window.id))
        if result is None or result.get("setup") != signature:
            status[f"{window.source}:not_simulated"] += 1
            continue
        status[f"{window.source}:{result['status']}"] += 1
        if result["status"] != "ok":
            continue
        observed = window.track
        paths = {
            "stationary": stationary_path(window.start, setup.hours),
            "persistence": persistence_path(
                window.before, window.start, setup.hours, persistence_h
            ),
            SERVICE: np.asarray(result["ensemble"]["median"], dtype=float),
        }
        for name, path in zip(variants, result["grid"]["paths"], strict=True):
            paths[name] = np.asarray(path, dtype=float)
        paths["currents_only"] = paths[variant_name(0.0, False)]
        row: dict[str, Any] = {
            "id": window.id,
            "source": window.source,
            "drifter": window.drifter,
            "group": bootstrap_group(window.source, window.drifter),
            "kind": window.kind,
            "drogue": window.drogue,
            "period": window.period,
            "split": item.split,
            "class": window_class(window.source, window.drogue),
            "t0": window.moment,
            "horizon": window.horizon,
            "lon": float(window.start[0]),
            "lat": float(window.start[1]),
            "wind_ms": result["wind"]["mean_ms"],
            "marine_step_deg": result["forcing"]["marine_step_deg"],
            "left_domain": result["ensemble"]["left_domain"],
            "beached": result["ensemble"]["beached"],
        }
        for horizon in setup.horizons:
            available = horizon <= window.horizon
            for name, path in paths.items():
                row[f"D{horizon}:{name}"] = (
                    float(separation_km(path[horizon], observed[horizon])) if available else np.nan
                )
                row[f"S{horizon}:{name}"] = (
                    liu_weisberg(path, observed, horizon, tolerance) if available else np.nan
                )
            cover = result["ensemble"]["cover"].get(str(horizon), {})
            for share in setup.shares:
                value = cover.get(f"{share:g}")
                row[f"C{horizon}:{share:g}"] = (
                    float(value) if available and value is not None else np.nan
                )
            row[f"spread{horizon}"] = result["ensemble"]["spread_km"].get(str(horizon), np.nan)
        rows.append(row)
    frame = pd.DataFrame(rows)
    if not frame.empty:
        coast = coast_distance(frame.rename(columns={"lat": "latitude", "lon": "longitude"}))
        frame["coast_km"] = coast.to_numpy()
    return frame, dict(status)


class Summarizer:
    def __init__(self, repeats: int, confidence: float, seed: int, min_groups: int) -> None:
        self.repeats = repeats
        self.confidence = confidence
        self.seed = seed
        self.min_groups = min_groups

    def samples(self, frame: pd.DataFrame) -> list[np.ndarray] | None:
        if frame.empty or frame["group"].nunique() < self.min_groups:
            return None
        rng = np.random.default_rng(self.seed)
        return cluster_resamples(frame["group"].to_numpy(), self.repeats, rng)

    def _ci(
        self,
        samples: list[np.ndarray] | None,
        statistic: Callable[[np.ndarray], float],
        groups: int,
    ) -> list[float] | None:
        if not samples or groups < self.min_groups:
            return None
        return interval(samples, statistic, self.confidence)

    def method(
        self,
        frame: pd.DataFrame,
        method: str,
        horizon: int,
        samples: list[np.ndarray] | None,
    ) -> dict[str, Any]:
        distance = frame[f"D{horizon}:{method}"].to_numpy(dtype=float)
        valid = np.isfinite(distance)
        skill = frame[f"S{horizon}:{method}"].to_numpy(dtype=float)
        entry: dict[str, Any] = {
            **counts(frame[valid]),
            "separation_km": distribution(distance),
            "liu_weisberg": distribution(skill),
        }
        if not valid.any():
            return entry
        groups = entry["groups"]
        entry["separation_km"]["median_ci"] = self._ci(
            samples, lambda index: finite_median(distance[index]), groups
        )
        entry["liu_weisberg"]["median_ci"] = self._ci(
            samples, lambda index: finite_median(skill[index]), groups
        )
        for reference in REFERENCES:
            if method == reference:
                continue
            base = frame[f"D{horizon}:{reference}"].to_numpy(dtype=float)
            skill_ci = self._ci(
                samples, lambda index, b=base: skill_vs(distance[index], b[index]), groups
            )
            share_ci = self._ci(
                samples, lambda index, b=base: share_better(distance[index], b[index]), groups
            )
            entry[f"skill_vs_{reference}"] = {
                "value": skill_vs(distance, base),
                "ci": skill_ci,
                "verdict": significance(skill_ci, 0.0),
            }
            entry[f"better_than_{reference}"] = {
                "value": share_better(distance, base),
                "ci": share_ci,
                "verdict": significance(share_ci, 0.5),
            }
        return entry

    def coverage(
        self,
        frame: pd.DataFrame,
        horizon: int,
        shares: Sequence[float],
        samples: list[np.ndarray] | None,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {}
        errors = frame[f"D{horizon}:{SERVICE}"].to_numpy(dtype=float)
        spread = frame[f"spread{horizon}"].to_numpy(dtype=float)
        for share in shares:
            values = frame[f"C{horizon}:{share:g}"].to_numpy(dtype=float)
            valid = np.isfinite(values)
            groups = int(frame.loc[valid, "group"].nunique())
            result[f"{share:g}"] = {
                "nominal": share,
                "windows": int(valid.sum()),
                "groups": groups,
                "covered": finite_mean(values) if valid.any() else None,
                "ci": self._ci(samples, lambda index, v=values: finite_mean(v[index]), groups)
                if valid.any()
                else None,
            }
        valid = np.isfinite(errors) & np.isfinite(spread)
        result["spread_to_error"] = (
            float(np.median(spread[valid]) / np.median(errors[valid]))
            if valid.any() and np.median(errors[valid]) > 0
            else None
        )
        result["median_spread_km"] = float(np.median(spread[valid])) if valid.any() else None
        return result

    def block(
        self,
        frame: pd.DataFrame,
        methods: Sequence[str],
        horizons: Sequence[int],
        shares: Sequence[float],
        bootstrap: bool = True,
    ) -> dict[str, Any]:
        if frame.empty:
            return {"windows": 0, "drifters": 0, "groups": 0}
        samples = self.samples(frame) if bootstrap else None
        return {
            "windows": len(frame),
            "drifters": int(frame["drifter"].nunique()),
            "groups": int(frame["group"].nunique()),
            "horizons": {
                str(horizon): {
                    "methods": {
                        method: self.method(frame, method, horizon, samples) for method in methods
                    },
                    "envelopes": self.coverage(frame, horizon, shares, samples),
                }
                for horizon in horizons
            },
        }


def grid_curve(frame: pd.DataFrame, variants: Sequence[str], horizon: int) -> dict[str, Any]:
    return {
        name: {
            "median_km": float(np.nanmedian(frame[f"D{horizon}:{name}"]))
            if frame[f"D{horizon}:{name}"].notna().any()
            else None,
            "windows": int(frame[f"D{horizon}:{name}"].notna().sum()),
        }
        for name in variants
    }


def best_variant(frame: pd.DataFrame, variants: Sequence[str], horizon: int) -> str | None:
    scores = []
    for order, name in enumerate(variants):
        values = frame[f"D{horizon}:{name}"].to_numpy(dtype=float)
        if np.isfinite(values).any():
            scores.append((float(np.nanmedian(values)), order, name))
    return min(scores)[2] if scores else None


def selection_horizon(frame: pd.DataFrame, horizons: Sequence[int], minimum: int) -> int | None:
    for horizon in sorted(horizons, reverse=True):
        column = f"D{horizon}:{SERVICE}"
        if column in frame and frame[column].notna().sum() >= minimum:
            return horizon
    return None


def calibrate(
    fit: pd.DataFrame,
    variants: Sequence[str],
    parameters: dict[str, tuple[float, bool]],
    horizons: Sequence[int],
    summarizer: Summarizer,
    minimum: int,
) -> dict[str, Any] | None:
    horizon = selection_horizon(fit, horizons, minimum)
    if horizon is None:
        return None
    used = horizon_part(fit, horizon)
    best = best_variant(used, variants, horizon)
    size = counts(used)
    choices: Counter[str] = Counter()
    samples = summarizer.samples(used)
    for index in samples or []:
        chosen = best_variant(used.iloc[index], variants, horizon)
        if chosen:
            choices[chosen] += 1
    total = sum(choices.values())
    windages = sorted(parameters[name][0] for name, count in choices.items() for _ in range(count))
    tail = (1 - summarizer.confidence) / 2
    return {
        "horizon_h": horizon,
        "rule": f"минимум медианы расстояния через {horizon} ч на окнах подбора",
        "sample": size,
        "best": best,
        "windage": parameters[best][0] if best else None,
        "stokes": parameters[best][1] if best else None,
        "curve": grid_curve(used, variants, horizon),
        "bootstrap_choice": {name: count / total for name, count in choices.most_common()}
        if total
        else {},
        "bootstrap_note": None
        if samples
        else f"групп на {horizon} ч {size['groups']}, меньше {summarizer.min_groups}: "
        "бутстреп выбора не считается",
        "windage_range": [
            float(np.quantile(windages, tail)),
            float(np.quantile(windages, 1 - tail)),
        ]
        if windages
        else None,
    }


def _cell(part: pd.DataFrame, horizon: int, key: str | None) -> dict[str, Any]:
    columns = [
        f"D{horizon}:{SERVICE}",
        f"D{horizon}:stationary",
        f"D{horizon}:persistence",
        f"S{horizon}:{SERVICE}",
    ]
    values = part[columns] if key is None else part.groupby(key)[columns].median()
    service, still, moving, skill = (values[column].to_numpy(dtype=float) for column in columns)
    return {
        **counts(part),
        "units": len(values),
        "service_km": finite_median(service),
        "stationary_km": finite_median(still),
        "persistence_km": finite_median(moving),
        "liu_weisberg": finite_median(skill),
        "better_than_stationary": share_better(service, still),
        "better_than_persistence": share_better(service, moving),
    }


def table_row(
    part: pd.DataFrame, horizons: Sequence[int], label: str, subset: str, key: str | None = None
) -> dict[str, Any]:
    cells = {}
    for horizon in horizons:
        used = horizon_part(part, horizon)
        if not used.empty:
            cells[str(horizon)] = _cell(used, horizon, key)
    return {
        "label": label,
        "subset": subset,
        "weighting": key or "window",
        "kinds": sorted(part["kind"].unique()),
        "horizons": cells,
    }


def _years(part: pd.DataFrame) -> str:
    first, last = part["t0"].min().year, part["t0"].max().year
    return f"{first}" if first == last else f"{first}–{last}"


def class_table(part: pd.DataFrame, horizons: Sequence[int]) -> list[dict[str, Any]]:
    litter = bool((part["source"] == "nautilos").all())
    item, group = ("предметам", "миссиям") if litter else ("дрифтерам", "группам")
    rows = [
        table_row(part, horizons, "все окна", "all"),
        table_row(part, horizons, f"все, медиана по {item}", "all", "drifter"),
    ]
    if part["group"].nunique() < part["drifter"].nunique():
        rows.append(table_row(part, horizons, f"все, медиана по {group}", "all", "group"))
    for split in ("fit", "test"):
        chosen = part[part["split"] == split]
        if not chosen.empty:
            label = f"{SPLIT_LABELS[split]} {_years(chosen)}"
            rows.append(table_row(chosen, horizons, label, f"split:{split}"))
    if part["kind"].nunique() > 1:
        for kind in sorted(part["kind"].unique()):
            label = KIND_LABELS.get(kind, kind)
            rows.append(table_row(part[part["kind"] == kind], horizons, label, f"kind:{kind}"))
    if 1 < part["group"].nunique() <= GROUP_ROWS_MAX:
        noun = "миссия" if litter else "дрифтер"
        for name in sorted(part["group"].unique()):
            chosen = part[part["group"] == name]
            rows.append(table_row(chosen, horizons, f"{noun} {name}", f"group:{name}"))
    return rows


def build_report(
    config: dict[str, Any],
    queue: Sequence[Queued],
    census: dict[str, Any],
    setup: Setup,
    run_summary: dict[str, Any] | None,
    plan_summary: dict[str, Any] | None,
) -> tuple[dict[str, Any], pd.DataFrame]:
    metrics = config["metrics"]
    work = resolve(config["paths"]["work"])
    frame, status = window_rows(
        queue,
        setup,
        work,
        float(config["windows"]["persistence_h"]),
        float(metrics["skill_tolerance"]),
    )
    summarizer = Summarizer(
        int(metrics["bootstrap"]),
        float(metrics["confidence"]),
        config["seed"],
        int(metrics["min_groups"]),
    )
    variants = [variant_name(w, s) for w, s in setup.grid.variants]
    parameters = {variant_name(w, s): (w, s) for w, s in setup.grid.variants}
    horizons = setup.horizons
    shares = setup.shares
    minimum = int(config["calibration"]["min_windows"])
    report: dict[str, Any] = {
        "name": config["name"],
        "created_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "config": {"path": config["_path"], "sha256": config["_sha256"]},
        "question": "насколько сценарий дрейфа сервиса (littora-drift-1) совпадает с реальными "
        "траекториями дрифтеров и предметов мусора через 24, 48 и 72 ч",
        "service": {
            "model": "app.drift: integrate() RK2, шаг 900 с, диффузия K = 5 м²/с, 40 частиц на "
            "вариант, точечная зона — круг 50 м; форсинг OpenMeteoForcing (SMOC − параметрический "
            "Стокс, MFWAM → Стокс, ERA5 10 м), область = точка старта ± 50 км, маска суши по сетке "
            "Open-Meteo (снимка SCL нет)",
            "ensemble": {
                "windages": list(setup.service.windages),
                "stokes": list(setup.service.stokes),
                "variants": len(setup.service.variants),
                "members": setup.service.members,
                "envelope": "выпуклая оболочка доли частиц на плаву, ближайших к их медиане, "
                "+ 150 м (как products.envelopes; 0,9 — ровно контур сервиса, 0,5 — тот же "
                "алгоритм)",
            },
            "grid": {"windages": list(setup.grid.windages), "stokes": list(setup.grid.stokes)},
            "setup_hash": setup_hash(setup),
        },
        "forcing_access": {
            "provider": "Open-Meteo (marine-api: meteofrance_currents, meteofrance_wave; "
            "archive-api: ERA5)",
            "cache": "те же запросы OpenMeteoForcing; ответ собирается из кэша по узлу сетки и "
            "14-дневному блоку, значения не меняются",
            "quota": "бесплатный Open-Meteo считает каждую точку запроса отдельным вызовом "
            "(10 000 в сутки на IP); проверено: лимит в минуту срабатывает примерно на 600 точках",
            "run": run_summary,
            "remaining_plan": plan_summary,
        },
        "baselines": {
            "stationary": "x(t0 + τ) = x(t0)",
            "persistence": f"x(t0) + ū·τ, ū — средняя скорость дрифтера за "
            f"[t0 − {config['windows']['persistence_h']} ч, t0]",
            "currents_only": "та же модель, α = 0, Стокс выкл.",
        },
        "metrics_definition": {
            "separation": "расстояние по большому кругу между прогнозом и дрифтером через τ",
            "service_median": "медиана всех 320 частиц ансамбля сервиса (median_path)",
            "grid_variant": "медиана 40 частиц одного варианта α × Стокс",
            "liu_weisberg": "s = max(0, 1 − Σd_i / Σl_oi), n = 1, шаг 1 ч; l_oi — длина пройденной "
            "дрифтером траектории к шагу i (Liu, Weisberg 2011, doi:10.1029/2010JC006837)",
            "skill_vs_persistence": "1 − медиана D(модель) / медиана D(персистентность)",
            "better_than_persistence": "доля окон, где модель ближе, чем персистентность",
            "skill_vs_stationary": "1 − медиана D(модель) / медиана D(неподвижная точка)",
            "better_than_stationary": "доля окон, где модель ближе, чем неподвижная точка",
            "coverage": "доля окон, где реальная точка внутри огибающей ансамбля",
            "spread_to_error": "медиана расстояния частиц до медианы ансамбля / медиана ошибки",
            "intervals": f"{metrics['confidence']:.0%} бутстреп по группам целиком, "
            f"{metrics['bootstrap']} повторов; группа — миссия NAUTILOS (предметы одной миссии "
            "выпущены вместе и дрейфуют рядом), для остальных источников — дрифтер; если групп "
            f"с данными на горизонте меньше {metrics['min_groups']}, интервала нет",
            "significance": "«не значимо» — интервал SS содержит 0 или интервал доли окон "
            "содержит 0,5; «интервала нет» — групп меньше порога",
            "table": "строки classes.*.table: «все окна» — медиана по окнам; «медиана по "
            "предметам/миссиям» — медиана медиан каждого предмета или миссии, и доля «ближе» — "
            "доля предметов или миссий; остальные строки — медианы по окнам подвыборки",
        },
        "sample": {"census": census, "status": status},
    }
    if frame.empty:
        report["verdict"] = ["нет посчитанных окон"]
        return report, frame
    med_like = frame[frame["source"] != "blacksea"]
    report["forcing_grid"] = {
        "marine_step_deg": {
            f"{step:g}": int(count)
            for step, count in frame["marine_step_deg"].value_counts().items()
        },
        "left_domain_share": distribution(frame["left_domain"].to_numpy(dtype=float)),
        "beached_share": distribution(frame["beached"].to_numpy(dtype=float)),
        "note": "шаг морской сетки выбирает marine_axes: не больше 200 узлов на область ±50 км, "
        "поэтому на широтах 40–45° часто получается 1/6°, а не 1/12°",
    }
    report["caveats"] = caveats(report, plan_summary) + concentration_caveats(frame, max(horizons))
    classes = {}
    for name in CLASS_LABELS:
        part = frame[frame["class"] == name]
        if name == "blacksea":
            part = part[part["period"] == "free"]
        if part.empty:
            continue
        classes[name] = {
            "label": CLASS_LABELS[name],
            "all": summarizer.block(part, KEY_METHODS, horizons, shares),
        }
        if part["drifter"].nunique() > 1:
            classes[name]["table"] = class_table(part, horizons)
    report["classes"] = classes
    calibration = {}
    for name, members in config["calibration"]["classes"].items():
        pool = frame[frame["class"].isin(members)]
        fit, test = pool[pool["split"] == "fit"], pool[pool["split"] == "test"]
        chosen = calibrate(fit, variants, parameters, horizons, summarizer, minimum)
        entry: dict[str, Any] = {
            "members": [CLASS_LABELS[member] for member in members],
            "fit_windows": len(fit),
            "fit_drifters": int(fit["drifter"].nunique()) if not fit.empty else 0,
            "fit_groups": int(fit["group"].nunique()) if not fit.empty else 0,
            "test_windows": len(test),
            "test_drifters": int(test["drifter"].nunique()) if not test.empty else 0,
            "test_groups": int(test["group"].nunique()) if not test.empty else 0,
            "selection": chosen,
        }
        if chosen and chosen["best"] and not test.empty:
            methods = [chosen["best"], *KEY_METHODS]
            entry["test"] = summarizer.block(test, methods, horizons, shares)
            entry["test_oracle"] = {
                "note": "лучший вариант, выбранный прямо на проверке, — только для сравнения",
                "best": best_variant(test, variants, chosen["horizon_h"]),
                "curve": grid_curve(test, variants, chosen["horizon_h"]),
            }
        if chosen and chosen["best"] and not fit.empty:
            entry["fit"] = summarizer.block(fit, [chosen["best"], *KEY_METHODS], horizons, shares)
            entry["error_radius"] = error_radius(fit, test, horizons, shares)
        calibration[name] = entry
    report["calibration"] = calibration
    report["litter_types"] = litter_types(frame, variants, parameters, horizons, minimum)
    strata: dict[str, Any] = {}
    split_wind = float(metrics["wind_split_ms"])
    split_coast = float(metrics["coast_split_km"])
    masks = {
        "drogue:on": med_like["drogue"] == "on",
        "drogue:off": med_like["drogue"] == "off",
        f"wind:<{split_wind:g}": med_like["wind_ms"] < split_wind,
        f"wind:>={split_wind:g}": med_like["wind_ms"] >= split_wind,
        f"coast:<{split_coast:g}km": med_like["coast_km"] < split_coast,
        f"coast:>={split_coast:g}km": med_like["coast_km"] >= split_coast,
    }
    for kind in sorted(med_like["kind"].unique()):
        masks[f"type:{kind}"] = med_like["kind"] == kind
    for label, mask in masks.items():
        part = med_like[mask.to_numpy()]
        if not part.empty:
            strata[label] = summarizer.block(part, KEY_METHODS, horizons, shares, bootstrap=False)
    report["strata"] = strata
    report["blacksea"] = blacksea_section(frame, variants, parameters, horizons, shares, summarizer)
    fit_black = report["blacksea"].get("free_fit") or {}
    if fit_black.get("windage") is not None:
        report["blacksea"]["versus_mediterranean"] = {
            name: {
                "windage_range": entry["selection"]["windage_range"],
                "inside": entry["selection"]["windage_range"][0]
                <= fit_black["windage"]
                <= entry["selection"]["windage_range"][1],
            }
            for name, entry in calibration.items()
            if entry.get("selection") and entry["selection"].get("windage_range")
        }
    report["verdict"] = verdict(report)
    return report, frame


def caveats(report: dict[str, Any], plan_summary: dict[str, Any] | None) -> list[str]:
    status = report["sample"]["status"]
    missing = {
        source: status.get(f"{source}:not_simulated", 0)
        for source in ("blacksea", "nautilos", "swot", "med")
    }
    notes = []
    if plan_summary and plan_summary.get("pending"):
        notes.append(
            f"не посчитано {plan_summary['pending']} окон из {plan_summary['queued']} "
            f"(SWOT-Med {missing['swot']}, Средиземное море {missing['med']}): им нужно ещё до "
            f"{plan_summary['upper_bound_calls']['total']} вызовов Open-Meteo, это больше суточной "
            "квоты бесплатного API (10 000 точек в сутки на IP, общая с сервисом); прогон "
            "продолжается с того же места командой drift check --stage simulate --budget N"
        )
    notes.extend(
        [
            "прогон на реанализе ERA5 и архивных SMOC/MFWAM; для снимков моложе 7 дней сервис "
            "берёт прогноз ветра, там ошибка будет больше",
            "область форсинга — точка старта ± 50 км, как у сервиса; частицы, вышедшие за неё, "
            "берут ветер и течение с края (доля в forcing_grid.left_domain_share)",
            "маска суши — по сетке Open-Meteo (узлы без данных о море), снимка SCL нет; "
            "у берега выброс на сушу грубый",
            "окна одного дрифтера перекрываются (старт каждые 6 или 24 ч), а предметы NAUTILOS "
            "одной миссии выпущены вместе и дрейфуют рядом; поэтому бутстреп идёт по миссиям "
            "целиком (для остальных источников — по дрифтерам), и при числе групп меньше порога "
            "интервала нет: независимых случаев столько, сколько миссий, а не окон",
            "Чёрное море — один дрифтер: разбор случая без интервалов",
        ]
    )
    return notes


def concentration_caveats(frame: pd.DataFrame, horizon: int) -> list[str]:
    notes = []
    for name in CLASS_LABELS:
        part = horizon_part(frame[frame["class"] == name], horizon)
        if part.empty or part["drifter"].nunique() < 2:
            continue
        top = part["group"].value_counts().head(2)
        heavy = part["drifter"].value_counts().head(1)
        notes.append(
            f"{CLASS_LABELS[name]}, {horizon} ч: {int(top.sum())} из {len(part)} окон дают "
            + " и ".join(f"{group} ({count})" for group, count in top.items())
            + f", один предмет {heavy.index[0]} — {int(heavy.iloc[0])} "
            + plural(int(heavy.iloc[0]), "окно", "окна", "окон")
            + "; медиана по окнам "
            "описывает в основном эти случаи, см. строки по миссиям и медианы по предметам"
        )
    return notes


def error_radius(
    fit: pd.DataFrame, test: pd.DataFrame, horizons: Sequence[int], shares: Sequence[float]
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "note": "круг вокруг медианы ансамбля с радиусом — квантилем ошибки на окнах подбора; "
        "покрытие проверено на окнах проверки",
    }
    for horizon in horizons:
        errors = fit[f"D{horizon}:{SERVICE}"].to_numpy(dtype=float)
        errors = errors[np.isfinite(errors)]
        checks = test[f"D{horizon}:{SERVICE}"].to_numpy(dtype=float) if not test.empty else []
        checks = np.asarray(checks, dtype=float)
        checks = checks[np.isfinite(checks)]
        entry = {}
        for share in shares:
            if errors.size == 0:
                continue
            radius = float(np.quantile(errors, share))
            entry[f"{share:g}"] = {
                "radius_km": radius,
                "test_windows": int(checks.size),
                "test_covered": float(np.mean(checks <= radius)) if checks.size else None,
            }
        result[str(horizon)] = entry
    return result


def litter_types(
    frame: pd.DataFrame,
    variants: Sequence[str],
    parameters: dict[str, tuple[float, bool]],
    horizons: Sequence[int],
    minimum: int,
) -> dict[str, Any]:
    items = frame[frame["class"] == "litter_items"]
    result: dict[str, Any] = {
        "note": "описание по всем окнам типа (подбор и проверка вместе): это парусность, "
        "лучше всего совпадающая с треками, а не проверенная настройка",
    }
    for kind in sorted(items["kind"].unique()):
        part = items[items["kind"] == kind]
        horizon = selection_horizon(part, horizons, min(minimum, 5))
        if horizon is None:
            continue
        best = best_variant(part, variants, horizon)
        result[kind] = {
            "windows": len(part),
            "drifters": int(part["drifter"].nunique()),
            "horizon_h": horizon,
            "best": best,
            "windage": parameters[best][0] if best else None,
            "stokes": parameters[best][1] if best else None,
            "curve": grid_curve(part, variants, horizon),
            "service_median_km": finite_median(part[f"D{horizon}:{SERVICE}"].to_numpy()),
            "persistence_median_km": finite_median(part[f"D{horizon}:persistence"].to_numpy()),
        }
    return result


def blacksea_section(
    frame: pd.DataFrame,
    variants: Sequence[str],
    parameters: dict[str, tuple[float, bool]],
    horizons: Sequence[int],
    shares: Sequence[float],
    summarizer: Summarizer,
) -> dict[str, Any]:
    part = frame[frame["source"] == "blacksea"]
    section: dict[str, Any] = {
        "note": "один дрифтер: разбор случая, не статистика; интервалов нет, окна перекрываются "
        "(старт каждые 6 ч); флага дрога нет, номинально SVP-B с дрогом 15 м, но перед "
        "свободным дрейфом буй волочил якорь — дрог мог быть потерян",
        "periods": {},
    }
    for period in ("free", "anchored", "grounding"):
        subset = part[part["period"] == period]
        if subset.empty:
            continue
        section["periods"][period] = summarizer.block(
            subset, KEY_METHODS, horizons, shares, bootstrap=False
        )
    free = part[part["period"] == "free"]
    if not free.empty:
        horizon = max(horizons)
        best = best_variant(free, variants, horizon)
        section["free_fit"] = {
            "horizon_h": horizon,
            "best": best,
            "windage": parameters[best][0] if best else None,
            "stokes": parameters[best][1] if best else None,
            "curve": grid_curve(free, variants, horizon),
        }
    return section


def _ci_text(ci: Sequence[float] | None, percent: bool = False) -> str:
    if not ci:
        return "[—]"
    if percent:
        return f"[{ci[0]:.0%}–{ci[1]:.0%}]"
    return f"[{ci[0]:+.2f}; {ci[1]:+.2f}]"


def comparison_text(service: dict[str, Any], reference: str) -> str:
    skill = service.get(f"skill_vs_{reference}") or {}
    better = service.get(f"better_than_{reference}") or {}
    if skill.get("value") is None or better.get("value") is None:
        return f"{REFERENCE_DATIVE[reference]}: —"
    if not skill["ci"] and not better["ci"]:
        return (
            f"{REFERENCE_DATIVE[reference]}: SS {skill['value']:+.2f}, ближе в "
            f"{better['value']:.0%} окон, интервала нет"
        )
    return (
        f"{REFERENCE_DATIVE[reference]}: SS {skill['value']:+.2f} {_ci_text(skill['ci'])} "
        f"{skill['verdict']}, ближе в {better['value']:.0%} окон "
        f"{_ci_text(better['ci'], percent=True)} {better['verdict']}"
    )


def class_lines(entry: dict[str, Any]) -> list[str]:
    lines = []
    verdicts: dict[str, list[str]] = {reference: [] for reference in REFERENCES}
    horizons = entry["all"].get("horizons", {})
    for horizon, block in horizons.items():
        methods = block["methods"]
        service = methods.get(SERVICE)
        if not service or not service["windows"]:
            continue
        distance = service["separation_km"]
        ci = distance.get("median_ci")
        spread = f" [{ci[0]:.1f}–{ci[1]:.1f}]" if ci else ""
        parts = [f"сервис {distance['median']:.1f}{spread} км"]
        for reference in ("stationary", "persistence"):
            parts.append(
                f"{REFERENCE_LABELS[reference]} "
                f"{methods[reference]['separation_km']['median']:.1f} км"
            )
        lines.append(
            f"{entry['label']}, {horizon} ч ({units_text(service)}): "
            + ", ".join(parts)
            + "; "
            + "; ".join(comparison_text(service, reference) for reference in REFERENCES)
        )
        for reference in REFERENCES:
            verdicts[reference].append(
                (service.get(f"skill_vs_{reference}") or {}).get("verdict", "интервала нет")
            )
    found = [value for values in verdicts.values() for value in values]
    if found and any(value != "интервала нет" for value in found):
        hours = "/".join(horizons)
        if all(value != "значимо лучше" for value in found):
            lines.append(
                f"{entry['label']}: ни на одном горизонте ({hours} ч) сервис значимо не лучше "
                "ни персистентности, ни неподвижной точки"
            )
        else:
            lines.append(
                f"{entry['label']}, значимость SS по горизонтам {hours} ч: "
                + "; ".join(
                    f"{REFERENCE_DATIVE[reference]} {', '.join(values)}"
                    for reference, values in verdicts.items()
                )
            )
    lines.extend(table_lines(entry))
    return lines


def _share_text(row: dict[str, Any], cell: dict[str, Any], reference: str) -> str:
    value = cell[f"better_than_{reference}"]
    if value is None or not np.isfinite(value):
        return "—"
    if row["weighting"] == "window":
        return f"{value:.0%} окон"
    if row["weighting"] == "drifter":
        noun = "предм." if cell["missions"] == cell["groups"] else "дрифт."
    else:
        noun = "миссий" if cell["missions"] == cell["groups"] else "групп"
    return f"{round(value * cell['units'])}/{cell['units']} {noun}"


def table_lines(entry: dict[str, Any]) -> list[str]:
    rows = entry.get("table") or []
    if not rows:
        return []
    horizon = max((key for row in rows for key in row["horizons"]), key=int)
    lines = [f"{entry['label']}, таблица на {horizon} ч (сервис / точка / персистентность):"]
    for row in rows:
        cell = row["horizons"].get(horizon)
        if not cell:
            continue
        lines.append(
            f"  {row['label']}: {units_text(cell)}; {cell['service_km']:.1f} / "
            f"{cell['stationary_km']:.1f} / {cell['persistence_km']:.1f} км, LW "
            f"{cell['liu_weisberg']:.2f}; сервис ближе точки: "
            f"{_share_text(row, cell, 'stationary')}, ближе персистентности: "
            f"{_share_text(row, cell, 'persistence')}"
        )
    return lines


def calibration_line(name: str, entry: dict[str, Any]) -> str:
    chosen = entry.get("selection")
    if not chosen or not chosen.get("best"):
        return f"подбор «{name}»: недостаточно окон подбора"
    horizon = str(chosen["horizon_h"])
    size = chosen["sample"]
    text = (
        f"подбор «{name}» на {horizon} ч ({units_text(size)}, крупнейшая группа — "
        f"{size['largest_group_share']:.0%} окон): α = {chosen['windage'] * 100:g} %, Стокс "
        f"{'вкл.' if chosen['stokes'] else 'выкл.'}"
    )
    spread = chosen.get("windage_range")
    if spread:
        text += f", бутстреп по группам α {spread[0] * 100:g}–{spread[1] * 100:g} %"
    else:
        text += f"; {chosen['bootstrap_note']}"
    methods = entry.get("test", {}).get("horizons", {}).get(horizon, {}).get("methods", {})
    best, service = methods.get(chosen["best"]), methods.get(SERVICE)
    if not best or not service or not service["windows"]:
        return text + "; проверочных окон нет"
    skill = service.get("skill_vs_persistence") or {}
    medians = {name: block["separation_km"]["median"] for name, block in methods.items()}
    return text + (
        f"; проверка на {horizon} ч ({units_text(service)}, один предмет — "
        f"{service['largest_drifter_share']:.0%} окон): подобранный вариант "
        f"{medians[chosen['best']]:.1f} км, ансамбль {medians[SERVICE]:.1f} км, неподвижная "
        f"точка {medians['stationary']:.1f} км, персистентность {medians['persistence']:.1f} км; "
        f"SS ансамбля к персистентности {skill.get('verdict', 'интервала нет')}"
    )


def verdict(report: dict[str, Any]) -> list[str]:
    lines = []
    for entry in report.get("classes", {}).values():
        lines.extend(class_lines(entry))
    for name, entry in report.get("calibration", {}).items():
        lines.append(calibration_line(name, entry))
    lines.extend(envelope_lines(report))
    lines.extend(coast_lines(report))
    fit = report.get("blacksea", {}).get("free_fit")
    if fit and fit.get("best"):
        ranges = report["blacksea"].get("versus_mediterranean", {})
        inside = ", ".join(
            f"{name}: {'внутри' if entry['inside'] else 'вне'} {entry['windage_range'][0] * 100:g}–"
            f"{entry['windage_range'][1] * 100:g} %"
            for name, entry in ranges.items()
        )
        lines.append(
            f"Чёрное море, свободный дрейф: лучший α = {fit['windage'] * 100:g} %, "
            f"Стокс {'вкл.' if fit['stokes'] else 'выкл.'} (подбор прямо на этом дрифтере)"
            + (f"; диапазон подбора {inside}" if inside else "")
        )
    grid = report.get("forcing_grid", {})
    steps = grid.get("marine_step_deg", {})
    if steps:
        total = sum(steps.values())
        coarse = sum(count for step, count in steps.items() if float(step) > 0.1)
        left = grid["left_domain_share"]["mean"]
        lines.append(
            f"форсинг сервиса: в {coarse} из {total} окон сетка течений 1/6°, а не 1/12° "
            f"(предел 200 узлов на область ±50 км); в среднем {left:.0%} частиц за 72 ч "
            "выходят за область и берут форсинг с её края"
        )
    lines.append(
        "все окна посчитаны на реанализе ERA5 и архивных SMOC/MFWAM; для снимков моложе 7 дней "
        "сервис берёт прогноз ветра, там ошибка будет больше"
    )
    return lines


def envelope_lines(report: dict[str, Any]) -> list[str]:
    lines = []
    for entry in report.get("classes", {}).values():
        horizons = entry["all"].get("horizons", {})
        parts = []
        for horizon, block in horizons.items():
            envelope = block["envelopes"]
            ninety = (envelope.get("0.9") or {}).get("covered")
            ratio = envelope.get("spread_to_error")
            radius = block["methods"][SERVICE]["separation_km"]["p90"]
            if ninety is None or ratio is None or radius is None:
                continue
            parts.append(
                f"{horizon} ч — внутри 90 % {ninety:.0%}, разброс/ошибка {ratio:.2f}, "
                f"p90 ошибки {radius:.0f} км"
            )
        if parts:
            lines.append(f"огибающие, {entry['label']}: " + "; ".join(parts))
    return lines


def coast_lines(report: dict[str, Any]) -> list[str]:
    lines = []
    for label, block in report.get("strata", {}).items():
        if not label.startswith("coast:"):
            continue
        methods = block.get("horizons", {}).get("72", {}).get("methods", {})
        service = methods.get(SERVICE, {}).get("separation_km", {}).get("median")
        still = methods.get("stationary", {}).get("separation_km", {}).get("median")
        moving = methods.get("persistence", {}).get("separation_km", {}).get("median")
        if service is None:
            continue
        lines.append(
            f"старт {label.split(':', 1)[1].replace('km', ' км')} от берега, 72 ч: сервис "
            f"{service:.1f} км, неподвижная точка {still:.1f} км, персистентность {moving:.1f} км "
            f"({units_text(methods[SERVICE])}, без интервалов)"
        )
    return lines


def write_report(config: dict[str, Any], report: dict[str, Any]) -> str:
    path = resolve(config["paths"]["report"])
    write_json(path, report)
    return str(path.relative_to(resolve(".")))
