from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from joblib import Parallel, delayed

from littora_ml.common.io import write_json
from littora_ml.common.paths import REPORTS, resolve
from littora_ml.concentration.dataset import modeling_table
from littora_ml.concentration.external_sources import (
    BURGAS_FILE,
    BURGAS_KEY,
    EMBLAS_FILE,
    PROFILE,
    burgas_items,
    campaign_labels,
    model_rows,
    prepare_sources,
)
from littora_ml.concentration.features import (
    FEATURE_GROUPS,
    coast_distance,
    local_xy,
    river_inputs,
    seasonal,
    weather,
)
from littora_ml.concentration.guard import LeakageError, blocked_columns, check_features
from littora_ml.concentration.models import Candidate, candidate_zoo, to_log
from littora_ml.concentration.validation import folds, metrics, paired_difference

SOURCE_COLUMN = "source_doors"
SPATIAL = FEATURE_GROUPS["spatial"]
WEATHER = set(FEATURE_GROUPS["weather"])
CACHE_KEY = ["sample_id", "date", "latitude", "longitude", "concentration"]
BURGAS, DOORS, EMBLAS = "burgas", "doors", "emblas"
SITE = "site_climatology"
NESTED = "nested"
OPTIMISTIC = "справочно: выбор лучшего варианта по этим числам был бы выбором на тесте"


@dataclass(frozen=True)
class Spec:
    label: str
    candidate: Candidate
    columns: list[str]
    pooled: bool = False

    @property
    def baseline(self) -> bool:
        return "|" not in self.label

    @property
    def weather(self) -> bool:
        return bool(WEATHER & set(self.columns))


@dataclass
class Fold:
    name: str
    train: np.ndarray
    test: np.ndarray


@dataclass
class Design:
    name: str
    title: str
    frame: pd.DataFrame
    specs: list[Spec]
    folds: list[Fold]
    inner_groups: np.ndarray
    reference: np.ndarray
    boot_groups: np.ndarray
    notes: list[str] = field(default_factory=list)


@dataclass
class Outcome:
    design: Design
    rows: np.ndarray
    predictions: dict[str, np.ndarray]
    nested: np.ndarray
    selections: list[dict[str, Any]]
    scores: list[dict[str, float]]
    pools: dict[str, np.ndarray] = field(default_factory=dict)


def external_table() -> tuple[pd.DataFrame, dict[str, Any]]:
    paths = prepare_sources()
    if "burgas" not in paths:
        raise FileNotFoundError(
            f"нет {BURGAS_FILE}: python scripts/data/fetch.py download {BURGAS_KEY}"
        )
    burgas, burgas_check = model_rows(paths["burgas"])
    burgas["source"] = BURGAS
    burgas["campaign"] = campaign_labels(burgas["date"])
    burgas["transect"] = burgas["event_id"].str.rsplit(":", n=1).str[-1]
    burgas["group"] = BURGAS + ":" + burgas["campaign"]
    doors = modeling_table()
    doors = doors[doors["measurement_profile"] == PROFILE].copy()
    doors["source"] = DOORS
    doors["campaign"] = DOORS + ":" + doors["date"]
    doors["transect"] = doors["event_id"]
    doors["group"] = doors["campaign"]
    parts = [burgas, doors]
    checks = {"burgas": burgas_check}
    if "emblas" in paths:
        emblas, emblas_check = model_rows(paths["emblas"])
        emblas["source"] = EMBLAS
        emblas["campaign"] = EMBLAS + ":" + emblas["date"]
        emblas["transect"] = emblas["event_id"]
        emblas["group"] = emblas["campaign"]
        parts.append(emblas)
        checks["emblas"] = emblas_check
    table = pd.concat(parts, ignore_index=True)
    return table, checks


def build_features(table: pd.DataFrame) -> pd.DataFrame:
    parts = [
        table,
        local_xy(table),
        seasonal(table),
        coast_distance(table).to_frame(),
        river_inputs(table),
        weather(table),
    ]
    features = pd.concat(parts, axis=1)
    features[SOURCE_COLUMN] = (features["source"] != BURGAS).astype(float)
    return features


