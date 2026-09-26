"""Executed analysis of the prespecified L2A adaptation experiment."""

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import nbformat
import numpy as np
import pandas as pd
import rasterio
from nbclient import NotebookClient
from nbconvert import HTMLExporter

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml"))
from marida.dataset import BANDS, CLASSES

OUT = ROOT / "reports/l2a_adaptation"
T = OUT / "tables"
F = OUT / "figures"
CACHE = ROOT / "data/processed/l2a_adaptation"
NAMES = {
    "marida_original": "MARIDA / old threshold",
    "joint_original": "Joint / old threshold",
    "marida_l2a_threshold": "MARIDA / L2A threshold",
    "joint_l2a_threshold": "Joint / L2A threshold",
    "paired_rhorc_l2a_threshold": "Paired rhorc RF / L2A threshold",
    "l2a_rf": "New L2A RF / L2A threshold",
}


def table(df):
    lines = [
        "| " + " | ".join(df.columns) + " |",
        "| " + " | ".join(["---"] * len(df.columns)) + " |",
    ]
    for row in df.itertuples(index=False, name=None):
        lines.append(
            "| "
            + " | ".join(
                f"{v:.4f}" if isinstance(v, (float, np.floating)) else str(v)
                for v in row
            )
            + " |"
        )
    return "\n".join(lines)


def save(fig, name):
    fig.tight_layout()
    fig.savefig(F / name, dpi=160, bbox_inches="tight")
    plt.close(fig)


def eda_and_figures(metrics):
    F.mkdir(exist_ok=True)
    patches = pd.read_csv(T / "selected_patches.csv")
    d = dict(np.load(CACHE / "paired_pixels.npz"))
    roles = patches["split"].to_numpy()[d["patch_index"]]
    rows = []
    for role in ["train", "val", "test"]:
        for name, mask in [("debris", d["y"] == 1), ("background", d["y"] != 1)]:
            keep = (roles == role) & mask
            for b, band in enumerate(BANDS):
                a = d["rhorc"][keep, b]
                z = d["l2a"][keep, b]
                rows.append(
                    {
                        "split": role,
                        "class_scope": name,
                        "band": band,
                        "pixels": len(a),
                        "rhorc_median": float(np.median(a)),
                        "l2a_median": float(np.median(z)),
                        "median_shift": float(np.median(z - a)),
                        "l2a_p01": float(np.quantile(z, 0.01)),
                        "l2a_p99": float(np.quantile(z, 0.99)),
                    }
                )
    spectral = pd.DataFrame(rows)
    spectral.to_csv(T / "spectral_eda.csv", index=False)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    for ax, cls in zip(axes, ["debris", "background"]):
        sub = spectral[(spectral["split"] == "train") & (spectral.class_scope == cls)]
        for col, label in [("rhorc_median", "rhorc"), ("l2a_median", "L2A")]:
            ax.plot(sub.band, sub[col], marker="o", label=label)
        ax.set(title=f"Identical train pixels: {cls}", ylabel="Median reflectance")
        ax.legend()
        ax.tick_params(axis="x", labelsize=8)
    save(fig, "paired_train_spectra.png")
    counts = pd.read_csv(T / "class_counts.csv")
    pivot = (
        counts.pivot(index="class_id", columns="split", values="pixels")
        .fillna(0)
        .reindex(columns=["train", "val", "test"])
    )
    fig, ax = plt.subplots(figsize=(12, 5))
    pivot.plot.bar(ax=ax, logy=True, color=["#2a9d8f", "#f2a541", "#4c78a8"])
    ax.set_xticklabels(
        [CLASSES[c] for c in pivot.index], rotation=40, ha="right", fontsize=9
    )
    ax.set_ylabel("Labelled pixels (log scale)")
    ax.set_title("Same paired-pixel extraction; class 0 excluded")
    save(fig, "class_coverage.png")
    main = (
        metrics[(metrics["split"] == "test") & (metrics.scope == "all")]
        .set_index("variant")
        .loc[list(NAMES)]
    )
    cis = pd.read_csv(T / "bootstrap.csv")
    cis = cis[cis.metric == "F1"].set_index("comparison")
    fig, ax = plt.subplots(figsize=(10, 6))
    yy = np.arange(len(main))
    ax.barh(
        yy,
        main.f1,
        color=["#8d99ae", "#8d99ae", "#f2a541", "#f2a541", "#4c78a8", "#2a9d8f"],
    )
    for i, (name, r) in enumerate(main.iterrows()):
        lo, hi = cis.loc[name, ["low", "high"]]
        ax.plot([lo, hi], [i, i], color="black", lw=1.5)
        ax.scatter([lo, hi], [i, i], marker="|", color="black")
        ax.text(min(r.f1 + 0.015, 0.96), i + 0.28, f"{r.f1:.3f}", fontsize=9)
    ax.set_yticks(yy, [NAMES[k] for k in main.index])
    ax.invert_yaxis()
    ax.set(
        xlim=(0, 1.05),
        xlabel="Test F1; 95% group bootstrap interval",
        title="Frozen thresholds chosen before test; no test-based model selection",
    )
    save(fig, "test_f1.png")
    fig, ax = plt.subplots(figsize=(10, 5))
    errs = pd.read_csv(T / "errors_by_class.csv")
    names = ["joint_original", "joint_l2a_threshold", "l2a_rf"]
    part = (
        errs[(errs.class_id != 1) & errs.variant.isin(names)]
        .pivot(index="class_id", columns="variant", values="predicted_debris")
        .fillna(0)
    )
    part[names].plot.bar(ax=ax, color=["#8d99ae", "#f2a541", "#2a9d8f"])
    ax.set_xticklabels(
        [CLASSES[c] for c in part.index], rotation=40, ha="right", fontsize=9
    )
    ax.set(
        ylabel="False-positive pixels", title="Test false positives by reference class"
    )
    ax.legend(fontsize=8)
    save(fig, "false_positives.png")
    fig, ax = plt.subplots(figsize=(9, 4))
    for role, color in [("train", "#2a9d8f"), ("val", "#f2a541"), ("test", "#4c78a8")]:
        p = patches[patches["split"] == role]
        ax.scatter(p.longitude, p.latitude, s=25, c=color, label=role, alpha=0.7)
    ax.set(
        xlabel="Longitude",
        ylabel="Latitude",
        title="Paired patch locations — repeated regions across dates remain",
    )
    ax.legend()
    ax.grid(alpha=0.2)
    save(fig, "split_geography.png")


