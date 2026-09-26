from __future__ import annotations

import copy
import math
from collections import Counter
from typing import Any

import joblib
import numpy as np
import pandas as pd
from joblib import Parallel, delayed

from littora_ml.common.io import write_json
from littora_ml.common.paths import MODELS, REPORTS, resolve
from littora_ml.concentration.dataset import modeling_table, survey_day_groups
from littora_ml.concentration.features import FEATURE_GROUPS, build_features
from littora_ml.concentration.guard import blocked_columns, check_features
from littora_ml.concentration.models import BASELINES, candidate_zoo, ensemble
from littora_ml.concentration.validation import (
    Option,
    RepeatedCV,
    confidence_label,
    date_block_split,
    folds,
    metrics,
    out_of_fold,
    paired_difference,
    repeated_nested_cv,
    spatial_groups,
    spread,
)

OPTIMISTIC = "выбор на тех же фолдах (оптимистично)"
HOLDOUT_OPTIMISTIC = "минимум по вариантам на самом отложенном блоке: выбор на тесте (оптимистично)"
PRIMARY = "основной результат: полный набор моделей и признаков, выбор только на внутренних фолдах"
SHORTLIST = (
    "шорт-лист вариантов составлен после разведочных прогонов на тех же данных (оптимистично)"
)
SERVICE_NESTED = (
    "исследовательская метрика: вложенный выбор среди координатных вариантов на внутренних "
    "фолдах; в сервис идёт одна модель по правилу service.rule, а не эта процедура"
)
SERVICE_SELECTION = (
    "если шлюз прошли несколько кандидатов, берётся наименьшая MAE на тех же фолдах: "
    "оценка выданной модели слегка оптимистична"
)
COVERAGE_DEFINITION = (
    "доля событий внутри интервала на внешних фолдах; квантиль строился по остаткам log1p "
    "одной внутренней CV той же модели на обучающей части; у выданной модели квантиль — "
    "медиана по повторам внешней CV на всех событиях, правило близкое, но не тождественное"
)
QUANTILE_DEFINITION = (
    "медиана по повторам конформного квантиля остатков log1p внешней CV выданной модели"
)
FAMILY_ALPHA = 0.05
KM_PER_DEGREE = 110.0
SPLITS_FILE = REPORTS / "splits" / "concentration.csv"


def load_features(config: dict[str, Any], refresh: bool = False) -> pd.DataFrame:
    path = resolve(config["features_cache"])
    if path.exists() and not refresh:
        return pd.read_parquet(path)
    features = build_features(modeling_table())
    path.parent.mkdir(parents=True, exist_ok=True)
    features.to_parquet(path, index=False)
    return features


def _columns(feature_set: list[str]) -> list[str]:
    return [column for group in feature_set for column in FEATURE_GROUPS[group]]


def _usable(columns: list[str], table: pd.DataFrame) -> list[str]:
    return [c for c in columns if table[c].notna().all() and table[c].nunique() > 1]


def _threads(config: dict[str, Any]) -> int:
    return -1 if config.get("jobs", -1) == 1 else 1


def _options(config: dict[str, Any], table: pd.DataFrame) -> list[Option]:
    threads = _threads(config)
    zoo = [*candidate_zoo(config["seed"], threads), ensemble(config["seed"], threads)]
    by_name = {candidate.name: candidate for candidate in zoo}
    options = []
    search = config.get("search", {})
    allowed = search.get("options")
    for candidate in zoo:
        if candidate.name in BASELINES:
            options.append((candidate.name, candidate, ["x_km", "y_km"]))
            continue
        for set_name, groups in config["feature_sets"].items():
            label = f"{candidate.name}|{set_name}"
            columns = _usable(_columns(groups), table)
            if columns and (allowed is None or label in allowed):
                options.append((label, by_name[candidate.name], columns))
    unknown = set(allowed or []) - {label for label, _, _ in options}
    if unknown:
        raise ValueError(f"варианты шорт-листа не найдены: {sorted(unknown)}")
    return options


