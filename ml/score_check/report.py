"""Render the executed EDA and frozen-score comparison without retraining."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import nbformat
import numpy as np
import pandas as pd
from nbclient import NotebookClient
from nbconvert import HTMLExporter

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports/score_check"
T = OUT / "tables"
F = OUT / "figures"
NAMES = {
    "marida_frozen": "MARIDA RF",
    "mados_only": "MADOS RF",
    "joint": "MARIDA + MADOS",
}
COLORS = ["#4c78a8", "#f2a541", "#2a9d8f"]


def save(fig, name):
    fig.tight_layout()
    fig.savefig(F / name, dpi=160, bbox_inches="tight")
    plt.close(fig)


def md_table(frame):
    columns = list(frame.columns)
    rows = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join(["---"] * len(columns)) + " |",
    ]
    for row in frame.itertuples(index=False, name=None):
        rows.append(
            "| "
            + " | ".join(
                f"{v:.4f}" if isinstance(v, (float, np.floating)) else str(v)
                for v in row
            )
            + " |"
        )
    return "\n".join(rows)


def figures(metrics):
    F.mkdir(exist_ok=True)
    main = metrics[
        (metrics.confidence_mode == "all") & (metrics.threshold_mode == "frozen")
    ]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for ax, dataset in zip(axes, ["marida_development_test", "mados_test"]):
        part = main[main.dataset == dataset].set_index("model").loc[list(NAMES)]
        ax.bar(list(NAMES.values()), part.f1, color=COLORS)
        for i, v in enumerate(part.f1):
            ax.text(i, v + 0.02, f"{v:.3f}", ha="center")
        ax.set(ylim=(0, 1), ylabel="F1", title=dataset.replace("_", " "))
        ax.tick_params(axis="x", labelsize=9)
    fig.suptitle("Fresh inference reproduces the earlier MADOS gain — no new training")
    save(fig, "full_benchmarks.png")
    fig, ax = plt.subplots(figsize=(9, 4))
    for i, mode in enumerate(["frozen", "common_marida_threshold"]):
        part = (
            metrics[
                (metrics.dataset == "paired_test")
                & (metrics["product"] == "L2A")
                & (metrics.confidence_mode == "all")
                & (metrics.threshold_mode == mode)
            ]
            .set_index("model")
            .loc[list(NAMES)]
        )
        xx = np.arange(3) + (i - 0.5) * 0.32
        ax.bar(
            xx,
            part.f1,
            width=0.30,
            label="Original frozen thresholds"
            if i == 0
            else "Same old MARIDA threshold (0.631)",
            color=["#4c78a8", "#f2a541"][i],
        )
        for x, v in zip(xx, part.f1):
            ax.text(x, v + 0.025, f"{v:.3f}", ha="center", fontsize=9)
    ax.set_xticks(range(3), list(NAMES.values()))
    ax.set(
        ylim=(0, 1.08),
        ylabel="F1",
        title="L2A diagnostic: ONE test crop, 114 labels (28 debris / 86 water)",
    )
    ax.legend(loc="upper left", fontsize=9)
    save(fig, "l2a_threshold_effect.png")
    pred = pd.read_csv(T / "paired_pixel_scores.csv")
    pos = pred[(pred["split"] == "test") & (pred.reference_class == 1)]
    metadata = json.loads((OUT / "run_manifest.json").read_text())
    fig, axes = plt.subplots(1, 3, figsize=(12, 4), sharex=True, sharey=True)
    for ax, (name, title) in zip(axes, NAMES.items()):
        for product, color in [("rhorc", "#2a9d8f"), ("L2A", "#4c78a8")]:
            values = np.sort(pos.loc[pos["product"] == product, name])
            ax.plot(
                values,
                np.arange(1, len(values) + 1) / len(values),
                marker=".",
                label=product,
                color=color,
            )
        ax.axvline(
            metadata["thresholds"][name],
            color="#d1495b",
            ls="--",
            label="Frozen threshold",
        )
        ax.axvline(
            metadata["thresholds"]["marida_frozen"],
            color="#f2a541",
            ls=":",
            label="Common threshold",
        )
        ax.set(
            title=title,
            xlabel="Raw detector score (not calibrated probability)",
            xlim=(-0.01, 1.01),
        )
    axes[0].set_ylabel("Fraction of 28 annotated debris pixels")
    axes[0].legend(fontsize=8)
    fig.suptitle(
        "Lower scores on L2A despite AP = 1 on this easy water-only background"
    )
    save(fig, "paired_score_shift.png")
    spectra = pd.read_csv(T / "rrs_spectral_summary.csv")
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    axes[0].fill_between(
        spectra.wavelength_nm,
        spectra.p10,
        spectra.p90,
        alpha=0.25,
        color="#4c78a8",
        label="p10–p90",
    )
    axes[0].plot(
        spectra.wavelength_nm, spectra["median"], color="#4c78a8", label="Median"
    )
    axes[0].set(
        title="27 DOORS TriOS observations",
        xlabel="Wavelength (nm)",
        ylabel="Rrs (sr⁻¹)",
    )
    axes[0].legend()
    points = pd.read_csv(T / "optical_coverage.csv")
    for available, color in [(False, "#98a2b3"), (True, "#2a9d8f")]:
        p = points[points.has_optical_candidate == available]
        axes[1].scatter(
            p.Longitude,
            p.Latitude,
            c=color,
            s=40,
            alpha=0.8,
            label="Same-day satellite candidate" if available else "No candidate",
        )
    axes[1].set(
        xlabel="Longitude (°E)",
        ylabel="Latitude (°N)",
        title="Optical station coverage; no litter labels",
    )
    axes[1].legend(fontsize=8)
    axes[1].grid(alpha=0.2)
    save(fig, "doors_spectra_coverage.png")
    hydro = pd.read_csv(
        ROOT / "reports/validation_bridge/tables/doors_water_quality.csv"
    )
    fig, axes = plt.subplots(1, 3, figsize=(10, 4))
    for ax, col in zip(axes, ["tsm (mg/l)", "chl (mg/m3)", "secchi disk (m)"]):
        ax.boxplot(hydro[col].dropna())
        ax.set(title=col, xticks=[])
    fig.suptitle(
        "DOORS water properties — 27 measurements, kept separate from litter transects"
    )
    save(fig, "water_quality.png")
    stats = pd.read_csv(T / "blacksea_band_statistics.csv")
    matrix = stats[stats.scope == "SCL_water"].pivot(
        index="chip_id", columns="band", values="median"
    )
    bands = [
        "B01",
        "B02",
        "B03",
        "B04",
        "B05",
        "B06",
        "B07",
        "B08",
        "B8A",
        "B11",
        "B12",
    ]
    matrix = matrix[bands]
    fig, ax = plt.subplots(figsize=(10, 6))
    im = ax.imshow(matrix.to_numpy(), aspect="auto", cmap="viridis")
    ax.set_xticks(range(11), bands)
    ax.set_yticks(range(len(matrix)), matrix.index, fontsize=9)
    ax.set(
        title="Black Sea L2A: median reflectance in SCL-water pixels\nNo detector predictions or negative labels"
    )
    fig.colorbar(im, ax=ax, label="BOA reflectance")
    save(fig, "blacksea_radiometry.png")


def main():
    metrics = pd.read_csv(T / "model_metrics.csv")
    figures(metrics)
    frozen = metrics[
        (metrics.confidence_mode == "all") & (metrics.threshold_mode == "frozen")
    ]
    wide = (
        frozen[frozen.dataset.isin(["marida_development_test", "mados_test"])]
        .pivot(index="dataset", columns="model", values="f1")
        .reset_index()
    )
    wide["joint_delta"] = wide.joint - wide.marida_frozen
    paired = metrics[
        (metrics.dataset == "paired_test")
        & (metrics["product"] == "L2A")
        & (metrics.confidence_mode == "all")
    ]
    paired_table = (
        paired.pivot(index="model", columns="threshold_mode", values="f1")
        .reindex(list(NAMES))
        .reset_index()
    )
    intervals = pd.read_csv(T / "paired_bootstrap.csv")
    ci = intervals[intervals.comparison == "joint minus marida_frozen"][
        ["dataset", "groups", "low", "high"]
    ]
    negative = pd.read_csv(T / "blacksea_band_statistics.csv")
    negative[(negative.scope == "SCL_water")]
    water = pd.read_csv(T / "water_quality_summary.csv", index_col=0)
    primary = pd.read_csv(
        ROOT / "reports/validation_bridge/tables/doors_optical_primary_candidates.csv"
    )
    primary_dt = (
        primary.time_difference_hours.min(),
        primary.time_difference_hours.max(),
    )
    readiness = pd.read_csv(T / "data_readiness.csv")
    summary = f"""# EDA и прогон моделей — 26.09.2026