def pairing_examples():
    patches = pd.read_csv(T / "selected_patches.csv")
    fig, axes = plt.subplots(3, 2, figsize=(9, 13))
    records = []
    for i, role in enumerate(["train", "val", "test"]):
        row = (
            patches[patches["split"] == role]
            .sort_values(["class_1", "patch_id"], ascending=[False, True])
            .iloc[0]
        )
        with rasterio.open(ROOT / "data/external/marida" / row.image_path) as ds:
            rhorc = ds.read()
        with rasterio.open(
            ROOT / "data/external/l2a-adaptation/patches" / row.patch_id / "l2a.tif"
        ) as ds:
            l2a = ds.read()
        with rasterio.open(ROOT / "data/external/marida" / row.label_path) as ds:
            labels = ds.read(1)
        valid = np.isfinite(rhorc).all(axis=0) & np.isfinite(l2a).all(axis=0)
        correlation = np.corrcoef(rhorc[2, valid], l2a[2, valid])[0, 1]
        records.append(
            {
                "split": role,
                "patch_id": row.patch_id,
                "green_band_correlation": correlation,
            }
        )
        yy, xx = np.where((labels == 1) & valid)
        for ax, product, image in zip(axes[i], ["rhorc", "L2A"], [rhorc, l2a]):
            rgb = []
            for b in [3, 2, 1]:
                band = image[b]
                low, high = np.nanquantile(band, [0.02, 0.98])
                rgb.append(
                    np.clip((np.nan_to_num(band) - low) / max(high - low, 1e-8), 0, 1)
                )
            ax.imshow(np.stack(rgb, axis=-1))
            ax.scatter(
                xx, yy, s=14, facecolors="none", edgecolors="red", linewidths=0.6
            )
            ax.set_title(f"{role}: {row.patch_id} / {product}", fontsize=9)
            ax.axis("off")
    fig.suptitle(
        "Same grids; red rings: transferred debris reference labels (not predictions)"
    )
    save(fig, "pairing_examples.png")
    pd.DataFrame(records).to_csv(T / "pairing_example_qa.csv", index=False)