def research_role(config: dict[str, Any]) -> dict[str, str]:
    if config.get("search", {}).get("options") is None:
        return {"role": "primary", "selection": PRIMARY}
    return {"role": "shortlist", "selection": SHORTLIST}


def _service_options(config: dict[str, Any], table: pd.DataFrame) -> list[Option]:
    by_name = {c.name: c for c in candidate_zoo(config["seed"], _threads(config))}
    spatial = FEATURE_GROUPS["spatial"]
    options = []
    for label in config["service"]["options"]:
        name, _, set_name = label.partition("|")
        columns = spatial
        if set_name:
            columns = _usable(_columns(config["feature_sets"][set_name]), table)
        if not set(columns) <= set(spatial):
            raise ValueError(f"сервисная модель {label} должна использовать только координаты")
        options.append((label, by_name[name], list(columns)))
    if "median" not in {label for label, _, _ in options}:
        raise ValueError("в сервисных вариантах нужна медиана как опорная модель")
    return options


def _aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    spearman = [row["spearman"] for row in rows if row["spearman"] is not None]
    return {
        "mae": spread([row["mae"] for row in rows]),
        "rmse": spread([row["rmse"] for row in rows]),
        "medae": float(np.mean([row["medae"] for row in rows])),
        "bias": float(np.mean([row["bias"] for row in rows])),
        "mae_log1p": float(np.mean([row["mae_log1p"] for row in rows])),
        "spearman": float(np.mean(spearman)) if spearman else None,
    }


def _track(cv: RepeatedCV, config: dict[str, Any]) -> dict[str, Any]:
    nested_rows, base_rows = cv.nested_metrics(), cv.option_metrics("median")
    nested_coverage, base_coverage = cv.coverage(), cv.coverage("median")
    draws = config.get("bootstrap", 2000)
    difference = paired_difference(
        cv.target, cv.nested, cv.oof["median"], cv.groups, draws, config["seed"]
    )
    chosen = Counter(fold["selected"] for rows in cv.selections for fold in rows)
    return {
        "nested": {
            **_aggregate(nested_rows),
            "coverage": spread(nested_coverage),
            "target_coverage": config["coverage"],
            "median_width": spread(cv.width()),
        },
        "baseline": {
            **_aggregate(base_rows),
            "coverage": spread(base_coverage),
            "median_width": spread(cv.width("median")),
        },
        "difference_vs_median": difference,
        "gain_over_median": bool(difference["mae"]["ci"][1] < 0),
        "selected_in_folds": dict(chosen.most_common()),
        "repetitions": [
            {
                "repetition": repetition,
                "nested_mae": nested["mae"],
                "nested_rmse": nested["rmse"],
                "nested_coverage": float(nested_coverage[repetition]),
                "baseline_mae": base["mae"],
                "baseline_rmse": base["rmse"],
                "baseline_coverage": float(base_coverage[repetition]),
                "folds": cv.selections[repetition],
            }
            for repetition, (nested, base) in enumerate(zip(nested_rows, base_rows, strict=True))
        ],
    }


def calendar_day(dates: pd.Series) -> np.ndarray:
    stamps = pd.to_datetime(pd.Series(dates))
    day = stamps.dt.dayofyear
    return (day - (stamps.dt.is_leap_year & (day >= 60)).astype(int)).to_numpy()