**Устойчивый прирост от новых EMBLAS/DOORS данных пока не подтверждён: новых обучающих меток мусора нет. Выполнены EDA и свежий inference трёх сохранённых моделей. Прежний выигрыш от MADOS воспроизведён; на новой L2A-проверке результат зависит от порога и ограничен одной test-сценой.**

## Какие данные реально использованы

{md_table(readiness[["source", "rows", "new_detector_training_labels", "new_eligible_T3_events"]])}

Это строки разных типов, их нельзя суммировать как независимые наблюдения. DOORS TriOS — 27 спектров × 451 канал (400–850 нм), без пропусков и отрицательных значений. Есть UTC и координаты. Пригодных оптических кандидатов со спутником — 6/27 измерений, |Δt| {primary_dt[0]:.2f}–{primary_dt[1]:.2f} ч. Перекрывающиеся тайлы не увеличивают число полевых измерений. Rrs имеет размерность sr⁻¹ и не является ни L2A BOA reflectance, ни rhorc; оценку точности водной атмосферной коррекции здесь не выполняем.

Водные свойства 27 строк: TSM медиана {water.loc["50%", "tsm (mg/l)"]:.3f} мг/л, диапазон {water.loc["min", "tsm (mg/l)"]:.3f}–{water.loc["max", "tsm (mg/l)"]:.3f}; хлорофилл медиана {water.loc["50%", "chl (mg/m3)"]:.3f} мг/м³, Secchi медиана {water.loc["50%", "secchi disk (m)"]:.1f} м. Есть сильная неоднородность мутности; наблюдение с TSM 26.5 мг/л сохранено, не удалено как «ошибка». Это контекст водной оптики, не размеченные классы мусора. Время и свойства водных станций не приписывались litter-трансектам.

