# %% [markdown]
# # MARIDA: EDA растров, разбиение и первые детекторы
#
# Продолжение полевого EDA Littora. Цель — проверить реальные изображения/маски, сохранить
# разбиение с учётом зависимостей и получить первые воспроизводимые метрики обнаружения marine debris.
# Концентрацию в шт./км² этот набор не содержит; доля пикселей не заменяет концентрацию.
#
# Источники: [MARIDA v1, CC BY 4.0](https://zenodo.org/records/5151941),
# [авторский код и словари](https://github.com/marine-debris/marine-debris.github.io),
# [статья](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0262247).
# Словари классов и порядок каналов сверены с `utils/assets.py`; номера классов сохраняются.
#
# По статье: исходные L1C обработаны ACOLITE, Rayleigh reflectance приведена к сетке 10 м.
# Каналы с исходным разрешением 20/60 м не получают новую детализацию. Это иной радиометрический
# домен, чем текущий Sentinel-2 L2A Littora. Без отдельной проверки перенос модели не подтверждён.
#
# Протокол эксперимента зафиксирован в `ml/marida/config.toml`: 125 деревьев, depth=20,
# min_samples_leaf=2, confidence-веса 1, 2/3, 1/3, seed=42. Подбора этих параметров нет.
# Порог выбирается по F1 validation; test используется после фиксации порогов.
# Оба алгоритма оцениваются на одних пикселях, игнорируется класс 0.
# Аудит наличия классов во всех частях не используется для перебора split/параметров.

# %%
from pathlib import Path
import hashlib
import importlib.metadata
import json
import platform
import sys
import tomllib
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, BoundaryNorm
import seaborn as sns
import rasterio
from IPython.display import display, Markdown

ROOT = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p / "data/sources.toml").exists())
sys.path.insert(0, str(ROOT / "ml/marida"))
from dataset import CLASSES, BANDS, WAVELENGTHS, NATIVE_RESOLUTION, scan_dataset, assign_strict_split
from models import train_evaluate, group_bootstrap, predict_patch

CFG = tomllib.loads((ROOT / "ml/marida/config.toml").read_text())
DATA = ROOT / "data/external/marida"
PROCESSED = ROOT / "data/processed/marida"
OUT = ROOT / "reports/marida"
MODEL_OUT = ROOT / "data/processed/marida_baseline"
for p in [PROCESSED, OUT / "tables", OUT / "figures", MODEL_OUT / "examples"]:
    p.mkdir(parents=True, exist_ok=True)
sns.set_theme(style="whitegrid", font="DejaVu Sans")
plt.rcParams.update({"figure.dpi": 100, "savefig.dpi": 140})
pd.set_option("display.max_columns", 18)
pd.set_option("display.float_format", lambda x: f"{x:,.4g}")
TABLES = {}

def table(name, frame, show=True):
    TABLES[name] = frame.copy()
    frame.to_csv(OUT / "tables" / f"{name}.csv", index=False)
    if show:
        display(frame)
    return frame

def figure(name):
    plt.tight_layout()
    plt.savefig(OUT / "figures" / f"{name}.png", bbox_inches="tight")
    plt.show()
    plt.close()

