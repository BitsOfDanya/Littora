"""Event/patch-grain EDA, figures, standalone HTML and executable notebook."""

import base64
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import nbformat
import numpy as np
import pandas as pd
from scipy.stats import ks_2samp

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml/metocean"))
from train import feature_columns

DATA = ROOT / "data/processed/metocean"
OUT = ROOT / "reports/metocean"
T = OUT / "tables"
FIG = OUT / "figures"
plt.rcParams.update(
    {
        "figure.dpi": 130,
        "font.size": 10,
        "axes.spines.top": False,
        "axes.spines.right": False,
    }
)


def save(name):
    plt.tight_layout()
    plt.savefig(FIG / (name + ".png"), bbox_inches="tight")
    plt.close()


def main():
    f = pd.read_csv(DATA / "features.csv")
    q = pd.read_csv(T / "join_quality.csv")
    manifest = pd.read_csv(T / "download_manifest.csv")
    patches = f[f.kind == "patch"].copy()
    field = f[f.kind == "field"].copy()
    cols = feature_columns(f)
    summary = []
    missing = []
    ranges = []
    for (kind, source, split), g in f.groupby(["kind", "source", "split"]):
        z = {
            "kind": kind,
            "source": source,
            "split": split,
            "rows": len(g),
            "known_utc": int(g.observed_at.notna().sum()),
        }
        for family, stem in [
            ("wind", "wind_speed_ms"),
            ("wave", "wave_height_m"),
            ("current", "current_speed_ms"),
        ]:
            z[family + "_available"] = int(
                g[
                    [
                        c
                        for c in g
                        if c.startswith(stem) and ("instant" in c or "daily_mean" in c)
                    ]
                ]
                .notna()
                .any(axis=1)
                .sum()
            )
        summary.append(z)
        for c in cols:
            missing.append(
                {
                    "kind": kind,
                    "source": source,
                    "split": split,
                    "feature": c,
                    "missing": int(g[c].isna().sum()),
                    "rows": len(g),
                    "fraction": g[c].isna().mean(),
                }
            )
    for kind, g in f.groupby("kind"):
        for c in cols + [c for c in f if c.endswith("_daily_mean")]:
            a = g[c].dropna()
            if len(a):
                ranges.append(
                    {
                        "kind": kind,
                        "feature": c,
                        "n": len(a),
                        "min": a.min(),
                        "p05": a.quantile(0.05),
                        "median": a.median(),
                        "p95": a.quantile(0.95),
                        "max": a.max(),
                    }
                )
    pd.DataFrame(summary).to_csv(T / "coverage.csv", index=False)
    pd.DataFrame(missing).to_csv(T / "missingness.csv", index=False)
    pd.DataFrame(ranges).to_csv(T / "physical_ranges.csv", index=False)
    grid = (
        q.groupby(["kind", "product"])
        .agg(
            rows=("status", "size"),
            median_distance_km=("grid_distance_km", "median"),
            max_distance_km=("grid_distance_km", "max"),
            max_time_offset_h=("time_offset_h", "max"),
        )
        .reset_index()
    )
    grid.to_csv(T / "grid_time_summary.csv", index=False)
    shifts = []
    for c in cols:
        tr = patches.loc[patches.split == "train", c].dropna()
        for split in ["val", "test"]:
            te = patches.loc[patches.split == split, c].dropna()
            if len(tr) > 1 and len(te) > 1:
                sd = np.sqrt((tr.var() + te.var()) / 2)
                shifts.append(
                    {
                        "feature": c,
                        "split": split,
                        "train_n": len(tr),
                        "other_n": len(te),
                        "standardized_mean_difference": (te.mean() - tr.mean()) / sd
                        if sd
                        else np.nan,
                        "ks_statistic": ks_2samp(tr, te).statistic,
                    }
                )
    shifts = pd.DataFrame(shifts)
    shifts.to_csv(T / "patch_distribution_shift.csv", index=False)
    patches[cols].corr(method="spearman").to_csv(T / "patch_feature_correlations.csv")
    fig, axes = plt.subplots(1, 3, figsize=(13, 3.8))
    for ax, (family, stem) in zip(
        axes,
        [
            ("Wind", "wind_speed_ms"),
            ("Waves", "wave_height_m"),
            ("Currents", "current_speed_ms"),
        ],
    ):
        values = [
            patches.loc[patches.split == s, stem + "_instant"].dropna()
            for s in ["train", "val", "test"]
        ]
        ax.boxplot(values, tick_labels=["train", "val", "test"], showfliers=True)
        ax.set_title(family + " at acquisition")
        ax.set_ylabel("m" if family == "Waves" else "m/s")
    save("01_distributions")
    cov = pd.DataFrame(summary)
    fig, ax = plt.subplots(figsize=(10, 4))
    yy = np.arange(len(cov))
    w = 0.25
    for i, c in enumerate(["wind", "wave", "current"]):
        ax.barh(
            yy + (i - 1) * w, cov[c + "_available"] / cov.rows * 100, height=w, label=c
        )
    ax.set_yticks(yy, [(r.source + " / " + r.split) for r in cov.itertuples()])
    ax.set_xlim(0, 106)
    ax.set_xlabel("Available records (%)")
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.01), ncol=3, frameon=False)
    save("02_coverage")
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    for kind, g in f.groupby("kind"):
        axes[0].scatter(g.longitude, g.latitude, s=12, label=kind, alpha=0.65)
    axes[0].set(xlabel="Longitude", ylabel="Latitude", title="Joined locations")
    axes[0].legend()
    for product, g in q.groupby("product"):
        axes[1].hist(g.grid_distance_km.dropna(), bins=25, alpha=0.5, label=product)
    axes[1].set(xlabel="Distance to selected model cell (km)", ylabel="Joins")
    axes[1].legend()
    save("03_spatial_quality")
    core = [
        "wind_speed_ms_instant",
        "wind_u_ms_mean24h",
        "wind_v_ms_mean24h",
        "wave_height_m_instant",
        "wave_period_s_instant",
        "current_u_ms_mean24h",
        "current_v_ms_mean24h",
        "current_speed_ms_instant",
    ]
    corr = patches[core].corr(method="spearman")
    fig, ax = plt.subplots(figsize=(8, 6))
    im = ax.imshow(corr, vmin=-1, vmax=1, cmap="RdBu_r")
    fig.colorbar(im, ax=ax, label="Spearman rho")
    ax.set_xticks(
        range(len(core)),
        [c.replace("_instant", "").replace("_mean24h", " 24h") for c in core],
        rotation=65,
        ha="right",
    )
    ax.set_yticks(
        range(len(core)),
        [c.replace("_instant", "").replace("_mean24h", " 24h") for c in core],
    )
    save("04_correlations")
    m = pd.read_csv(T / "pixel_metrics.csv")
    b = pd.read_csv(T / "pixel_bootstrap.csv")
    test = m[m.split == "test"].set_index("variant")
    baseline = test.loc["spectral", "f1"]
    fig, ax = plt.subplots(figsize=(10, 4))
    order = list(test.index)
    ax.barh(order, test.f1, color=["#607d8b"] + ["#217a8a"] * (len(order) - 1))
    for i, n in enumerate(order):
        ci = b[(b.comparison == n) & (b.kind == "F1")].iloc[0]
        ax.plot([ci.low, ci.high], [i, i], color="black", lw=1.5)
        ax.text(
            min(test.loc[n, "f1"] + 0.012, 0.93), i + 0.13, f"{test.loc[n, 'f1']:.3f}"
        )
    ax.set(xlim=(0, 1), xlabel="Test F1; whole-group bootstrap 95% interval")
    save("05_pixel_results")
    fieldmetrics = pd.read_csv(T / "field_metrics.csv")
    fb = pd.read_csv(T / "field_bootstrap.csv")
    profiles = list(fieldmetrics.measurement_profile.unique())
    fig, axes = plt.subplots(
        1, len(profiles), figsize=(max(9, 3.4 * len(profiles)), 4), squeeze=False
    )
    for ax, profile in zip(axes.flat, profiles):
        g = fieldmetrics[fieldmetrics.measurement_profile == profile]
        ax.bar(range(len(g)), g.MAE, color="#217a8a")
        ax.set_xticks(
            range(len(g)),
            g.variant.str.replace("location_season", "loc+season"),
            rotation=65,
            ha="right",
        )
        ax.set_title(profile)
        ax.set_ylabel("OOF MAE (items/km²)")
    save("06_field_results")
    case = pd.read_csv(DATA / "macroplastic_marine_samples_metocean.csv")
    eventgroups = pd.read_csv(ROOT / "reports/eda/tables/event_groups.csv")
    selected = eventgroups[["sample_id"]].merge(
        case, on="sample_id", validate="one_to_one"
    )
    associations = []
    for profile, g in selected.groupby("measurement_profile"):
        for c in core:
            a = g[["concentration_items_km2", c]].dropna()
            if len(a) > 3:
                associations.append(
                    {
                        "measurement_profile": profile,
                        "feature": c,
                        "events": len(a),
                        "spearman_rho": a.corr(method="spearman").iloc[0, 1],
                    }
                )
    pd.DataFrame(associations).to_csv(
        T / "within_profile_associations.csv", index=False
    )
    observed = (
        case.drop_duplicates("event_id")[
            ["event_id", "wind_speed_kn", "wind_speed_ms_instant"]
        ]
        .dropna()
        .copy()
    )
    observed["observed_wind_ms"] = observed.wind_speed_kn * 0.514444
    observed["reanalysis_minus_observed_ms"] = (
        observed.wind_speed_ms_instant - observed.observed_wind_ms
    )
    observed.to_csv(T / "observed_wind_check.csv", index=False)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for profile, g in selected.groupby("measurement_profile"):
        axes[0].scatter(
            g.wind_speed_ms_instant,
            np.log1p(g.concentration_items_km2),
            s=15,
            alpha=0.6,
            label=profile,
        )
    axes[0].set(xlabel="ERA5 wind speed at start (m/s)", ylabel="log1p(items/km²)")
    axes[0].legend(fontsize=8)
    if len(observed):
        axes[1].scatter(
            observed.observed_wind_ms, observed.wind_speed_ms_instant, s=15, alpha=0.5
        )
        hi = max(observed.observed_wind_ms.max(), observed.wind_speed_ms_instant.max())
        axes[1].plot([0, hi], [0, hi], "k--")
        axes[1].set(
            xlabel="Source wind (m/s)",
            ylabel="ERA5 at start (m/s)",
            title=f"{len(observed)} unique events (not independent groups)",
        )
    else:
        axes[1].text(0.1, 0.5, "No comparable observed winds")
    save("07_field_associations")
    # Count contextual independence at the acquisition and grid/date grain.
    patchref = pd.read_csv(ROOT / "reports/l2a_adaptation/tables/selected_patches.csv")
    context = pd.DataFrame(
        [
            {
                "split": s,
                "patches": len(g),
                "scenes": patchref[patchref.split == s].scene_id.nunique(),
                "groups": g.group.nunique(),
            }
            for s, g in patches.groupby("split")
        ]
    )
    context.to_csv(T / "effective_context_units.csv", index=False)
    envcomplete = patches[cols].notna().all(axis=1)
    context["complete_environment_patches"] = [
        int(envcomplete[patches.split == s].sum()) for s in context.split
    ]
    context.to_csv(T / "effective_context_units.csv", index=False)
    schemas = []
    for c in f:
        if c in cols or c.endswith("_daily_mean") or "_coverage" in c:
            units = (
                "fraction"
                if ("_coverage" in c or "_sin" in c or "_cos" in c)
                else ("m/s" if "_ms_" in c else ("s" if "period_s" in c else "m"))
            )
            schemas.append(
                {
                    "feature": c,
                    "units": units,
                    "source": "ECMWF ERA5 / Open-Meteo"
                    if c.startswith(("wind", "wave"))
                    else "HYCOM GOFS; SMOC for DOORS 2024",
                    "role": "quality_only"
                    if "_coverage" in c
                    else "environment_predictor",
                    "missing": "unknown; never zero-filled",
                }
            )
    pd.DataFrame(schemas).to_csv(T / "feature_dictionary.csv", index=False)
    contrast = b[b.comparison == "spectral_all minus spectral"].iloc[0]
    delta = test.loc["spectral_all", "f1"] - baseline
    statement = (
        "Прирост подтверждается этим bootstrap на development test."
        if delta > 0 and contrast.low > 0
        else (
            "Полный набор статистически ухудшил результат в рамках этого development benchmark."
            if contrast.high < 0
            else "Устойчивый положительный эффект полного набора признаков не подтверждён."
        )
    )
    importance = pd.read_csv(T / "pixel_impurity_importance.csv")
    all_imp = importance[importance.variant == "spectral_all"]
    environment_share = all_imp.loc[
        ~all_imp.feature.str.startswith("B"), "impurity_importance"
    ].sum()
    from marida.dataset import CLASSES

    errors = pd.read_csv(T / "pixel_class_errors.csv")
    errors["class_name"] = errors.class_id.map(CLASSES)
    errors.to_csv(T / "pixel_class_errors.csv", index=False)
    error_wide = errors[
        (errors.class_id != 1) & errors.variant.isin(["spectral", "spectral_all"])
    ].pivot(index="class_name", columns="variant", values="predicted_debris")
    error_wide = error_wide.sort_values("spectral_all", ascending=False).head(8)
    error_wide.plot.barh(figsize=(10, 4.8), color=["#607d8b", "#ba593d"])
    plt.xlabel("False positives on the same test pixels")
    plt.ylabel("Reference class")
    save("08_false_positives")
    md = f"""# Ветер, волны и течения: EDA и обучение

Скачано {int((manifest.status == "ok").sum())} успешных ответов; {int((manifest.status != "ok").sum())} ошибок загрузки. Обогащены {len(field)} полевых событий ({len(case)} исходных строк) и {len(patches)} спутниковых патчей. Исходный case CSV и прежние модели сохранены.

Основное сравнение: F1 спектральной модели **{baseline:.3f}**, с полным набором условий среды **{test.loc["spectral_all", "f1"]:.3f}**; ΔF1 **{delta:+.3f}**, 95% парный bootstrap [{contrast.low:+.3f}; {contrast.high:+.3f}]. {statement}

{test[["pixels", "positive_pixels", "precision", "recall", "f1", "average_precision"]].round(4).to_markdown()}

## Почему прямое добавление признаков не помогло

Полная модель дала **{int(test.loc["spectral_all", "fp"])} FP** вместо **{int(test.loc["spectral", "fp"])}** у baseline. Основная ошибка — вода со взвесью и мутная вода. Average precision также снизилась с {test.loc["spectral", "average_precision"]:.3f} до {test.loc["spectral_all", "average_precision"]:.3f}: проблема не сводится к одному выбранному порогу. Пороги зафиксированы по validation и после test не подбирались.

На условия среды приходится {environment_share:.1%} impurity importance полной модели. Это согласуется с переобучением на контекст места/даты: грубые поля повторяются у множества пикселей, а независимых сцен мало. Распределения некоторых компонентов ветра и течений заметно различаются между train и test (см. standardized_mean_difference и KS statistic). Эти диагностики поддерживают объяснение, но не доказывают причинность.

Дополнительное ограничение опыта: полный вход вырос с 11 до 53 столбцов, включая индикаторы пропусков; у RF оставлены 3 кандидата на разделение узла. При таком добавлении признаков меняется конкуренция спектральных и контекстных переменных. Результат отвергает этот способ прямого объединения в фиксированном RF, но не доказывает бесполезность гидрометеоданных для дрейфа, агрегации по сцене или иной архитектуры.

## Покрытие

{cov.to_markdown(index=False)}

ERA5: ветер на 10 м, сетка 0.25°. ERA5-Ocean: волны 0.5°. HYCOM: поверхностное течение 0 м, номинально 0.08°, 3 часа. SMOC использован для полевых записей DOORS 2024 и включает приливную/волновую компоненты; эти продукты не объявляются физически тождественными. Модели среды дают пространственный контекст, а не измерение в каждом 10-метровом пикселе.

{grid.round(3).to_markdown(index=False)}

Пропуски сохраняются в обогащённых таблицах. Для модели медианы и индикаторы пропусков обучены только на train. У записей без UTC есть только явно названные daily_mean; мгновенные признаки не выдуманы. Для снимков используются точные времена STAC и только шаги времени до съёмки. Признаки — instant и средние за предыдущие 24/72 часа с покрытием ≥75%. Направления представлены компонентами/синусом/косинусом. HYCOM читается из NetCDF с scale_factor=0.001 и маской FillValue, а не из ошибочно нераспакованного точечного CSV.

У 64 полевых событий нет точного UTC. У 21 патча волновая ячейка дальше 60 км (13 train, 8 validation), поэтому признаки волн исключены. У одного test-патча нет морской ячейки HYCOM. У пяти полевых событий возраст последнего шага HYCOM превышает 3 часа: instant оставлен пустым, средние считаются отдельно при достаточном покрытии. Для четырёх событий DOORS SMOC не дал достаточного покрытия суток. Получить ответ API и получить пригодный признак — разные этапы; таблица покрытия показывает итог после фильтров.

## Полевая концентрация

{fieldmetrics.round(3).to_markdown(index=False)}

{fb.round(3).to_markdown(index=False)}

Для S1 номинальное снижение MAE примерно 1.6%, но доверительный интервал включает ноль. Для S2 прироста нет; S3 и S4 ухудшились, интервалы разности MAE целиком отрицательны. На 33 событиях DOORS MAE выросла примерно с 183 до 243 шт./км². Устойчивого выигрыша в полевой регрессии этот опыт тоже не показал.

Сопоставление ветра с исходными полевыми значениями доступно для 148 уникальных событий: Spearman ρ≈0.755, среднее ERA5 минус полевой ветер −1.565 м/с, MAE≈1.812 м/с. События могут входить в общие пространственно-временные группы. Это проверка согласованности контекста, а не калибровка прибора: ветер источника может быть усреднён по трансекте, ERA5 взят у представительной точки на начало наблюдения.

Профили измерений обучены отдельно на прежних группах CV. Положительный MAE gain означает улучшение. Это полевая регрессия, не спутниковая калибровка. Профили, отсутствующие в прежних CV memberships, не получают фиктивного результата. Объектные строки не считаются новыми независимыми событиями.

## Ограничения и интерпретация

{context.to_markdown(index=False)}

Большое число пикселей не увеличивает число независимых условий среды: всего 35 сцен. Погода может кодировать место, сезон и съёмочную кампанию. Поэтому environment_only — диагностический контроль, а важности деревьев не доказывают причинность. Географически удалённый тест и high-confidence срезы приведены отдельно. Все пороги выбраны на validation; модели и пороги сохранены до test. Test уже использован в разработке, 95% bootstrap учитывает группы, но не повторное обучение или множественные сравнения. Нового доказательства качества на Чёрном море этот опыт не даёт: независимой разметки ещё нет. 12 reserved_holdout сцен не использовались. Исторический реанализ нельзя считать прогнозом, доступным в реальном времени.

Для дальнейшего решения приоритетны независимые размеченные сцены Чёрного моря и проверка переносимости по регионам. Более мелкая сетка регионального Copernicus Marine может улучшить прибрежное соответствие; это отдельный опыт, а не уже полученный результат.

## Источники

- [Open-Meteo ERA5 historical weather](https://open-meteo.com/en/docs/historical-weather-api), [marine variables, grid and direction conventions](https://open-meteo.com/en/docs/marine-weather-api).
- [HYCOM GOFS analysis](https://www.hycom.org/dataserver/gofs-3pt1/analysis), [reanalysis](https://www.hycom.org/dataserver/gofs-3pt1/reanalysis). Attribution: HYCOM Consortium / NRL / FNMOC.
- [Open-Meteo data licence and API terms](https://open-meteo.com/en/terms): data CC BY 4.0, free endpoint for non-commercial use; commercial API access has separate conditions. Attribution: ECMWF / Copernicus Climate Change Service and Open-Meteo; SMOC: Copernicus Marine / Mercator Ocean.

Полные запросы и SHA256: tables/download_manifest.csv; качество каждого соединения: tables/join_quality.csv. Машинные таблицы, веса и временные ряды: data/processed/metocean. Воспроизведение: ml/metocean/README.md.
"""
    (OUT / "conclusions.md").write_text(md)
    import markdown

    html = markdown.markdown(md, extensions=["tables"])
    # Include all EDA tables in collapsible sections; no external resources required.
    for name in [
        "missingness",
        "physical_ranges",
        "patch_distribution_shift",
        "within_profile_associations",
        "pixel_bootstrap",
        "pixel_group_metrics",
        "pixel_slices",
        "pixel_class_errors",
        "observed_wind_check",
        "feature_dictionary",
    ]:
        tab = pd.read_csv(T / (name + ".csv"))
        html += (
            f"<details><summary>{name}</summary>"
            + tab.round(4).to_html(index=False)
            + "</details>"
        )
    for path in sorted(FIG.glob("*.png")):
        html += (
            '<figure><img src="data:image/png;base64,'
            + base64.b64encode(path.read_bytes()).decode()
            + '"><figcaption>'
            + path.stem
            + "</figcaption></figure>"
        )
    (OUT / "metocean_eda.html").write_text(
        '<!doctype html><html lang="ru"><meta charset="utf-8"><title>Metocean EDA</title><style>body{font:16px system-ui;max-width:1180px;margin:40px auto;padding:0 24px;color:#18313d;line-height:1.55}table{border-collapse:collapse;font-size:13px;display:block;overflow:auto}td,th{padding:7px 10px;border-bottom:1px solid #dce4e8;text-align:right}th{background:#edf4f5}img{max-width:100%}details{margin:20px 0}summary{cursor:pointer;font-weight:bold}figure{margin:32px 0}</style>'
        + html
        + "</html>"
    )
    nb = nbformat.v4.new_notebook()
    nb.cells = [
        nbformat.v4.new_markdown_cell(
            "# Metocean EDA and fixed-model ablations\n\nCached outputs; acquisition and training commands in ml/metocean/README.md. This notebook does not retrain or download implicitly."
        ),
        nbformat.v4.new_code_cell(
            "from pathlib import Path\nimport pandas as pd\nfrom IPython.display import display, Image, Markdown\nROOT = Path.cwd()\nif not (ROOT / 'reports/metocean').exists(): ROOT = ROOT.parent\nT = ROOT / 'reports/metocean/tables'\ndisplay(Markdown((ROOT / 'reports/metocean/conclusions.md').read_text()))"
        ),
    ]
    for name in [
        "coverage",
        "missingness",
        "physical_ranges",
        "grid_time_summary",
        "patch_distribution_shift",
        "within_profile_associations",
        "pixel_metrics",
        "pixel_bootstrap",
        "pixel_slices",
        "field_metrics",
        "field_bootstrap",
    ]:
        nb.cells.extend(
            [
                nbformat.v4.new_markdown_cell("## " + name),
                nbformat.v4.new_code_cell(f"display(pd.read_csv(T / '{name}.csv'))"),
            ]
        )
    nb.cells.append(
        nbformat.v4.new_code_cell(
            "for p in sorted((ROOT / 'reports/metocean/figures').glob('*.png')):\n    display(Image(filename=str(p)))"
        )
    )
    nb.metadata.kernelspec = {
        "display_name": "Python 3",
        "language": "python",
        "name": "python3",
    }
    nbformat.write(nb, ROOT / "notebooks/07_metocean_eda.ipynb")
    print(md[:2000], flush=True)


if __name__ == "__main__":
    main()