12 черноморских кропов: 786432 пикселя, все пока unknown/ignore. Подтверждённых debris/background labels: 0. Сохранены статистики всех 11 каналов, SCL и сравнение с диапазоном p01–p99 MARIDA train water. Значительная разница между сценами/месяцами — описательная характеристика отражения и обработки; выход за диапазон rhorc не является ошибкой L2A, меткой мусора или доказанным OOD классификатора. Модель на зарезервированных кропах не запускалась, чтобы сохранить просмотр разметчиками без подсказок модели.

## Полные контрольные выборки: свежий повтор прежнего результата

Заново вычислены scores для 642168 пикселей × 3 модели (не просто прочитана старая таблица). Совпадение с сохранёнными scores проверено с atol=1e-12. Пороги и веса не менялись, обучения не было.

{md_table(wide[["dataset", "marida_frozen", "mados_only", "joint", "joint_delta"]])}

95% paired bootstrap интервалы прироста joint F1, 1000 повторов целыми группами:

{md_table(ci)}

MADOS: +0.1217 F1, MARIDA development: +0.0601. **Это воспроизведение ранее полученного эффекта MADOS, а не новый буст от DOORS.** Для MARIDA интервал включает ноль. Неустановленные пространственно-временные пересечения MADOS/MARIDA по-прежнему ограничивают независимость оценки. Основные метрики учитывают разные исходные validation-пороги; AP также сохранён для оценки ранжирования без одного порога.

## Новая парная проверка L2A/rhorc