def season_window(dates: pd.Series, margin: int) -> dict[str, Any]:
    stamps = pd.to_datetime(pd.Series(dates)).reset_index(drop=True)
    numbers = calendar_day(stamps)
    days = np.unique(numbers)
    gaps = np.diff(np.append(days, days[0] + 365))
    cut = int(np.argmax(gaps))
    first, last = int(days[(cut + 1) % len(days)]), int(days[cut])
    span = (last - first) % 365
    edges = [stamps[numbers == day].iloc[0].strftime("%d.%m") for day in (first, last)]
    window = {
        "margin_days": margin,
        "dates": [str(dates.min()), str(dates.max())],
        "span": edges,
        "day_numbering": "1–365, 29.02 считается как 28.02",
    }
    if span + 2 * margin >= 364:
        return {**window, "doy_start": 1, "doy_end": 365}
    return {
        **window,
        "doy_start": (first - margin - 1) % 365 + 1,
        "doy_end": (last + margin - 1) % 365 + 1,
    }


def domain_bbox(latitude, longitude, km: float) -> list[float]:
    south = float(np.min(latitude)) - km / KM_PER_DEGREE
    north = float(np.max(latitude)) + km / KM_PER_DEGREE
    edge = min(89.9, max(abs(south), abs(north)))
    pad = km / (KM_PER_DEGREE * math.cos(math.radians(edge)))
    return [float(np.min(longitude)) - pad, south, float(np.max(longitude)) + pad, north]


def season_pools(options: list[Option]) -> tuple[list[Option], list[Option]]:
    season = set(FEATURE_GROUPS["season"])
    with_season = [option for option in options if season & set(option[2])]
    without_season = [option for option in options if not season & set(option[2])]
    seen = {(candidate.name, tuple(columns)) for _, candidate, columns in without_season}
    for label, candidate, columns in with_season:
        plain = [column for column in columns if column not in season]
        key = (candidate.name, tuple(plain))
        if plain and key not in seen:
            seen.add(key)
            without_season.append((f"{label}-season", candidate, plain))
    return with_season, without_season


def _holdout_task(
    candidate, columns: list[str], fit: pd.DataFrame, held: pd.DataFrame, target, inner
) -> tuple[float, np.ndarray]:
    oof = out_of_fold(candidate, fit[columns], target, inner)
    model = copy.deepcopy(candidate).fit(fit[columns], target)
    return float(np.mean(np.abs(oof - target))), model.predict(held[columns])


def season_check(
    options: list[Option],
    table: pd.DataFrame,
    target: np.ndarray,
    groups: np.ndarray,
    config: dict[str, Any],
) -> dict[str, Any]:
    fraction = config["service"].get("season_holdout", 0.7)
    train, test = date_block_split(table["date"], fraction)
    fit, held = table.iloc[train], table.iloc[test]
    inner = folds(groups[train], config["inner_splits"], config["seed"])
    with_season, without_season = season_pools(options)
    pool = [*with_season, *without_season]
    results = Parallel(n_jobs=config.get("jobs", -1))(
        delayed(_holdout_task)(candidate, columns, fit, held, target[train], inner)
        for _, candidate, columns in pool
    )
    seasonal_labels = {label for label, _, _ in with_season}
    scores = {}
    for (label, _, _), (inner_mae, prediction) in zip(pool, results, strict=True):
        result = metrics(target[test], prediction)
        scores[label] = {
            "season": label in seasonal_labels,
            "inner_mae": inner_mae,
            "holdout_mae": result["mae"],
            "holdout_rmse": result["rmse"],
        }

    def chosen(group: list[Option]) -> dict[str, Any] | None:
        if not group:
            return None
        label = min((option[0] for option in group), key=lambda name: scores[name]["inner_mae"])
        row = {key: value for key, value in scores[label].items() if key != "season"}
        return {"selected": label, "candidates": len(group), **row}

    def lowest(flag: bool) -> float | None:
        values = [row["holdout_mae"] for row in scores.values() if row["season"] is flag]
        return min(values) if values else None

    picked_with, picked_without = chosen(with_season), chosen(without_season)
    holds = None
    if picked_with and picked_without:
        holds = bool(picked_with["holdout_mae"] < picked_without["holdout_mae"])
    median = metrics(target[test], np.full(len(test), np.median(target[train])))
    return {
        "scheme": f"первые {fraction:.0%} дней съёмки по времени → остальные дни",
        "selection": (
            "в группах «с сезоном» и «без сезона» вариант выбран по внутренней CV по дням "
            f"съёмки (фолдов: {config['inner_splits']}) только на первых днях; выбранный вариант "
            "обучен на первых днях и один раз оценён на отложенном блоке"
        ),
        "train_days": [str(fit["date"].min()), str(fit["date"].max())],
        "test_days": [str(held["date"].min()), str(held["date"].max())],
        "train_events": len(train),
        "test_events": len(test),
        "median": {"mae": median["mae"], "rmse": median["rmse"]},
        "with_season": picked_with,
        "without_season": picked_without,
        "season_holds_up": holds,
        "options_note": (
            "holdout_mae каждой опции — справочно; выбор по нему был бы выбором на отложенном "
            "блоке (оптимистично)"
        ),
        "holdout_minimum": {
            "selection": HOLDOUT_OPTIMISTIC,
            "with_season_mae": lowest(True),
            "without_season_mae": lowest(False),
        },
        "options": scores,
        "used_for_service": False,
    }


