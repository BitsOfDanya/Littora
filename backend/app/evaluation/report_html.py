from __future__ import annotations

import hashlib
import html
import json
import math
import threading
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.schemas.models import (
    BlackSeaNegatives,
    CollectionCheck,
    ConcentrationEvaluation,
    ConcentrationProfile,
    ConcentrationReport,
    DetectionRate,
    DetectorReport,
    DetectorRun,
    DriftMethod,
    LeaveRegionOut,
    MetricIntervals,
    Metrics,
    ModelsResponse,
    PlasticLitterProject,
    SatelliteLink,
    ServedConcentration,
    ZoneFlagCheck,
)

NNBSP = "\u202f"
DASH = "\u2014"
MINUS = "\u2212"
TITLE = "Отчёт валидации моделей"
PRODUCT = "Littora"
DEFAULT_DATA = "marida_l2a"
SIGNIFICANCE = 0.05
DRIFT_ARTIFACTS = (
    ("drifters", Path("metrics") / "drift" / "drifters.json"),
    ("spread", Path("metrics") / "drift" / "spread.json"),
)
BINARY_DIR = Path("detector") / "service"
BINARY_SUFFIXES = (".onnx",)

METHOD_NAMES = {
    "raunet": "RA-U-Net, BCE + Dice",
    "raunet_hard": "RA-U-Net, веса трудных классов",
    "raunet_aux": "RA-U-Net + многоклассовая голова",
    "raunet_focal_dice": "RA-U-Net, Focal + Dice",
    "raunet_focal_tversky": "RA-U-Net, Focal + Tversky",
    "unetpp_resnet34": "U-Net++ (ResNet34)",
    "rf_pixel": "Random Forest",
    "lgbm_pixel": "LightGBM: каналы, индексы, окрестность",
    "lgbm_bands_indices": "LightGBM: каналы и индексы",
    "lgbm_bands": "LightGBM: только каналы",
    "lgbm_rgb": "LightGBM: только RGB",
    "fdi_rule": "Правило FDI + NDVI",
    "fdi_threshold": "FDI, порог",
}

KIND_FAMILIES = {
    "raunet": "Residual Attention U-Net",
    "unetplusplus": "U-Net++ · энкодер ResNet-34",
    "lightgbm": "LightGBM · пиксельный",
    "random_forest": "Random Forest · пиксельный",
    "fdi": "Индекс FDI · порог",
    "fdi_rule": "Правило по FDI, NDVI и синему",
}

DATA_LABELS = {
    "marida": "MARIDA (ACOLITE)",
    "marida_l2a": "MARIDA на L2A",
    "marida_mixed": "MARIDA + L2A",
}

CLASS_LABELS = {
    "marine_debris": "мусор",
    "dense_sargassum": "плотный саргассум",
    "sparse_sargassum": "редкий саргассум",
    "natural_organic_material": "природная органика",
    "foam": "пена",
    "ship": "суда",
    "wakes": "кильватерный след",
    "waves": "волны",
    "clouds": "облака",
    "cloud_shadows": "тени облаков",
    "marine_water": "морская вода",
    "sediment_laden_water": "вода со взвесью",
    "turbid_water": "мутная вода",
    "shallow_water": "мелководье",
    "mixed_water": "смешанная вода",
}

REGION_LABELS = {
    "east_asia": "Восточная Азия",
    "hispaniola": "Эспаньола",
    "honduras": "Гондурас",
    "indonesia": "Индонезия",
    "scotland": "Шотландия",
    "south_africa": "ЮАР",
    "south_china_sea": "Южно-Китайское море",
}

NEGATIVE_LABELS = {
    "aquaculture": "садки",
    "cloud": "облака",
    "river_plume": "речной шлейф",
    "ship": "суда",
    "slick": "пятна на воде",
    "turbid_front": "фронт мутности",
    "water": "вода",
}

PLP_LABELS = {
    "plastic": "Пластик",
    "mixed": "Смесь пластика и органики",
    "plastic_or_mixed": "Пластик и смесь",
    "natural_controls": "Природные мишени (контроль)",
}

PROFILE_LABELS = {
    "S1_trawl_5_to_50": "S1 · пластик 5–50 см, трал",
    "S2_visual_GT2": "S2 · пластик, визуально",
    "S3_visual_GT2": "S3 · мусор, визуально",
    "S4_visual_GT2_5": "S4 · мусор, визуально",
}

ROLE_LABELS = {"primary": "основной", "shortlist": "шорт-лист"}
UNIT_LABELS = {"items/km2": "шт./км²"}
THRESHOLD_SOURCES = {"val_max_f1": "максимум F1 на валидации", "fixed": "фиксированный"}

EXTRA_TITLES = {
    "team_audit": "Аудит зон командой",
    "audit": "Аудит зон командой",
    "zone_audit": "Аудит зон командой",
    "calibration": "Калибровка вероятностей",
    "validation": "Проверка",
    "envelopes": "Огибающие",
}

KNOWN_RESPONSE = {"detector", "concentration", "drift", "sources"}
KNOWN_DETECTOR = {"service", "test_set", "runs", "checks"}
KNOWN_CHECKS = {
    "domain_shift",
    "leave_region_out",
    "black_sea_negatives",
    "plp",
    "zone_flags",
    "collection",
}
KNOWN_CONCENTRATION = {"profiles", "satellite_link"}
KNOWN_SERVICE = {
    "name",
    "threshold",
    "min_pixels",
    "bands",
    "patch",
    "stride",
    "data",
    "split",
    "sea_mask",
    "validation",
    "test",
    "test_ci95",
    "postprocessed_test",
    "service_test",
    "service_mode",
    "calibration",
}
KNOWN_DRIFT = {
    "model",
    "status",
    "label",
    "reason",
    "velocity",
    "integration",
    "windages",
    "stokes",
    "particles",
    "members",
    "diffusivity_m2s",
    "horizons_h",
    "max_hours",
    "max_hindcast_hours",
    "forcing",
}

LIMITATIONS = (
    (
        "Пена",
        "белая пена и прибойные полосы ярко отражают в ближнем ИК, как плавающий пластик; "
        "отличаются формой и тем, что держатся недолго.",
    ),
    (
        "Саргассум при слабом красном крае",
        "редкий или притопленный саргассум почти не даёт подъёма на красном крае "
        "(B05–B07), и FDI у него положителен, как у мусора.",
    ),
    (
        "Судовые следы",
        "суда и кильватерные следы — яркие вытянутые объекты; маска судов снижает число "
        "ложных пятен, но не убирает их полностью.",
    ),
    (
        "Края облаков",
        "на кромке облаков и в их тени отражение смешанное; облако — это «не наблюдалось», "
        "а не «чистая вода».",
    ),
    (
        "Солнечные блики",
        "блик поднимает отражение во всех каналах; остаточный блик даёт ложные пятна.",
    ),
    (
        "Малая доля покрытия",
        "мелкое скопление занимает малую долю пикселя 10 × 10 м; ниже порога обнаружимости — "
        "«не обнаружимо», а не «чисто». Доли по размерам мишеней — в проверке PLP.",
    ),
    (
        "Другая обработка снимков",
        "часть обучающих данных — ACOLITE; снимки Sen2Cor L2A дают сдвиг значений, "
        "его величина — в проверке сдвига домена.",
    ),
)

_HASH_LOCK = threading.Lock()
_HASHES: dict[tuple[str, int, int], str] = {}


@dataclass(frozen=True)
class Artifact:
    path: str
    size: int | None
    modified: datetime | None
    sha256: str | None
    role: str


@dataclass(frozen=True)
class Column:
    title: str
    numeric: bool = False


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def number(value: float | None, digits: int = 0) -> str:
    if value is None or not math.isfinite(value):
        return DASH
    text = f"{abs(value):.{digits}f}"
    whole, _, fraction = text.partition(".")
    if len(whole) > 4:
        groups: list[str] = []
        while len(whole) > 3:
            groups.insert(0, whole[-3:])
            whole = whole[:-3]
        whole = NNBSP.join([whole, *groups])
    body = f"{whole},{fraction}" if fraction else whole
    return f"{MINUS}{body}" if value < 0 and float(text) != 0 else body