def load_features(table: pd.DataFrame, path, refresh: bool = False) -> pd.DataFrame:
    if path.exists() and not refresh:
        cached = pd.read_parquet(path)
        same = len(cached) == len(table) and all(
            cached[column].astype(str).tolist() == table[column].astype(str).tolist()
            for column in CACHE_KEY
        )
        if same:
            return cached
    features = build_features(table)
    path.parent.mkdir(parents=True, exist_ok=True)
    features.to_parquet(path, index=False)
    return features


def _columns(groups: list[str]) -> list[str]:
    return [column for group in groups for column in FEATURE_GROUPS[group]]


def usable(columns: list[str], frame: pd.DataFrame) -> list[str]:
    return [c for c in columns if frame[c].notna().all() and frame[c].nunique() > 1]


def zoo(config: dict[str, Any]) -> dict[str, Candidate]:
    candidates = {c.name: c for c in candidate_zoo(config["seed"], threads=1)}
    candidates[SITE] = Candidate(
        SITE, "site_mean", {"radius_km": config["site_radius_km"]}, seed=config["seed"]
    )
    return candidates


def make_specs(
    config: dict[str, Any],
    frame: pd.DataFrame,
    set_names: list[str],
    pooled: bool = False,
    site: bool = True,
) -> list[Spec]:
    candidates = zoo(config)
    specs = [
        Spec(name, candidates[name], list(SPATIAL))
        for name in config["baselines"]
        if site or name != SITE
    ]
    for name in config["models"]:
        for set_name in set_names:
            columns = usable(_columns(config["feature_sets"][set_name]), frame)
            if not columns:
                continue
            if pooled:
                columns = [*columns, SOURCE_COLUMN]
            specs.append(Spec(f"{name}|{set_name}", candidates[name], columns, pooled))
    return specs


def guard(specs: list[Spec], blocked: set[str] | None = None) -> dict[str, Any]:
    used = sorted({c for spec in specs for c in spec.columns if c != SOURCE_COLUMN})
    report = check_features(used, blocked)
    pooled = any(SOURCE_COLUMN in spec.columns for spec in specs)
    report["design_columns"] = (
        {
            SOURCE_COLUMN: (
                "индикатор метода съёмки (фиксированный эффект источника): 0 — Бургас, полоса 6 м, "
                "лодка; 1 — судовые трансекты DOORS; известен до измерения, не зависит от "
                "концентрации"
            )
        }
        if pooled
        else {}
    )
    return report


def check_design(design: Design) -> None:
    sources = design.frame["source"].to_numpy()
    groups = design.frame["group"].to_numpy()
    for fold in design.folds:
        if (sources[fold.train] == EMBLAS).any():
            raise LeakageError("EMBLAS 2016 — только внешний тест, в обучение не допускается")
        shared = set(groups[fold.train]) & set(groups[fold.test])
        if shared:
            raise LeakageError(f"{design.name}: группы в обучении и тесте: {sorted(shared)}")
        if set(fold.train) & set(fold.test):
            raise LeakageError(f"{design.name}: строки в обучении и тесте")


def _inner_mae(
    spec: Spec,
    frame: pd.DataFrame,
    target: np.ndarray,
    train: np.ndarray,
    inner: list[tuple[np.ndarray, np.ndarray]],
    reference: np.ndarray,
) -> float:
    errors = []
    for fit_index, held_index in inner:
        fit_rows, held_rows = train[fit_index], train[held_index]
        if not spec.pooled:
            fit_rows = fit_rows[reference[fit_rows]]
        held_rows = held_rows[reference[held_rows]]
        if not len(fit_rows) or not len(held_rows):
            continue
        fit = frame.iloc[fit_rows][spec.columns]
        model = copy.deepcopy(spec.candidate).fit(fit, target[fit_rows])
        prediction = model.predict(frame.iloc[held_rows][spec.columns])
        errors.append(np.abs(prediction - target[held_rows]))
    return float(np.mean(np.concatenate(errors))) if errors else float("inf")