def _service(cv: RepeatedCV, options: list[Option], config: dict[str, Any]) -> dict[str, Any]:
    draws, seed = config.get("bootstrap", 2000), config["seed"]
    rivals = [label for label, _, _ in options if label != "median"]
    confidence = 1 - FAMILY_ALPHA / max(1, len(rivals))
    candidates = {}
    for label in rivals:
        difference = paired_difference(
            cv.target, cv.oof[label], cv.oof["median"], cv.groups, draws, seed, confidence
        )
        candidates[label] = {
            **_aggregate(cv.option_metrics(label)),
            "coverage": spread(cv.coverage(label)),
            "median_width": spread(cv.width(label)),
            "difference_vs_median": difference,
            "passes": bool(difference["mae"]["ci"][1] < 0),
        }
    passed = [label for label in rivals if candidates[label]["passes"]]
    deployed = (
        min(passed, key=lambda label: candidates[label]["mae"]["mean"]) if passed else "median"
    )
    baseline = {
        **_aggregate(cv.option_metrics("median")),
        "coverage": spread(cv.coverage("median")),
        "median_width": spread(cv.width("median")),
    }
    own = candidates[deployed] if deployed != "median" else baseline
    return {
        "options": [label for label, _, _ in options],
        "features": FEATURE_GROUPS["spatial"],
        "rule": (
            "каждый координатный кандидат отдельно против медианы: те же повторы CV по дням "
            f"съёмки, кластерный бутстрэп по дням, {confidence_label(confidence)} ДИ "
            f"(Бонферрони на {len(rivals)}); выдаётся кандидат с наименьшей MAE, "
            "у которого верхняя граница ДИ разницы MAE < 0, иначе медиана"
        ),
        "confidence": confidence,
        "candidates": candidates,
        "deployed_model": deployed,
        "gain_over_median": deployed != "median",
        "selection": SERVICE_SELECTION,
        "baseline": baseline,
        "deployed": {
            "mae": own["mae"],
            "rmse": own["rmse"],
            "coverage": own["coverage"],
            "median_width": own["median_width"],
        },
        "log_quantile": cv.quantile(deployed, config["coverage"]),
        "quantile_definition": QUANTILE_DEFINITION,
        "coverage": {
            "nominal": config["coverage"],
            **_named(own["coverage"], "empirical"),
            "model": deployed,
            "definition": COVERAGE_DEFINITION,
        },
        "repetitions": cv.repetitions,
        "nested_procedure": {"selection": SERVICE_NESTED, **_track(cv, config)},
    }


def _named(values: dict[str, float], name: str) -> dict[str, float]:
    return {name: values["mean"], f"{name}_sd": values["sd"]}