def signed(value: float | None, digits: int = 1) -> str:
    if value is None or not math.isfinite(value):
        return DASH
    body = number(abs(value), digits)
    if float(f"{value:.{digits}f}") > 0:
        return f"+{body}"
    if float(f"{value:.{digits}f}") < 0:
        return f"{MINUS}{body}"
    return body


def share(value: float | None) -> str:
    return number(value, 2)


def span(interval: Sequence[float] | None, digits: int = 2) -> str:
    if not interval:
        return DASH
    return f"{number(interval[0], digits)}–{number(interval[1], digits)}"


def percent(ratio: float | None, digits: int = 0) -> str:
    if ratio is None or not math.isfinite(ratio):
        return DASH
    return f"{number(ratio * 100, digits)}{NNBSP}%"


def auto(value: float) -> str:
    size = abs(value)
    digits = 0 if size >= 1000 else 1 if size >= 10 else 3
    return number(value, digits)


def plural(count: int, forms: tuple[str, str, str]) -> str:
    tail, tens = count % 10, count % 100
    if tail == 1 and tens != 11:
        return forms[0]
    if 2 <= tail <= 4 and not 12 <= tens <= 14:
        return forms[1]
    return forms[2]


def counted(count: int, forms: tuple[str, str, str]) -> str:
    return f"{number(count)}{NNBSP}{plural(count, forms)}"


def mono(text: object) -> str:
    return f'<span class="mono">{esc(text)}</span>'


def minor(text: str) -> str:
    return f'<span class="minor">{text}</span>'


def note(text: str) -> str:
    return f'<p class="note">{text}</p>'


def tag(text: str, kind: str = "") -> str:
    return f'<span class="tag {kind}">{esc(text)}</span>'