def main():
    m = pd.read_csv(T / "metrics.csv")
    eda_and_figures(m)
    pairing_examples()
    main = m[(m["split"] == "test") & (m.scope == "all")].set_index("variant")
    val = m[(m["split"] == "val") & (m.scope == "all")].set_index("variant")
    comparisons = (
        main[
            [
                "precision",
                "recall",
                "f1",
                "average_precision",
                "tp",
                "fp",
                "fn",
                "tn",
                "threshold",
            ]
        ]
        .copy()
        .reset_index()
    )
    summary_splits = pd.read_csv(T / "split_summary.csv")
    c = pd.read_csv(T / "bootstrap.csv")
    delta = c[c.metric == "paired_delta_F1"].copy()
    delta["point_delta"] = [
        main.loc[x.split(" minus ")[0], "f1"] - main.loc[x.split(" minus ")[1], "f1"]
        for x in delta.comparison
    ]
    delta.to_csv(T / "paired_deltas.csv", index=False)
    gain = float(main.loc["l2a_rf", "f1"] - main.loc["joint_original", "f1"])
    above_threshold = float(
        main.loc["l2a_rf", "f1"] - main.loc["joint_l2a_threshold", "f1"]
    )
    contrast = delta[delta.comparison == "l2a_rf minus joint_original"].iloc[0]
    if gain > 0 and contrast.low > 0:
        verdict = "Новый L2A RF улучшил F1 относительно исходного joint на этой development-выборке; paired-интервал прироста выше нуля."
    elif gain > 0:
        verdict = "Новый L2A RF дал положительный точечный прирост относительно исходного joint, но paired-интервал включает отсутствие улучшения."
    else:
        verdict = "Новый L2A RF не улучшил F1 относительно исходного joint на этой development-выборке."
    patches = pd.read_csv(T / "selected_patches.csv")
    search = pd.read_csv(T / "scene_search.csv")
    audit = pd.read_csv(T / "pixel_audit.csv")
    geo = pd.read_csv(T / "geographic_audit.csv")
    far = geo[(geo["split"] == "test") & geo.beyond_100km_from_train]
    far_pixels = m[
        (m["split"] == "test")
        & (m.scope == "beyond_100km_train")
        & (m.variant == "l2a_rf")
    ]
    far_description = (
        "Нет такого test-среза."
        if far_pixels.empty
        else f"В срезе >100 км: {int(far_pixels.iloc[0].pixels)} пикселей, {int(far_pixels.iloc[0].positive_pixels)} debris, {int(far_pixels.iloc[0].groups)} групп; F1 нового RF {far_pixels.iloc[0].f1:.4f}."
    )
    text = f"""# Обучение на L2A: результат эксперимента

**{verdict}** Выполнено настоящее обучение двух новых RF; выбраны пороги на L2A validation; тестовые ответы получены после сохранения весов и порогов. Это оценка переноса существующей MARIDA-разметки на L2A, не новый региональный тест Чёрного моря.

## Данные и EDA

Проверены {len(search)} сцены MARIDA; уникальный продукт найден для {int(search.match_status.eq("paired").sum())}, остальные статусы сохранены в scene_search.csv. Зафиксировано {len(patches)} патчей — до 6 на сцену, с debris и разнообразным размеченным фоном; плюс один заранее добавленный train-патч для покрытия Foam (18 меток), отсутствовавшего после первоначального ограничения. Поправка сделана до обучения/метрик; исходный реестр 189 патчей сохранён. Скачаны 11 каналов L2A и SCL; применены scale/offset из STAC, nearest-neighbour на исходную сетку. Сравниваются строго одинаковые координаты размеченных пикселей rhorc/L2A. [Визуальная проверка трёх пар](figures/pairing_examples.png): красные кольца — исходная разметка debris, не предсказания. Исключено {int(audit.excluded_labelled_pixels.sum())} размеченных пикселей с невалидными каналами.

{table(summary_splits)}

Разметка содержит несколько отрицательных классов, а не только чистую воду. class=0 исключён, confidence=0 исключён. Спектры и частоты классов представлены на графиках. Выбор патчей обогащён редкими классами; доля positives различается между split. Метрики характеризуют эту выборку, не естественную частоту мусора на снимках.

Один group и один STAC product принадлежат только одной части. Сохранены прежние строгие MARIDA split/group. Географическая независимость неполная: одни регионы встречаются в разные даты. За пределами 100 км от train находятся {len(far)} из {int(geo["split"].eq("test").sum())} test-патчей. {far_description} Малый пространственный срез — дополнительная диагностика, не доказательство глобального переноса.

## Что обучено

- l2a_rf: новый RF по L2A train.
- paired_rhorc_l2a_threshold: новый RF по rhorc **ровно тех же train-пикселей**, с выбором рабочего порога на L2A validation. Это контроль продукта при одинаковом составе обучения.
- Существующие MARIDA и joint RF: исходные пороги и, отдельно, новые пороги по L2A validation; веса старых моделей не менялись.

Все новые RF: 125 деревьев, depth20, leaf2, balanced_subsample, seed42, confidence weights 1 / 2⁄3 / 1⁄3. Порог — максимум validation F1, при равенстве больший. Без перебора гиперпараметров. Все варианты заранее перечислены в [протоколе](../../ml/l2a_adaptation/protocol.md); после test новые варианты не выбирались и не обучались. Веса и thresholds зафиксированы в frozen_before_test.json до расчёта test scores.

## Test: одинаковые пиксели для всех вариантов

{table(comparisons)}

Относительно исходного joint новый L2A RF: **ΔF1={gain:+.4f}**. Дополнительный эффект относительно joint, которому уже подобран L2A-порог: **ΔF1={above_threshold:+.4f}**. Это разные сравнения: второй контраст показывает, превосходит ли обучение простую перенастройку порога.

Paired bootstrap, 1000 повторов целыми test-группами, seed42:

{table(delta[["comparison", "point_delta", "low", "high", "groups", "valid_repeats"]])}

Интервалы учитывают выбор групп, но не неопределённость повторного обучения, выбора validation-порога, переноса разметки или возможные пересечения MADOS/MARIDA. Семь групп — ограниченная база для выводов; число пикселей не является числом независимых наблюдений.

## Validation и ограничения

{table(val[["f1", "precision", "recall", "threshold"]].reset_index())}

Validation F1 использован для выбора порогов и не является независимым подтверждением качества. Test MARIDA уже использовался в разработке раньше, поэтому этот результат — **development benchmark**. Наличие MADOS в joint требует оговорки о непроверенной межисточниковой географии/датах. Старый RF обучался на большем MARIDA train, чем парные контроль и новый L2A RF; контроль одинаковых train-пикселей нужен именно для разграничения этих эффектов.

Разметка перенесена по геопривязке, дате и MGRS с rhorc на повторно обработанный L2A. Исходный L1C product ID MARIDA не восстановлен; возможны субпиксельные сдвиги/различия обработки. Значения rhorc и L2A физически различаются, поэтому разности спектров не являются ошибкой относительно наземной истины.

## Перенос на новый регион: отдельный слабый результат

В географически удалённой test-группе M018 (Филиппины, более 1300 км до ближайшего train-патча) новый L2A RF пропустил **все 10 debris-пикселей из 10**, F1=0. Совместная модель с L2A-порогом обнаружила 2/10. Это одна группа и мало объектов, но её результат не поддерживает географическое обобщение. Общий прирост в основном относится к другим датам знакомых регионов; его нельзя переносить на Чёрное море. Следующие независимые данные должны в первую очередь расширять географию, а не только число соседних пикселей.

## Что это значит для Littora

Получены воспроизводимые исследовательские L2A-модель и пороги; численный результат приведён выше без перенастройки по test. Автоматической замены production-модели нет. Для подтверждения эффекта в Чёрном море нужны независимые метки его сцен. Все 12 ранее подготовленных Black Sea кропов остаются reserved_holdout: не использованы при обучении/калибровке и не получили модельных подсказок. DOORS Rrs не превращён в метки мусора, концентрация items/km² здесь не оценивалась.

[Исполненный HTML-анализ](l2a_adaptation.html) · [Notebook 06](../../notebooks/06_l2a_adaptation.ipynb) · [Воспроизведение](../../ml/l2a_adaptation/README.md).

Большие артефакты: data/processed/l2a_adaptation/paired_pixels.npz, l2a_rf.joblib, paired_rhorc_rf.joblib, validation_scores.npz, test_scores.npz. Реестр, поклассовые ошибки, групповые confusion matrices и хеши находятся в tables/. Контроль исходных моделей, case-таблицы и черноморских labels — run_manifest.json.
"""
    (OUT / "conclusions.md").write_text(text)
    nb = nbformat.v4.new_notebook()
    nb.metadata.kernelspec = {
        "name": "python3",
        "display_name": "Python 3",
        "language": "python",
    }
    nb.cells = [
        nbformat.v4.new_markdown_cell(
            "# 06 — Обучение и калибровка на L2A\nГрупповые split сохранены; основной кандидат зафиксирован до test."
        ),
        nbformat.v4.new_code_cell(
            "from pathlib import Path\nimport pandas as pd, numpy as np, json, hashlib\nfrom IPython.display import display, Markdown, Image\nROOT=Path.cwd()\nwhile not (ROOT/'reports/l2a_adaptation').exists(): ROOT=ROOT.parent\nOUT=ROOT/'reports/l2a_adaptation'\nCACHE=ROOT/'data/processed/l2a_adaptation'\ndisplay(Markdown((OUT/'conclusions.md').read_text()))"
        ),
        nbformat.v4.new_code_cell(
            "display(pd.read_csv(OUT/'tables/split_summary.csv'))\ndisplay(Image(filename=str(OUT/'figures/class_coverage.png')))\ndisplay(Image(filename=str(OUT/'figures/split_geography.png')))\ndisplay(Image(filename=str(OUT/'figures/paired_train_spectra.png')))"
        ),
        nbformat.v4.new_code_cell(
            "m=pd.read_csv(OUT/'tables/metrics.csv')\ndisplay(m[(m['split']=='test')&(m.scope=='all')])\ndisplay(Image(filename=str(OUT/'figures/test_f1.png')))\ndisplay(pd.read_csv(OUT/'tables/paired_deltas.csv'))\ndisplay(Image(filename=str(OUT/'figures/false_positives.png')))"
        ),
        nbformat.v4.new_code_cell(
            "display(m[(m['split']=='test')&(m.scope!='all')])\ndisplay(pd.read_csv(OUT/'tables/geographic_audit.csv').groupby('split').nearest_train_patch_km.describe())"
        ),
        nbformat.v4.new_code_cell(
            "f=json.loads((CACHE/'frozen_before_test.json').read_text())\nt=dict(np.load(CACHE/'test_scores.npz'))\nfor variant in f['threshold_variants']:\n    y=t['y']==1; p=t[variant['forest']]>=variant['threshold']\n    counts={'tp':int((y&p).sum()),'fp':int((~y&p).sum()),'fn':int((y&~p).sum()),'tn':int((~y&~p).sum())}\n    row=m[(m['split']=='test')&(m.scope=='all')&(m.variant==variant['variant'])].iloc[0]\n    assert all(row[k]==v for k,v in counts.items())\n    assert np.isclose(row.f1,2*counts['tp']/(2*counts['tp']+counts['fp']+counts['fn']))\nmanifest=json.loads((OUT/'run_manifest.json').read_text())\nfor rel,digest in manifest['protected_sha256'].items():\n    assert hashlib.sha256((ROOT/rel).read_bytes()).hexdigest()==digest\nassert manifest['training_performed'] and not manifest['new_blacksea_predictions']\nprint('All 6 test variants reproduced; original weights and Black Sea labels unchanged.')"
        ),
    ]
    NotebookClient(
        nb,
        timeout=180,
        kernel_name="python3",
        resources={"metadata": {"path": str(ROOT)}},
    ).execute()
    nbformat.write(nb, ROOT / "notebooks/06_l2a_adaptation.ipynb")
    html, _ = HTMLExporter().from_notebook_node(nb)
    (OUT / "l2a_adaptation.html").write_text(html)
    print("L2A report and notebook executed.", flush=True)


if __name__ == "__main__":
    main()