def _predictions(
    table: pd.DataFrame, cv: RepeatedCV, service: RepeatedCV, groups: np.ndarray, deployed: str
) -> pd.DataFrame:
    frames = []
    base = table[["sample_id", "event_id", "date", "latitude", "longitude"]]
    for repetition in range(cv.repetitions):
        selected = np.empty(len(table), dtype=object)
        for fold in cv.selections[repetition]:
            selected[cv.assignments[repetition] == fold["fold"]] = fold["selected"]
        frames.append(
            base.assign(
                repetition=repetition,
                outer_fold=cv.assignments[repetition],
                survey_day_group=groups,
                concentration=cv.target,
                median_baseline=cv.oof["median"][repetition],
                median_lower=cv.lower["median"][repetition],
                median_upper=cv.upper["median"][repetition],
                nested_selected=selected,
                nested_prediction=cv.nested[repetition],
                nested_lower=cv.nested_lower[repetition],
                nested_upper=cv.nested_upper[repetition],
                service_model=deployed,
                service_prediction=service.oof[deployed][repetition],
                service_lower=service.lower[deployed][repetition],
                service_upper=service.upper[deployed][repetition],
            )
        )
    return pd.concat(frames, ignore_index=True)


def _assignments(
    table: pd.DataFrame, cv: RepeatedCV, groups: np.ndarray, blocks: np.ndarray, report: str
) -> pd.DataFrame:
    base = table[["sample_id", "event_id", "measurement_profile", "date"]]
    return pd.concat(
        [
            base.assign(
                report=report,
                repetition=repetition,
                day_group=groups,
                outer_fold=cv.assignments[repetition],
                spatial_block=blocks,
            )
            for repetition in range(cv.repetitions)
        ],
        ignore_index=True,
    )


