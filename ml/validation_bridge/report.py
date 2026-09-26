"""Rebuild the source/radiometry analysis and blind review gallery from local artifacts."""

import hashlib
import importlib.metadata
import json
import platform
from pathlib import Path

import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import nbformat
from nbclient import NotebookClient
from nbconvert import HTMLExporter

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports/validation_bridge"
TABLES = OUT / "tables"


def main():
    rrs = pd.read_csv(TABLES / "doors_trios_rrs.csv")
    pairs = pd.read_csv(TABLES / "doors_optical_satellite_candidates.csv")
    radiometry = pd.read_csv(TABLES / "radiometry_stress_metrics.csv")
    holdout = pd.read_csv(TABLES / "blacksea_holdout_registry.csv")
    audit = pd.read_csv(TABLES / "blacksea_scene_selection.csv")
    bands = [f"Rrs_{w}" for w in range(400, 851)]
    negative = rrs[bands].to_numpy() < 0
    missing = rrs[bands].isna().to_numpy()
    optics_qa = pd.DataFrame(
        {
            "record_id": rrs.record_id,
            "negative_spectral_samples": negative.sum(axis=1),
            "missing_spectral_samples": missing.sum(axis=1),
        }
    )
    optics_qa.to_csv(TABLES / "doors_spectral_quality.csv", index=False)
    accepted = pairs[pairs.accepted].sort_values(
        ["record_id", "time_difference_hours", "stac_id"]
    )
    # Several tiles can cover one measurement. Preserve candidates, select one deterministic primary.
    primary = accepted.drop_duplicates("record_id").copy()
    primary["selection_rule"] = (
        "minimum_time_difference_then_stac_id; optical_candidate_only"
    )
    primary.to_csv(TABLES / "doors_optical_primary_candidates.csv", index=False)
    sums = radiometry.groupby("product")[["tp", "fp", "fn", "tn"]].sum()
    sums["f1"] = 2 * sums.tp / (2 * sums.tp + sums.fp + sums.fn)
    sums.to_csv(TABLES / "radiometry_pooled_diagnostic.csv")
    for name, paths in [
        ("inputs", list((ROOT / "data/external/doors-research").glob("*"))),
        ("imagery", list((ROOT / "data/external/validation-bridge").rglob("*"))),
    ]:
        manifest = []
        for p in paths:
            if p.is_file():
                manifest.append(
                    {
                        "path": str(p.relative_to(ROOT)),
                        "bytes": p.stat().st_size,
                        "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                    }
                )
        pd.DataFrame(manifest).to_csv(TABLES / f"{name}_hashes.csv", index=False)
    model = ROOT / "data/processed/marida_baseline/spectral_forest.joblib"
    case = ROOT / "data/case/macroplastic_marine_samples.csv"
    provenance = {
        "python": platform.python_version(),
        "case_sha256": hashlib.sha256(case.read_bytes()).hexdigest(),
        "frozen_model_sha256": hashlib.sha256(model.read_bytes()).hexdigest(),
        "packages": {
            p: importlib.metadata.version(p)
            for p in [
                "numpy",
                "pandas",
                "rasterio",
                "scikit-learn",
                "requests",
                "pyproj",
                "nbformat",
                "nbclient",
            ]
        },
    }
    (OUT / "provenance.json").write_text(json.dumps(provenance, indent=2))
    assert (
        provenance["case_sha256"]
        == "30ce0a65e3880b833b5dfe3bc6f528ee5f5af14a0d22f25995f4ef8af585a764"
    )
    fig, ax = plt.subplots(figsize=(9, 4))
    for row in rrs[bands].to_numpy():
        ax.plot(range(400, 851), row, alpha=0.45, lw=0.8)
    ax.set(
        xlabel="Wavelength (nm)",
        ylabel="Rrs (sr⁻¹)",
        title="DOORS June 2024 — 27 measured water spectra",
    )
    ax.axhline(0, color="black", lw=0.5)
    fig.tight_layout()
    fig.savefig(OUT / "figures/doors_spectra.png", dpi=150)
    plt.close(fig)
    diff = pd.read_csv(TABLES / "radiometry_differences.csv")
    fig, ax = plt.subplots(figsize=(9, 4))
    for patch, g in diff[diff.scope == "all_common_labelled"].groupby(
        "patch_id", sort=False
    ):
        ax.plot(g.band, g.median_l2a_minus_rhorc, marker="o", label=patch)
    ax.set(
        xlabel="Sentinel-2 band",
        ylabel="Median L2A − rhorc",
        title="120 labelled pixels, 2 crops — domain shift diagnostic",
    )
    ax.axhline(0, color="black", lw=0.5)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / "figures/radiometry_shift.png", dpi=150)
    plt.close(fig)
    fig, axes = plt.subplots(6, 2, figsize=(14, 20))
    for ax, row in zip(axes.flat, holdout.itertuples()):
        ax.imshow(plt.imread(OUT / row.preview))
        ax.axis("off")
    fig.suptitle("Black Sea 2025 — unlabelled, no detector predictions", fontsize=17)
    fig.tight_layout()
    fig.savefig(OUT / "figures/blacksea_review_contact_sheet.jpg", dpi=110)
    plt.close(fig)
    summary = f"""# Продолжение валидации: EMBLAS / DOORS / L2A — 26.09.2026

**Готовы оптические данные DOORS, диагностика двух пар rhorc/L2A и 12 снимков для независимой разметки. Новых готовых событий T3: 0. Улучшение скора модели в этом шаге не заявляется.**

## Полевые данные и новые источники

| Набор | Что собрано | Что ещё нужно |
|---|---|---|
| EMBLAS 2017/2019 | 302 сессии, площадь и counts, 40 нулей (ранее подготовлены) | Координаты/треки по Session ID, timezone/UTC |
| DOORS июнь 2024 | Два DOI сверены: те же 33 даты, midpoints и плотности | UTC, endpoints/track, ширина, площадь, counts |
| DOORS TriOS | 27 спектров × 451 длина волны, координаты и UTC | Проверка водной атмосферной коррекции, SRF и протокола matchup |
| DOORS MicroPro / гидрология | 11 агрегированных AOP; 27 строк CHL/TSM/Secchi; исходный AOT | Межприборная проверка; отдельные единицы и протоколы |
| Румыния, июль 2024 | Новая таблица 8 трансект: даты, длины, суммарная площадь 0.7231 км² | Числовая геометрия, UTC, counts/density по каждой трансекте |

Источник TriOS: [Zenodo 15778382](https://zenodo.org/records/15778382). Rrs имеет единицу sr⁻¹, это не rhorc и не L2A BOA reflectance. Отрицательных спектральных значений: {int(negative.sum())}, пропусков: {int(missing.sum())}; значения сохранены без обрезания. Сравнение абсолютной точности атмосферной коррекции по ним ещё не выполнено.

Спутниковый поиск по точному UTC: {len(accepted)} подходящих пар тайлов для **{len(primary)} из 27 измерений**, по одной основной паре на измерение сохранено отдельно. Условие — тот же календарный день, |Δt| ≤3 ч, все 3×3 пикселя SCL water и без nodata. Остальные причины отказа сохранены в таблице. Это кандидаты для оптического matchup: нужны проверка неоднородности, glint/adjacency, SRF и водный продукт. Маска SCL не подтверждает отсутствие мусора.

В обоих litter XLSX у T33 перепутаны latitude/longitude. В существующей базе исправление уже было документировано; исходник сохранён без переписывания. Время водных станций в litter-наблюдения не перенесено. В D4.5 обнаружены точные сетевые треки **микропластика**, но они не заменяют визуальные T1–T33. [Аудит и источники](search_audit.md), [готовые запросы владельцам](owner_requests.md). Сообщения не отправлялись.

## Одни и те же участки в rhorc и L2A

Из четырёх заранее выбранных MARIDA кропов два сопоставлены по уникальному tile/date/footprint. Для двух других в проверенной коллекции C1 совпадений нет; это не доказательство отсутствия снимков в других архивах. У исходного MARIDA нет product ID, поэтому идентичность исходной обработки/субсцены полностью не восстановлена.

Обе пары приведены к исходной сетке: 11 каналов, 10 м, nearest-neighbour. У C1 применены asset scale=0.0001 и offset=−0.1, nodata исключены. Сравниваются 120 размеченных пикселей, из них 32 debris. RF и порог 0.6310449457633717 заморожены.

| Кроп / исходный split | rhorc F1 | L2A F1 | Debris: TP/FN на L2A |
|---|---:|---:|---:|
| 22-12-20_18QYF_0 / test, 114 пикселей | 1.000 | 0.727 | 16 / 12 |
| 24-4-19_36JUN_0 / train, 6 пикселей | 1.000 | 0.667 | 2 / 2 |

Объединённый F1 L2A = {sums.loc["L2A_stress_only", "f1"]:.3f}; 14 из 32 положительных пикселей пропущены. **Это stress-test, не независимая оценка качества**: один кроп из train, соседние пиксели зависимы, всего две сцены; pooled F1 нельзя выдавать за test score. Общий участок 36JUN содержит облака; фильтр общей выборки здесь — валидность/существующая разметка, не чистая вода. Для анализа отдельно сохранены статистики только SCL water. Продукты физически различаются, поэтому спектральная разность не является ошибкой относительно наземной истины.

Вывод для следующего эксперимента: расширить парные сцены, затем обучать и валидировать вариант на целевом продукте либо проверять водную коррекцию. Эти четыре кропа не использовать для подбора преобразования или порога.

## Независимая разметка Чёрного моря

12 кропов 256×256×11 за июнь/сентябрь 2025, по два для Новороссийска, Сочи, Батуми, Синопа, Бургаса, Констанцы. **Разметки пока нет:** все labels=0/ignore, не negative; 786432 неизвестных пикселя. Для каждого подготовлены два независимых комплекта review.json / labels.tif / annotations.geojson. Все reserved_holdout, training_allowed=False, предсказания не вычислялись.

Выбор фиксирован по времени/качеству: первый подходящий снимок в окне, tile cloud ≤20%, локальные cloud/shadow ≤10%, water ≥60%, без nodata во всех каналах. Отказов из-за спектральных пропусков при годной SCL: {int(audit.reason.eq("spectral_nodata").sum())}. Набор смещён к прибрежным, ясным, водным сценам; не представляет всё Чёрное море и все погодные условия. Даты 2025 отделяют его от опубликованного временного покрытия обучающих наборов; это не гарантирует географическую независимость MADOS с неполными метаданными.

[Галерея для разметки](review_gallery.html) · [инструкция](review_instructions.md) · [реестр](tables/blacksea_holdout_registry.csv). До двух независимых проверок, разрешения разногласий и аудита доказательств score не рассчитывать. Детекция пикселей не переводится в items/km² без отдельной калибровки по полевым полосам.

## Что сильнее всего поможет модели дальше

1. Авторский экспорт EMBLAS/DOORS: UTC + реальные полосы/треки. Это исправит пространственно-временную связь цели со снимком.
2. Независимые подтверждённые положительные объекты и трудные отрицательные примеры Чёрного моря: пена, кильватер, суда, природные скопления, мутная вода. Текущий пакет готов к такому обзору, но 12 случайно выбранных кропов могут не содержать ни одного подтверждаемого мусорного объекта.
3. Больше одинаковых сцен L2A/rhorc и водной коррекции, с географически/временно разделённой валидацией. Найденные TriOS/AOP позволят проверять радиометрию; score мусора ими напрямую не измеряется.
4. Отдельный обучающий набор региона, затем замороженный тест на зарезервированных сценах. Результат этого теста не использовать для выбора порога или следующей версии модели.

Воспроизведение: [README](../../ml/validation_bridge/README.md). Контрольные суммы и версии: provenance.json, tables/source_manifest.csv, inputs_hashes.csv, imagery_hashes.csv. Существующая case-таблица и модели не изменены.
"""
    (OUT / "summary.md").write_text(summary)
    gallery = [
        '<!doctype html><html lang="ru"><meta charset="utf-8"><title>Чёрное море — независимая разметка</title><style>body{font:16px system-ui;max-width:1200px;margin:32px auto;padding:0 20px;background:#f7f8fa;color:#182638}article{background:white;padding:20px;margin:24px 0;border:1px solid #dce3ec}img{max-width:100%;height:auto}code{overflow-wrap:anywhere}a{color:#125da8}</style><h1>Чёрное море: 12 сцен для разметки</h1><p>Все пиксели пока неизвестны. Модельные предсказания не вычислялись. <a href="review_instructions.md">Инструкция разметчикам</a>. RGB и NIR/red/green растянуты отдельно по 2–98 процентилям; цвет не является меткой пластика.</p>'
    ]
    for row in holdout.itertuples():
        gallery.append(
            f'<article><h2>{row.chip_id}</h2><p>UTC: {row.satellite_datetime} · SCL water: {row.water_fraction:.1%} · cloud/shadow: {row.cloud_fraction:.1%}</p><img src="{row.preview}" alt="RGB and false colour of {row.chip_id}"><p><code>{row.stac_id}</code></p><a href="../../{row.folder}/l2a.tif">11-канальный GeoTIFF</a> · <a href="../../{row.folder}/reviewer_a/review.json">Reviewer A</a> · <a href="../../{row.folder}/reviewer_b/review.json">Reviewer B</a></article>'
        )
    (OUT / "review_gallery.html").write_text("\n".join(gallery) + "</html>")
    nb = nbformat.v4.new_notebook()
    nb.metadata.kernelspec = {
        "name": "python3",
        "display_name": "Python 3",
        "language": "python",
    }
    nb.cells = [
        nbformat.v4.new_markdown_cell(
            "# 04 — DOORS / EMBLAS / L2A validation bridge\nЛокальный воспроизводимый анализ; новых независимых labels ещё нет."
        ),
        nbformat.v4.new_code_cell(
            "from pathlib import Path\nimport pandas as pd\nfrom IPython.display import display, Markdown, Image\nROOT=Path.cwd()\nwhile not (ROOT/'reports/validation_bridge').exists(): ROOT=ROOT.parent\nOUT=ROOT/'reports/validation_bridge'\ndisplay(Markdown((OUT/'summary.md').read_text()))"
        ),
        nbformat.v4.new_code_cell(
            "display(pd.read_csv(OUT/'tables/radiometry_stress_metrics.csv'))\ndisplay(Image(filename=str(OUT/'figures/radiometry_shift.png')))"
        ),
        nbformat.v4.new_code_cell(
            "display(pd.read_csv(OUT/'tables/doors_optical_primary_candidates.csv'))\ndisplay(Image(filename=str(OUT/'figures/doors_spectra.png')))"
        ),
        nbformat.v4.new_code_cell(
            "display(pd.read_csv(OUT/'tables/blacksea_holdout_registry.csv'))\ndisplay(Image(filename=str(OUT/'figures/blacksea_review_contact_sheet.jpg')))"
        ),
        nbformat.v4.new_code_cell(
            "from hashlib import sha256\nimport json\np=json.loads((OUT/'provenance.json').read_text())\nassert sha256((ROOT/'data/case/macroplastic_marine_samples.csv').read_bytes()).hexdigest()==p['case_sha256']\nassert not pd.read_csv(OUT/'tables/blacksea_holdout_registry.csv').training_allowed.any()\nprint('Case hash unchanged; all 12 review chips excluded from training.')"
        ),
    ]
    NotebookClient(
        nb,
        timeout=120,
        kernel_name="python3",
        resources={"metadata": {"path": str(ROOT)}},
    ).execute()
    path = ROOT / "notebooks/04_validation_bridge.ipynb"
    nbformat.write(nb, path)
    html, _ = HTMLExporter().from_notebook_node(nb)
    (OUT / "analysis.html").write_text(html)
    print("Report and notebook ready; holdout labels remain unknown.")


if __name__ == "__main__":
    main()