def _task(
    spec: Spec,
    frame: pd.DataFrame,
    target: np.ndarray,
    fold: Fold,
    inner: list[tuple[np.ndarray, np.ndarray]],
    reference: np.ndarray,
) -> tuple[float, np.ndarray]:
    score = _inner_mae(spec, frame, target, fold.train, inner, reference)
    rows = fold.train if spec.pooled else fold.train[reference[fold.train]]
    model = copy.deepcopy(spec.candidate).fit(frame.iloc[rows][spec.columns], target[rows])
    return score, model.predict(frame.iloc[fold.test][spec.columns])


def run_design(design: Design, config: dict[str, Any]) -> Outcome:
    check_design(design)
    frame = design.frame
    target = frame["concentration"].to_numpy(dtype=float)
    inners = [
        folds(design.inner_groups[fold.train], config["inner_splits"], [config["seed"], index])
        for index, fold in enumerate(design.folds)
    ]
    for fold, inner in zip(design.folds, inners, strict=True):
        for fit_index, held_index in inner:
            fit_groups = set(design.inner_groups[fold.train[fit_index]])
            if fit_groups & set(design.inner_groups[fold.train[held_index]]):
                raise LeakageError(f"{design.name}: внутренние фолды делят группу")
    tasks = [(index, spec) for index in range(len(design.folds)) for spec in design.specs]
    results = Parallel(n_jobs=config.get("jobs", 4))(
        delayed(_task)(spec, frame, target, design.folds[index], inners[index], design.reference)
        for index, spec in tasks
    )
    labels = [spec.label for spec in design.specs]
    predictions = {label: np.full(len(frame), np.nan) for label in labels}
    nested = np.full(len(frame), np.nan)
    scores: list[dict[str, float]] = [{} for _ in design.folds]
    for (index, spec), (score, prediction) in zip(tasks, results, strict=True):
        predictions[spec.label][design.folds[index].test] = prediction
        scores[index][spec.label] = score
    selections = []
    for index, fold in enumerate(design.folds):
        best = min(labels, key=lambda label: scores[index][label])
        nested[fold.test] = predictions[best][fold.test]
        selections.append(
            {
                "fold": fold.name,
                "selected": best,
                "inner_mae": scores[index][best],
                "train_rows": len(fold.train),
                "test_rows": len(fold.test),
            }
        )
    rows = np.concatenate([fold.test for fold in design.folds])
    return Outcome(design, np.sort(rows), predictions, nested, selections, scores)


def pool_prediction(outcome: Outcome, keep) -> tuple[np.ndarray, list[str]]:
    prediction = np.full(len(outcome.design.frame), np.nan)
    chosen = []
    for index, fold in enumerate(outcome.design.folds):
        pool = [spec.label for spec in outcome.design.specs if keep(spec)]
        best = min(pool, key=lambda label: outcome.scores[index][label])
        prediction[fold.test] = outcome.predictions[best][fold.test]
        chosen.append(best)
    return prediction, chosen


def level(truth: np.ndarray, prediction: np.ndarray) -> dict[str, float]:
    return {
        "geometric_ratio": float(np.exp(np.mean(to_log(prediction) - to_log(truth)))),
        "median_ratio": float(np.median(prediction) / max(np.median(truth), 1e-9)),
        "mean_ratio": float(np.mean(prediction) / max(np.mean(truth), 1e-9)),
    }


def bootstrap(
    truth: np.ndarray, prediction: np.ndarray, groups: np.ndarray, draws: int, seed: int
) -> dict[str, list[float] | None]:
    unique, index = np.unique(groups, return_inverse=True)
    members = [np.flatnonzero(index == k) for k in range(len(unique))]
    rng = np.random.default_rng(seed)
    values: dict[str, list[float]] = {
        name: [] for name in ("mae", "rmse", "mae_log1p", "bias", "spearman")
    }
    for _ in range(draws):
        rows = np.concatenate([members[k] for k in rng.integers(0, len(unique), len(unique))])
        result = metrics(truth[rows], prediction[rows])
        for name in values:
            if result[name] is not None:
                values[name].append(result[name])
    return {
        name: [float(v) for v in np.percentile(series, [2.5, 97.5])] if series else None
        for name, series in values.items()
    }


