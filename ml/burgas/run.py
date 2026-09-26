"""Additive Burgas registry and fixed field-transfer experiments."""

import base64
import concurrent.futures
import hashlib
import io
import json
import sys
from pathlib import Path

import joblib
import markdown
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import nbformat
import numpy as np
import pandas as pd
import requests
from shapely.geometry import Point, shape
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data/external/burgas-floating-litter"
DATA = ROOT / "data/processed/burgas"
OUT = ROOT / "reports/burgas"
T = OUT / "tables"
SOURCE = "https://doi.org/10.17882/98351"
PARAMS = {
    "n_estimators": 125,
    "max_depth": 8,
    "min_samples_leaf": 3,
    "max_features": 1.0,
    "random_state": 42,
    "n_jobs": 4,
}


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def parse():
    p = RAW / "burgas_107709.txt"
    lines = p.read_text().splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("Cruise\t"))
    d = pd.read_csv(io.StringIO("\n".join(lines[start:])), sep="\t")
    assert len(d) == 84 and d.shape[1] == 55
    timestamp = d.iloc[:, 3]
    e = pd.DataFrame(
        {
            "event_id": "S5:BURGAS:" + d.Station + ":" + timestamp,
            "sample_id": ["BURGAS-" + str(i + 1).zfill(4) for i in range(len(d))],
            "source_id": "S5_BURGAS_BRIDGE",
            "station": d.Station,
            "source_event_id": d.LOCAL_CDI_ID,
            "reported_datetime": timestamp,
            "date_reported": timestamp.str[:10],
            "date_utc": "",
            "date_precision": "reported_calendar_date_timezone_unconfirmed",
            "confirmed_datetime_utc": "",
            "campaign": timestamp.str[:7],
            "year": timestamp.str[:4].astype(int),
            "latitude": d.iloc[:, 5],
            "longitude": d.iloc[:, 4],
            "concentration_items_km2": d.iloc[:, 11],
            "total_quality_flag": d.iloc[:, 12],
            "sampled_area_km2": 0.0135,
            "transect_length_km": 2.25,
            "transect_width_m": 6.0,
            "target_scope": "all_litter",
            "record_type": "transect_density",
            "sampling_method": "ship-based visual transect; minimum detection size unconfirmed",
            "measurement_profile": "S5_visual_size_unconfirmed",
            "position_role": "representative_point_role_unconfirmed",
            "source_doi": "10.17882/98351",
            "source_license": "CC-BY-4.0 in DataCite/icon; conflicting project-access prose",
            "license_status": "primary_metadata_conflict_pending_clarification",
            "provenance": SOURCE,
            "source_row_refs": [
                f"107709.txt line {start + i + 2}" for i in range(len(d))
            ],
        }
    )
    e["quality_flags"] = (
        "all_litter_not_plastic;timezone_unconfirmed;station_clock_repeats;position_role_unconfirmed;raw_counts_unavailable;minimum_size_unconfirmed;licence_prose_conflict"
    )
    e["calculation_method"] = (
        "published integer-rounded total density; area from dataset description/paper; no raw numerator reconstructed"
    )
    e["zero_scope"] = np.where(
        e.concentration_items_km2 == 0,
        "all floating litter detectable by this visual survey",
        "",
    )
    e["source_sha256"] = sha(p)
    e["source_category_sum_items_km2"] = d.iloc[:, 13::2].sum(axis=1)
    e["total_minus_category_sum"] = (
        e.concentration_items_km2 - e.source_category_sum_items_km2
    )
    e["implied_count_not_raw"] = e.concentration_items_km2 * e.sampled_area_km2
    e["raw_integer_count_compatible_with_rounding"] = (
        np.abs(e.implied_count_not_raw - e.implied_count_not_raw.round())
        <= 0.00675 + 1e-8
    )
    assert (
        e.event_id.is_unique
        and e.sample_id.is_unique
        and e.total_quality_flag.eq(1).all()
    )
    assert e.concentration_items_km2.ge(0).all()
    categories = []
    for col in range(13, len(d.columns), 2):
        for i in range(len(d)):
            categories.append(
                {
                    "event_id": e.event_id.iloc[i],
                    "category": d.columns[col].split(" [")[0],
                    "density_items_km2": d.iloc[i, col],
                    "quality_flag": d.iloc[i, col + 1],
                    "source_column": col + 1,
                }
            )
    e.to_csv(DATA / "events.csv", index=False)
    pd.DataFrame(categories).to_csv(DATA / "categories.csv", index=False)
    case = pd.read_csv(ROOT / "data/case/macroplastic_marine_samples.csv")
    add = e.copy()
    add["source_short"] = "Bobchev et al.; IBER-BAS BRIDGE-BS"
    add["region"] = "Burgas Bay, Bulgaria"
    add["sea_area"] = "Black Sea"
    add["litter_category"] = "total floating marine macrolitter (all materials)"
    add["material"] = "mixed"
    add["platform"] = "research boat"
    add["size_class"] = "minimum detection size unconfirmed"
    add["concentration_basis"] = "visual transect"
    add["optical_missions_available"] = "candidate_search_only"
    add["notes"] = (
        "Sandbox research integration; source UTC, tracks, raw counts and licence prose need clarification."
    )
    # Do not turn a timezone-unspecified source clock into confirmed UTC.
    registry = pd.concat([case, add], ignore_index=True, sort=False)
    assert len(registry) == 1019 and registry.event_id.nunique() == 402
    registry.to_csv(DATA / "macroplastic_marine_samples_with_burgas.csv", index=False)
    e[
        [
            "event_id",
            "source_row_refs",
            "total_minus_category_sum",
            "implied_count_not_raw",
            "raw_integer_count_compatible_with_rounding",
        ]
    ].to_csv(T / "density_audit.csv", index=False)
    e.groupby("year").agg(
        events=("event_id", "size"),
        mean=("concentration_items_km2", "mean"),
        median=("concentration_items_km2", "median"),
        maximum=("concentration_items_km2", "max"),
        zeros=("concentration_items_km2", lambda s: (s == 0).sum()),
    ).to_csv(T / "annual_summary.csv")
    e.groupby("campaign").agg(
        events=("event_id", "size"),
        mean=("concentration_items_km2", "mean"),
        std=("concentration_items_km2", "std"),
        zeros=("concentration_items_km2", lambda s: (s == 0).sum()),
    ).to_csv(T / "campaign_summary.csv")
    metadata = {
        "source": SOURCE,
        "provider": "IBER-BAS; Bobchev, Berov, Karamfilov",
        "local_matches_download": sha(p) == sha(RAW / "data_original.txt"),
        "source_sha256": sha(p),
        "events": len(e),
        "stations": e.station.nunique(),
        "calendar_days": e.date_reported.nunique(),
        "campaigns": e.campaign.nunique(),
        "reported_objects_in_abstract": 502,
        "sum_density_times_nominal_area": float(e.implied_count_not_raw.sum()),
        "rounded_category_discrepancies": int(e.total_minus_category_sum.ne(0).sum()),
        "inconsistent_count_area_rounding": int(
            (~e.raw_integer_count_compatible_with_rounding).sum()
        ),
        "licence": "DataCite CC BY 4.0 + SEANOE CC BY icon; SEANOE prose lists FP7/H2020 BRIDGE-BS and partner/on-request access until public release",
        "external_reuse_status": "written clarification pending; local exploratory analysis only",
        "method_source": "https://zenodo.org/records/14608279",
        "units_source": "https://vocab.nerc.ac.uk/collection/P06/current/NPKM/",
    }
    (OUT / "source_audit.json").write_text(json.dumps(metadata, indent=2))
    print(json.dumps(metadata, indent=2), flush=True)
    return e