Основной результат относится только к 22-12-20_18QYF_0, прежний split=test: **114 размеченных пикселей, 28 debris и 86 water, одна сцена, вне Чёрного моря**. Другой кроп — train, 6 пикселей; он представлен отдельно только как диагностика. Не смешиваем train и test в одной итоговой метрике.

F1 на L2A:

{md_table(paired_table)}

При сохранённых порогах MARIDA RF обнаруживает 16/28 debris (12 FN), joint — 11/28 (17 FN), MADOS-only — 9/28 (19 FN); FP=0 у всех. То есть joint **ухудшает F1 на 0.1632**, добавляя 5 пропусков. На исходном rhorc того же test-кропа все три модели дают F1=1.

При заранее предусмотренном общем пороге 0.6310449457633717 joint и MADOS-only обнаруживают 18/28 debris, FP=0: F1=0.7826 против 0.7273, **+0.0553**. Это небольшой локальный сигнал и контроль чувствительности к рабочему порогу; общий порог не подбирался по этой сцене. Он **не заменён** в моделях. Поскольку scores RF не калиброванные вероятности, одинаковый числовой порог не означает одинаковую рабочую точку.

У всех моделей AP=1 на этой маленькой L2A-выборке: все 86 отрицательных меток — water со score=0. Ранжирование debris/water здесь сохраняется, а положительные scores на L2A снижаются. В этой сцене совсем нет размеченных судов, пены, органики и других сложных отрицательных классов. Поэтому ни AP=1, ни +0.0553 F1 не доказывают устойчивый перенос. При одной сцене осмысленный межсценовый доверительный интервал невозможен. Срез только high-confidence сохранён отдельно, пороги по нему не настраивались.

## Ответ на вопрос о бусте

- **Прежнее добавление MADOS:** прирост на исследовательских rhorc-выборках воспроизводится.
- **Новые DOORS/EMBLAS:** причинный эффект добавления в обучение пока не измерить — нет совместимых новых detector labels и готовых T3-событий. Модели не переобучались на оптике или неизвестных пикселях.
- **Новый L2A-материал:** у joint нет улучшения с исходным порогом. При общем старом пороге есть +0.0553 на одной сцене, но этого недостаточно для выбора версии или заявления о региональном бусте.

Следующий содержательный эксперимент для скора — собрать размеченные L2A пары **train/validation из нескольких независимых мест/дат**, включая трудный фон; на validation определить порог/обработку и затем оценить замороженный вариант на отдельном test. Для Чёрного моря нужны независимые подтверждённые метки подготовленных 12 сцен; они остаются reserved_holdout. Для концентрации нужны авторские треки/UTC EMBLAS/DOORS, а не перенос водных измерений на litter-ID.

## Артефакты

- [Полный исполненный HTML-анализ](eda_score_check.html), [notebook 05](../../notebooks/05_eda_score_check.ipynb).
- [Все метрики](tables/model_metrics.csv), [пиксельные scores пар](tables/paired_pixel_scores.csv), [изменившиеся ошибки](tables/paired_error_changes.csv).
- [Проверка воспроизведения](tables/reproduction_checks.csv), [интервалы](tables/paired_bootstrap.csv), [готовность данных](tables/data_readiness.csv).
- [Протокол](../../ml/score_check/protocol.md), [команды](../../ml/score_check/README.md), run_manifest.json.