def within_folds(truth: np.ndarray, prediction: np.ndarray, blocks: np.ndarray) -> dict[str, Any]:
    values = []
    for block in np.unique(blocks):
        inside = blocks == block
        if inside.sum() >= 3 and np.ptp(truth[inside]) > 0 and np.ptp(prediction[inside]) > 0:
            values.append(metrics(truth[inside], prediction[inside])["spearman"])
    return {
        "mean": float(np.mean(values)) if values else None,
        "folds_defined": len(values),
        "folds": len(np.unique(blocks)),
    }


def scored(
    truth: np.ndarray,
    prediction: np.ndarray,
    groups: np.ndarray,
    blocks: np.ndarray,
    config: dict[str, Any],
) -> dict[str, Any]:
    return {
        **metrics(truth, prediction),
        "spearman_within_folds": within_folds(truth, prediction, blocks),
        "level": level(truth, prediction),
        "ci95": bootstrap(truth, prediction, groups, config["bootstrap"], config["seed"]),
    }


def _difference(
    truth: np.ndarray, model: np.ndarray, base: np.ndarray, groups: np.ndarray, config
) -> dict[str, Any]:
    result = paired_difference(
        truth, model[None, :], base[None, :], groups, config["bootstrap"], config["seed"]
    )
    mae = result["mae"]
    return {"mae": mae, "rmse": result["rmse"], "model_better": bool(mae["ci"][1] < 0)}


def evaluate(outcome: Outcome, config: dict[str, Any]) -> dict[str, Any]:
    design = outcome.design
    rows = outcome.rows
    truth = design.frame["concentration"].to_numpy(dtype=float)[rows]
    groups = design.boot_groups[rows]
    fold_of = np.full(len(design.frame), -1)
    for index, fold in enumerate(design.folds):
        fold_of[fold.test] = index
    blocks = fold_of[rows]
    baselines = [spec.label for spec in design.specs if spec.baseline]
    result: dict[str, Any] = {
        "design": design.name,
        "title": design.title,
        "test_rows": len(rows),
        "test_groups": len(np.unique(groups)),
        "folds": len(design.folds),
        "notes": design.notes,
        "spearman_note": (
            "spearman — по всем тестовым строкам сразу, смешивает фолды: у предсказания, "
            "постоянного внутри фолда (медиана), он отражает смену обучающей выборки, а не "
            "ранжирование; spearman_within_folds — среднее по фолдам (внутри отложенной кампании "
            "или трансекты)"
        ),
        "baselines": {
            label: scored(truth, outcome.predictions[label][rows], groups, blocks, config)
            for label in baselines
        },
        NESTED: {
            **scored(truth, outcome.nested[rows], groups, blocks, config),
            "selection": (
                "вариант (модель|набор признаков или базовая линия) выбран по MAE внутренней CV "
                "на обучающей части, группы внутренней CV не пересекаются с тестом"
            ),
            "selected": [row["selected"] for row in outcome.selections],
        },
        "folds_detail": outcome.selections,
    }
    result["difference"] = {
        f"{NESTED}_minus_{label}": _difference(
            truth, outcome.nested[rows], outcome.predictions[label][rows], groups, config
        )
        for label in baselines
    }
    pools = {"models_only": lambda spec: not spec.baseline}
    if any(spec.weather for spec in design.specs):
        pools["with_weather"] = lambda spec: spec.weather
        pools["without_weather"] = lambda spec: not spec.weather
    predicted = {}
    result["pools"] = {
        "selection": (
            "вложенный выбор по внутренней CV внутри подмножества вариантов: models_only — только "
            "модели зоопарка без базовых линий; with_weather / without_weather — с погодными "
            "признаками и без них (без погоды входят и базовые линии)"
        )
    }
    for name, keep in pools.items():
        predicted[name], chosen = pool_prediction(outcome, keep)
        result["pools"][name] = {
            **scored(truth, predicted[name][rows], groups, blocks, config),
            "selected": chosen,
        }
    result["pools"]["differences"] = {
        f"models_only_minus_{label}": _difference(
            truth, predicted["models_only"][rows], outcome.predictions[label][rows], groups, config
        )
        for label in baselines
    }
    if "with_weather" in predicted:
        result["pools"]["differences"]["with_weather_minus_without_weather"] = _difference(
            truth,
            predicted["with_weather"][rows],
            predicted["without_weather"][rows],
            groups,
            config,
        )
    outcome.pools = predicted
    result["options"] = {
        "selection": OPTIMISTIC,
        "metrics": {
            label: metrics(truth, prediction[rows])
            for label, prediction in outcome.predictions.items()
        },
    }
    return result