def predictors(d):
    date = d.date_utc.copy()
    if "date_reported" in d:
        date = d.date_reported.fillna(date)
    day = pd.to_datetime(date).dt.dayofyear
    return np.column_stack(
        [
            d.latitude,
            d.longitude,
            np.sin(2 * np.pi * day / 365.25),
            np.cos(2 * np.pi * day / 365.25),
        ]
    )


def fit_predict(tr, te):
    model = RandomForestRegressor(**PARAMS)
    model.fit(predictors(tr), np.log1p(tr.concentration_items_km2))
    return model, np.maximum(0, np.expm1(model.predict(predictors(te))))


def metrics(y, p):
    return {
        "n": len(y),
        "MAE": mean_absolute_error(y, p),
        "RMSE": np.sqrt(mean_squared_error(y, p)),
        "RMSLE": np.sqrt(mean_squared_error(np.log1p(y), np.log1p(p))),
        "R2": r2_score(y, p),
    }


def train(e):
    (DATA / "frozen_experiment.json").write_text(
        json.dumps(
            {
                "params": PARAMS,
                "protocol_sha256": sha(ROOT / "ml/burgas/protocol.md"),
                "events_sha256": sha(DATA / "events.csv"),
                "time_split": "train 2021-2022, test 2023",
                "predictors": ["latitude", "longitude", "season_sin", "season_cos"],
                "frozen_at": pd.Timestamp.now(tz="UTC").isoformat(),
            },
            indent=2,
        )
    )
    tr = e[e.year < 2023]
    te = e[e.year == 2023]
    assert len(tr) == 56 and len(te) == 28 and set(tr.campaign).isdisjoint(te.campaign)
    model, pr = fit_predict(tr, te)
    joblib.dump(model, DATA / "burgas_2021_2022_rf.joblib", compress=3)
    temporal = []
    preds = []
    for name, p in [
        ("train_median", np.full(len(te), tr.concentration_items_km2.median())),
        ("location_season_rf", pr),
    ]:
        temporal.append(dict(variant=name, **metrics(te.concentration_items_km2, p)))
        for r, v in zip(te.itertuples(), p):
            preds.append(
                {
                    "event_id": r.event_id,
                    "campaign": r.campaign,
                    "station": r.station,
                    "variant": name,
                    "y_true": r.concentration_items_km2,
                    "y_pred": v,
                }
            )
    pd.DataFrame(temporal).to_csv(T / "burgas_temporal_metrics.csv", index=False)
    pd.DataFrame(preds).to_csv(T / "burgas_temporal_predictions.csv", index=False)
    e.assign(split=np.where(e.year < 2023, "train", "test"))[
        ["event_id", "station", "campaign", "split"]
    ].to_csv(T / "temporal_memberships.csv", index=False)
    case = pd.read_csv(ROOT / "data/case/macroplastic_marine_samples.csv").set_index(
        "sample_id"
    )
    member = pd.read_csv(ROOT / "reports/eda/tables/cv_memberships.csv")
    member = member[member.measurement_profile == "S4_visual_GT2_5"]
    rows = []
    members = []
    for fold, m in member.groupby("fold"):
        tr = case.loc[m.loc[m.role == "train", "sample_id"]].copy()
        te = case.loc[m.loc[m.role == "test", "sample_id"]].copy()
        assert set(tr.event_id).isdisjoint(set(te.event_id))
        augmented = pd.concat([tr.reset_index(), e], ignore_index=True)
        assert set(augmented.event_id).isdisjoint(set(te.event_id))
        for name, training in [("doors_only", tr), ("doors_plus_burgas", augmented)]:
            _, pr = fit_predict(training, te)
            for (sid, r), p in zip(te.iterrows(), pr):
                group = m.set_index("sample_id").loc[sid, "group"]
                rows.append(
                    {
                        "fold": fold,
                        "event_id": r.event_id,
                        "sample_id": sid,
                        "group": group,
                        "variant": name,
                        "y_true": r.concentration_items_km2,
                        "y_pred": p,
                        "abs_error": abs(p - r.concentration_items_km2),
                    }
                )
        members.append(
            {
                "fold": fold,
                "doors_train": len(tr),
                "burgas_train": len(e),
                "doors_test": len(te),
                "test_group_overlap": 0,
            }
        )
    pred = pd.DataFrame(rows)
    pred.to_csv(T / "doors_transfer_predictions.csv", index=False)
    pd.DataFrame(members).to_csv(T / "transfer_fold_integrity.csv", index=False)
    score = pd.DataFrame(
        [
            dict(variant=n, **metrics(g.y_true, g.y_pred))
            for n, g in pred.groupby("variant")
        ]
    )
    score.to_csv(T / "doors_transfer_metrics.csv", index=False)
    pd.DataFrame(
        [
            dict(variant=n, fold=fold, **metrics(g.y_true, g.y_pred))
            for (n, fold), g in pred.groupby(["variant", "fold"])
        ]
    ).to_csv(T / "transfer_fold_metrics.csv", index=False)
    wide = pred.pivot(
        index=["event_id", "group"], columns="variant", values="abs_error"
    ).reset_index()
    arrays = [
        (g.doors_only - g.doors_plus_burgas).to_numpy()
        for _, g in wide.groupby("group")
    ]
    rng = np.random.default_rng(42)
    boot = [
        np.concatenate(
            [arrays[i] for i in rng.integers(0, len(arrays), len(arrays))]
        ).mean()
        for _ in range(1000)
    ]
    delta = {
        "comparison": "MAE doors_only minus doors_plus_burgas; positive improves",
        "groups": len(arrays),
        "gain": (wide.doors_only - wide.doors_plus_burgas).mean(),
        "low": np.quantile(boot, 0.025),
        "high": np.quantile(boot, 0.975),
    }
    (OUT / "transfer_bootstrap.json").write_text(json.dumps(delta, indent=2))
    old = pd.read_csv(ROOT / "reports/metocean/tables/field_oof_predictions.csv")
    old = old[
        (old.measurement_profile == "S4_visual_GT2_5")
        & (old.variant == "location_season")
    ]
    baseline = pred[pred.variant == "doors_only"].merge(
        old[["event_id", "y_pred"]],
        on="event_id",
        suffixes=("", "_previous"),
        validate="one_to_one",
    )
    assert np.allclose(baseline.y_pred, baseline.y_pred_previous), (
        "Baseline must reproduce previous experiment"
    )
    print("Temporal", pd.DataFrame(temporal).to_string(index=False), flush=True)
    print("DOORS transfer", score.to_string(index=False), delta, flush=True)


