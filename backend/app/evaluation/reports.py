from __future__ import annotations

import csv
import json
import logging
import threading
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from app.analysis.vessels import decimal
from app.schemas.models import (
    BlackSeaNegatives,
    ClassFalsePositives,
    CollectionCheck,
    CollectionCheckRow,
    ConcentrationEvaluation,
    ConcentrationProfile,
    ConcentrationReport,
    Correlation,
    DetectionRate,
    DetectorChecks,
    DetectorReport,
    DetectorRun,
    DetectorService,
    DetectorTestSet,
    Difference,
    FlagDiscrimination,
    FlagShare,
    LeaveRegionOut,
    MeanSd,
    MetricIntervals,
    Metrics,
    NegativeClass,
    NegativeScene,
    PlasticLitterProject,
    PlpBackground,
    Postprocessing,
    RegionResult,
    SatelliteLink,
    SatellitePair,
    ServedConcentration,
    SplitEvaluation,
    ZoneFlagCheck,
)

logger = logging.getLogger("littora.evaluation")

DETECTOR_METRICS = Path("metrics") / "detector"
CONCENTRATION_METRICS = Path("metrics") / "concentration"
DETECTOR_SPLITS = Path("splits") / "detector_marida.csv"
DETECTOR_MANIFEST = Path("detector") / "service" / "detector.json"
CONCENTRATION_SERVICE = Path("concentration") / "service"
CALIBRATION_PREFIX = "calibration__"
SUMMARY_FILE = "summary.json"
CONCENTRATION_REPORTS = ("broad", "compact")
PLP_GROUPS = ("plastic", "mixed", "plastic_or_mixed", "natural_controls")
METRIC_KEYS = ("precision", "recall", "f1", "iou")
EVALUATION_DATASET = "MARIDA"
FLAGS_DIR = Path("flags")
VESSELS_REPORT = "vessels.json"
STABILITY_REPORT = "stability.json"
C1_REPORT = "c1_check.json"
C1_MODES = {
    "tolerant": "объекты, допуск 1 пикс.",
    "strict": "пиксели, точное совмещение",
}
FLAG_GROUPS = {
    "ship": "суда",
    "debris": "обломки",
    "other_labeled": "другие размеченные",
    "false_labeled": "ложные размеченные",
    "unlabeled": "неразмеченные",
}
DISCRIMINATION = (
    ("agreement_auc", "AUC согласия: обломки против ложных"),
    ("agreement_auc_within_probability", "то же внутри групп по вероятности"),
    ("probability_auc", "AUC вероятности, для сравнения"),
)

Signature = tuple[tuple[str, int, int], ...]