def _fold(name: str, train_mask: np.ndarray, test_mask: np.ndarray) -> Fold:
    return Fold(name, np.flatnonzero(train_mask), np.flatnonzero(test_mask))


def _burgas_only(features: pd.DataFrame) -> pd.DataFrame:
    return features[features["source"] == BURGAS].reset_index(drop=True)


def v1_designs(features: pd.DataFrame, config: dict[str, Any]) -> list[Design]:
    sets = list(config["feature_sets"])
    burgas = _burgas_only(features)
    campaigns = burgas["campaign"].to_numpy()
    only = Design(
        name="v1_burgas",
        title="V1: отложена одна кампания Бургаса (обучение — остальные кампании Бургаса)",
        frame=burgas,
        specs=make_specs(config, burgas, sets),
        folds=[_fold(c, campaigns != c, campaigns == c) for c in sorted(np.unique(campaigns))],
        inner_groups=burgas["group"].to_numpy(),
        reference=np.ones(len(burgas), dtype=bool),
        boot_groups=campaigns,
    )
    pooled = features[features["source"].isin([BURGAS, DOORS])].reset_index(drop=True)
    is_burgas = (pooled["source"] == BURGAS).to_numpy()
    campaign = pooled["campaign"].to_numpy()
    with_doors = Design(
        name="v1_burgas_plus_doors",
        title=(
            "V1 + DOORS: отложена одна кампания Бургаса; DOORS всегда в обучении, "
            "фиксированный эффект источника"
        ),
        frame=pooled,
        specs=make_specs(config, pooled[is_burgas], sets, pooled=True),
        folds=[
            _fold(c, ~(is_burgas & (campaign == c)), is_burgas & (campaign == c))
            for c in sorted(np.unique(campaign[is_burgas]))
        ],
        inner_groups=pooled["group"].to_numpy(),
        reference=is_burgas,
        boot_groups=campaign,
        notes=[
            "базовые линии (медиана, климатология трансекты, idw_k5) обучаются только на "
            "кампаниях Бургаса: уровни 6-метровой полосы и судовых трансект не смешиваются",
            "модели зоопарка обучаются на Бургасе и DOORS с индикатором источника source_doors; "
            "внутренняя CV сгруппирована по кампаниям Бургаса и дням DOORS, MAE считается "
            "только по Бургасу",
        ],
    )
    return [only, with_doors]


def v2_design(features: pd.DataFrame, config: dict[str, Any]) -> Design:
    burgas = _burgas_only(features)
    early = (burgas["date"] < config["forward_split"]).to_numpy()
    campaigns = burgas["campaign"].to_numpy()
    return Design(
        name="v2_forward",
        title=(
            f"V2: вперёд во времени, обучение до {config['forward_split']}, "
            "проверка на кампаниях 2023"
        ),
        frame=burgas,
        specs=make_specs(config, burgas[early], list(config["feature_sets"])),
        folds=[_fold("2023", early, ~early)],
        inner_groups=burgas["group"].to_numpy(),
        reference=np.ones(len(burgas), dtype=bool),
        boot_groups=campaigns,
        notes=[
            "DOORS (июнь 2024) в обучение не берём: это данные из будущего относительно теста",
            f"в тесте {len(np.unique(campaigns[~early]))} кампании: ДИ по бутстрэпу кампаний "
            "широкие",
        ],
    )