def when(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%d.%m.%Y, %H:%M UTC")


def bar(value: float | None, interval: Sequence[float] | None = None) -> str:
    width = 56

    def at(point: float) -> float:
        return round(min(1.0, max(0.0, point)) * width, 1)

    parts = [f'<rect x="0" y="0" width="{width}" height="4" class="track"/>']
    if value is not None and math.isfinite(value):
        parts.append(f'<rect x="0" y="0" width="{at(value)}" height="4" class="fill"/>')
    if interval:
        low, high = at(interval[0]) + 0.5, at(interval[1]) - 0.5
        parts.append(f'<path d="M{low} 7.5H{high}M{low} 5.5V9.5M{high} 5.5V9.5" class="whisker"/>')
    return (
        f'<svg class="bar" width="{width}" height="10" viewBox="0 0 {width} 10" '
        f'aria-hidden="true">{"".join(parts)}</svg>'
    )


def table(
    columns: Sequence[Column],
    rows: Iterable[Sequence[str]],
    *,
    caption: str | None = None,
    classes: Sequence[str] | None = None,
    wide: bool = False,
) -> str:
    head = "".join(
        f'<th scope="col" class="{"num" if column.numeric else ""}">{esc(column.title)}</th>'
        for column in columns
    )
    body = []
    for index, row in enumerate(rows):
        cells = []
        for position, (column, cell) in enumerate(zip(columns, row, strict=True)):
            kind = "num" if column.numeric else ""
            if position == 0:
                cells.append(f'<th scope="row" class="{kind}">{cell}</th>')
            else:
                cells.append(f'<td class="{kind}">{cell}</td>')
        row_class = classes[index] if classes and index < len(classes) else ""
        body.append(f'<tr class="{row_class}">{"".join(cells)}</tr>')
    title = f"<caption>{esc(caption)}</caption>" if caption else ""
    return (
        f'<table class="{"wide" if wide else ""}">{title}<thead><tr>{head}</tr></thead>'
        f"<tbody>{''.join(body)}</tbody></table>"
    )


def facts(rows: Iterable[tuple[str, str]]) -> str:
    items = "".join(f"<dt>{esc(label)}</dt><dd>{value}</dd>" for label, value in rows if value)
    return f'<dl class="facts">{items}</dl>'


def block(title: str, body: str, detail: str | None = None) -> str:
    extra = f'<span class="detail">{detail}</span>' if detail else ""
    return f'<div class="block"><h3>{esc(title)}{extra}</h3>{body}</div>'


def section(index: int, key: str, title: str, lede: str | None, body: str, page: bool) -> str:
    intro = f'<p class="lede">{lede}</p>' if lede else ""
    return (
        f'<section id="{key}" class="section{" page" if page else ""}">'
        f'<header class="section-head"><span class="index">{index:02d}</span>'
        f"<h2>{esc(title)}</h2></header>{intro}{body}</section>"
    )


def sha256_of(path: Path) -> str | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    key = (str(path), stat.st_mtime_ns, stat.st_size)
    with _HASH_LOCK:
        cached = _HASHES.get(key)
    if cached is not None:
        return cached
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
    except OSError:
        return None
    value = digest.hexdigest()
    with _HASH_LOCK:
        _HASHES[key] = value
    return value


def resolve(source: str, reports_dir: Path, models_dir: Path) -> Path | None:
    prefix, _, rest = source.partition("/")
    base = {"reports": reports_dir, "models": models_dir}.get(prefix)
    return base / rest if base is not None and rest else None


def artifact(source: str, path: Path | None, role: str) -> Artifact:
    if path is None or not path.is_file():
        return Artifact(source, None, None, None, role)
    stat = path.stat()
    return Artifact(
        path=source,
        size=stat.st_size,
        modified=datetime.fromtimestamp(stat.st_mtime, UTC),
        sha256=sha256_of(path),
        role=role,
    )


def collect_artifacts(
    sources: Sequence[str], reports_dir: Path, models_dir: Path, drift_files: Sequence[str]
) -> list[Artifact]:
    rows = [
        artifact(source, resolve(source, reports_dir, models_dir), "метрики API")
        for source in sources
    ]
    rows += [
        artifact(source, resolve(source, reports_dir, models_dir), "проверка дрейфа")
        for source in drift_files
    ]
    folder = models_dir / BINARY_DIR
    if folder.is_dir():
        for path in sorted(folder.iterdir()):
            if path.suffix in BINARY_SUFFIXES and path.is_file():
                source = f"models/{path.relative_to(models_dir).as_posix()}"
                rows.append(artifact(source, path, "веса модели"))
    return rows


def fingerprint(artifacts: Sequence[Artifact]) -> str:
    lines = "\n".join(f"{item.path}:{item.sha256 or '-'}" for item in artifacts)
    return hashlib.sha256(lines.encode("utf-8")).hexdigest()


def read_drift_validation(reports_dir: Path) -> dict[str, tuple[str, dict[str, Any]]]:
    found: dict[str, tuple[str, dict[str, Any]]] = {}
    for key, relative in DRIFT_ARTIFACTS:
        path = reports_dir / relative
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(payload, dict):
            found[key] = (f"reports/{relative.as_posix()}", payload)
    return found


def size_label(size: int | None) -> str:
    if size is None:
        return DASH
    if size >= 1 << 20:
        return f"{number(size / (1 << 20), 1)}{NNBSP}МиБ"
    if size >= 1 << 10:
        return f"{number(size / (1 << 10), 1)}{NNBSP}КиБ"
    return f"{number(size)}{NNBSP}Б"


def method_name(run: DetectorRun) -> str:
    if run.members:
        return f"Ансамбль из {len(run.members)} моделей"
    base = METHOD_NAMES.get(run.method, run.method)
    return base if run.data == DEFAULT_DATA else f"{base}, {DATA_LABELS.get(run.data, run.data)}"


def family_of(run: DetectorRun) -> str:
    if run.members:
        if run.weights:
            return "Среднее · веса " + "/".join(number(weight, 1) for weight in run.weights)
        return "Среднее вероятностей"
    return (run.kind and KIND_FAMILIES.get(run.kind)) or run.kind or run.method


def data_label(data: str | None) -> str:
    return DATA_LABELS.get(data or "", data or DASH)


def served_run(detector: DetectorReport | None) -> DetectorRun | None:
    if detector is None:
        return None
    return next((run for run in detector.runs if run.in_service), None)


def comparable(detector: DetectorReport) -> list[DetectorRun]:
    test_set = detector.test_set
    runs = detector.runs
    if test_set is not None:
        runs = [
            run
            for run in runs
            if run.split == test_set.split
            and run.test.pixels == test_set.pixels
            and run.test.positives == test_set.positives
        ]
    return sorted(
        runs,
        key=lambda run: (-(run.val.metrics.f1 if run.val else -1.0), run.name),
    )


def metric_cell(value: float | None, interval: Sequence[float] | None) -> str:
    return f"{share(value)}{minor(span(interval))}" if interval else share(value)


def generic(value: Any, depth: int = 0) -> str:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    if value is None:
        return DASH
    if isinstance(value, bool):
        return "да" if value else "нет"
    if isinstance(value, int):
        return number(value)
    if isinstance(value, float):
        return auto(value)
    if isinstance(value, str):
        return esc(value)
    if isinstance(value, list | tuple):
        if not value:
            return DASH
        if depth < 3 and all(isinstance(item, dict) for item in value):
            keys: list[str] = []
            for item in value:
                keys += [key for key in item if key not in keys]
            columns = [
                Column(
                    key,
                    numeric=all(
                        isinstance(item.get(key), int | float)
                        and not isinstance(item.get(key), bool)
                        for item in value
                        if item.get(key) is not None
                    ),
                )
                for key in keys
            ]
            rows = [[generic(item.get(key), depth + 1) for key in keys] for item in value]
            return table(columns, rows)
        return ", ".join(generic(item, depth + 1) for item in value)
    if isinstance(value, dict):
        if depth >= 3:
            return esc(json.dumps(value, ensure_ascii=False))
        items = "".join(
            f"<dt>{mono(key)}</dt><dd>{generic(item, depth + 1)}</dd>"
            for key, item in value.items()
        )
        return f'<dl class="facts generic">{items}</dl>'
    return esc(value)


def extras(model: BaseModel | None, known: set[str]) -> list[str]:
    if model is None:
        return []
    names = [name for name in type(model).model_fields if name not in known]
    names += [name for name in (model.model_extra or {}) if name not in known]
    blocks = []
    for name in names:
        value = getattr(model, name, None)
        if value in (None, [], {}, ""):
            continue
        title = EXTRA_TITLES.get(name, name.replace("_", " "))
        blocks.append(block(title, generic(value), detail=mono(name)))
    return blocks


def summary_section(response: ModelsResponse, index: int) -> str:
    detector = response.detector
    service = detector.service if detector else None
    run = served_run(detector)
    metrics: Metrics | None = run.test.metrics if run else service.test if service else None
    intervals: MetricIntervals | None = (
        run.test.ci95 if run and run.test.ci95 else service.test_ci95 if service else None
    )
    kpis = []
    for key, label, gloss in (
        ("f1", "F1", "баланс точности и полноты"),
        ("iou", "IoU", "перекрытие с разметкой"),
        ("precision", "Precision", "доля верных среди найденного"),
        ("recall", "Recall", "доля найденного из размеченного"),
    ):
        value = getattr(metrics, key) if metrics else None
        interval = getattr(intervals, key) if intervals else None
        kpis.append(
            f'<div class="kpi"><div class="kpi-label">{label}</div>'
            f'<div class="kpi-gloss">{gloss}</div>'
            f'<div class="kpi-value">{share(value)}</div>'
            f'<div class="kpi-ci">95{NNBSP}% ДИ {span(interval)}</div></div>'
        )
    if detector is None or (service is None and run is None):
        body = note("Артефактов детектора нет: метрики сервисной модели не посчитаны.")
        return section(index, "summary", "Сводка", None, body, page=False)
    name = service.name if service else run.name if run else DASH
    threshold = service.threshold if service else run.threshold if run else None
    min_pixels = service.min_pixels if service else None
    post = service.postprocessed_test if service and service.postprocessed_test else None
    if post is None and run and run.postprocessing:
        post = run.postprocessing.test
    bands = service.bands if service and service.bands else (run.inputs if run else None) or []
    training = service.data if service and service.data else run.data if run else None
    test_set = detector.test_set
    sample = DASH
    if test_set:
        parts = [f"{esc(test_set.dataset)} ({esc(data_label(test_set.data))}, разбиение "]
        parts.append(f"{esc(test_set.split)}), test: ")
        pieces = []
        if test_set.patches is not None:
            pieces.append(counted(test_set.patches, ("патч", "патча", "патчей")))
        if test_set.scenes:
            pieces.append(counted(test_set.scenes, ("сцена", "сцены", "сцен")))
        pieces.append(f"{number(test_set.pixels)}{NNBSP}размеченных пикс.")
        pieces.append(f"{number(test_set.positives)}{NNBSP}пикс. мусора")
        sample = "".join(parts) + ", ".join(pieces)
    rows = [
        (
            "Модель",
            f"{mono(name)}{minor(esc(method_name(run)) + ' · ' + esc(family_of(run)))}"
            if run
            else mono(name),
        ),
        ("Конфигурация", mono(run.config_sha256) if run and run.config_sha256 else ""),
        ("Обучение", esc(data_label(training)) if training else ""),
        ("Входные каналы", esc(", ".join(bands)) if bands else ""),
        (
            "Окно",
            f"патч {number(service.patch)}{NNBSP}пикс., шаг {number(service.stride)}{NNBSP}пикс."
            if service and service.patch and service.stride
            else "",
        ),
        (
            "Порог",
            f"{mono(number(threshold, 4) if threshold is not None else DASH)}"
            + (
                f" · {esc(THRESHOLD_SOURCES.get(run.threshold_source, run.threshold_source))}"
                if run and run.threshold_source
                else ""
            ),
        ),
        ("TTA", ("да" if run.tta else "нет") if run and run.tta is not None else ""),
        (
            "Постобработка",
            f"зоны от {number(min_pixels)}{NNBSP}пикс." if min_pixels is not None else "",
        ),
        ("Маска моря", esc(service.sea_mask) if service and service.sea_mask else ""),
        ("Выбор", esc(service.validation) if service and service.validation else ""),
        ("Тестовая выборка", sample),
    ]
    lines = []
    served = service.service_test if service else None
    if served:
        lines.append(
            f"В сервисе на том же test: P {mono(share(served.precision))} · "
            f"R {mono(share(served.recall))} · F1 {mono(share(served.f1))} · "
            f"IoU {mono(share(served.iou))}"
            + (f" — {esc(service.service_mode)}." if service and service.service_mode else ".")
        )
    if post:
        lead = "Исследовательская оценка с TTA" if served else "С постобработкой сервиса"
        lines.append(
            f"{lead} на том же test: P {mono(share(post.precision))} · "
            f"R {mono(share(post.recall))} · F1 {mono(share(post.f1))} · "
            f"IoU {mono(share(post.iou))}."
        )
    if service and service.calibration:
        lines.append(f"Вероятность в интерфейсе: {esc(service.calibration)}.")
    pr_auc = metrics.pr_auc if metrics else None
    if pr_auc is not None:
        lines.append(f"PR-AUC на test: {mono(share(pr_auc))}.")
    if run and run.unlabeled_alarms_per_100km2 is not None:
        lines.append(
            f"На неразмеченной воде test — "
            f"{mono(number(round(run.unlabeled_alarms_per_100km2)))}{NNBSP}пикс. срабатываний "
            f"на 100{NNBSP}км²; в метрики они не входят."
        )
    lines.append(
        f"95{NNBSP}% ДИ — бутстреп по сценам test. Модель, порог и постобработка выбраны на "
        "валидации, test посчитан один раз."
    )
    body = (
        f'<div class="kpis">{"".join(kpis)}</div>'
        + facts(rows)
        + "".join(note(line) for line in lines)
        + "".join(extras(service, KNOWN_SERVICE))
    )
    lede = (
        "Метрики сервисной модели по классу «морской мусор» на пиксельном уровне, "
        "с 95-процентными интервалами."
    )
    return section(index, "summary", "Сводка · сервисный детектор", lede, body, page=False)


def compare_section(detector: DetectorReport, index: int) -> str:
    runs = comparable(detector)
    rows, classes = [], []
    for position, run in enumerate(runs, start=1):
        metrics, ci = run.test.metrics, run.test.ci95
        name = esc(method_name(run))
        if run.in_service:
            name += " " + tag("в сервисе", "served")
        members = minor(esc(" + ".join(run.members))) if run.members else minor(esc(run.name))
        rows.append(
            [
                mono(position),
                f"{name}{members}",
                esc(family_of(run)),
                f"{bar(metrics.f1, ci.f1 if ci else None)} {mono(share(metrics.f1))}"
                + minor(span(ci.f1) if ci else DASH),
                share(metrics.iou),
                share(metrics.precision),
                share(metrics.recall),
                share(metrics.pr_auc),
                share(run.val.metrics.f1 if run.val else None),
                number(run.threshold, 3),
            ]
        )
        classes.append("served" if run.in_service else "")
    columns = [
        Column("№", numeric=True),
        Column("Модель"),
        Column("Архитектура"),
        Column("F1 test · 95 % ДИ", numeric=True),
        Column("IoU", numeric=True),
        Column("P", numeric=True),
        Column("R", numeric=True),
        Column("PR-AUC", numeric=True),
        Column("F1 val", numeric=True),
        Column("Порог", numeric=True),
    ]
    body = table(columns, rows, classes=classes, wide=True)
    others = [run for run in detector.runs if run not in runs]
    if others:
        names = ", ".join(mono(run.name) for run in others)
        body += note(
            f"Ещё {counted(len(others), ('прогон', 'прогона', 'прогонов'))} посчитаны на другом "
            f"наборе test и с этой таблицей не сравнимы: {names}."
        )
    lede = (
        "Метрики — на одном и том же test; строки упорядочены по F1 на валидации, по ней "
        "выбиралась модель. Сервисная модель выделена."
    )
    return section(index, "compare", "Сравнение моделей", lede, body, page=False)


def errors_section(run: DetectorRun, index: int) -> str:
    test = run.test
    rows = [
        [
            esc(CLASS_LABELS.get(item.label, item.label.replace("_", " "))),
            number(item.pixels),
            number(item.false_positives),
            percent(item.false_positives / item.pixels, 1) if item.pixels else DASH,
        ]
        for item in test.false_positives_by_class
    ]
    columns = [
        Column("Класс разметки"),
        Column("Пикселей", numeric=True),
        Column("Ложных срабатываний", numeric=True),
        Column("Доля", numeric=True),
    ]
    counts = []
    if test.true_positives is not None:
        counts.append(f"верно найдено {mono(number(test.true_positives))}")
    if test.false_negatives is not None:
        counts.append(f"пропущено {mono(number(test.false_negatives))}")
    if test.false_positives is not None:
        counts.append(f"ложных {mono(number(test.false_positives))}")
    body = ""
    if counts:
        body += note(
            f"Из {mono(number(test.positives))} пикс. мусора на test: " + ", ".join(counts) + "."
        )
    body += table(columns, rows) if rows else note("Разбивки по классам в артефакте нет.")
    lede = (
        f"Сервисная модель {mono(run.name)} при рабочем пороге {mono(number(run.threshold, 4))}: "
        "где на размеченном фоне test появляются ложные пиксели мусора."
    )
    return section(index, "errors", "Порог и ошибки", lede, body, page=False)


def domain_shift_blocks(detector: DetectorReport) -> list[str]:
    shifted = detector.checks.domain_shift
    sources: list[str] = []
    for run in shifted:
        key = run.source_run or run.method
        if key not in sources:
            sources.append(key)
    blocks = []
    for source in sources:
        origin = next((run for run in detector.runs if run.name == source), None)
        parts = source.split("__")
        home = origin.data if origin else parts[1] if len(parts) > 1 else None
        results = sorted(
            (run for run in shifted if (run.source_run or run.method) == source),
            key=lambda run: run.data != home,
        )
        rows = [
            [
                esc(data_label(run.data)) + minor(esc(run.name)),
                metric_cell(run.test.metrics.f1, run.test.ci95.f1 if run.test.ci95 else None),
                share(run.test.metrics.precision),
                share(run.test.metrics.recall),
                share(run.test.metrics.iou),
            ]
            for run in results
        ]
        columns = [
            Column("Обработка снимков test"),
            Column("F1 · 95 % ДИ", numeric=True),
            Column("P", numeric=True),
            Column("R", numeric=True),
            Column("IoU", numeric=True),
        ]
        text = "Та же модель и тот же порог на тех же патчах test; меняется только обработка."
        if len(results) > 1:
            drop = results[-1].test.metrics.f1 - results[0].test.metrics.f1
            text += f" Разница F1: {mono(signed(drop, 3))}."
        name = method_name(origin) if origin else source
        threshold = results[0].threshold if results else None
        detail = f"{esc(name)} · порог {mono(number(threshold, 3))} заморожен"
        blocks.append(block("Сдвиг домена", table(columns, rows) + note(text), detail))
    return blocks


def region_block(check: LeaveRegionOut) -> str:
    rows = [
        [
            esc(REGION_LABELS.get(region.region, region.region)),
            number(region.positives),
            number(region.threshold, 3),
            share(region.metrics.f1),
            share(region.metrics.precision),
            share(region.metrics.recall),
            share(region.metrics.iou),
        ]
        for region in check.regions
    ]
    pooled = check.pooled
    rows.append(
        [
            "<strong>Сводно</strong>",
            DASH,
            DASH,
            share(pooled.f1),
            share(pooled.precision),
            share(pooled.recall),
            share(pooled.iou),
        ]
    )
    columns = [
        Column("Регион"),
        Column("Пикс. мусора", numeric=True),
        Column("Порог", numeric=True),
        Column("F1", numeric=True),
        Column("P", numeric=True),
        Column("R", numeric=True),
        Column("IoU", numeric=True),
    ]
    method = check.run.split("__")[0]
    detail = f"{esc(METHOD_NAMES.get(method, check.run))} · {mono(check.run)}"
    text = note(f"Протокол: {esc(check.protocol)}.") if check.protocol else ""
    classes = [""] * len(check.regions) + ["total"]
    return block("Новая география", table(columns, rows, classes=classes) + text, detail)


def negatives_block(check: BlackSeaNegatives) -> str:
    rows = [
        [
            esc(NEGATIVE_LABELS.get(item.label, item.label)),
            number(item.polygons),
            number(item.pixels),
            number(item.area_km2, 2),
            number(item.alarm_pixels),
            number(item.polygons_with_alarm),
        ]
        for item in check.classes
    ]
    columns = [
        Column("Класс фона"),
        Column("Полигонов", numeric=True),
        Column("Пикселей", numeric=True),
        Column("км²", numeric=True),
        Column("Срабатываний, пикс.", numeric=True),
        Column("Полигонов со срабатыванием", numeric=True),
    ]
    scene_rows = [
        [
            esc(scene.aoi),
            mono(scene.scene_id),
            number(scene.pixels),
            number(scene.detected_pixels),
            number(scene.zones),
        ]
        for scene in check.scenes
    ]
    scene_columns = [
        Column("Район"),
        Column("Сцена"),
        Column("Пикселей воды", numeric=True),
        Column("Выше порога", numeric=True),
        Column("Зон", numeric=True),
    ]
    polygons = sum(item.polygons for item in check.classes)
    scenes = len({scene.scene_id for scene in check.scenes})
    zones = sum(scene.zones for scene in check.scenes)
    detail = (
        f"{number(check.alarm_pixels)} "
        f"{plural(check.alarm_pixels, ('срабатывание', 'срабатывания', 'срабатываний'))} "
        f"на {number(check.pixels)}{NNBSP}пикс."
    )
    text = [
        f"{counted(polygons, ('полигон', 'полигона', 'полигонов'))} разметки команды на "
        f"{counted(scenes, ('сцене', 'сценах', 'сценах'))}; модель {mono(check.run)}."
    ]
    if check.definition:
        text.append(f"Метрика: {esc(check.definition)}.")
    if check.collection:
        text.append(f"Снимки: {mono(check.collection)}.")
    text.append(
        f"Во всех окнах этих сцен сервис выделил {counted(zones, ('зону', 'зоны', 'зон'))}; "
        "вне полигонов разметки нет, их верность здесь не оценена."
    )
    body = table(columns, rows) + note(" ".join(text))
    if scene_rows:
        body += table(scene_columns, scene_rows, caption="Окна сцен")
    return block("Чёрное море: заведомый фон", body, detail)


def rate_row(label: str, rate: DetectionRate) -> list[str]:
    return [
        esc(label),
        f"{number(rate.detected)} из {number(rate.targets)}",
        f"{bar(rate.rate, rate.ci95)} {mono(share(rate.rate))}",
        span(rate.ci95),
        number(rate.zone_detected) if rate.zone_detected is not None else DASH,
    ]


def plp_block(check: PlasticLitterProject) -> str:
    rows = [rate_row(PLP_LABELS.get(rate.group, rate.group), rate) for rate in check.groups]
    rows += [rate_row(f"пластик {rate.group}", rate) for rate in check.by_size]
    classes = [""] * len(check.groups) + ["sub"] * len(check.by_size)
    columns = [
        Column("Мишени"),
        Column("Выше порога", numeric=True),
        Column("Доля", numeric=True),
        Column("95 % ДИ", numeric=True),
        Column("Зоной", numeric=True),
    ]
    text = []
    if check.description:
        text.append(f"{esc(check.description[:1].upper() + check.description[1:])}.")
    text.append(
        f"Мишеней {number(check.targets)}, пригодных {number(check.usable)}. "
        "Природные мишени — отрицательный контроль: срабатывание на них ложное."
    )
    if check.threshold:
        text.append(f"Порог — {esc(check.threshold)}.")
    background = check.background
    if background:
        text.append(
            f"Фон: {counted(background.zones, ('зона', 'зоны', 'зон'))} на "
            f"{number(background.water_km2, 1)}{NNBSP}км² воды в "
            f"{counted(background.windows, ('окне', 'окнах', 'окнах'))} "
            f"({number(background.zones_per_100_km2, 1)} на 100{NNBSP}км²); в кольце "
            f"{number(background.ring_km2, 1)}{NNBSP}км² вокруг мишеней срабатываний — "
            f"{number(background.ring_alarm_pixels)}."
        )
    body = table(columns, rows, classes=classes) + note(" ".join(text))
    return block("Мишени Plastic Litter Project", body, "Лесбос, пластик известного размера")


def collection_block(check: CollectionCheck) -> str:
    columns = [
        Column("Выборка"),
        Column("Патчей", numeric=True),
        Column("F1 C1", numeric=True),
        Column("F1 L2A", numeric=True),
        Column("C1 − L2A", numeric=True),
        Column("95 % ДИ", numeric=True),
    ]
    rows = [
        [
            esc(f"{row.part}, {row.mode}" + ("" if row.in_service else f" · {row.run}")),
            f"{number(row.patches)} ({counted(row.scenes, ('сцена', 'сцены', 'сцен'))})",
            share(row.c1_f1),
            share(row.l2a_f1),
            signed(row.difference, 3),
            span(row.difference_ci95, 3),
        ]
        for row in check.rows
    ]
    text = (
        f"{esc(check.alignment)}. Сервис читает C1, обучение и основные метрики — на старой "
        f"обработке L2A. Правило выбора модели: {esc(check.rule)}."
    )
    return block("Коллекция сервиса C1", table(columns, rows) + note(text), "те же патчи")


def flag_block(check: ZoneFlagCheck) -> str:
    columns = [
        Column("Выборка"),
        Column("Группа"),
        Column("Отмечено", numeric=True),
        Column("Доля", numeric=True),
    ]
    rows = [
        [
            esc(row.part),
            esc(row.group),
            f"{number(row.flagged)} из {number(row.objects)}",
            share(row.share),
        ]
        for row in check.shares
    ]
    body = table(columns, rows)
    if check.discrimination:
        items = "".join(
            f"<li>{esc(row.part)}: {esc(row.measure)} — {mono(share(row.value))}"
            + (f", 95{NNBSP}% ДИ {span(row.ci95)}" if row.ci95 else "")
            + "</li>"
            for row in check.discrimination
        )
        body += f'<ul class="limits">{items}</ul>'
    body += note(f"Правило: {esc(check.rule)}. Флаг зону не скрывает.")
    status = "в сервисе" if check.in_service else "выключен"
    return block(f"Флаг {check.title}", body, status)


def checks_section(response: ModelsResponse, index: int) -> str | None:
    detector = response.detector
    if detector is None:
        return None
    checks = detector.checks
    blocks = domain_shift_blocks(detector)
    blocks += [region_block(check) for check in checks.leave_region_out]
    if checks.black_sea_negatives:
        blocks.append(negatives_block(checks.black_sea_negatives))
    if checks.plp:
        blocks.append(plp_block(checks.plp))
    if checks.collection:
        blocks.append(collection_block(checks.collection))
    blocks += [flag_block(check) for check in checks.zone_flags]
    blocks += extras(checks, KNOWN_CHECKS)
    blocks += extras(detector, KNOWN_DETECTOR)
    blocks += extras(response, KNOWN_RESPONSE)
    if not blocks:
        return None
    lede = (
        "Порог заморожен: на этих данных ничего не подбиралось. Другая обработка снимков, "
        "новые регионы, фон Чёрного моря и мишени с известным пластиком."
    )
    return section(index, "checks", "Проверки вне обучения", lede, "".join(blocks), page=True)


def mean_sd(mean: float, sd: float | None) -> str:
    text = mono(number(mean, 1))
    return text + minor(f"± {number(sd, 1)}") if sd is not None else text


def evaluation_row(item: ConcentrationEvaluation) -> list[str]:
    difference = item.difference_mae
    diff = DASH
    if difference:
        low, high = difference.ci
        diff = f"{mono(signed(difference.mean))}" + minor(
            f"{number(difference.confidence * 100)}{NNBSP}% ДИ [{signed(low)}; {signed(high)}]"
        )
    coverage = item.nested_coverage
    return [
        esc(ROLE_LABELS.get(item.role or "", item.role or item.report)) + minor(esc(item.report)),
        mean_sd(item.baseline_mae.mean, item.baseline_mae.sd),
        mean_sd(item.nested_mae.mean, item.nested_mae.sd),
        f"{number(item.baseline_rmse.mean, 1)} / {number(item.nested_rmse.mean, 1)}",
        diff,
        share(coverage.mean) if coverage else DASH,
        "значим" if item.gain_over_median else "не значим",
    ]


def served_facts(served: ServedConcentration) -> str:
    unit = UNIT_LABELS.get(served.unit or "", served.unit or "")
    model = "медиана полевых данных" if served.model == "median" else served.model
    value = (
        f" {mono(number(served.value, 1))}{NNBSP}{esc(unit)}" if served.value is not None else ""
    )
    coverage = ""
    if served.coverage_nominal is not None:
        coverage = (
            f"интервал {percent(served.coverage_nominal)}, эмпирическое покрытие "
            f"{mono(share(served.coverage_empirical))}"
        )
    return facts(
        [
            ("В сервисе", f"{esc(model)}{value}"),
            ("Интервал", coverage),
            ("Почему", esc(served.reason) if served.reason else ""),
        ]
    )


def profile_block(profile: ConcentrationProfile) -> str:
    columns = [
        Column("Оценка"),
        Column("MAE медианы", numeric=True),
        Column("MAE вложенного выбора", numeric=True),
        Column("RMSE мед. / выбора", numeric=True),
        Column("Разница MAE", numeric=True),
        Column("Покрытие", numeric=True),
        Column("Выигрыш", numeric=True),
    ]
    rows = [evaluation_row(item) for item in profile.evaluations]
    body = table(columns, rows) if rows else note("Кросс-валидации для профиля нет.")
    selections = [
        f"{esc(ROLE_LABELS.get(item.role or '', item.report))}: {esc(item.selection)}"
        + (
            f"; {counted(item.repetitions, ('повтор', 'повтора', 'повторов'))} CV"
            if item.repetitions
            else ""
        )
        for item in profile.evaluations
        if item.selection
    ]
    if selections:
        body += note(". ".join(selections) + ".")
    if profile.served:
        body += served_facts(profile.served)
    detail_parts = [mono(profile.profile)]
    if profile.target_key:
        detail_parts.append(mono(profile.target_key))
    if profile.events is not None:
        detail_parts.append(
            f"{counted(profile.events, ('событие', 'события', 'событий'))}"
            + (
                f", {counted(profile.survey_days, ('день', 'дня', 'дней'))} съёмки"
                if profile.survey_days is not None
                else ""
            )
        )
    title = PROFILE_LABELS.get(profile.profile, profile.profile)
    return block(title, body, " · ".join(detail_parts))


def link_block(link: SatelliteLink) -> str:
    rows = [
        [mono(item.feature), signed(item.spearman, 2), number(item.p_value, 2)]
        for item in link.correlations
    ]
    columns = [
        Column("Признак снимка"),
        Column("ρ Спирмена", numeric=True),
        Column("p", numeric=True),
    ]
    values = [item.p_value for item in link.correlations if item.p_value is not None]
    lowest = min(values) if values else None
    text = (
        f"{counted(link.events, ('пара', 'пары', 'пар'))} «снимок — измерение того же дня»"
        + (f", детектор {mono(link.detector)}" if link.detector else "")
        + f"; наименьшее p = {mono(number(lowest, 2))}"
    )
    if lowest is not None and lowest < SIGNIFICANCE:
        text += "."
    else:
        text += " — значимой связи нет, поэтому концентрация по снимку не выводится."
    return block("Связь «снимок → концентрация»", table(columns, rows) + note(text))


def concentration_section(concentration: ConcentrationReport, index: int) -> str:
    blocks = [profile_block(profile) for profile in concentration.profiles]
    rules = {
        profile.served.rule
        for profile in concentration.profiles
        if profile.served and profile.served.rule
    }
    tail = ""
    if len(rules) == 1:
        tail = note(f"Правило выдачи в сервис: {esc(next(iter(rules)))}.")
    if concentration.satellite_link:
        blocks.append(link_block(concentration.satellite_link))
    blocks += extras(concentration, KNOWN_CONCENTRATION)
    method = note(
        "MAE и RMSE — в единицах профиля, среднее ± SD по повторам кросс-валидации; группы — "
        "дни съёмки. Разница — вложенный выбор минус медиана, кластерный бутстреп по дням. "
        "Покрытие — доля измерений внутри интервала вложенного выбора. Шорт-лист составлен "
        "после разведки на тех же данных, его оценка оптимистична."
    )
    lede = (
        "Кросс-валидация по дням съёмки против медианы профиля. Модель идёт в сервис, только "
        "если её выигрыш над медианой значим."
    )
    return section(
        index,
        "concentration",
        "Концентрация, шт./км²",
        lede,
        "".join(blocks) + method + tail,
        page=True,
    )


def verdict_list(lines: Sequence[Any]) -> str:
    items: list[str] = []
    for line in lines:
        if not isinstance(line, str) or not line.strip():
            continue
        nested = line.startswith(" ")
        items.append(f'<li class="{"nested" if nested else ""}">{esc(line.strip())}</li>')
    return f'<ul class="verdict">{"".join(items)}</ul>' if items else ""


def validation_block(title: str, source: str, payload: dict[str, Any]) -> str:
    parts = []
    question = payload.get("question")
    if isinstance(question, str):
        parts.append(f'<p class="question">Вопрос: {esc(question)}.</p>')
    verdict = payload.get("verdict")
    if isinstance(verdict, list):
        parts.append(verdict_list(verdict))
    caveats = payload.get("caveats")
    if isinstance(caveats, list) and caveats:
        parts.append(f"<h4>Оговорки</h4>{verdict_list(caveats)}")
    stamp = payload.get("created_at")
    config = payload.get("config") if isinstance(payload.get("config"), dict) else {}
    meta = [mono(source)]
    if isinstance(stamp, str):
        meta.append(f"посчитан {esc(stamp.replace('T', ' ')[:16])} UTC")
    if isinstance(config.get("sha256"), str):
        meta.append(f"конфиг {mono(config['sha256'][:12])}")
    parts.append(note(" · ".join(meta)))
    return block(title, "".join(parts))


def drift_section(
    drift: DriftMethod | None,
    validation: dict[str, tuple[str, dict[str, Any]]],
    index: int,
) -> str | None:
    if drift is None and not validation:
        return None
    blocks = []
    if drift is not None:
        stokes = "/".join("вкл" if on else "выкл" for on in drift.stokes)
        windages = ", ".join(number(value * 100, 1).removesuffix(",0") for value in drift.windages)
        rows = [
            ("Модель", mono(drift.model)),
            ("Статус", f"{tag(drift.label, 'warn')} {esc(drift.reason)}."),
            ("Скорость", esc(drift.velocity)),
            ("Шаг", esc(drift.integration)),
            (
                "Ансамбль",
                f"парусность {windages}{NNBSP}% × стоксов дрейф {stokes} × "
                f"{number(drift.particles)} частиц = {number(drift.members)} на зону",
            ),
            (
                "Диффузия",
                f"{number(drift.diffusivity_m2s, 0 if drift.diffusivity_m2s.is_integer() else 1)}"
                f"{NNBSP}м²/с",
            ),
            (
                "Горизонты",
                f"{', '.join(str(hour) for hour in drift.horizons_h)}{NNBSP}ч вперёд; "
                f"назад до {number(drift.max_hindcast_hours)}{NNBSP}ч",
            ),
            (
                "Форсинг",
                esc("; ".join([drift.forcing.currents, drift.forcing.waves, *drift.forcing.wind])),
            ),
        ]
        blocks.append(block("Метод сервиса", facts(rows), detail=mono("GET /api/v1/models")))
        blocks += extras(drift, KNOWN_DRIFT)
    titles = {"drifters": "Сверка с дрифтерами", "spread": "Разброс ансамбля и огибающие"}
    for key, (source, payload) in validation.items():
        blocks.append(validation_block(titles.get(key, key), source, payload))
    if not validation:
        blocks.append(note("Артефактов проверки дрейфа по траекториям нет."))
    lede = (
        "Ансамбль частиц на течениях, волнах и ветре Open-Meteo. Ниже — метод из API и итоги "
        "проверки по реальным траекториям дословно из артефактов проверки."
    )
    return section(index, "drift", "Сценарий дрейфа", lede, "".join(blocks), page=True)


def provenance_section(
    response: ModelsResponse, artifacts: Sequence[Artifact], digest: str, index: int
) -> str:
    detector = response.detector
    rows: list[tuple[str, str]] = []
    if detector and detector.test_set:
        test_set = detector.test_set
        rows.append(
            (
                "Тест детектора",
                f"{esc(test_set.dataset)} · {esc(data_label(test_set.data))} · разбиение "
                f"{mono(test_set.split)}",
            )
        )
    if detector:
        variants = sorted({run.data for run in detector.runs})
        rows.append(
            (
                "Варианты данных",
                ", ".join(f"{esc(data_label(item))} ({mono(item)})" for item in variants),
            )
        )
        plp = detector.checks.plp
        if plp and plp.description:
            rows.append(("Внешняя проверка", esc(plp.description)))
        negatives = detector.checks.black_sea_negatives
        if negatives:
            aois = sorted({scene.aoi for scene in negatives.scenes})
            rows.append(
                (
                    "Фон Чёрного моря",
                    f"{mono(negatives.collection or DASH)} · районы: {esc(', '.join(aois))}",
                )
            )
    if response.concentration:
        profiles = [
            f"{mono(profile.profile)}"
            + (f" → {mono(profile.target_key)}" if profile.target_key else "")
            for profile in response.concentration.profiles
        ]
        rows.append(("Полевые профили", ", ".join(profiles)))
    if response.drift:
        forcing = response.drift.forcing
        rows.append(
            ("Форсинг дрейфа", esc("; ".join([forcing.currents, forcing.waves, *forcing.wind])))
        )
    columns = [
        Column("Артефакт"),
        Column("Роль"),
        Column("Размер", numeric=True),
        Column("Изменён, UTC", numeric=True),
        Column("SHA-256"),
    ]
    table_rows = [
        [
            mono(item.path),
            esc(item.role),
            size_label(item.size),
            item.modified.strftime("%d.%m.%Y %H:%M") if item.modified else DASH,
            f'<span class="hash">{esc(item.sha256 or "файл не найден")}</span>',
        ]
        for item in artifacts
    ]
    body = (
        facts(rows)
        + table(columns, table_rows, wide=True)
        + note(
            f"Отпечаток набора — SHA-256 по строкам «путь:хеш» в порядке таблицы: "
            f'<span class="hash">{esc(digest)}</span>. Пути — относительно корня репозитория.'
        )
    )
    lede = "Откуда числа этого отчёта: наборы данных и файлы артефактов с контрольными суммами."
    return section(index, "provenance", "Происхождение данных", lede, body, page=True)


def derived_limits(response: ModelsResponse) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    detector = response.detector
    run = served_run(detector)
    if run and run.test.ci95:
        items.append(
            (
                "Малая тестовая выборка",
                f"test — {number(run.test.positives)}{NNBSP}пикс. мусора; 95{NNBSP}% ДИ F1 "
                f"сервисной модели {span(run.test.ci95.f1)}.",
            )
        )
    if detector:
        for check in detector.checks.leave_region_out:
            worst = min(check.regions, key=lambda region: region.metrics.f1, default=None)
            if worst is None:
                continue
            items.append(
                (
                    "Новая география",
                    f"при исключении региона F1 сводно {share(check.pooled.f1)} "
                    f"({esc(check.run)}); хуже всего — "
                    f"{esc(REGION_LABELS.get(worst.region, worst.region))}, "
                    f"F1 {share(worst.metrics.f1)}.",
                )
            )
        plp = detector.checks.plp
        group = (
            next((item for item in plp.groups if item.group == "plastic_or_mixed"), None)
            if plp
            else None
        )
        if group:
            items.append(
                (
                    "Мишени PLP",
                    f"выше порога {number(group.detected)} из {number(group.targets)} "
                    f"мишеней с пластиком, доля {share(group.rate)}, 95{NNBSP}% ДИ "
                    f"{span(group.ci95)}.",
                )
            )
    concentration = response.concentration
    if concentration:
        served = [profile for profile in concentration.profiles if profile.served]
        medians = [
            profile for profile in served if profile.served and not profile.served.gain_over_median
        ]
        if served and len(medians) == len(served):
            items.append(
                (
                    "Концентрация",
                    f"ни в одном из {counted(len(served), ('профиля', 'профилей', 'профилей'))} "
                    "выигрыш над медианой не значим: сервис выдаёт медиану полевых данных "
                    "профиля с интервалом, а не оценку по снимку.",
                )
            )
        link = concentration.satellite_link
        values = (
            [item.p_value for item in link.correlations if item.p_value is not None] if link else []
        )
        if link and (not values or min(values) >= SIGNIFICANCE):
            items.append(
                (
                    "Снимок → концентрация",
                    f"на {counted(link.events, ('паре', 'парах', 'парах'))} значимой связи нет "
                    f"(наименьшее p = {number(min(values), 2) if values else DASH}).",
                )
            )
    if response.drift:
        items.append(("Дрейф", f"{esc(response.drift.label)}: {esc(response.drift.reason)}."))
    return items


def limits_section(response: ModelsResponse, index: int) -> str:
    rows = derived_limits(response)
    derived = "".join(f"<li><strong>{esc(term)}.</strong> {text}</li>" for term, text in rows)
    known = "".join(
        f"<li><strong>{esc(term)}:</strong> {esc(text)}</li>" for term, text in LIMITATIONS
    )
    body = ""
    if derived:
        body += f'<h3>Из артефактов</h3><ul class="limits">{derived}</ul>'
    body += f'<h3>Известные ошибки детектора</h3><ul class="limits">{known}</ul>'
    lede = "Где модели ошибаются и чего этот отчёт не доказывает."
    return section(index, "limits", "Ограничения", lede, body, page=False)


STYLE = """
:root{--paper:#fff;--app:#e9e7e0;--panel:#f5f4ef;--hair:#d8d6ce;--ink:#111416;
--ink2:#4a5256;--ink3:#5c6569;--accent:#9c3399;--wash:rgba(156,51,153,.07);
--caution:#835f00;
--sans:"IBM Plex Sans",-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",
Arial,sans-serif;
--serif:"Source Serif 4","Source Serif Pro","PT Serif",Georgia,"Times New Roman",serif;
--mono:"IBM Plex Mono",ui-monospace,"SF Mono",Menlo,Consolas,"Liberation Mono",monospace;
color-scheme:light}
*{box-sizing:border-box}
html{background:var(--app)}
body{margin:0;color:var(--ink);font:9.5pt/1.45 var(--sans);font-variant-numeric:tabular-nums;
-webkit-print-color-adjust:exact;print-color-adjust:exact;overflow-wrap:break-word}
.toolbar{position:sticky;top:0;z-index:1;display:flex;flex-wrap:wrap;gap:8px 12px;
align-items:center;justify-content:center;padding:8px 16px;background:var(--panel);
border-bottom:1px solid var(--hair);font-size:12px;color:var(--ink2)}
.toolbar button,.toolbar a{display:inline-flex;align-items:center;height:28px;padding:0 10px;
border:1px solid #7b8083;border-radius:3px;background:#fff;color:var(--ink);
font:500 13px var(--sans);text-decoration:none;cursor:pointer}
.toolbar button:hover,.toolbar a:hover{background:var(--panel)}
.sheet{width:210mm;max-width:100%;margin:24px auto;padding:16mm 15mm;background:var(--paper);
box-shadow:0 0 0 1px var(--hair),0 12px 32px rgba(40,38,30,.12)}
.cover{border-bottom:1.5pt solid var(--ink);padding-bottom:12pt}
.eyebrow{margin:0;font:600 7.5pt var(--sans);letter-spacing:.1em;text-transform:uppercase;
color:var(--ink3)}
h1{margin:8pt 0 6pt;font:400 26pt/1.12 var(--serif);letter-spacing:-.01em}
h2{margin:0;font:400 16pt/1.2 var(--serif)}
h3{margin:16pt 0 6pt;font:600 7.5pt/1.3 var(--sans);letter-spacing:.09em;text-transform:uppercase;
color:var(--ink2)}
h3 .detail{margin-left:8pt;font:400 8.5pt var(--sans);letter-spacing:0;text-transform:none}
h4{margin:10pt 0 4pt;font:600 8pt var(--sans);color:var(--ink2)}
.cover .lede{font-size:10.5pt;max-width:62ch}
.meta{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:6pt 14pt;margin:12pt 0 0}
.meta div{border-top:.75pt solid var(--hair);padding-top:4pt}
.meta dt{font-size:7.5pt;color:var(--ink3)}
.meta dd{margin:1pt 0 0;font:500 8.5pt var(--mono);word-break:break-all}
.toc{margin:10pt 0 0;padding:0;list-style:none;columns:2;column-gap:14pt;font-size:8.5pt}
.toc li{display:flex;gap:6pt;padding:1.5pt 0;border-bottom:.5pt dotted var(--hair)}
.toc a{color:var(--ink);text-decoration:none}
.toc span{min-width:14pt;font-family:var(--mono);color:var(--ink3)}
.section{margin-top:20pt;padding-top:9pt;border-top:1pt solid var(--ink)}
.section-head{display:flex;gap:10pt;align-items:baseline}
.index{min-width:14pt;font:8pt var(--mono);color:var(--ink3)}
.lede{max-width:72ch;margin:4pt 0 8pt;color:var(--ink2)}
.section>.lede{margin-left:24pt}
table{width:100%;margin:4pt 0 4pt;border-collapse:collapse;font-size:8.3pt}
caption{padding:6pt 0 3pt;text-align:left;font-size:7.5pt;color:var(--ink3)}
th,td{padding:3pt 7pt 3pt 0;border-bottom:.5pt solid var(--hair);text-align:left;
vertical-align:top;font-weight:400}
th[scope=row]{color:var(--ink)}
thead th{padding-bottom:4pt;border-bottom:1pt solid var(--ink);color:var(--ink2);font-weight:500;
vertical-align:bottom}
.num{text-align:right;white-space:nowrap;font-family:var(--mono);font-size:8pt}
thead .num{font-family:var(--sans);font-size:8.3pt;white-space:normal}
th:last-child,td:last-child{padding-right:0}
table.wide{font-size:7.8pt}
table.wide .num{font-size:7.6pt}
tr.served>*{background:var(--wash)}
tr.served>th:first-child{box-shadow:inset 2pt 0 0 var(--accent)}
tr.total>*{border-top:1pt solid var(--ink);font-weight:600}
tr.sub>th{padding-left:10pt;color:var(--ink2)}
.mono{font-family:var(--mono)}
.minor{display:block;margin-top:1pt;font:7.2pt/1.3 var(--mono);color:var(--ink3);
white-space:normal;word-break:break-all}
.note{margin:4pt 0 0;font-size:8pt;line-height:1.4;color:var(--ink3);max-width:none}
.tag{display:inline-block;margin-left:2pt;padding:0 3pt;border:.75pt solid currentColor;
border-radius:2pt;font:600 6.5pt/1.5 var(--sans);letter-spacing:.06em;text-transform:uppercase;
vertical-align:1pt;white-space:nowrap}
.tag.served{color:var(--accent)}
.tag.warn{margin-left:0;color:var(--caution)}
.kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:0 14pt;margin:8pt 0 10pt}
.kpi{padding-top:5pt;border-top:1pt solid var(--ink)}
.kpi-label{font-weight:600;font-size:8.5pt;color:var(--ink2)}
.kpi-gloss{font-size:7.5pt;color:var(--ink3)}
.kpi-value{margin-top:6pt;font:500 21pt/1.1 var(--mono)}
.kpi-ci{margin-top:2pt;font:7.5pt var(--mono);color:var(--ink2)}
dl.facts{display:grid;grid-template-columns:32mm minmax(0,1fr);gap:3pt 10pt;margin:8pt 0}
dl.facts dt{color:var(--ink3);font-size:8.3pt}
dl.facts dd{margin:0;font-size:8.5pt}
dl.generic{grid-template-columns:auto minmax(0,1fr)}
.block{margin-top:4pt}
.bar{vertical-align:middle;margin-right:3pt}
.bar .track{fill:var(--hair)}
.bar .fill{fill:var(--ink2)}
.bar .whisker{fill:none;stroke:var(--ink3);stroke-width:1}
.question{margin:2pt 0 4pt;color:var(--ink2);font-style:italic}
ul.verdict,ul.limits{margin:4pt 0;padding:0;list-style:none}
ul.verdict li{position:relative;padding:2pt 0 2pt 10pt;border-bottom:.5pt solid var(--hair);
font-size:8.2pt}
ul.verdict li:before{content:"";position:absolute;left:0;top:7pt;width:4pt;height:4pt;
background:var(--ink2)}
ul.verdict li.nested{padding-left:22pt;color:var(--ink2);font-size:7.8pt}
ul.verdict li.nested:before{left:12pt;width:3pt;height:3pt;background:var(--ink3)}
ul.limits li{padding:3pt 0;border-bottom:.5pt solid var(--hair)}
.hash{font:7pt/1.3 var(--mono);word-break:break-all;color:var(--ink2)}
.footer{margin-top:22pt;padding-top:6pt;border-top:.75pt solid var(--hair);font-size:7.5pt;
color:var(--ink3)}
@page{size:A4;margin:14mm 14mm 16mm;
@bottom-left{content:"Littora · отчёт валидации моделей";font:7pt sans-serif;color:#5c6569}
@bottom-right{content:counter(page) " / " counter(pages);font:7pt sans-serif;color:#5c6569}}
@media screen and (max-width:820px){.sheet{margin:0;padding:24px 16px;box-shadow:none}
.meta,.kpis{grid-template-columns:repeat(2,minmax(0,1fr));gap:8pt 14pt}.toc{columns:1}
table.wide{display:block;overflow-x:auto}}
@media print{html{background:none}.toolbar{display:none}
.sheet{width:auto;margin:0;padding:0;box-shadow:none}
.page{break-before:page;margin-top:0;border-top-width:1pt}
h2,h3,h4,.section-head,caption{break-after:avoid}
tr,.kpi,.meta,dl.facts>*,ul li{break-inside:avoid}
thead{display:table-header-group}a{color:inherit;text-decoration:none}}
"""

PRINT_SCRIPT = (
    '<script>(function(){var b=document.getElementById("print");'
    'if(b)b.addEventListener("click",function(){window.print()});'
    "%s})();</script>"
)
AUTO_PRINT = (
    'window.addEventListener("load",function(){setTimeout(function(){window.print()},300)});'
)

CONTENTS = (
    ("summary", "Сводка · сервисный детектор"),
    ("compare", "Сравнение моделей"),
    ("errors", "Порог и ошибки"),
    ("checks", "Проверки вне обучения"),
    ("concentration", "Концентрация, шт./км²"),
    ("drift", "Сценарий дрейфа"),
    ("provenance", "Происхождение данных"),
    ("limits", "Ограничения"),
)


def download_name(generated_at: datetime) -> str:
    return f"littora-models-report-{generated_at.astimezone(UTC).strftime('%Y%m%d-%H%M')}.html"


def render_models_report(
    response: ModelsResponse,
    *,
    reports_dir: Path,
    models_dir: Path,
    version: str,
    generated_at: datetime,
    auto_print: bool = False,
    standalone: bool = False,
) -> str:
    validation = read_drift_validation(reports_dir)
    artifacts = collect_artifacts(
        response.sources,
        reports_dir,
        models_dir,
        [source for source, _ in validation.values()],
    )
    digest = fingerprint(artifacts)
    detector = response.detector
    run = served_run(detector)
    sections: dict[str, str | None] = {}
    position = 1

    def add(key: str, build: Any) -> None:
        nonlocal position
        html_text = build(position)
        if html_text:
            sections[key] = html_text
            position += 1

    add("summary", lambda index: summary_section(response, index))
    if detector and detector.runs:
        add("compare", lambda index: compare_section(detector, index))
    if run is not None:
        add("errors", lambda index: errors_section(run, index))
    add("checks", lambda index: checks_section(response, index))
    if response.concentration:
        concentration = response.concentration
        add("concentration", lambda index: concentration_section(concentration, index))
    add("drift", lambda index: drift_section(response.drift, validation, index))
    add("provenance", lambda index: provenance_section(response, artifacts, digest, index))
    add("limits", lambda index: limits_section(response, index))

    numbered = [key for key, _ in CONTENTS if key in sections]
    toc = "".join(
        f'<li><span>{numbered.index(key) + 1:02d}</span><a href="#{key}">{esc(title)}</a></li>'
        for key, title in CONTENTS
        if key in sections
    )
    service_name = (
        detector.service.name if detector and detector.service else run.name if run else DASH
    )
    meta = [
        ("Сформирован", when(generated_at)),
        ("Версия API", version),
        ("Сервисный детектор", service_name),
        ("Артефактов", f"{len(artifacts)} · {digest[:12]}"),
    ]
    meta_html = "".join(
        f"<div><dt>{esc(label)}</dt><dd>{esc(value)}</dd></div>" for label, value in meta
    )
    toolbar = ""
    if not standalone:
        toolbar = (
            '<div class="toolbar"><span>Для PDF выберите «Сохранить как PDF» в диалоге печати, '
            "формат A4.</span>"
            '<button type="button" id="print">Печать / PDF</button>'
            '<a href="report.html?download=1" download>Скачать HTML</a></div>'
        )
    script = "" if standalone else PRINT_SCRIPT % (AUTO_PRINT if auto_print else "")
    stamp = generated_at.astimezone(UTC)
    title = f"{PRODUCT} — {TITLE.lower()} {stamp.strftime('%Y-%m-%d')}"
    return (
        "<!doctype html>"
        '<html lang="ru"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<meta name="generator" content="{esc(PRODUCT)} API {esc(version)}">'
        f'<meta name="dcterms.created" content="{esc(stamp.isoformat(timespec="seconds"))}">'
        f"<title>{esc(title)}</title><style>{STYLE}</style></head><body>"
        f"{toolbar}"
        '<main class="sheet">'
        '<header class="cover">'
        f'<p class="eyebrow">{PRODUCT} · модели и качество · {esc(TITLE.lower())}</p>'
        "<h1>Насколько можно доверять детекции</h1>"
        '<p class="lede">Детектор плавающего макропластика на снимках Sentinel-2, оценка '
        "концентрации по полевым профилям и сценарий дрейфа. Все числа взяты из артефактов "
        "оценки на сервере — тех же, что отдаёт GET /api/v1/models; отчёт ничего не "
        "пересчитывает.</p>"
        f'<dl class="meta">{meta_html}</dl>'
        f'<ol class="toc">{toc}</ol>'
        "</header>"
        f"{''.join(text for text in sections.values() if text)}"
        '<p class="footer">'
        f"{PRODUCT} · GET /api/v1/models/report.html · сформирован {esc(when(generated_at))} · "
        f"отпечаток артефактов {esc(digest)}</p>"
        "</main>"
        f"{script}</body></html>"
    )