def scene_search(e):
    cache = RAW / "stac"
    cache.mkdir(exist_ok=True)
    bbox = [
        float(e.longitude.min() - 0.025),
        float(e.latitude.min() - 0.025),
        float(e.longitude.max() + 0.025),
        float(e.latitude.max() + 0.025),
    ]

    def one(day):
        path = cache / (day + ".json")
        if path.exists():
            return day, json.loads(path.read_text())
        body = {
            "collections": ["sentinel-2-c1-l2a"],
            "bbox": bbox,
            "datetime": day + "T00:00:00Z/" + day + "T23:59:59Z",
            "limit": 100,
        }
        try:
            r = requests.post(
                "https://earth-search.aws.element84.com/v1/search",
                json=body,
                timeout=60,
            )
            r.raise_for_status()
            j = r.json()
            assert len(j["features"]) < 100, "Pagination required"
            path.write_text(json.dumps(j))
            return day, j
        except (requests.RequestException, ValueError, AssertionError) as ex:
            return day, {"error": repr(ex)}

    with concurrent.futures.ThreadPoolExecutor(4) as pool:
        results = dict(pool.map(one, sorted(e.date_reported.unique())))
    rows = []
    for r in e.itertuples():
        j = results[r.date_reported]
        matches = [
            f
            for f in j.get("features", [])
            if shape(f["geometry"]).covers(Point(r.longitude, r.latitude))
        ]
        if not matches:
            rows.append(
                {
                    "event_id": r.event_id,
                    "date": r.date_reported,
                    "status": "search_error" if "error" in j else "no_same_day_product",
                    "error": j.get("error", ""),
                }
            )
        for f in matches:
            rows.append(
                {
                    "event_id": r.event_id,
                    "date": r.date_reported,
                    "status": "candidate_only_time_geometry_quality_unconfirmed",
                    "stac_id": f["id"],
                    "acquisition_utc": f["properties"]["datetime"],
                    "tile_cloud_percent": f["properties"].get("eo:cloud_cover"),
                    "item_url": "https://earth-search.aws.element84.com/v1/collections/sentinel-2-c1-l2a/items/"
                    + f["id"],
                }
            )
    pd.DataFrame(rows).to_csv(T / "satellite_inventory.csv", index=False)
    print(
        "Satellite search",
        pd.DataFrame(rows).groupby("status").event_id.nunique().to_dict(),
        flush=True,
    )