def v3_designs(features: pd.DataFrame, config: dict[str, Any]) -> list[Design]:
    sets = config["transfer"]["feature_sets"]
    designs = []
    pair = features[features["source"].isin([BURGAS, DOORS])].reset_index(drop=True)
    source = pair["source"].to_numpy()
    for train_source, test_source in ((DOORS, BURGAS), (BURGAS, DOORS)):
        train_mask = source == train_source
        designs.append(
            Design(
                name=f"v3_{train_source}_to_{test_source}",
                title=f"V3: перенос {train_source} → {test_source}",
                frame=pair,
                specs=make_specs(config, pair[train_mask], sets, site=False),
                folds=[_fold(f"{train_source}->{test_source}", train_mask, ~train_mask)],
                inner_groups=pair["group"].to_numpy(),
                reference=train_mask,
                boot_groups=pair["group"].to_numpy(),
                notes=[
                    "уровень плотности зависит от метода (ширина полосы, наблюдатель, судно); "
                    "перенос уровня между источниками ожидаемо не работает — смотрим Spearman",
                    "группы бутстрэпа: кампании Бургаса или дни DOORS в тестовом источнике",
                ],
            )
        )
    if (features["source"] == EMBLAS).any():
        frame = features.copy().reset_index(drop=True)
        source = frame["source"].to_numpy()
        train_mask = np.isin(source, [BURGAS, DOORS])
        test_mask = source == EMBLAS
        frame.loc[test_mask, SOURCE_COLUMN] = 1.0
        groups = frame["group"].to_numpy().copy()
        groups[test_mask] = frame.loc[test_mask, "transect"].to_numpy()
        designs.append(
            Design(
                name="v3_both_to_emblas",
                title="V3: Бургас + DOORS → EMBLAS 2016, российские воды (только внешний тест)",
                frame=frame,
                specs=make_specs(config, frame[train_mask], sets, pooled=True, site=False),
                folds=[_fold("burgas+doors->emblas", train_mask, test_mask)],
                inner_groups=groups,
                reference=source == DOORS,
                boot_groups=groups,
                notes=[
                    "EMBLAS 2016 восстановлен по таблицам отчёта, привязка станций выведена; "
                    "в обучение не входит",
                    "прогноз на уровне DOORS (source_doors = 1): судовые трансекты ближе к "
                    "методу EMBLAS, но полоса EMBLAS 50 м (JOSS) и 20 м (NPMS) — уровень не "
                    "переносится, смотрим Spearman",
                    "базовые линии обучены на DOORS; выбор варианта — по внутренней CV на DOORS "
                    "(дни съёмки), модели обучены на обоих источниках с индикатором",
                    "бутстрэп по 12 трансектам EMBLAS: кампаний две, дней съёмки три; соседние "
                    "трансекты одного дня считаются независимыми, поэтому ДИ оптимистичен",
                    "EMBLAS вне правила смены сервисной модели; выигрыш по MAE без Spearman > 0 "
                    "означает сдвиг уровня, а не перенос ранжирования",
                ],
            )
        )
    return designs


def v4_design(features: pd.DataFrame, config: dict[str, Any]) -> Design:
    burgas = _burgas_only(features)
    transects = burgas["transect"].to_numpy()
    return Design(
        name="v4_leave_transect_out",
        title="V4: отложена одна трансекта Бургаса (все кампании)",
        frame=burgas.assign(group=BURGAS + ":" + burgas["transect"]),
        specs=make_specs(config, burgas, list(config["feature_sets"]), site=False),
        folds=[_fold(t, transects != t, transects == t) for t in sorted(np.unique(transects))],
        inner_groups=transects,
        reference=np.ones(len(burgas), dtype=bool),
        boot_groups=burgas["campaign"].to_numpy(),
        notes=[
            "климатология трансекты не определена для отложенной трансекты — не участвует",
            "кампании общие у обучения и теста: погода того же дня видна модели по соседним "
            "трансектам, это проверка пространственной части, а не прогноз на новую дату",
            "бутстрэп по кампаниям",
        ],
    )