Модели, исходная case-таблица и 36 мастер/индивидуальных файлов labels 12 сцен проверены по SHA256 до/после и не изменились. Перенастройки порогов, публикации или изменения production не выполнялись.
"""
    (OUT / "conclusions.md").write_text(summary)
    nb = nbformat.v4.new_notebook()
    nb.metadata.kernelspec = {
        "name": "python3",
        "display_name": "Python 3",
        "language": "python",
    }
    nb.cells = [
        nbformat.v4.new_markdown_cell(
            "# 05 — EDA и проверка буста скора\nСвежий inference замороженных моделей; новые полевые optical данные не являются метками мусора."
        ),
        nbformat.v4.new_code_cell(
            "from pathlib import Path\nimport pandas as pd\nfrom IPython.display import display, Markdown, Image\nROOT=Path.cwd()\nwhile not (ROOT/'reports/score_check').exists(): ROOT=ROOT.parent\nOUT=ROOT/'reports/score_check'\ndisplay(Markdown((OUT/'conclusions.md').read_text()))"
        ),
        nbformat.v4.new_markdown_cell("## 1. Готовность и покрытие новых данных"),
        nbformat.v4.new_code_cell(
            "display(pd.read_csv(OUT/'tables/data_readiness.csv'))\ndisplay(pd.read_csv(OUT/'tables/water_quality_summary.csv'))\ndisplay(Image(filename=str(OUT/'figures/doors_spectra_coverage.png')))\ndisplay(Image(filename=str(OUT/'figures/water_quality.png')))"
        ),
        nbformat.v4.new_markdown_cell(
            "## 2. Радиометрия неразмеченных черноморских сцен"
        ),
        nbformat.v4.new_code_cell(
            "display(pd.read_csv(OUT/'tables/blacksea_radiometry_ranges.csv'))\ndisplay(Image(filename=str(OUT/'figures/blacksea_radiometry.png')))"
        ),
        nbformat.v4.new_markdown_cell(
            "## 3. Повторная проверка полных development-выборок"
        ),
        nbformat.v4.new_code_cell(
            "m=pd.read_csv(OUT/'tables/model_metrics.csv')\nkeep=(m.confidence_mode=='all') & (m.threshold_mode=='frozen')\ndisplay(m[keep & ~m.dataset.str.startswith('paired')])\ndisplay(pd.read_csv(OUT/'tables/paired_bootstrap.csv'))\ndisplay(Image(filename=str(OUT/'figures/full_benchmarks.png')))"
        ),
        nbformat.v4.new_markdown_cell("## 4. Парные L2A/rhorc: test отдельно от train"),
        nbformat.v4.new_code_cell(
            "display(m[(m.dataset=='paired_test') & (m['product']=='L2A')])\ndisplay(Image(filename=str(OUT/'figures/l2a_threshold_effect.png')))\ndisplay(Image(filename=str(OUT/'figures/paired_score_shift.png')))\ndisplay(pd.read_csv(OUT/'tables/paired_error_changes.csv'))"
        ),
        nbformat.v4.new_markdown_cell(
            "## 5. Независимый пересчёт всех confusion matrices и защита входов"
        ),
        nbformat.v4.new_code_cell(
            "import numpy as np, json, hashlib\nmanifest=json.loads((OUT/'run_manifest.json').read_text())\nfor rel,expected in manifest['protected_input_sha256'].items():\n    assert hashlib.sha256((ROOT/rel).read_bytes()).hexdigest()==expected\nthresholds=manifest['thresholds']\nfor dataset in ['mados_test','marida_development_test']:\n    d=dict(np.load(ROOT/f'data/processed/score_check/{dataset}_scores.npz'))\n    for model,t in thresholds.items():\n        y=d['y']==1; p=d[model]>=t\n        counts={'tp':int((y&p).sum()),'fp':int((~y&p).sum()),'fn':int((y&~p).sum()),'tn':int((~y&~p).sum())}\n        row=m[(m.dataset==dataset)&(m.model==model)&(m.threshold_mode=='frozen')&(m.confidence_mode=='all')].iloc[0]\n        assert all(row[k]==v for k,v in counts.items())\n        assert np.isclose(row.f1,2*counts['tp']/(2*counts['tp']+counts['fp']+counts['fn']))\nassert not manifest['training_performed']\nassert not manifest['new_blacksea_detector_predictions']\nprint('All 6 full-benchmark confusion matrices reproduced; protected hashes unchanged; new labels = 0.')"
        ),
    ]
    NotebookClient(
        nb,
        timeout=180,
        kernel_name="python3",
        resources={"metadata": {"path": str(ROOT)}},
    ).execute()
    nbformat.write(nb, ROOT / "notebooks/05_eda_score_check.ipynb")
    html, _ = HTMLExporter().from_notebook_node(nb)
    (OUT / "eda_score_check.html").write_text(html)
    print("EDA notebook and report executed successfully.")


if __name__ == "__main__":
    main()