def report(e):
    plt.rcParams.update(
        {
            "font.size": 10,
            "figure.dpi": 130,
            "axes.spines.top": False,
            "axes.spines.right": False,
        }
    )

    def save(name):
        plt.tight_layout()
        plt.savefig(OUT / "figures" / name, bbox_inches="tight")
        plt.close()

    pivot = e.pivot(
        index="station", columns="campaign", values="concentration_items_km2"
    )
    fig, ax = plt.subplots(figsize=(12, 4))
    im = ax.imshow(np.log1p(pivot), aspect="auto", cmap="viridis")
    fig.colorbar(im, ax=ax, label="log1p(items/km²)")
    for i in range(len(pivot)):
        for j in range(len(pivot.columns)):
            v = pivot.iloc[i, j]
            ax.text(
                j,
                i,
                "missing" if pd.isna(v) else str(int(v)),
                ha="center",
                va="center",
                fontsize=8,
                color="white" if pd.notna(v) and v < 300 else "black",
            )
    ax.set_xticks(range(len(pivot.columns)), pivot.columns, rotation=45, ha="right")
    ax.set_yticks(range(len(pivot)), pivot.index)
    save("01_campaigns.png")
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    g = e.groupby("station").first()
    axes[0].scatter(g.longitude, g.latitude, s=35)
    for r in g.itertuples():
        axes[0].annotate(
            r.Index,
            (r.longitude, r.latitude),
            xytext=(4, 3),
            textcoords="offset points",
        )
    axes[0].set(
        xlabel="Longitude",
        ylabel="Latitude",
        title="Representative points; track role unconfirmed",
    )
    axes[1].hist(e.concentration_items_km2, bins=25, color="#257786")
    axes[1].set(
        xlabel="Reported all-litter density (items/km²)",
        ylabel="Events",
        title="84 events; 26 reported zeros",
    )
    save("02_distribution.png")
    fm = pd.read_csv(T / "doors_transfer_metrics.csv")
    tm = pd.read_csv(T / "burgas_temporal_metrics.csv")
    p = pd.read_csv(T / "burgas_temporal_predictions.csv")
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    axes[0].bar(fm.variant, fm.MAE, color=["#607d8b", "#257786"])
    axes[0].set(ylabel="MAE (items/km²)", title="Same 33 DOORS held-out predictions")
    for name, g in p.groupby("variant"):
        axes[1].scatter(g.y_true, g.y_pred, s=22, alpha=0.7, label=name)
    axes[1].plot([0, 4000], [0, 4000], "k--", lw=1)
    axes[1].set(
        xlabel="Observed Burgas 2023",
        ylabel="Predicted (items/km²)",
        title="Train 2021–2022; test 2023",
    )
    axes[1].legend(fontsize=8)
    save("03_experiments.png")
    audit = json.loads((OUT / "source_audit.json").read_text())
    b = json.loads((OUT / "transfer_bootstrap.json").read_text())
    sat = pd.read_csv(T / "satellite_inventory.csv")
    candidates = sat[sat.status.str.startswith("candidate")]
    prior = fm.set_index("variant").loc["doors_only", "MAE"]
    after = fm.set_index("variant").loc["doors_plus_burgas", "MAE"]
    md = f"""# Бургас: интеграция и проверка пользы

Источник подходит для задачи T3 как **полевые плотности всего плавающего мусора, визуальный учёт**. Добавлены 84 записи за 2021–2023: 8 повторяемых трансект, 21 день, 11 месячных кампаний; 26 настоящих нулей. Это увеличивает черноморский полевой слой с 33 до 117 событий. Эти события не являются пиксельной разметкой и не дают нового F1 детектора.

Интеграция сделана в отдельный исследовательский реестр: **1019 строк, 402 события**, включая исходные 935 строк без изменения их значений. Источник хранится под отдельным measurement_profile, поскольку минимальный обнаруживаемый размер явно не подтверждён. Сходство с DOORS позволяет проверить перенос как гипотезу; одинаковость измерений не доказана.

## Что дал эксперимент

На тех же 33 событиях DOORS и тех же CV-группах MAE контрольной модели **{prior:.2f}**, после добавления Бургаса в обучение **{after:.2f} шт./км²**. Разница control−augmented **{b["gain"]:+.2f}**, 95% групповой bootstrap **[{b["low"]:+.2f}; {b["high"]:+.2f}]**, групп {b["groups"]}. Положительное значение означает улучшение. Контрольные предсказания воспроизвели предыдущий metocean-эксперимент.

{fm.round(3).to_markdown(index=False)}

Модель: координаты и сезон, RF на log1p плотности; метеопризнаки и категории/счётчики предметов не использованы. Все 84 наблюдения Бургаса поступают только в train каждого фолда, DOORS test остаётся тем же. Это проверка переноса между исследованиями, не доказательство универсальной точности или качества спутникового детектора.

Второй опыт: обучение на 56 наблюдениях 2021–2022, проверка на 28 наблюдениях 2023, на тех же трансектах.

{tm.round(3).to_markdown(index=False)}

Сильный сдвиг по годам: средняя плотность в 2022 — 120.4, в 2023 — 790.9 шт./км². Авторы обсуждают штормовые события 2023 года. Координаты и сезон сами по себе их не описывают. Нужна проверка переноса между кампаниями; случайное деление строк дало бы слишком лёгкую задачу.

## Качество и смысл полей

- DOI 10.17882/98351, авторы Nikola Bobchev, Dimitar Berov, Ventzislav Karamfilov; организация **IBER-BAS**, проект BRIDGE-BS. Локальный файл побайтно совпадает с опубликованным 107709.txt.
- Total_Items — **шт./км²**, не количество предметов. Код единиц NPKM подтверждён словарём NERC. Плотности сохраняются как опубликованы.
- Длина 2250 м, ширина 6 м, площадь 13 500 м² (=0.0135 км²) подтверждены описанием источника и методикой статьи. Обследованная полоса существенно отличается от одного спутникового пикселя.
- LOCAL_CDI_ID имеет только 8 уникальных значений, поэтому ключ события составлен из станции и полного исходного timestamp. Иначе потерялись бы повторные наблюдения.
- Часовой пояс не задан; время каждой станции повторяется между кампаниями. Подтверждённый UTC оставлен пустым, дата помечена как исходная календарная. Роль точки, концы/треки и фактические времена нужно подтвердить у владельцев.
- Все опубликованные QV у плотностей равны 1. В {audit["rounded_category_discrepancies"]} строках сумма округлённых категорий отличается от total на ±1 шт./км²; total не переписывался.
- Сумма density × nominal area = {audit["sum_density_times_nominal_area"]:.3f} условных предметов, а описание сообщает 502. В {audit["inconsistent_count_area_rounding"]} строках сочетание плотности и номинальной площади не объясняется простым округлением целого счётчика. Поэтому **сырые числители не восстановлены**; нужен ответ авторов по этому расхождению.
- Нули относятся к обследованной полосе и порогу обнаружения. Они не размечают весь спутниковый кроп как чистую воду. Средняя доля пластика 88.72% не применяется к каждой строке.

## Спутниковые пары

Для **{candidates.event_id.nunique()} из 84 событий** найден Sentinel-2 C1 L2A в тот же календарный день, всего {candidates.stac_id.nunique() if len(candidates) else 0} продуктов. Проверено покрытие представительной точки. Это кандидаты: точный UTC полевого учёта, геометрия полосы, локальные облака и блики ещё не подтверждены; tile cloud cover не равен качеству точки. Обучение пиксельного детектора на этих плотностях не запускалось.

## Условия использования

DataCite указывает CC BY 4.0 и на SEANOE есть такой же значок. При этом текст Licence/Utilisation упоминает FP7/H2020 BRIDGE-BS и доступ партнёрам/по запросу до публичного выпуска. Это расхождение сохранено в provenance. Выполнен локальный исследовательский анализ предоставленного файла; внешнее использование и распространение помечены как требующие письменного уточнения у владельцев. Контакты SEANOE: bobchev.nikola@gmail.com, dimitar.berov@gmail.com. Письма не отправлялись.

## Следующий практический шаг

Запросить одним письмом подтверждение лицензии, точность/пояс/роль времени, координатную роль и треки восьми трансект, минимальный размер и расхождение 502 предмета против таблицы. После этого проверить локальное качество спутниковых кандидатов и строить признаки по всей полосе. Плотность трансекты использовать как цель концентрации или пространственно агрегированной модели, а независимую пиксельную разметку получать отдельно.

## Источники

- [SEANOE, DOI и файл](https://www.seanoe.org/data/00872/98351/), [DataCite metadata](https://api.datacite.org/dois/10.17882/98351).
- [Авторская статья и методика, Bobchev et al. 2024](https://zenodo.org/records/14608279).
- [NERC P06 NPKM: number per square kilometre](https://vocab.nerc.ac.uk/collection/P06/current/NPKM/).
- [DEIMS: владелец IBER-BAS и описание мониторинга](https://deims.org/dataset/4831ef9e-cb64-4467-afaa-c8739c26a272).
"""
    (OUT / "conclusions.md").write_text(md)
    html = markdown.markdown(md, extensions=["tables"])
    for name in [
        "annual_summary",
        "campaign_summary",
        "density_audit",
        "transfer_fold_metrics",
        "satellite_inventory",
    ]:
        html += (
            f"<details><summary>{name}</summary>"
            + pd.read_csv(T / (name + ".csv")).round(3).to_html(index=False)
            + "</details>"
        )
    for p in sorted((OUT / "figures").glob("*.png")):
        html += (
            '<img src="data:image/png;base64,'
            + base64.b64encode(p.read_bytes()).decode()
            + '">'
        )
    (OUT / "burgas_analysis.html").write_text(
        '<!doctype html><html lang="ru"><meta charset="utf-8"><title>Burgas analysis</title><style>body{font:16px system-ui;max-width:1120px;margin:40px auto;padding:0 24px;line-height:1.55;color:#203843}table{display:block;overflow:auto;border-collapse:collapse;font-size:13px}td,th{padding:8px;border-bottom:1px solid #ddd}img{max-width:100%;margin:20px 0}details{margin:20px 0}</style>'
        + html
        + "</html>"
    )
    nb = nbformat.v4.new_notebook()
    nb.cells = [
        nbformat.v4.new_markdown_cell("# Burgas integration and transfer experiments"),
        nbformat.v4.new_code_cell(
            "from pathlib import Path\nimport pandas as pd\nfrom IPython.display import display, Markdown, Image\nROOT = Path.cwd()\nif not (ROOT / 'reports/burgas').exists(): ROOT = ROOT.parent\ndisplay(Markdown((ROOT / 'reports/burgas/conclusions.md').read_text()))"
        ),
    ]
    for name in [
        "annual_summary",
        "campaign_summary",
        "density_audit",
        "burgas_temporal_metrics",
        "doors_transfer_metrics",
        "satellite_inventory",
    ]:
        nb.cells.append(
            nbformat.v4.new_code_cell(
                f"display(pd.read_csv(ROOT / 'reports/burgas/tables/{name}.csv'))"
            )
        )
    nb.cells.append(
        nbformat.v4.new_code_cell(
            "for p in sorted((ROOT / 'reports/burgas/figures').glob('*.png')): display(Image(filename=str(p)))"
        )
    )
    nb.metadata.kernelspec = {
        "display_name": "Python 3",
        "language": "python",
        "name": "python3",
    }
    nbformat.write(nb, ROOT / "notebooks/08_burgas_integration.ipynb")
    print(md[:1800], flush=True)


def main():
    for p in [DATA, T, OUT / "figures"]:
        p.mkdir(exist_ok=True, parents=True)
    protected = [
        ROOT / "data/case/macroplastic_marine_samples.csv",
        ROOT / "data/processed/l2a_adaptation/l2a_rf.joblib",
    ]
    before = {str(p): sha(p) for p in protected}
    e = parse()
    train(e)
    scene_search(e)
    report(e)
    assert before == {str(p): sha(p) for p in protected}
    (OUT / "protected_hashes.json").write_text(json.dumps(before, indent=2))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "report":
        report(pd.read_csv(DATA / "events.csv"))
    else:
        main()