def gate(results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    def beats(name: str, baseline: str) -> bool | None:
        entry = results.get(name, {}).get("difference", {}).get(f"{NESTED}_minus_{baseline}")
        return None if entry is None else entry["model_better"]

    def point(name: str, baseline: str) -> bool | None:
        entry = results.get(name)
        if entry is None or baseline not in entry["baselines"]:
            return None
        return entry[NESTED]["mae"] < entry["baselines"][baseline]["mae"]

    def transfer(name: str) -> bool | None:
        entry = results.get(name)
        if entry is None:
            return None
        pool = entry["pools"]["models_only"]
        better = entry["pools"]["differences"]["models_only_minus_median"]["model_better"]
        rho = pool["ci95"]["spearman"]
        return bool(better and rho is not None and rho[0] > 0)

    v1 = {
        name: {"vs_median": beats(name, "median"), "vs_site_climatology": beats(name, SITE)}
        for name in ("v1_burgas", "v1_burgas_plus_doors")
    }
    v2 = {
        "vs_median": point("v2_forward", "median"),
        "vs_site_climatology": point("v2_forward", SITE),
    }
    v3 = {name: transfer(name) for name in ("v3_doors_to_burgas", "v3_burgas_to_doors")}
    v1_gain = any(all(row.values()) for row in v1.values())
    v2_gain = all(v2.values())
    v3_gain = all(v3.values())
    gain = bool(v1_gain and v2_gain and v3_gain)
    return {
        "rule": (
            "сервисная модель S4 меняется только при явном выигрыше: V1 (любой вариант) — "
            "вложенная модель лучше медианы и климатологии трансекты, верхняя граница 95 % ДИ "
            "разницы MAE по кампаниям < 0; V2 — MAE вложенной модели ниже медианы и "
            "климатологии; V3 (DOORS → Бургас и Бургас → DOORS) — вложенный выбор среди моделей "
            "(models_only) лучше медианы обучающего источника по MAE (95 % ДИ) и нижняя граница "
            "ДИ Spearman > 0"
        ),
        "v1": v1,
        "v2": v2,
        "v3": v3,
        "clear_gain": gain,
        "service_model_changed": False,
        "decision": (
            "явный выигрыш есть — нужен отдельный экспорт"
            if gain
            else "явного выигрыша нет: сервисная модель S4 (медиана DOORS) не меняется"
        ),
    }


def _source_summary(table: pd.DataFrame, checks: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for source, group in table.groupby("source"):
        values = group["concentration"].to_numpy(dtype=float)
        summary[source] = {
            "rows": len(group),
            "groups": int(group["group"].nunique()),
            "dates": [group["date"].min(), group["date"].max()],
            "zeros": int((values == 0).sum()),
            "median": float(np.median(values)),
            "mean": float(np.mean(values)),
            "max": float(np.max(values)),
            "case_selection": checks.get(source),
        }
    burgas = table[table["source"] == BURGAS]
    items = burgas_items()
    areas = items["area_km2_by_campaign"]
    nominal = sum(value == "0.0135" for value in areas.values())
    doubled = ", ".join(key for key, value in areas.items() if value == "0.027")
    summary[BURGAS]["campaigns"] = burgas.groupby("campaign").size().to_dict()
    summary[BURGAS]["transects"] = sorted(burgas["transect"].unique())
    summary[BURGAS]["items_reconstructed"] = {
        **items,
        "concentration_check": checks[BURGAS]["concentration_check"],
        "paper_total_objects": 502,
        "note": (
            f"в статье (Bobchev et al. 2024) описано 502 предмета. В {nominal} кампаниях "
            "плотности кратны 74,07 = 1/0,0135 км², в кампаниях "
            f"{doubled} — 37,04 = 1/0,027 км²: там площадь учёта вдвое больше номинальной "
            "(как делились длина и ширина — неизвестно). С этой площадью строк без целого "
            f"числа предметов {items['rows_without_items']}, сумма {items['sum_items']} "
            "предметов (в статье 502); в модели используется опубликованная плотность"
        ),
    }
    summary["emblas_file"] = EMBLAS_FILE.exists()
    return summary


def _predictions(outcome: Outcome) -> pd.DataFrame:
    frame = outcome.design.frame
    rows = outcome.rows
    base = frame.iloc[rows][
        ["sample_id", "source", "campaign", "transect", "date", "latitude", "longitude"]
    ].copy()
    base["concentration"] = frame["concentration"].to_numpy(dtype=float)[rows]
    fold_of = np.empty(len(frame), dtype=object)
    selected_of = np.empty(len(frame), dtype=object)
    for fold, row in zip(outcome.design.folds, outcome.selections, strict=True):
        fold_of[fold.test] = fold.name
        selected_of[fold.test] = row["selected"]
    base["fold"] = fold_of[rows]
    for spec in outcome.design.specs:
        if spec.baseline:
            base[spec.label] = outcome.predictions[spec.label][rows]
    base["nested"] = outcome.nested[rows]
    base["nested_selected"] = selected_of[rows]
    return base.assign(design=outcome.design.name)


def _headline(result: dict[str, Any]) -> dict[str, Any]:
    def row(entry: dict[str, Any]) -> dict[str, Any]:
        return {
            "mae": entry["mae"],
            "mae_ci": entry["ci95"]["mae"],
            "rmse": entry["rmse"],
            "mae_log1p": entry["mae_log1p"],
            "spearman": entry["spearman"],
            "spearman_ci": entry["ci95"]["spearman"],
            "spearman_within_folds": entry["spearman_within_folds"]["mean"],
            "bias": entry["bias"],
            "geometric_ratio": entry["level"]["geometric_ratio"],
        }

    return {
        "test_rows": result["test_rows"],
        "test_groups": result["test_groups"],
        NESTED: row(result[NESTED]),
        **{label: row(entry) for label, entry in result["baselines"].items()},
        **{
            label: row(entry)
            for label, entry in result["pools"].items()
            if label not in ("selection", "differences")
        },
        "difference_mae": {
            key: {"mean": value["mae"]["mean"], "ci": value["mae"]["ci"]}
            for key, value in {**result["difference"], **result["pools"]["differences"]}.items()
        },
        "selected": result[NESTED]["selected"],
    }


def run_external(config: dict[str, Any], refresh: bool = False) -> dict[str, Any]:
    table, checks = external_table()
    features = load_features(table, resolve(config["features_cache"]), refresh)
    blocked = blocked_columns()
    designs = [
        *v1_designs(features, config),
        v2_design(features, config),
        *v3_designs(features, config),
        v4_design(features, config),
    ]
    out = REPORTS / "metrics" / "concentration" / config["report_name"]
    predictions_dir = REPORTS / "predictions" / "concentration" / config["report_name"]
    predictions_dir.mkdir(parents=True, exist_ok=True)
    results, outcomes = {}, {}
    for design in designs:
        leakage = guard(design.specs, blocked)
        outcome = run_design(design, config)
        result = evaluate(outcome, config)
        result["leakage_check"] = leakage
        result["options_count"] = len(design.specs)
        results[design.name], outcomes[design.name] = result, outcome
        _predictions(outcome).to_csv(predictions_dir / f"{design.name}.csv", index=False)
    files = {
        "v1_leave_campaign_out.json": ["v1_burgas", "v1_burgas_plus_doors"],
        "v2_forward.json": ["v2_forward"],
        "v3_cross_source.json": [n for n in results if n.startswith("v3_")],
        "v4_leave_transect_out.json": ["v4_leave_transect_out"],
    }
    for name, keys in files.items():
        write_json(out / name, {key: results[key] for key in keys})
    sources = _source_summary(table, checks)
    write_json(out / "sources.json", sources)
    decision = gate(results)
    summary = {
        "config_file": config.get("_path"),
        "config_sha256": config.get("_sha256"),
        "profile": PROFILE,
        "sources": {
            key: {k: v for k, v in value.items() if k in ("rows", "groups", "dates", "median")}
            for key, value in sources.items()
            if isinstance(value, dict)
        },
        "grouping": {
            BURGAS: "кампания: дни съёмки с разрывом не больше 7 суток (8 трансект за 2 дня)",
            DOORS: "день съёмки",
            EMBLAS: "только тест; бутстрэп по трансектам",
        },
        "designs": {name: _headline(result) for name, result in results.items()},
        "service": decision,
    }
    write_json(out / "summary.json", summary)
    return {"summary": summary, "results": results, "outcomes": outcomes}