def run_profile(
    profile: str, features: pd.DataFrame, config: dict[str, Any]
) -> tuple[dict[str, Any], pd.DataFrame]:
    report = config["report_name"]
    table = features[features["measurement_profile"] == profile].reset_index(drop=True)
    target = table["concentration"].to_numpy(dtype=float)
    groups = survey_day_groups(table).to_numpy()
    options = _options(config, table)
    service_options = _service_options(config, table)
    blocked = blocked_columns()
    used = sorted({c for _, _, columns in [*options, *service_options] for c in columns})
    leakage = check_features(used, blocked)
    cv = repeated_nested_cv(options, table, target, groups, config)
    service_cv = repeated_nested_cv(service_options, table, target, groups, config)
    ranked = cv.rank()
    comparison = {label: _aggregate(cv.option_metrics(label)) for label in ranked}
    best_label = ranked[0]
    _, best_candidate, best_columns = next(o for o in options if o[0] == best_label)
    blocks = spatial_groups(
        table[["x_km", "y_km"]].to_numpy(), config["spatial_clusters"], config["seed"]
    )
    spatial_splits = folds(blocks, config["spatial_clusters"], config["seed"])
    spatial_check = {
        label: metrics(target, out_of_fold(candidate, table[columns], target, spatial_splits))
        for label, candidate, columns in options
        if label in (best_label, "median", "idw_k5")
    }
    season = season_check(options, table, target, groups, config)
    service = _service(service_cv, service_options, config)
    _, service_candidate, service_columns = next(
        option for option in service_options if option[0] == service["deployed_model"]
    )
    folder = MODELS / "concentration" / report / profile
    folder.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        copy.deepcopy(best_candidate).fit(table[best_columns], target), folder / "model.joblib"
    )
    joblib.dump(
        copy.deepcopy(service_candidate).fit(table[service_columns], target),
        folder / "service.joblib",
    )
    reach = config["domain_buffer_km"]
    meta = {
        "profile": profile,
        "target_key": table["target_key"].iloc[0],
        "unit": "items/km2",
        "model": best_label,
        "model_selection": OPTIMISTIC,
        "features": best_columns,
        "events": len(table),
        "service": {
            "model": service["deployed_model"],
            "features": service_columns,
            "log_quantile": service["log_quantile"],
            "coverage": service["coverage"],
            "gain_over_median": service["gain_over_median"],
        },
        "domain": {
            "bbox": domain_bbox(table["latitude"], table["longitude"], reach),
            "max_distance_km": reach,
            "dates": [table["date"].min(), table["date"].max()],
            "season": season_window(table["date"], config["service"]["doy_margin_days"]),
            "reference": {
                "latitude": float(table["latitude"].mean()),
                "longitude": float(table["longitude"].mean()),
            },
        },
    }
    write_json(folder / "meta.json", meta)
    out = REPORTS / "predictions" / "concentration" / report
    out.mkdir(parents=True, exist_ok=True)
    _predictions(table, cv, service_cv, groups, service["deployed_model"]).to_csv(
        out / f"{profile}.csv", index=False
    )
    track = _track(cv, config)
    repetitions, outer = cv.repetitions, config["outer_splits"]
    role = research_role(config)
    result = {
        "profile": profile,
        "target_key": table["target_key"].iloc[0],
        "events": len(table),
        "survey_days": len(np.unique(groups)),
        "research": role,
        "validation": {
            "outer": (
                f"{repetitions} повторов случайного разбиения дней съёмки на {outer} фолдов, "
                f"seed [{config['seed']}, повтор]"
            ),
            "inner": (
                f"случайное разбиение дней съёмки обучающей части на {config['inner_splits']} "
                f"фолдов, seed [{config['seed']}, повтор, фолд]"
            ),
            "difference": (
                f"кластерный бутстрэп по дням съёмки, {config.get('bootstrap', 2000)} выборок, "
                "95 % ДИ разницы вложенная CV − медиана"
            ),
            "service_gate": service["rule"],
            "spatial_check": f"KMeans по координатам, {config['spatial_clusters']} блоков",
            "repetitions": repetitions,
        },
        "nested": {**track["nested"], "selection": role["selection"]},
        "baseline": track["baseline"],
        "difference_vs_median": track["difference_vs_median"],
        "gain_over_median": track["gain_over_median"],
        "selected_in_folds": track["selected_in_folds"],
        "service": service,
        "season_check": season,
        "best_config": {
            "selection": OPTIMISTIC,
            "label": best_label,
            "features": best_columns,
            **comparison[best_label],
        },
        "baselines": {name: comparison[name] for name in BASELINES},
        "spatial_blocks": spatial_check,
        "top_configs": {
            "selection": OPTIMISTIC,
            "configs": {label: comparison[label] for label in ranked[:10]},
        },
        "ablation": ablation(comparison, config),
        "leakage_check": leakage,
        "repetitions": track["repetitions"],
    }
    return result, _assignments(table, cv, groups, blocks, report)


def ablation(comparison: dict[str, dict], config: dict[str, Any]) -> dict[str, Any]:
    table = {}
    for set_name in config["feature_sets"]:
        rows = {
            label.split("|")[0]: result["mae"]["mean"]
            for label, result in comparison.items()
            if label.endswith(f"|{set_name}")
        }
        if rows:
            best = min(rows, key=rows.get)
            table[set_name] = {"best_model": best, "mae": rows[best]}
    return {"selection": OPTIMISTIC, "feature_sets": table}


TRANSFER_COLUMNS = [
    "doy_sin",
    "doy_cos",
    "coast_km",
    "river_weighted_log",
    "wind_now",
    "wind_72h",
    "wave_now",
]