def sha_file(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()

archive = DATA / "MARIDA.zip"
with archive.open("rb") as stream:
    archive_md5 = hashlib.file_digest(stream, "md5").hexdigest()
assert archive_md5 == CFG["expected_archive_md5"]
input_paths = [archive, ROOT / "data/manifests/marida.json", *sorted((DATA / "splits").glob("*.txt")),
               *sorted((ROOT / "ml/marida").glob("*.py")), ROOT / "ml/marida/config.toml", ROOT / "ml/marida/requirements.lock.txt"]
table("input_hashes", pd.DataFrame([dict(path=str(p.relative_to(ROOT)), bytes=p.stat().st_size, sha256=sha_file(p))
                                    for p in input_paths]), show=False)
run_info = dict(executed_at_utc=datetime.now(timezone.utc).isoformat(), python=sys.version, platform=platform.platform(),
    versions={p: importlib.metadata.version(p) for p in ["numpy", "pandas", "rasterio", "scikit-learn", "scipy", "nbclient"]},
    config=CFG, archive_md5=archive_md5, network_required_for_notebook=False)
(OUT / "run_info.json").write_text(json.dumps(run_info, ensure_ascii=False, indent=2))
display(Markdown(f"Архив проверен: **{archive.stat().st_size / 1e9:.3f} GB**, MD5 `{archive_md5}`. "
                 "Дальнейший запуск полностью локальный; GPU не нужен."))
table("band_contract", pd.DataFrame({"raster_band_1based": range(1, 12), "band": BANDS, "wavelength_nm": WAVELENGTHS,
                                    "native_resolution_m": NATIVE_RESOLUTION, "grid_resolution_m": 10}))

# %% [markdown]
# ## 1. Полный проход по изображениям и маскам
# Читаем все три растра каждого патча. Проверяем размер, сетку, CRS, категории и confidence.
# Pixel-valid означает конечные значения всех каналов и отсутствие raster nodata.
# Это техническая пригодность, а не отдельная маска облаков/пены/суши.
# Class=0 остаётся ignore. Облака и другие размеченные помехи входят в отрицательные примеры.
# Confidence не используется как признак; при обучении влияет только на вес метки.
# Float32 в масках проверяется на целочисленность до преобразования в uint8.

# %%
patches, band_stats, confidence_counts, pixels = scan_dataset(DATA, PROCESSED)
assert len(patches) == CFG["expected_patches"]
assert patches.patch_id.is_unique
table("patch_inventory", patches, show=False)
table("band_stats_per_patch", band_stats, show=False)
table("class_confidence_per_patch", confidence_counts, show=False)
contract = pd.DataFrame({"check": ["patches", "tile_date_scenes", "dates", "tiles", "pixels", "annotated_pixels", "usable_labelled_pixels",
    "invalid_annotated_pixels", "labelled_without_confidence", "confidence_without_label", "nonfinite_band_values",
    "negative_band_values", "above_one_band_values", "duplicate_image_content"],
    "value": [len(patches), patches.scene_id.nunique(), patches.date.nunique(), patches.tile.nunique(), patches.pixels.sum(),
    patches.annotated_pixels.sum(), patches.usable_pixels.sum(), patches.invalid_annotated_pixels.sum(),
    patches.labelled_without_confidence.sum(), patches.confidence_without_label.sum(), patches.nonfinite_band_values.sum(),
    patches.negative_band_values.sum(), patches.above_one_band_values.sum(), patches.image_sha256.duplicated().sum()]})
table("contract_checks", contract)
assert len(pixels["y"]) == patches.usable_pixels.sum()
assert patches.invalid_annotated_pixels.sum() == patches.labelled_without_confidence.sum() == 0
assert np.isfinite(pixels["x"]).all()
band_summary = band_stats.groupby("band").agg(min=("min", "min"), max=("max", "max"),
    negatives=("negatives", "sum"), above_one=("above_one", "sum")).reindex(BANDS).reset_index()
table("band_ranges", band_summary)
display(Markdown("Отрицательная reflectance не обнуляется автоматически; scale/offset и экстремумы сохранены. "
                 "Обучение использует готовые float-каналы без деления на 10000. Метаданные band descriptions "
                 "могут быть пусты, поэтому порядок каналов зафиксирован авторским словарём."))

# %% [markdown]
# ## 2. Проверка разбиения по событиям, а не только по именам файлов
# Сначала анализируем исходные train/val/test. Строгие группы задаются **без меток классов**:
# одна tile-date сцена; одинаковое содержимое изображения; центры ≤25 км при разнице дат ≤3 суток;
# либо ≤100 км в один день (консервативная связь соседних тайлов одного пролёта).
# Берём компоненты связности. Если исходные части пересекают компоненту, все её патчи перемещаются
# в часть с приоритетом test > val > train. Исходный test никогда не переходит в train/val.
# Это новый протокол, его метрики нельзя напрямую сравнивать с опубликованным benchmark.
# Общие тайлы в разные даты возможны: эта проверка оценивает перенос между событиями, не на новые регионы.
# Пороги расстояния/времени — сценарное ограничение зависимости, не оценка физической независимости океана.

# %%
patches, split_audit = assign_strict_split(patches, CFG)
table("split_integrity", split_audit)
table("split_membership", patches[["patch_index", "patch_id", "scene_id", "date", "tile", "group", "original_split", "split", "image_path",
                                   "label_path", "confidence_path", "image_sha256"]], show=False)
table("moved_patches", patches.loc[patches.original_split != patches.split,
    ["patch_id", "scene_id", "group", "original_split", "split"]], show=False)
split_summary = table("split_summary", patches.groupby("split").agg(patches=("patch_id", "size"), scenes=("scene_id", "nunique"),
    groups=("group", "nunique"), dates=("date", "nunique"), tiles=("tile", "nunique"), usable_pixels=("usable_pixels", "sum"),
    debris_pixels=("class_1", "sum")).reindex(["train", "val", "test"]).reset_index())
positive_groups = patches.loc[patches.class_1 > 0].groupby("split").agg(
    positive_groups=("group", "nunique"), positive_scenes=("scene_id", "nunique"), positive_patches=("patch_id", "size")).reset_index()
table("positive_support", positive_groups)
for split in ["train", "val", "test"]:
    (PROCESSED / f"{split}_patches.txt").write_text("\n".join(patches.loc[patches.split == split, "patch_id"]) + "\n")
(PROCESSED / "split_membership.csv").write_text(TABLES["split_membership"].to_csv(index=False))
table("tile_split_coverage", patches.groupby(["tile", "split"]).size().rename("patches").reset_index())
scene_metadata = patches.groupby(["scene_id", "date", "tile", "split", "group"]).agg(
    patches=("patch_id", "size"), latitude=("latitude", "mean"), longitude=("longitude", "mean")).reset_index()
table("scenes", scene_metadata, show=False)
plt.figure(figsize=(12, 5))
sns.scatterplot(data=scene_metadata, x="longitude", y="latitude", hue="split", size="patches", sizes=(30, 180), alpha=.75)
plt.title("География MARIDA: центры сцен, цвет — строгий split")
plt.xlabel("Долгота, °"); plt.ylabel("Широта, °")
figure("01_geography")

# %% [markdown]
# ## 3. Полнота разметки, дисбаланс и confidence
# Неразмеченная площадь не считается отрицательной. Частоты классов относятся к аннотациям;
# по ним нельзя оценивать распространённость мусора в океане.
# Сводки test здесь служат проверке покрытия протокола; по ним не меняем split или параметры.

# %%
class_counts = []
for split, group in patches.groupby("split"):
    for class_id, name in CLASSES.items():
        total = int(group[f"class_{class_id}"].sum())
        class_counts.append(dict(split=split, class_id=class_id, class_name=name, pixels=total,
            patches_with_class=int(group[f"class_{class_id}"].gt(0).sum()),
            fraction_all_pixels=total / group.pixels.sum(),
            fraction_annotated=total / group.annotated_pixels.sum() if class_id else np.nan))
class_counts = table("class_counts", pd.DataFrame(class_counts))
confidence_by_split = confidence_counts.merge(patches[["patch_index", "split"]], on="patch_index", validate="many_to_one")
confidence_summary = table("confidence_distribution", confidence_by_split.groupby(["split", "class_id", "confidence"]).pixels.sum().reset_index())
labelled_share = patches.annotated_pixels.sum() / patches.pixels.sum()
display(Markdown(f"Размечено **{labelled_share:.2%}** площади патчей. Остальные **{1-labelled_share:.2%}** "
                 "не участвуют в loss и расчёте метрик как фон."))
fig, axes = plt.subplots(1, 2, figsize=(15, 6))
sns.barplot(data=class_counts.query("class_id > 0"), y="class_name", x="pixels", hue="split", ax=axes[0])
axes[0].set(xscale="log", title="Число размеченных пикселей (логарифмическая шкала)", xlabel="Пикселей", ylabel="")
conf_plot = confidence_summary.query("class_id == 1").pivot(index="split", columns="confidence", values="pixels").fillna(0)
conf_plot.rename(columns={1: "High", 2: "Moderate", 3: "Low"}).plot.bar(stacked=True, ax=axes[1], rot=0)
axes[1].set(title="Marine Debris: уверенность аннотаторов", xlabel="Split", ylabel="Пикселей")
figure("02_class_balance")
table("patch_annotation_statistics", patches.groupby("split")[["annotated_pixels", "class_1"]].describe().stack(level=0).reset_index())

# %% [markdown]
# ## 4. Спектральные распределения на train
# Смотрим только train-пиксели. Отражательные значения уже обработаны ACOLITE.
# Корреляции считаются на детерминированной случайной подвыборке train; медианы/квантили — на всех
# пригодных train-аннотациях выбранного класса. Пиксели внутри сцены зависимы.

# %%
roles = patches.split.to_numpy()[pixels["patch_index"]]
train_idx = np.flatnonzero(roles == "train")
rng = np.random.default_rng(CFG["seed"])
sample_idx = rng.choice(train_idx, min(50000, len(train_idx)), replace=False)
corr = pd.DataFrame(pixels["x"][sample_idx], columns=BANDS).corr(method="spearman")
table("train_band_correlations", corr.reset_index(names="band"), show=False)
plt.figure(figsize=(9, 7))
sns.heatmap(corr, vmin=-1, vmax=1, cmap="vlag", annot=True, fmt=".2f")
plt.title("Train: Spearman-корреляции каналов")
figure("03_band_correlations")
spectra = []
for class_id in range(1, 16):
    keep = (roles == "train") & (pixels["y"] == class_id)
    if not keep.any():
        continue
    q = np.quantile(pixels["x"][keep], [.1, .5, .9], axis=0)
    for b, band in enumerate(BANDS):
        spectra.append(dict(class_id=class_id, class_name=CLASSES[class_id], band=band,
                            p10=q[0,b], median=q[1,b], p90=q[2,b], n=int(keep.sum())))
spectra = table("train_spectra", pd.DataFrame(spectra), show=False)
fig, axes = plt.subplots(2, 3, figsize=(14, 8))
for ax, other in zip(axes.flat, [2, 3, 4, 5, 7, 9]):
    for class_id, color in [(1, "#d54b41"), (other, "#237a83")]:
        s = spectra.loc[spectra.class_id == class_id].set_index("band").reindex(BANDS)
        ax.plot(BANDS, s["median"], label=CLASSES[class_id], color=color)
        ax.fill_between(BANDS, s.p10, s.p90, alpha=.15, color=color)
    ax.set(title=f"Debris vs {CLASSES[other]}", ylabel="Reflectance; p10–p90")
    ax.tick_params(axis="x", rotation=60); ax.legend(fontsize=7)
figure("04_train_spectra")

# %% [markdown]
# ## 5. Визуальная проверка train-аннотаций
# Для просмотра RGB используется B04/B03/B02 и общий по трём каналам stretch p2–p98 внутри патча.
# Этот stretch не применяется к признакам модели. Серые области маски — ignore, а не вода.
# Выбраны train-патчи с наибольшим числом аннотаций debris, ship, foam; это иллюстрации,
# не случайная репрезентативная выборка. Confidence: 0 — неизвестно, 1/2/3 — high/moderate/low.

# %%
def rgb_image(x):
    rgb = np.moveaxis(x[[3,2,1]], 0, -1)
    lo, hi = np.nanpercentile(rgb, [2,98])
    return np.clip((rgb - lo) / max(hi-lo, 1e-8), 0, 1)

class_colors = ["#bbbbbb", "#ef302e", "#006d2c", "#74c476", "#995c32", "#ff9f1c", "#ffffff", "#084594",
                "#a6611a", "#984ea3", "#bdb76b", "#40c9c9", "#f0e5cf", "#606060", "#ffe34d", "#d8a6ab"]
class_cmap = ListedColormap(class_colors)
picked = [patches.loc[patches.split == "train"].sort_values(f"class_{c}", ascending=False).iloc[0] for c in [1,5,9]]
fig, axes = plt.subplots(3, 3, figsize=(12, 11))
for row, p in enumerate(picked):
    with rasterio.open(DATA / p.image_path) as f: x = f.read()
    with rasterio.open(DATA / p.label_path) as f: y = f.read(1)
    with rasterio.open(DATA / p.confidence_path) as f: c = f.read(1)
    axes[row,0].imshow(rgb_image(x)); axes[row,0].set_title(p.patch_id, fontsize=9)
    axes[row,1].imshow(y, cmap=class_cmap, norm=BoundaryNorm(np.arange(17)-.5,16))
    axes[row,1].set_title("Класс: debris красный; ignore серый")
    im = axes[row,2].imshow(c, cmap=ListedColormap(["#bbbbbb", "#238b45", "#fed976", "#e34a33"]), vmin=0, vmax=3)
    axes[row,2].set_title("Confidence 1=high, 2=moderate, 3=low")
    for ax in axes[row]: ax.axis("off")
figure("05_train_examples")

# %% [markdown]
# ## 6. Обучение фиксированных baseline-моделей
# Положительный класс — 1 Marine Debris; остальные размеченные классы — отрицательные.
# **NIR threshold:** один порог на B08, направления `>=`; облака/пена/растительность могут давать ложные срабатывания.
# **Spectral RF:** 11 каналов, фиксированные параметры и confidence-веса только на train.
# Coordinates/date/tile/scene/confidence/class не входят в признаки. RF-score не калиброванная вероятность.
# Для каждой модели порог один раз выбирается по максимальному F1 validation (при равенстве выше порог).
# Test не участвует в выборе модели, признаков или порога; результаты test ниже диагностические.
# После просмотра ошибок не переобучаемся и не подбираем конфигурацию по этому test.

# %%
forest, thresholds, metrics, patch_metrics, class_errors = train_evaluate(patches, pixels, CFG, MODEL_OUT)
table("thresholds", thresholds)
table("detector_metrics", metrics)
table("per_patch_metrics", patch_metrics, show=False)
table("errors_by_reference_class", class_errors.assign(class_name=class_errors.class_id.map(CLASSES)))
ci = table("group_bootstrap_intervals", group_bootstrap(patch_metrics, CFG))
scene_metrics = patch_metrics.groupby(["model", "split", "scene_id", "group"])[["tp", "fp", "fn", "tn"]].sum().reset_index()
table("per_scene_confusion", scene_metrics, show=False)
display(Markdown("Метрики относятся только к размеченным технически пригодным пикселям. "
                 "Неразмеченные срабатывания нельзя автоматически объявлять FP. Интервалы bootstrap "
                 "пересэмплируют целые группы по фиксированным предсказаниям; не учитывают повторное обучение "
                 "и не дают гарантии переноса на новые регионы/процессоры."))
fig, axes = plt.subplots(1, 2, figsize=(13, 5))
test_all = metrics.query("split == 'test' and confidence == 'all'")
plot = test_all.melt(id_vars="model", value_vars=["precision", "recall", "f1", "iou"], var_name="metric", value_name="score")
sns.barplot(data=plot, x="metric", y="score", hue="model", ax=axes[0])
axes[0].set(ylim=(0,1), title="Строгий test: одинаковые эталонные пиксели", ylabel="Метрика", xlabel="")
negatives = class_errors.query("split == 'test' and model == 'spectral_forest' and class_id > 1").copy()
negatives["class_name"] = negatives.class_id.map(CLASSES)
sns.barplot(data=negatives.sort_values("predicted_debris_rate", ascending=False), y="class_name", x="predicted_debris_rate", ax=axes[1])
axes[1].set(title="RF: доля ошибочных debris по истинному классу", xlabel="FP / аннотации класса", ylabel="")
figure("06_detector_quality")

# %% [markdown]
# ## 7. Полные маски и сложные случаи после фиксации модели
# Из test выбираются патчи с максимальными FP, FN и TP для разбора ошибок.
# На них алгоритм запускается по **всем пригодным пикселям изображения**, без чтения эталона как входа.
# Сохраняются геопривязанные score/mask GeoTIFF. Эталоны используются только для иллюстрации ошибок.
# Красный на карте ошибок — FP, синий — FN, зелёный — TP; серый — ignore.

# %%
rf_test = patch_metrics.query("model == 'spectral_forest' and split == 'test'")
selected_examples = []
for error_type in ["fp", "fn", "tp"]:
    p = rf_test.sort_values(error_type, ascending=False).iloc[0]
    selected_examples.append((error_type, p, patches.iloc[int(p.patch_index)]))
threshold = float(thresholds.loc[thresholds.model == "spectral_forest", "threshold"].iloc[0])
fig, axes = plt.subplots(3, 4, figsize=(15, 11))
for row, (kind, scores, p) in enumerate(selected_examples):
    probability, predicted = predict_patch(forest, threshold, DATA / p.image_path, MODEL_OUT / "examples" / p.patch_id)
    with rasterio.open(DATA / p.image_path) as f: x = f.read()
    with rasterio.open(DATA / p.label_path) as f: y = f.read(1).astype(int)
    error = np.zeros(y.shape, dtype=int)
    error[(y > 1) & (predicted == 0)] = 1
    error[(y == 1) & (predicted == 1)] = 2
    error[(y > 1) & (predicted == 1)] = 3
    error[(y == 1) & (predicted == 0)] = 4
    axes[row,0].imshow(rgb_image(x)); axes[row,0].set_title(f"max {kind.upper()}: {p.patch_id}", fontsize=8)
    axes[row,1].imshow(y, cmap=class_cmap, norm=BoundaryNorm(np.arange(17)-.5,16)); axes[row,1].set_title("Эталон: red=debris, grey=ignore")
    prediction_cmap = ListedColormap(["#084594", "#ef302e"])
    prediction_cmap.set_bad("#bbbbbb")
    axes[row,2].imshow(np.ma.masked_equal(predicted, 255), cmap=prediction_cmap, vmin=0, vmax=1); axes[row,2].set_title("RF по всему изображению")
    axes[row,3].imshow(error, cmap=ListedColormap(["#bbbbbb", "#eeeeee", "#228b22", "#ef302e", "#2470ce"]), vmin=0, vmax=4)
    axes[row,3].set_title(f"TP={scores.tp}, FP={scores.fp}, FN={scores.fn}", fontsize=9)
    for ax in axes[row]: ax.axis("off")
figure("07_test_error_examples")
table("reviewed_examples", pd.DataFrame([dict(reason=kind, patch_id=p.patch_id, tp=s.tp, fp=s.fp, fn=s.fn,
    score_path=str((MODEL_OUT / "examples" / (p.patch_id + "_score.tif")).relative_to(ROOT)),
    mask_path=str((MODEL_OUT / "examples" / (p.patch_id + "_mask.tif")).relative_to(ROOT))) for kind,s,p in selected_examples]))

# %% [markdown]
# ## 8. Выводы и следующий эксперимент
# Результаты ниже вычисляются по текущему запуску. Для воспроизведения нужны архив и lock-файл.
# Этот опыт не заменяет полевую количественную модель; перенос на Littora L2A и на российские моря не проверен.

# %%
moved = int((patches.original_split != patches.split).sum())
top_fp = negatives.sort_values("predicted_debris_rate", ascending=False).head(4)
lines = ["# MARIDA: результаты EDA и первых детекторов", "",
    f"Проверен архив MD5 `{archive_md5}`. Прочитано {len(patches)} изображений и {2*len(patches)} масок; "
    f"{patches.scene_id.nunique()} tile-date сцен, {patches.tile.nunique()} тайлов, {patches.date.nunique()} дат.", "",
    f"Размечено {int(patches.annotated_pixels.sum()):,} из {int(patches.pixels.sum()):,} пикселей ({labelled_share:.2%}). "
    "Class=0 исключён из обучения и метрик. Положительный класс — marine debris; это не гарантированно чистый пластик.", "",
    f"В исходных каналах найдено {int(patches.nonfinite_band_values.sum()):,} неконечных значений; "
    f"непригодных размеченных пикселей {int(patches.invalid_annotated_pixels.sum())}. "
    "Технически непригодные пиксели исключены из inference и получают nodata=255 в маске. "
    "Отрицательные/большие reflectance сохранены и отражены в band_ranges.csv, без автоматического clipping.", "",
    "## Разбиение", "",
    f"Авторский split проверен отдельно. Для ограничения пространственно-временной зависимости перемещено {moved} патчей "
    "по правилу приоритета test > val > train, без использования значений меток. Параметры связей: "
    f"{CFG['link_distance_km']:g} км / {CFG['link_days']} дня, один день / {CFG['same_day_distance_km']:g} км, "
    "общая сцена или точный дубль изображения. Компоненты связности не разрываются. "
    "Original test полностью сохранён в test. Метрики строгого split не являются воспроизведением авторского benchmark.", "",
    split_summary.to_markdown(index=False), "", positive_groups.to_markdown(index=False), "",
    split_audit.to_markdown(index=False), "",
    "Общие тайлы в разные даты остаются: это перенос между событиями, не независимая проверка на новых акваториях. "
    "Увеличение числа пикселей одной сцены не увеличивает число независимых событий.", "",
    "## Детекторы", "",
    "Фиксированный спектральный RF (11 каналов, 125 деревьев) и порог B08. "
    "Пороги выбраны только на validation, одинаковые тестовые пиксели для обоих методов. "
    "Из признаков исключены confidence, координаты, идентификаторы, дата и эталонный класс. "
    "Confidence используется только как вес обучающих аннотаций.", "",
    test_all[["model", "pixels", "positive_pixels", "threshold", "precision", "recall", "f1", "iou", "average_precision"]].round(4).to_markdown(index=False), "",
    "Average precision — площадь под ступенчатой PR-кривой в определении sklearn, не ROC-AUC. "
    "Основные метрики по всем confidence; high-only приведены отдельно в detector_metrics.csv.", "",
    ci.query("split == 'test'").round(4).to_markdown(index=False), "",
    "Интервалы bootstrap групп относятся к фиксированной модели и текущему протоколу. "
    "Соседние пиксели не считаются независимыми репликами. Score RF не прошёл вероятностную калибровку.", "",
    "## Ошибки", "",
    "Наибольшая доля ложного debris у RF среди классов:", "",
    top_fp[["class_name", "pixels", "predicted_debris", "predicted_debris_rate"]].round(4).to_markdown(index=False), "",
    "Размеры подмножеств неодинаковы: высокая доля ошибок на редком классе требует проверки на дополнительных "
    "независимых сценах. Отдельная high-confidence проверка также меняет состав случаев, поэтому её результат "
    "нельзя интерпретировать только как влияние шума разметки.", "",
    "Сохранены полные маски для случаев max FP, max FN и max TP. Неразмеченные срабатывания остаются "
    "непроверенными; их нельзя автоматически включать в FP или интерпретировать как подтверждённый мусор.", "",
    "## Что делать дальше", "",
    "1. Зафиксировать текущий baseline и split. Если использовать ошибки этого test для проектирования новых "
    "признаков/модели, называть его development benchmark; для итоговой оценки подготовить дополнительный внешний test.",
    "2. Следующий эксперимент — проверить спектральные индексы/контекст и небольшой U-Net на validation. "
    "Приоритет — сложный фон из таблицы ошибок, достаточное число независимых положительных сцен, "
    "устойчивость на confidence-подмножествах; не оптимизация pixel accuracy.",
    "3. Перед интеграцией согласовать радиометрию ACOLITE MARIDA с текущим Sentinel-2 L2A сервиса. "
    "Проверить одинаковые сцены при обоих процессорах и внешний регион. Простое деление/умножение на 10000 "
    "не устраняет различие атмосферной коррекции.",
    "4. Концентрацию в шт./км² оценивать отдельно: MARIDA не содержит соответствующей полевой калибровки. "
    "Не переводить mask area, score или число положительных пикселей в количество предметов.", "",
    "## Файлы и воспроизведение", "",
    "Notebook: `notebooks/02_marida_eda.ipynb`; HTML: `reports/marida/marida_eda.html`. "
    "Команда из корня: `ml/.venv/bin/python ml/marida/run.py`. "
    "Все метрики/пороги/состав split: `reports/marida/tables/`. "
    "Модель, метаданные, heldout_predictions.npz и GeoTIFF: `data/processed/marida_baseline/`. "
    "Массивы размеченных пикселей и текстовые списки split: `data/processed/marida/`. "
    "Большие данные и веса исключены из Git; README содержит команды восстановления.", "",
    "Источники: [MARIDA v1](https://zenodo.org/records/5151941), "
    "[авторский код](https://github.com/marine-debris/marine-debris.github.io), "
    "[статья о подготовке изображений](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0262247).",
]
conclusions = "\n".join(lines)
(OUT / "conclusions.md").write_text(conclusions)
display(Markdown(conclusions))
summary = dict(patches=len(patches), scenes=patches.scene_id.nunique(), tiles=patches.tile.nunique(),
    annotated_pixels=int(patches.annotated_pixels.sum()), annotation_fraction=labelled_share, moved_patches=moved,
    split_summary=json.loads(split_summary.to_json(orient="records")),
    detector_metrics=json.loads(metrics.to_json(orient="records")),
    concentration_metrics=None, validated_for_littora_l2a=False, tables=len(TABLES))
(OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False))
artifacts = [*sorted(MODEL_OUT.glob("*.*")), *sorted((MODEL_OUT / "examples").glob("*.tif")),
             *sorted(PROCESSED.glob("*.*"))]
table("artifact_hashes", pd.DataFrame([dict(path=str(p.relative_to(ROOT)), bytes=p.stat().st_size, sha256=sha_file(p))
                                       for p in artifacts]), show=False)
print(f"Completed: {len(TABLES)} tables, {len(list((OUT / 'figures').glob('*.png')))} figures")