class ArtifactError(ValueError):
    pass


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _float(value: Any) -> float | None:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def _int(value: Any) -> int | None:
    return int(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def _interval(value: Any) -> tuple[float, float] | None:
    if isinstance(value, list | tuple) and len(value) == 2:
        low, high = _float(value[0]), _float(value[1])
        if low is not None and high is not None:
            return low, high
    return None


def _metrics(block: Any) -> Metrics | None:
    if not isinstance(block, dict):
        return None
    values = {key: _float(block.get(key)) for key in METRIC_KEYS}
    if any(value is None for value in values.values()):
        return None
    return Metrics(**values, pr_auc=_float(block.get("pr_auc")))


def _intervals(block: Any) -> MetricIntervals | None:
    if not isinstance(block, dict):
        return None
    values = {key: _interval(block.get(key)) for key in METRIC_KEYS}
    if any(value is None for value in values.values()):
        return None
    return MetricIntervals(**values)


def _mean_sd(block: Any) -> MeanSd | None:
    if not isinstance(block, dict) or _float(block.get("mean")) is None:
        return None
    return MeanSd(mean=block["mean"], sd=_float(block.get("sd")))


def _difference(block: Any) -> Difference | None:
    if not isinstance(block, dict):
        return None
    mean, ci = _float(block.get("mean")), _interval(block.get("ci"))
    if mean is None or ci is None:
        return None
    return Difference(
        mean=mean,
        confidence=_float(block.get("confidence")) or 0.95,
        ci=ci,
        relative=_float(block.get("relative")),
        relative_ci=_interval(block.get("relative_ci")),
    )


def _false_positives(block: Any) -> list[ClassFalsePositives]:
    if not isinstance(block, dict):
        return []
    rows = [
        ClassFalsePositives(
            label=label,
            pixels=_int(values.get("pixels")) or 0,
            false_positives=_int(values.get("false_positives")) or 0,
        )
        for label, values in block.items()
        if isinstance(values, dict)
    ]
    return sorted(rows, key=lambda row: (-row.false_positives, row.label))


def _split(block: Any, ci: Any) -> SplitEvaluation | None:
    metrics = _metrics(block)
    if metrics is None:
        return None
    pixels, positives = _int(block.get("pixels")), _int(block.get("positives"))
    if pixels is None or positives is None:
        return None
    return SplitEvaluation(
        pixels=pixels,
        positives=positives,
        true_positives=_int(block.get("tp")),
        false_positives=_int(block.get("fp")),
        false_negatives=_int(block.get("fn")),
        metrics=metrics,
        ci95=_intervals(ci),
        false_positives_by_class=_false_positives(block.get("false_positives_by_class")),
    )


def _tta(value: Any) -> bool | None:
    if isinstance(value, dict):
        value = value.get("used")
    return value if isinstance(value, bool) else None


def _strings(value: Any) -> list[str] | None:
    if isinstance(value, list) and value and all(isinstance(item, str) for item in value):
        return list(value)
    return None


def _inputs(run: dict[str, Any], config: dict[str, Any]) -> list[str] | None:
    features = config.get("features")
    explicit = features.get("bands") if isinstance(features, dict) else None
    return _strings(run.get("features")) or _strings(explicit)


def _postprocessing(block: Any) -> Postprocessing | None:
    if not isinstance(block, dict) or not isinstance(block.get("chosen"), dict):
        return None
    chosen = block["chosen"]
    threshold, min_pixels = _float(chosen.get("threshold")), _int(chosen.get("min_pixels"))
    if threshold is None or min_pixels is None:
        return None
    return Postprocessing(
        threshold=threshold,
        min_pixels=min_pixels,
        scene_classes=bool(chosen.get("scl")),
        ship_veto=bool(chosen.get("ship_veto")),
        test=_metrics(block.get("test")),
    )


def parse_run(payload: dict[str, Any], service_name: str | None) -> DetectorRun:
    config = payload.get("config") if isinstance(payload.get("config"), dict) else {}
    test = _split(payload.get("test"), payload.get("test_ci95_scene_bootstrap"))
    threshold = _float(payload.get("threshold"))
    name, data = payload.get("name"), payload.get("data")
    if test is None or threshold is None or not isinstance(name, str) or not isinstance(data, str):
        raise ArtifactError("нет test, порога, имени или данных")
    model = config.get("model") if isinstance(config.get("model"), dict) else {}
    loss = config.get("loss") if isinstance(config.get("loss"), dict) else {}
    members = _strings(config.get("members")) or []
    weights = payload.get("weights") if isinstance(payload.get("weights"), list) else []
    unlabeled = payload.get("test_unlabeled_alarms")
    source_run = payload.get("frozen_threshold_from")
    method = config.get("name")
    if not isinstance(method, str):
        method = "ensemble" if members else str(config.get("source_run") or name)
    digest = payload.get("config_sha256")
    return DetectorRun(
        name=name,
        config_sha256=digest if isinstance(digest, str) else None,
        method=method,
        kind=model.get("kind") if isinstance(model.get("kind"), str) else None,
        loss=loss.get("kind") if isinstance(loss.get("kind"), str) else None,
        data=data,
        split=config.get("split") if isinstance(config.get("split"), str) else None,
        members=members,
        weights=[value for value in (_float(item) for item in weights) if value is not None],
        source_run=source_run if isinstance(source_run, str) else None,
        threshold=threshold,
        threshold_source=payload.get("threshold_source")
        if isinstance(payload.get("threshold_source"), str)
        else None,
        tta=_tta(payload.get("tta")),
        inputs=_inputs(payload, config),
        val=_split(payload.get("val"), payload.get("val_ci95_scene_bootstrap")),
        test=test,
        postprocessing=_postprocessing(payload.get("postprocessing")),
        unlabeled_alarms_per_100km2=_float(unlabeled.get("alarm_pixels_per_100km2"))
        if isinstance(unlabeled, dict)
        else None,
        in_service=name == service_name,
    )


def parse_service(payload: dict[str, Any]) -> DetectorService:
    name, threshold = payload.get("name"), _float(payload.get("threshold"))
    if not isinstance(name, str) or threshold is None:
        raise ArtifactError("в манифесте детектора нет имени или порога")
    sea_mask = payload.get("sea_mask")
    service_metrics = payload.get("service_metrics")
    if not isinstance(service_metrics, dict):
        service_metrics = {}
    return DetectorService(
        name=name,
        threshold=threshold,
        min_pixels=_int(payload.get("min_pixels")) or 1,
        bands=_strings(payload.get("bands")) or [],
        patch=_int(payload.get("patch")),
        stride=_int(payload.get("stride")),
        data=payload.get("data") if isinstance(payload.get("data"), str) else None,
        split=payload.get("split") if isinstance(payload.get("split"), str) else None,
        sea_mask=sea_mask.get("rule") if isinstance(sea_mask, dict) else None,
        validation=payload.get("validation")
        if isinstance(payload.get("validation"), str)
        else None,
        test=_metrics(payload.get("test_metrics")),
        test_ci95=_intervals(payload.get("test_ci95")),
        postprocessed_test=_metrics(payload.get("postprocessed_test_metrics")),
        service_test=_metrics(service_metrics.get("test")),
        service_mode=service_metrics.get("mode")
        if isinstance(service_metrics.get("mode"), str)
        else None,
        calibration=_calibration_text(payload.get("calibration")),
    )


def split_patches(path: Path, split: str) -> int | None:
    column = f"{split}_split"
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except OSError:
        return None
    if not rows or column not in rows[0]:
        return None
    return sum(1 for row in rows if row[column] == "test")


def parse_regions(payload: dict[str, Any]) -> LeaveRegionOut:
    regions = payload.get("regions")
    pooled = _metrics(payload.get("pooled"))
    if not isinstance(regions, dict) or pooled is None:
        raise ArtifactError("нет регионов или сводной метрики")
    rows = []
    for region, values in regions.items():
        metrics = _metrics(values)
        if metrics is not None:
            rows.append(
                RegionResult(
                    region=region,
                    positives=_int(values.get("positives")) or 0,
                    threshold=_float(values.get("threshold")),
                    metrics=metrics,
                )
            )
    return LeaveRegionOut(
        run=str(payload.get("name") or ""),
        protocol=payload.get("protocol") if isinstance(payload.get("protocol"), str) else None,
        regions=sorted(rows, key=lambda row: -row.positives),
        pooled=pooled,
    )


def parse_negatives(payload: dict[str, Any]) -> BlackSeaNegatives:
    by_class = payload.get("by_class")
    if not isinstance(by_class, dict):
        raise ArtifactError("нет классов фона")
    classes = [
        NegativeClass(
            label=label,
            polygons=_int(values.get("polygons")) or 0,
            pixels=_int(values.get("pixels")) or 0,
            area_km2=_float(values.get("area_km2")) or 0.0,
            alarm_pixels=_int(values.get("alarm_pixels")) or 0,
            polygons_with_alarm=_int(values.get("polygons_with_alarm")) or 0,
        )
        for label, values in by_class.items()
        if isinstance(values, dict)
    ]
    scenes = [
        NegativeScene(
            aoi=str(scene.get("aoi") or ""),
            scene_id=str(scene.get("scene_id") or ""),
            pixels=_int(scene.get("pixels")) or 0,
            detected_pixels=_int(scene.get("detected_pixels")) or 0,
            zones=_int(scene.get("zones")) or 0,
        )
        for scene in payload.get("scenes") or []
        if isinstance(scene, dict)
    ]
    return BlackSeaNegatives(
        run=str(payload.get("run") or ""),
        collection=payload.get("collection")
        if isinstance(payload.get("collection"), str)
        else None,
        definition=payload.get("definition")
        if isinstance(payload.get("definition"), str)
        else None,
        pixels=sum(item.pixels for item in classes),
        alarm_pixels=sum(item.alarm_pixels for item in classes),
        classes=sorted(classes, key=lambda item: -item.pixels),
        scenes=scenes,
    )


def _rate(group: str, block: Any) -> DetectionRate | None:
    if not isinstance(block, dict):
        return None
    targets, detected = _int(block.get("targets")), _int(block.get("detected"))
    rate = _float(block.get("detection_rate"))
    if targets is None or detected is None or rate is None:
        return None
    return DetectionRate(
        group=group,
        targets=targets,
        detected=detected,
        rate=rate,
        ci95=_interval(block.get("detection_rate_ci95")),
        zone_detected=_int(block.get("zone_detected")),
    )


def _size_order(label: str) -> float:
    digits = "".join(char if char.isdigit() else " " for char in label).split()
    return float(digits[0]) if digits else 0.0


def parse_plp(payload: dict[str, Any]) -> PlasticLitterProject:
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        raise ArtifactError("нет сводки PLP")
    groups = [rate for key in PLP_GROUPS if (rate := _rate(key, summary.get(key)))]
    sizes = summary.get("by_size") if isinstance(summary.get("by_size"), dict) else {}
    by_size = [rate for label, block in sizes.items() if (rate := _rate(label, block))]
    by_size.sort(key=lambda rate: (not rate.group.startswith("<"), _size_order(rate.group)))
    background = summary.get("background")
    protocol = payload.get("protocol") if isinstance(payload.get("protocol"), dict) else {}
    return PlasticLitterProject(
        description=payload.get("description")
        if isinstance(payload.get("description"), str)
        else None,
        threshold=protocol.get("threshold") if isinstance(protocol.get("threshold"), str) else None,
        targets=_int(summary.get("targets")) or 0,
        usable=_int(summary.get("usable")) or 0,
        groups=groups,
        by_size=by_size,
        background=PlpBackground(
            windows=_int(background.get("windows")) or 0,
            water_km2=_float(background.get("window_water_km2")) or 0.0,
            zones=_int(background.get("window_zones")) or 0,
            zones_per_100_km2=_float(background.get("window_zones_per_100_km2")) or 0.0,
            ring_km2=_float(background.get("ring_km2")) or 0.0,
            ring_alarm_pixels=_int(background.get("alarm_pixels")) or 0,
        )
        if isinstance(background, dict)
        else None,
    )


def _shares(part: str, block: dict[str, Any], groups: Iterable[str]) -> list[FlagShare]:
    rows = []
    for group in groups:
        item = block.get(group)
        if not isinstance(item, dict):
            continue
        objects = int(item.get("objects", item.get("zones", 0)))
        rows.append(
            FlagShare(
                part=part,
                group=FLAG_GROUPS.get(group, group),
                objects=objects,
                flagged=int(item["flagged"]),
                share=_float(item.get("share")),
            )
        )
    return rows


def _percent(value: float) -> str:
    return f"{value * 100:.1f}".replace(".", ",") + " %"


def parse_vessels(payload: dict[str, Any]) -> ZoneFlagCheck:
    rule = payload["rule"]
    quantile = 1 - float(rule.get("quantile", 0.975))
    shares = _shares("train+val", payload["fit"]["rates"], ("ship", "debris"))
    shares += _shares("test", payload["test"]["rates"], ("ship", "debris"))
    zones = payload["test"].get("service_zones")
    if isinstance(zones, dict):
        shares += _shares(
            "test, зоны сервиса", zones, ("debris", "ship", "other_labeled", "unlabeled")
        )
    return ZoneFlagCheck(
        kind="vessel",
        title="«вероятно судно»",
        rule=(
            f"максимум B11 у зоны не ниже {decimal(rule['swir_peak'])} или видимая яркость выше "
            f"воды не меньше {decimal(rule['visible_contrast'])}; каждый порог отмечает не больше "
            f"{_percent(quantile)} обломков MARIDA train+val, test в подборе не участвовал"
        ),
        in_service=True,
        shares=shares,
    )


def _stability_shares(part: str, block: dict[str, Any]) -> list[FlagShare]:
    false = [block[name] for name in ("ship", "other_labeled") if isinstance(block.get(name), dict)]
    merged = {
        "debris": block.get("debris"),
        "false_labeled": {
            "zones": sum(int(item["zones"]) for item in false),
            "flagged": sum(int(item["flagged"]) for item in false),
        },
        "unlabeled": block.get("unlabeled"),
    }
    zones = merged["false_labeled"]["zones"]
    merged["false_labeled"]["share"] = merged["false_labeled"]["flagged"] / zones if zones else None
    return _shares(part, merged, ("debris", "false_labeled", "unlabeled"))


def parse_stability(payload: dict[str, Any]) -> ZoneFlagCheck:
    rule = payload["rule"]
    shares: list[FlagShare] = []
    discrimination: list[FlagDiscrimination] = []
    for key in ("fit", "test"):
        block = payload[key]
        part = block.get("part", key)
        shares += _stability_shares(part, block["flag_shares"])
        discrimination += [
            FlagDiscrimination(
                part=part,
                measure=title,
                value=_float(block.get(measure)),
                ci95=_interval(block.get(f"{measure}_ci95")),
            )
            for measure, title in DISCRIMINATION
        ]
    return ZoneFlagCheck(
        kind="unstable",
        title="«неустойчива к поворотам»",
        rule=(
            f"зона выше порога в среднем меньше чем в {_percent(float(rule['cutoff']))} из "
            f"{rule['views']} видов (4 поворота × отражение); порог — квантиль "
            f"{_percent(float(rule['quantile']))} обломков MARIDA val, test оценён один раз"
            + ("" if rule.get("flag") else "; на val условие включения не выполнено, флаг выключен")
        ),
        in_service=bool(rule.get("flag")),
        shares=shares,
        discrimination=discrimination,
    )


def parse_c1_check(payload: dict[str, Any], service_name: str | None) -> CollectionCheck:
    alignment = payload["alignment"]
    rows = []
    for run, block in payload["runs"].items():
        for part in ("val", "test"):
            for mode, title in C1_MODES.items():
                item = block.get(part, {}).get(mode, {})
                if "c1" not in item:
                    continue
                rows.append(
                    CollectionCheckRow(
                        run=run,
                        in_service=run == service_name,
                        part=part,
                        mode=title,
                        patches=int(item["patches"]),
                        scenes=int(item["scenes"]),
                        c1_f1=float(item["c1"]["f1"]),
                        c1_ci95=_interval(item.get("c1_f1_ci95")),
                        l2a_f1=float(item["l2a"]["f1"]),
                        l2a_ci95=_interval(item.get("l2a_f1_ci95")),
                        difference=float(item["c1_minus_l2a_f1"]),
                        difference_ci95=_interval(item.get("c1_minus_l2a_f1_ci95")),
                    )
                )
    shift = alignment.get("subpixel_shift_median_px")
    text = (
        f"C1 есть для {alignment['scenes_with_data']} сцен MARIDA; точно совмещены с разметкой "
        f"{alignment['scenes_aligned']}, с остаточным сдвигом до 1 пикс. — "
        f"{alignment['scenes_tolerant']}"
    )
    if shift is not None:
        text += f", медиана сдвига {shift:.2f} пикс.".replace(".", ",", 1)
    return CollectionCheck(
        alignment=text, rule=payload["selection_rule"], chosen=payload["chosen"], rows=rows
    )


def parse_evaluation(
    report: str, meta: dict[str, Any], block: dict[str, Any]
) -> ConcentrationEvaluation | None:
    nested, baseline = block.get("nested") or {}, block.get("baseline") or {}
    parts = [
        _mean_sd(baseline.get("mae")),
        _mean_sd(baseline.get("rmse")),
        _mean_sd(nested.get("mae")),
        _mean_sd(nested.get("rmse")),
    ]
    if any(part is None for part in parts):
        return None
    difference = block.get("difference_vs_median") or {}
    research = block.get("research") or meta.get("research") or {}
    return ConcentrationEvaluation(
        report=report,
        role=research.get("role"),
        selection=research.get("selection"),
        repetitions=_int(block.get("repetitions") or meta.get("repetitions")),
        baseline_mae=parts[0],
        baseline_rmse=parts[1],
        nested_mae=parts[2],
        nested_rmse=parts[3],
        nested_coverage=_mean_sd(nested.get("coverage")),
        difference_mae=_difference(difference.get("mae")),
        difference_rmse=_difference(difference.get("rmse")),
        gain_over_median=bool(block.get("gain_over_median")),
    )


def parse_served(payload: dict[str, Any]) -> ServedConcentration:
    model = payload.get("model")
    if not isinstance(model, str):
        raise ArtifactError("в модели концентрации нет имени")
    conformal = payload.get("conformal") if isinstance(payload.get("conformal"), dict) else {}
    validation = payload.get("validation") if isinstance(payload.get("validation"), dict) else {}
    return ServedConcentration(
        model=model,
        kind=payload.get("kind") if isinstance(payload.get("kind"), str) else None,
        gain_over_median=bool(payload.get("gain_over_median")),
        reason=payload.get("reason") if isinstance(payload.get("reason"), str) else None,
        value=_float(payload.get("constant")),
        unit=payload.get("unit") if isinstance(payload.get("unit"), str) else None,
        coverage_nominal=_float(conformal.get("nominal")),
        coverage_empirical=_float(conformal.get("empirical")),
        rule=validation.get("rule") if isinstance(validation.get("rule"), str) else None,
    )


def parse_satellite_link(payload: dict[str, Any]) -> SatelliteLink:
    correlations = payload.get("correlations")
    if not isinstance(correlations, dict):
        raise ArtifactError("нет корреляций")
    return SatelliteLink(
        detector=payload.get("detector") if isinstance(payload.get("detector"), str) else None,
        events=_int(payload.get("events")) or 0,
        correlations=[
            Correlation(
                feature=feature,
                spearman=_float(values.get("spearman")),
                p_value=_float(values.get("p_value")),
            )
            for feature, values in correlations.items()
            if isinstance(values, dict)
        ],
        pairs=[
            SatellitePair(
                event_id=str(row["event_id"]),
                scene_id=str(row["scene_id"]),
                concentration=_float(row.get("concentration")),
                water_pixels=_int(row.get("water_pixels")),
                detected_share=_float(row.get("detected_share")),
                probability_p99=_float(row.get("probability_p99")),
                fdi_p99=_float(row.get("fdi_p99")),
            )
            for row in payload.get("rows") or []
            if isinstance(row, dict) and row.get("event_id") and row.get("scene_id")
        ],
    )


class EvaluationReports:
    def __init__(self, reports_dir: Path, models_dir: Path) -> None:
        self.reports_dir = reports_dir
        self.models_dir = models_dir
        self._lock = threading.Lock()
        self._signature: Signature | None = None
        self._cached: tuple[DetectorReport | None, ConcentrationReport | None, list[str]] = (
            None,
            None,
            [],
        )

    def _detector_dir(self) -> Path:
        return self.reports_dir / DETECTOR_METRICS

    def _run_files(self) -> list[Path]:
        folder = self._detector_dir()
        return sorted(
            path
            for path in folder.glob("*.json")
            if path.name not in (SUMMARY_FILE, C1_REPORT)
            and not path.name.startswith(CALIBRATION_PREFIX)
        )

    def _files(self) -> list[Path]:
        detector = self._detector_dir()
        concentration = self.reports_dir / CONCENTRATION_METRICS
        candidates: list[Path] = [
            *self._run_files(),
            *sorted((detector / "regions").glob("*.json")),
            *sorted((detector / "external").glob("*.json")),
            *(detector / FLAGS_DIR / name for name in (VESSELS_REPORT, STABILITY_REPORT)),
            detector / C1_REPORT,
            self.reports_dir / DETECTOR_SPLITS,
            *(concentration / report / SUMMARY_FILE for report in CONCENTRATION_REPORTS),
            concentration / "satellite_pairs.json",
            self.models_dir / DETECTOR_MANIFEST,
            *sorted((self.models_dir / CONCENTRATION_SERVICE).glob("*.json")),
        ]
        return [path for path in candidates if path.is_file()]

    @staticmethod
    def _signature_of(files: Iterable[Path]) -> Signature:
        stamps = []
        for path in files:
            try:
                stat = path.stat()
            except OSError:
                continue
            stamps.append((str(path), stat.st_mtime_ns, stat.st_size))
        return tuple(stamps)

    def _relative(self, path: Path) -> str:
        for base, prefix in ((self.reports_dir, "reports"), (self.models_dir, "models")):
            try:
                return f"{prefix}/{path.relative_to(base).as_posix()}"
            except ValueError:
                continue
        return path.name

    def _load(self, path: Path, sources: list[str]) -> Any:
        try:
            payload = _read_json(path)
        except (OSError, ValueError) as error:
            logger.warning("artifact %s skipped: %s", path.name, error)
            return None
        sources.append(self._relative(path))
        return payload

    def _parse(self, path: Path, parser: Callable[..., Any], sources: list[str], *args: Any) -> Any:
        payload = self._load(path, sources)
        if not isinstance(payload, dict):
            return None
        try:
            return parser(payload, *args)
        except (ArtifactError, KeyError, TypeError, ValueError) as error:
            logger.warning("artifact %s skipped: %s", path.name, error)
            sources.remove(self._relative(path))
            return None

    def _service(self, sources: list[str]) -> DetectorService | None:
        path = self.models_dir / DETECTOR_MANIFEST
        return self._parse(path, parse_service, sources) if path.is_file() else None

    def _test_set(self, run: DetectorRun | None, payload: Any) -> DetectorTestSet | None:
        if run is None or run.split is None:
            return None
        groups = payload.get("test", {}).get("by_group") if isinstance(payload, dict) else None
        return DetectorTestSet(
            dataset=EVALUATION_DATASET,
            data=run.data,
            split=run.split,
            patches=split_patches(self.reports_dir / DETECTOR_SPLITS, run.split),
            scenes=len(groups) if isinstance(groups, dict) else None,
            pixels=run.test.pixels,
            positives=run.test.positives,
        )

    def _negatives(self, service: str | None, sources: list[str]) -> BlackSeaNegatives | None:
        folder = self._detector_dir() / "external"
        files = sorted(folder.glob("black_sea_negatives__*.json"))
        preferred = [path for path in files if service and path.stem.endswith(f"__{service}")]
        chosen = preferred[0] if preferred else (files[-1] if files else None)
        return self._parse(chosen, parse_negatives, sources) if chosen else None

    def _collection(self, service: str | None, sources: list[str]) -> CollectionCheck | None:
        path = self._detector_dir() / C1_REPORT
        return self._parse(path, parse_c1_check, sources, service) if path.is_file() else None

    def _zone_flags(self, sources: list[str]) -> list[ZoneFlagCheck]:
        folder = self._detector_dir() / FLAGS_DIR
        checks = []
        for name, parser in ((VESSELS_REPORT, parse_vessels), (STABILITY_REPORT, parse_stability)):
            path = folder / name
            if path.is_file() and (check := self._parse(path, parser, sources)) is not None:
                checks.append(check)
        return checks

    def _detector(self, sources: list[str]) -> DetectorReport | None:
        service = self._service(sources)
        service_name = service.name if service else None
        runs: list[DetectorRun] = []
        service_payload = None
        for path in self._run_files():
            payload = self._load(path, sources)
            if not isinstance(payload, dict):
                continue
            try:
                run = parse_run(payload, service_name)
            except (ArtifactError, KeyError, TypeError, ValueError) as error:
                logger.warning("artifact %s skipped: %s", path.name, error)
                sources.remove(self._relative(path))
                continue
            runs.append(run)
            if run.in_service:
                service_payload = payload
        if not runs:
            return None
        served = next((run for run in runs if run.in_service), None)
        regions = [
            region
            for path in sorted((self._detector_dir() / "regions").glob("*.json"))
            if (region := self._parse(path, parse_regions, sources)) is not None
        ]
        plp_path = self._detector_dir() / "external" / "plp.json"
        return DetectorReport(
            service=service,
            test_set=self._test_set(served, service_payload),
            runs=[run for run in runs if run.source_run is None],
            checks=DetectorChecks(
                domain_shift=[run for run in runs if run.source_run is not None],
                leave_region_out=regions,
                black_sea_negatives=self._negatives(service_name, sources),
                plp=self._parse(plp_path, parse_plp, sources) if plp_path.is_file() else None,
                zone_flags=self._zone_flags(sources),
                collection=self._collection(service_name, sources),
            ),
        )

    def _concentration(self, sources: list[str]) -> ConcentrationReport | None:
        folder = self.reports_dir / CONCENTRATION_METRICS
        profiles: dict[str, ConcentrationProfile] = {}
        for report in CONCENTRATION_REPORTS:
            path = folder / report / SUMMARY_FILE
            meta = self._load(path, sources) if path.is_file() else None
            if not isinstance(meta, dict) or not isinstance(meta.get("profiles"), dict):
                continue
            for name, block in meta["profiles"].items():
                if not isinstance(block, dict):
                    continue
                evaluation = parse_evaluation(report, meta, block)
                if evaluation is None:
                    continue
                profile = profiles.setdefault(
                    name,
                    ConcentrationProfile(
                        profile=name,
                        target_key=None,
                        events=_int(block.get("events")),
                        survey_days=_int(block.get("survey_days")),
                        served=None,
                        evaluations=[],
                    ),
                )
                profile.evaluations.append(evaluation)
        for path in sorted((self.models_dir / CONCENTRATION_SERVICE).glob("*.json")):
            payload = self._load(path, sources)
            if not isinstance(payload, dict) or not isinstance(payload.get("profile"), str):
                continue
            try:
                served = parse_served(payload)
            except ArtifactError as error:
                logger.warning("artifact %s skipped: %s", path.name, error)
                continue
            name = payload["profile"]
            validation = payload.get("validation") or {}
            profile = profiles.setdefault(
                name,
                ConcentrationProfile(
                    profile=name,
                    target_key=None,
                    events=_int(validation.get("events")),
                    survey_days=_int(validation.get("survey_days")),
                    served=None,
                    evaluations=[],
                ),
            )
            profile.served = served
            target = payload.get("target_key")
            profile.target_key = target if isinstance(target, str) else None
        if not profiles:
            return None
        link_path = folder / "satellite_pairs.json"
        link = (
            self._parse(link_path, parse_satellite_link, sources) if link_path.is_file() else None
        )
        return ConcentrationReport(
            profiles=[profiles[name] for name in sorted(profiles)],
            satellite_link=link,
        )

    def load(self) -> tuple[DetectorReport | None, ConcentrationReport | None, list[str]]:
        signature = self._signature_of(self._files())
        with self._lock:
            if signature != self._signature:
                sources: list[str] = []
                detector = self._detector(sources)
                concentration = self._concentration(sources)
                self._cached = (detector, concentration, sorted(set(sources)))
                self._signature = signature
            return self._cached

    def available(self) -> bool:
        detector, _, _ = self.load()
        return detector is not None


def _calibration_text(calibration: object) -> str | None:
    if not isinstance(calibration, dict) or calibration.get("method") != "temperature":
        return None
    temperature = calibration.get("temperature")
    if not isinstance(temperature, int | float):
        return None
    return (
        f"температурная калибровка на val, T = {temperature:.2f}".replace(".", ",")
        + "; решения детектора те же"
    )