def run_transfer(features: pd.DataFrame, config: dict[str, Any]) -> list[dict[str, Any]]:
    results = []
    columns = TRANSFER_COLUMNS
    leakage = check_features(columns, blocked_columns())
    for source, target_profile in config["transfer"]["pairs"]:
        train = features[features["measurement_profile"] == source]
        test = features[features["measurement_profile"] == target_profile]
        truth = test["concentration"].to_numpy(dtype=float)
        entry = {"train": source, "test": target_profile, "features": columns}
        for candidate in candidate_zoo(config["seed"]):
            if candidate.kind not in ("median", "random_forest", "catboost", "ridge"):
                continue
            model = copy.deepcopy(candidate).fit(
                train[columns], train["concentration"].to_numpy(dtype=float)
            )
            entry[candidate.name] = metrics(truth, model.predict(test[columns]))
        entry["target_median_as_reference"] = metrics(truth, np.full(len(truth), np.median(truth)))
        entry["leakage_check"] = {"checked": leakage["checked"], "passed": True}
        results.append(entry)
    return results


def _headline(result: dict[str, Any]) -> dict[str, Any]:
    service = result["service"]
    season = result["season_check"]
    return {
        "events": result["events"],
        "survey_days": result["survey_days"],
        "research": result["research"],
        "nested": {
            "mae": result["nested"]["mae"],
            "rmse": result["nested"]["rmse"],
            "coverage": result["nested"]["coverage"],
        },
        "baseline": {
            "mae": result["baseline"]["mae"],
            "rmse": result["baseline"]["rmse"],
            "coverage": result["baseline"]["coverage"],
        },
        "difference_vs_median": result["difference_vs_median"],
        "gain_over_median": result["gain_over_median"],
        "service": {
            "deployed_model": service["deployed_model"],
            "gain_over_median": service["gain_over_median"],
            "confidence": service["confidence"],
            "candidates": {
                label: {
                    "mae": row["mae"],
                    "rmse": row["rmse"],
                    "difference_mae": row["difference_vs_median"]["mae"],
                    "passes": row["passes"],
                }
                for label, row in service["candidates"].items()
            },
            "deployed": service["deployed"],
            "coverage": service["coverage"],
            "nested_procedure": {
                "selection": SERVICE_NESTED,
                "mae": service["nested_procedure"]["nested"]["mae"],
                "difference_mae": service["nested_procedure"]["difference_vs_median"]["mae"],
            },
        },
        "season_check": {
            "with_season": season["with_season"],
            "without_season": season["without_season"],
            "median_mae": season["median"]["mae"],
            "season_holds_up": season["season_holds_up"],
        },
        "best_config": {
            "selection": OPTIMISTIC,
            "label": result["best_config"]["label"],
            "mae": result["best_config"]["mae"],
            "rmse": result["best_config"]["rmse"],
        },
    }


def _write_splits(frames: list[pd.DataFrame], report: str) -> None:
    frame = pd.concat(frames, ignore_index=True)
    if SPLITS_FILE.exists():
        previous = pd.read_csv(SPLITS_FILE)
        if "report" in previous and "repetition" in previous:
            frame = pd.concat([previous[previous["report"] != report], frame], ignore_index=True)
    SPLITS_FILE.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(SPLITS_FILE, index=False)


def run_experiment(config: dict[str, Any], refresh: bool = False) -> dict[str, Any]:
    features = load_features(config, refresh)
    report = config["report_name"]
    summary = {
        "config_file": config.get("_path"),
        "config_sha256": config.get("_sha256"),
        "report": report,
        "research": research_role(config),
        "repetitions": config.get("repetitions", 10),
        "profiles": {},
        "leakage_guard": sorted(
            set(features.columns)
            & {"items_count", "density_numerator_items", "sampled_area_km2", "wind_speed_kn"}
        ),
    }
    splits = []
    for profile in config["profiles"]:
        result, assignment = run_profile(profile, features, config)
        write_json(REPORTS / "metrics" / "concentration" / report / f"{profile}.json", result)
        summary["profiles"][profile] = _headline(result)
        splits.append(assignment)
    _write_splits(splits, report)
    summary["transfer"] = run_transfer(features, config)
    write_json(REPORTS / "metrics" / "concentration" / report / "summary.json", summary)
    return summary
