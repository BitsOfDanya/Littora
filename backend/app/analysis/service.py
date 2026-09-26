from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import re
import threading
import time
from collections.abc import Callable, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from rasterio.warp import transform as transform_points
from shapely.geometry import Point, box, mapping, shape
from shapely.geometry.base import BaseGeometry

from app.analysis.conditions import WeatherSource
from app.analysis.detector import bbox_pixels, oversize_side_km
from app.analysis.models import (
    ConcentrationModel,
    DetectionOutcome,
    Detector,
    EstimateContext,
    UnavailableConcentrationModel,
    UnavailableDetector,
)
from app.analysis.pixels import PIXELS_FILE, read_pixel
from app.analysis.statuses import STATUS_LABELS, ResultStatus, ValueKind
from app.analysis.structures import OsmStructures, PortLike, annotate
from app.analysis.upload import read_upload, rgb_anomalies
from app.case.concentration import UNIT
from app.case.repository import CaseRepository
from app.core.errors import AppError, NotFoundError, NotImplementedYetError
from app.earth.catalog import CatalogError, Scene, SceneCatalog
from app.earth.raster import (
    MASK_COLORS,
    SCL_GROUPS,
    QualityShares,
    RasterError,
    RasterReadError,
    RenderedLayer,
    encode_png,
    layer_corners,
    quality_shares,
    render_quality_mask,
    render_true_color,
)

PIPELINE_VERSION = "4"
ANALYSIS_ID = re.compile(r"^[0-9a-f]{16}$")
IMAGE_FILE = "image.png"
MASK_FILE = "mask.png"
PROBABILITY_FILE = "probability.png"
UPLOAD_MAX_PIXELS = 12_000_000
UPLOAD_MIN_WATER = 0.05
ANOMALY_FILE = "anomalies.png"
EXTRA_LAYER_FILES = ("false_color.png", "fdi.png", "ndvi.png", "coverage.png", ANOMALY_FILE)
RESULT_FILE = "result.json"
CONDITIONS_FILE = "conditions.json"
WAIT_SECONDS = 20.0
WORKERS = 2
FAILURE_KEEP_SECONDS = 120.0


class CatalogUnavailableError(AppError):
    status_code = 502
    code = "catalog_unavailable"


@dataclass(frozen=True)
class AnalysisRequest:
    bbox: tuple[float, float, float, float]
    date: dt.date
    window_days: int
    aoi_id: str | None = None
    aoi_name: str | None = None
    scene_id: str | None = None
    target: str | None = None


QualityReader = Callable[[Scene, BaseGeometry, float, int], QualityShares]
Renderer = Callable[..., RenderedLayer]


@dataclass(frozen=True)
class _Prepared:
    request: AnalysisRequest
    target: Any
    area: BaseGeometry
    scene: Scene | None
    analysis_id: str


@dataclass
class _Job:
    future: Future
    started: float
    started_at: str
    scene: Scene | None
    finished: float | None = None


def _default_quality(scene: Scene, area: BaseGeometry, bright: float, size: int) -> QualityShares:
    return quality_shares(scene, area, bright, size)


def _scene_summary(scene: Scene) -> dict[str, Any]:
    return {
        "id": scene.id,
        "collection": scene.collection,
        "platform": scene.platform,
        "acquired_at": scene.acquired_at.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "cloud_cover": scene.cloud_cover,
        "tile": scene.tile,
        "relative_orbit": scene.relative_orbit,
        "sun_elevation": scene.sun_elevation,
        "water_percentage": scene.water_percentage,
        "footprint": list(scene.footprint_bbox),
    }


def _status(status: ResultStatus) -> dict[str, str]:
    return {"status": status.value, "label": STATUS_LABELS[status]}


class AnalysisService:
    def __init__(
        self,
        repository: CaseRepository,
        catalog: SceneCatalog,
        storage_dir: Path,
        detector: Detector | None = None,
        concentration_model: ConcentrationModel | None = None,
        quality_reader: QualityReader = _default_quality,
        true_color: Renderer = render_true_color,
        quality_mask: Renderer = render_quality_mask,
        weather: WeatherSource | None = None,
        structures: OsmStructures | None = None,
        ports: Sequence[PortLike] = (),
    ) -> None:
        self.repository = repository
        self.catalog = catalog
        self.storage_dir = storage_dir
        self.detector = detector or UnavailableDetector()
        self.concentration_model = concentration_model or UnavailableConcentrationModel()
        self.quality_reader = quality_reader
        self.true_color = true_color
        self.quality_mask = quality_mask
        self.weather = weather
        self.structures = structures
        self.ports = list(ports)
        self.wait_seconds = WAIT_SECONDS
        self._scene_cache: dict[tuple, tuple[float, list[Scene]]] = {}
        self._lock = threading.Lock()
        self._jobs: dict[str, _Job] = {}
        self._executor: ThreadPoolExecutor | None = None

    def _annotate(self, zones: list[dict], area: BaseGeometry) -> list[str]:
        if not zones:
            return []
        structures: list = []
        messages = []
        if self.structures is not None:
            try:
                structures = self.structures.around(area.bounds)
            except (OSError, ValueError) as error:
                messages.append(f"сооружения OpenStreetMap не загружены: {error}")
        annotate(zones, structures, self.ports)
        return messages

    @property
    def config(self):
        return self.repository.data().config

    def search_scenes(
        self, area: BaseGeometry, start: dt.datetime, end: dt.datetime
    ) -> list[Scene]:
        rules = self.config.analysis
        key = (tuple(round(v, 5) for v in area.bounds), start.isoformat(), end.isoformat())
        now = time.monotonic()
        with self._lock:
            cached = self._scene_cache.get(key)
            if cached and now - cached[0] < rules.scene_cache_seconds:
                return cached[1]
        try:
            scenes = self.catalog.search(rules.collection, area, start, end)
        except CatalogError as error:
            raise CatalogUnavailableError(str(error)) from error
        with self._lock:
            if len(self._scene_cache) > 256:
                self._scene_cache.clear()
            self._scene_cache[key] = (now, scenes)
        return scenes

    def validate(self, request: AnalysisRequest) -> None:
        rules = self.config.analysis
        west, south, east, north = request.bbox
        if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
            raise AppError("Район задан неверно: нужны запад < восток и юг < север")
        if east - west > rules.max_span_deg or north - south > rules.max_span_deg:
            raise AppError(f"Район больше {rules.max_span_deg}° по стороне — уменьшите его")
        if not 0 <= request.window_days <= rules.max_window_days:
            raise AppError(f"Окно поиска должно быть от 0 до {rules.max_window_days} суток")
        if request.date > dt.date.today():
            raise AppError("Дата в будущем: снимков ещё нет")
        if request.target and self.config.target(request.target) is None:
            raise AppError(f"Нет целевой величины «{request.target}»")
        max_pixels = getattr(self.detector, "max_pixels", None)
        if max_pixels and bbox_pixels(request.bbox) > max_pixels:
            side = oversize_side_km(max_pixels)
            raise AppError(
                f"Район больше {side}×{side} км для детектора — "
                "в «Мониторинге» выберите «вид карты» и приблизьте карту"
            )

    def _pick_scene(self, request: AnalysisRequest, area: BaseGeometry) -> Scene | None:
        collection = self.config.analysis.collection
        if request.scene_id:
            try:
                return self.catalog.get(collection, request.scene_id)
            except CatalogError as error:
                raise CatalogUnavailableError(str(error)) from error
        start = dt.datetime.combine(
            request.date - dt.timedelta(days=request.window_days), dt.time.min, tzinfo=dt.UTC
        )
        end = dt.datetime.combine(
            request.date + dt.timedelta(days=request.window_days),
            dt.time(23, 59, 59),
            tzinfo=dt.UTC,
        )
        scenes = self.search_scenes(area, start, end)
        if not scenes:
            return None

        def rank(scene: Scene) -> tuple:
            return (
                abs((scene.acquired_at.date() - request.date).days),
                not scene.geometry.contains(area),
                scene.cloud_cover if scene.cloud_cover is not None else 100.0,
                scene.id,
            )

        return sorted(scenes, key=rank)[0]

    def models(self) -> dict[str, str | None]:
        return {
            "detector": getattr(self.detector, "fingerprint", self.detector.name),
            "concentration": getattr(
                self.concentration_model, "fingerprint", self.concentration_model.name
            ),
        }

    def _digest(
        self,
        bbox: list[float] | tuple[float, ...],
        day: str,
        window_days: int,
        scene_id: str | None,
        target: str,
    ) -> str:
        models = self.models()
        canonical = {
            "bbox": [round(value, 5) for value in bbox],
            "date": day,
            "window_days": window_days,
            "scene_id": scene_id,
            "target": target,
            "pipeline": PIPELINE_VERSION,
            "models": [models["detector"], models["concentration"]],
        }
        digest = hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()
        return digest[:16]

    def analysis_id(self, request: AnalysisRequest, scene: Scene | None, target: str) -> str:
        return self._digest(
            request.bbox,
            request.date.isoformat(),
            request.window_days,
            scene.id if scene else None,
            target,
        )

    def is_stale(self, result: dict[str, Any]) -> bool:
        if result.get("upload") is not None:
            return (
                result.get("pipeline_version") != PIPELINE_VERSION
                or result.get("models") != self.models()
            )
        request = result.get("request") or {}
        scene = result.get("scene")
        try:
            current = self._digest(
                request["bbox"],
                request["date"],
                request["window_days"],
                scene["id"] if scene else None,
                request["target"],
            )
        except (KeyError, TypeError):
            return True
        return current != result.get("id")

    def _read(self, path: Path) -> dict[str, Any]:
        result = self._finite(json.loads(path.read_text(encoding="utf-8")))
        return {**result, "stale": self.is_stale(result)}

    def _folder(self, analysis_id: str) -> Path:
        if not ANALYSIS_ID.match(analysis_id):
            raise NotFoundError("Нет такого анализа")
        return self.storage_dir / analysis_id

    def get(self, analysis_id: str) -> dict[str, Any]:
        path = self._folder(analysis_id) / RESULT_FILE
        if not path.exists():
            raise NotFoundError("Нет такого анализа")
        return self._read(path)

    def concentration_domains(self) -> dict[str, Any]:
        domains = getattr(self.concentration_model, "domains", None)
        if domains is None:
            raise NotImplementedYetError("Модель концентрации не подключена")
        return domains()

    def target_estimates(self, analysis_id: str) -> dict[str, Any]:
        result = self.get(analysis_id)
        area = shape(result["area"])
        day = dt.date.fromisoformat(result["request"]["date"])
        detection = DetectionOutcome(status=ResultStatus.NOT_DETECTED, reason="")
        rows = []
        for target in self.config.targets:
            outcome = self.concentration_model.estimate(
                None, area, detection, EstimateContext(target.key, day)
            )
            rows.append(
                {
                    "key": target.key,
                    "title": target.title,
                    "material": target.material,
                    "size_class": target.size_class,
                    "profiles": list(target.profiles),
                    "selected": target.key == result["target"]["key"],
                    "status": _status(outcome.status),
                    "reason": outcome.reason,
                    "value": outcome.value,
                    "lower": outcome.lower,
                    "upper": outcome.upper,
                    "profile": outcome.profile,
                    "unit": UNIT,
                }
            )
        return {"analysis_id": analysis_id, "date": day.isoformat(), "targets": rows}

    @staticmethod
    def _finite(value: Any) -> Any:
        if isinstance(value, float):
            return value if math.isfinite(value) else None
        if isinstance(value, dict):
            return {key: AnalysisService._finite(item) for key, item in value.items()}
        if isinstance(value, list):
            return [AnalysisService._finite(item) for item in value]
        return value

    def pixel(self, analysis_id: str, lon: float, lat: float) -> dict[str, Any]:
        result = self.get(analysis_id)
        path = self._folder(analysis_id) / PIXELS_FILE
        if not path.exists():
            raise NotFoundError(
                "Значений пикселей нет: детекция не запускалась или район больше 4 млн пикселей"
            )
        return read_pixel(path, result["detection"].get("zones", []), lon, lat)

    def layer_path(self, analysis_id: str, name: str) -> Path:
        path = self._folder(analysis_id) / name
        if not path.exists():
            raise NotFoundError("Слоя нет: у анализа нет снимка")
        return path

    def history(
        self,
        status: str | None = None,
        aoi_id: str | None = None,
        date_from: dt.date | None = None,
        date_to: dt.date | None = None,
    ) -> list[dict[str, Any]]:
        if not self.storage_dir.exists():
            return []
        items = []
        for path in self.storage_dir.glob(f"*/{RESULT_FILE}"):
            result = self._read(path)
            request = result["request"]
            day = dt.date.fromisoformat(request["date"])
            statuses = {result["status"]["status"], result["concentration"]["status"]}
            if status and status not in statuses:
                continue
            if aoi_id and request.get("aoi_id") != aoi_id:
                continue
            if (date_from and day < date_from) or (date_to and day > date_to):
                continue
            scene = result["scene"]
            items.append(
                {
                    "id": result["id"],
                    "computed_at": result["computed_at"],
                    "request": request,
                    "scene_id": scene["id"] if scene else None,
                    "scene_acquired_at": scene["acquired_at"] if scene else None,
                    "status": result["status"],
                    "concentration": {
                        "status": result["concentration"]["status"],
                        "label": result["concentration"]["label"],
                    },
                    "observations": len(result["observations"]),
                    "zones": len(result["detection"].get("zones") or []),
                    "stale": result["stale"],
                }
            )
        items.sort(key=lambda item: item["computed_at"], reverse=True)
        return sorted(items, key=lambda item: item["stale"])

    def _observations(self, area: BaseGeometry, day: dt.date, window: int) -> list[dict]:
        data = self.repository.data()
        selections = [
            s
            for s in data.selections
            if s.record.record_type == data.config.selection.record_type
            and s.record.position is not None
            and area.intersects(Point(s.record.position))
        ]
        items = []
        for selection in selections:
            feature = self.repository.observation_feature(selection)
            if feature is None:
                continue
            record_day = selection.record.date
            delta = (record_day - day).days if record_day else None
            feature["properties"]["delta_days"] = delta
            feature["properties"]["synchronous"] = delta is not None and abs(delta) <= window
            items.append(feature)
        return sorted(items, key=lambda f: (abs(f["properties"]["delta_days"] or 10**6), f["id"]))

    def _quality_verdict(self, quality: QualityShares) -> tuple[bool, list[str]]:
        rules = self.config.analysis
        reasons = []
        if quality.nodata > rules.max_nodata:
            reasons.append("много пикселей без данных")
        if quality.cloud_or_shadow > rules.max_cloud:
            reasons.append("облака или тени")
        if quality.water < rules.min_water:
            reasons.append("мало воды в районе")
        return not reasons, reasons

    def _prepare(self, request: AnalysisRequest) -> _Prepared:
        self.validate(request)
        config = self.config
        target = config.target(request.target) if request.target else config.primary_target
        area = box(*request.bbox)
        scene = self._pick_scene(request, area)
        return _Prepared(request, target, area, scene, self.analysis_id(request, scene, target.key))

    def _saved(self, analysis_id: str) -> dict[str, Any] | None:
        path = self._folder(analysis_id) / RESULT_FILE
        if not path.exists():
            return None
        result = self._read(path)
        return None if result.get("retryable") else result

    def _job(self, prepared: _Prepared) -> _Job:
        analysis_id = prepared.analysis_id
        with self._lock:
            job = self._jobs.get(analysis_id)
            if job is not None and job.finished is not None:
                self._jobs.pop(analysis_id, None)
                if time.monotonic() - job.finished < FAILURE_KEEP_SECONDS:
                    return job
                job = None
            if job is not None:
                return job
            if self._executor is None:
                self._executor = ThreadPoolExecutor(WORKERS, "littora-analysis")
            future = self._executor.submit(self._compute, prepared)
            job = _Job(
                future,
                time.monotonic(),
                dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
                prepared.scene,
            )
            self._jobs[analysis_id] = job
        future.add_done_callback(lambda done: self._settle(analysis_id, done))
        return job

    def _settle(self, analysis_id: str, future: Future) -> None:
        with self._lock:
            job = self._jobs.get(analysis_id)
            if job is None or job.future is not future:
                return
            if future.exception() is None:
                self._jobs.pop(analysis_id, None)
            else:
                job.finished = time.monotonic()

    def run(self, request: AnalysisRequest) -> dict[str, Any]:
        prepared = self._prepare(request)
        return self._saved(prepared.analysis_id) or self._job(prepared).future.result()

    def submit(self, request: AnalysisRequest, wait_seconds: float | None = None) -> dict[str, Any]:
        prepared = self._prepare(request)
        saved = self._saved(prepared.analysis_id)
        if saved is not None:
            return saved
        job = self._job(prepared)
        try:
            return job.future.result(
                timeout=self.wait_seconds if wait_seconds is None else wait_seconds
            )
        except FutureTimeout:
            return {
                "id": prepared.analysis_id,
                "state": "running",
                "started_at": job.started_at,
                "elapsed_s": round(time.monotonic() - job.started),
                "scene": _scene_summary(job.scene) if job.scene else None,
            }

    def _compute(self, prepared: _Prepared) -> dict[str, Any]:
        saved = self._saved(prepared.analysis_id)
        if saved is not None:
            return saved
        request, target, area, scene = (
            prepared.request,
            prepared.target,
            prepared.area,
            prepared.scene,
        )
        config = self.config
        analysis_id = prepared.analysis_id
        folder = self._folder(analysis_id)
        folder.mkdir(parents=True, exist_ok=True)
        messages: list[str] = []
        retryable = False
        quality_payload = None
        layers: dict[str, Any] = {}
        detection = DetectionOutcome(
            status=ResultStatus.INSUFFICIENT_DATA,
            reason=f"нет снимков Sentinel-2 в окне ±{request.window_days} сут",
        )
        concentration = None
        timings: dict[str, float] = {}
        started = time.perf_counter()
        if scene is not None:
            try:
                quality = self.quality_reader(
                    scene,
                    area,
                    config.pairing.bright_water_reflectance,
                    config.analysis.quality_max_size,
                )
                usable, reasons = self._quality_verdict(quality)
                quality_payload = {**quality.as_dict(), "usable": usable, "reasons": reasons}
                size = config.analysis.render_max_size
                image = self.true_color(scene, area, size)
                mask = self.quality_mask(scene, area, config.pairing.bright_water_reflectance, size)
                (folder / IMAGE_FILE).write_bytes(image.png)
                (folder / MASK_FILE).write_bytes(mask.png)
                layers = {
                    "image": {"file": IMAGE_FILE, "corners": image.corners},
                    "mask": {"file": MASK_FILE, "corners": mask.corners},
                }
                timings["quality_and_image_s"] = round(time.perf_counter() - started, 2)
                if usable:
                    detection = self.detector.detect(scene, area)
                    step = time.perf_counter()
                    messages.extend(self._annotate(detection.zones, area))
                    timings.update(detection.timings)
                    timings["structures_s"] = round(time.perf_counter() - step, 2)
                    if detection.layer is not None:
                        (folder / PROBABILITY_FILE).write_bytes(detection.layer.png)
                        layers["probability"] = {
                            "file": PROBABILITY_FILE,
                            "corners": detection.layer.corners,
                        }
                    if detection.pixels is not None:
                        (folder / PIXELS_FILE).write_bytes(detection.pixels)
                    for key, extra in detection.extra_layers.items():
                        name = f"{key}.png"
                        (folder / name).write_bytes(extra.png)
                        layers[key] = {"file": name, "corners": extra.corners}
                else:
                    detection = DetectionOutcome(
                        status=ResultStatus.INSUFFICIENT_DATA,
                        reason="снимок непригоден: " + ", ".join(reasons),
                    )
            except RasterError as error:
                messages.append(str(error))
                retryable = isinstance(error, RasterReadError)
                detection = DetectionOutcome(
                    status=ResultStatus.INSUFFICIENT_DATA, reason=f"снимок не читается: {error}"
                )
            concentration = self.concentration_model.estimate(
                scene, area, detection, EstimateContext(target.key, request.date)
            )
        overall = (
            detection.status
            if detection.status in (ResultStatus.DETECTED, ResultStatus.NOT_DETECTED)
            else ResultStatus.INSUFFICIENT_DATA
        )
        concentration_status = (
            concentration.status if concentration else ResultStatus.CONCENTRATION_UNAVAILABLE
        )
        result = {
            "id": analysis_id,
            "pipeline_version": PIPELINE_VERSION,
            "retryable": retryable or detection.retryable,
            "models": self.models(),
            "computed_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
            "request": {
                "aoi_id": request.aoi_id,
                "aoi_name": request.aoi_name,
                "bbox": list(request.bbox),
                "date": request.date.isoformat(),
                "window_days": request.window_days,
                "scene_id": request.scene_id,
                "target": target.key,
            },
            "area": mapping(area),
            "target": {
                "key": target.key,
                "title": target.title,
                "material": target.material,
                "size_class": target.size_class,
                "unit": UNIT,
            },
            "scene": _scene_summary(scene) if scene else None,
            "quality": quality_payload,
            "layers": layers,
            "timings": {**timings, "total_s": round(time.perf_counter() - started, 2)},
            "status": _status(overall),
            "detection": {
                **_status(detection.status),
                "reason": detection.reason,
                "model": detection.model,
                "threshold": detection.threshold,
                "zones": detection.zones,
                "zones_total": detection.zones_total
                if detection.zones_total is not None
                else len(detection.zones),
            },
            "concentration": {
                **_status(concentration_status),
                "reason": concentration.reason if concentration else "нет снимка",
                "model": concentration.model if concentration else None,
                "value": concentration.value if concentration else None,
                "lower": concentration.lower if concentration else None,
                "upper": concentration.upper if concentration else None,
                "profile": concentration.profile if concentration else None,
                "coverage": concentration.coverage if concentration else None,
                "unit": UNIT,
                "value_kind": ValueKind.MODEL_ESTIMATE.value,
            },
            "observations": self._observations(area, request.date, request.window_days),
            "messages": messages,
        }
        result = self._finite(result)
        (folder / RESULT_FILE).write_text(
            json.dumps(result, ensure_ascii=False, indent=1, allow_nan=False), encoding="utf-8"
        )
        return {**result, "stale": False}

    def analyze_upload(
        self,
        content: bytes,
        name: str,
        bbox: tuple[float, float, float, float] | None,
        day: dt.date | None,
    ) -> dict[str, Any]:
        upload = read_upload(content, getattr(self.detector, "max_pixels", UPLOAD_MAX_PIXELS), bbox)
        day = day or dt.datetime.now(dt.UTC).date()
        target = self.config.primary_target
        digest = hashlib.sha256(content)
        digest.update(json.dumps([PIPELINE_VERSION, self.models(), day.isoformat(), bbox]).encode())
        analysis_id = digest.hexdigest()[:16]
        saved = self._saved(analysis_id)
        if saved is not None:
            return saved
        started = time.perf_counter()
        folder = self._folder(analysis_id)
        folder.mkdir(parents=True, exist_ok=True)
        west, south, east, north = upload.bounds
        area = box(west, south, east, north)
        height, width = upload.scl.shape
        corners = layer_corners(upload.transform, upload.crs, height, width)
        (folder / IMAGE_FILE).write_bytes(encode_png(upload.rgb))
        mask = np.zeros((height, width, 4), dtype=np.uint8)
        total = max(int(upload.valid.sum()), 1)
        shares = {}
        for group, codes in SCL_GROUPS.items():
            inside = np.isin(upload.scl, codes)
            mask[inside] = MASK_COLORS[group]
            shares[group] = float((inside & upload.valid).sum()) / total
        (folder / MASK_FILE).write_bytes(encode_png(mask))
        layers: dict[str, Any] = {
            "image": {"file": IMAGE_FILE, "corners": corners},
            "mask": {"file": MASK_FILE, "corners": corners},
        }
        usable = upload.stack is not None and shares["water"] >= UPLOAD_MIN_WATER
        reasons = [] if usable else ["детекция по этому файлу невозможна"]
        quality = {
            "pixels": total,
            **shares,
            "bright_water": None,
            "usable": usable,
            "reasons": reasons,
        }
        messages = list(upload.notes)
        timings: dict[str, float] = {}
        detect_stack = getattr(self.detector, "detect_stack", None)
        upload_info: dict[str, Any] = {
            "kind": "sentinel2" if upload.stack is not None else "visible",
            "bands": upload.bands,
            "anomalies": [],
        }
        if upload.stack is None:
            overlay, anomalies = rgb_anomalies(upload.visible, upload.valid)
            (folder / ANOMALY_FILE).write_bytes(encode_png(overlay))
            layers["anomalies"] = {"file": ANOMALY_FILE, "corners": corners}
            points = [
                upload.transform * (item["col"] + 0.5, item["row"] + 0.5) for item in anomalies
            ]
            lons, lats = (
                transform_points(upload.crs, "EPSG:4326", *map(list, zip(*points, strict=True)))
                if points
                else ([], [])
            )
            upload_info["anomalies"] = [
                {
                    "id": f"a-{rank}",
                    "centroid": [round(lon, 6), round(lat, 6)],
                    "pixels": item["pixels"],
                    "contrast": item["contrast"],
                }
                for rank, (item, lon, lat) in enumerate(zip(anomalies, lons, lats, strict=True), 1)
            ]
            detection = DetectionOutcome(
                status=ResultStatus.INSUFFICIENT_DATA,
                reason="в файле нет 11 каналов Sentinel-2: по видимым каналам мусор не виден",
            )
        elif detect_stack is None:
            detection = DetectionOutcome(
                status=ResultStatus.INSUFFICIENT_DATA, reason="детектор не подключён"
            )
        elif not usable:
            detection = DetectionOutcome(
                status=ResultStatus.INSUFFICIENT_DATA, reason="воды на снимке меньше 5 %"
            )
        else:
            detection = detect_stack(upload.stack)
            messages.extend(self._annotate(detection.zones, area))
            timings.update(detection.timings)
            if detection.layer is not None:
                (folder / PROBABILITY_FILE).write_bytes(detection.layer.png)
                layers["probability"] = {"file": PROBABILITY_FILE, "corners": corners}
            if detection.pixels is not None:
                (folder / PIXELS_FILE).write_bytes(detection.pixels)
            for key, extra in detection.extra_layers.items():
                file = f"{key}.png"
                (folder / file).write_bytes(extra.png)
                layers[key] = {"file": file, "corners": corners}
        concentration = self.concentration_model.estimate(
            None, area, detection, EstimateContext(target.key, day)
        )
        overall = (
            detection.status
            if detection.status in (ResultStatus.DETECTED, ResultStatus.NOT_DETECTED)
            else ResultStatus.INSUFFICIENT_DATA
        )
        label = f"Свой снимок · {name}"[:160]
        result = {
            "id": analysis_id,
            "pipeline_version": PIPELINE_VERSION,
            "retryable": False,
            "models": self.models(),
            "computed_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
            "request": {
                "aoi_id": None,
                "aoi_name": label,
                "bbox": [round(value, 5) for value in upload.bounds],
                "date": day.isoformat(),
                "window_days": 0,
                "scene_id": None,
                "target": target.key,
            },
            "area": mapping(area),
            "target": {
                "key": target.key,
                "title": target.title,
                "material": target.material,
                "size_class": target.size_class,
                "unit": UNIT,
            },
            "scene": {
                "id": f"upload:{name}"[:120],
                "collection": "upload",
                "platform": "свой снимок",
                "acquired_at": f"{day.isoformat()}T00:00:00.000Z",
                "cloud_cover": None,
                "tile": f"{upload.bands} кан.",
                "relative_orbit": None,
                "sun_elevation": None,
                "water_percentage": round(shares["water"] * 100, 1),
                "footprint": [round(value, 5) for value in upload.bounds],
            },
            "quality": quality,
            "layers": layers,
            "timings": {**timings, "total_s": round(time.perf_counter() - started, 2)},
            "status": _status(overall),
            "detection": {
                **_status(detection.status),
                "reason": detection.reason,
                "model": detection.model,
                "threshold": detection.threshold,
                "zones": detection.zones,
                "zones_total": detection.zones_total
                if detection.zones_total is not None
                else len(detection.zones),
            },
            "concentration": {
                **_status(concentration.status),
                "reason": concentration.reason,
                "model": concentration.model,
                "value": concentration.value,
                "lower": concentration.lower,
                "upper": concentration.upper,
                "profile": concentration.profile,
                "coverage": concentration.coverage,
                "unit": UNIT,
                "value_kind": ValueKind.MODEL_ESTIMATE.value,
            },
            "observations": self._observations(area, day, 3),
            "messages": messages,
            "upload": upload_info,
        }
        result = self._finite(result)
        (folder / RESULT_FILE).write_text(
            json.dumps(result, ensure_ascii=False, indent=1, allow_nan=False), encoding="utf-8"
        )
        return {**result, "stale": False}

    def conditions(self, analysis_id: str) -> dict[str, Any]:
        result = self.get(analysis_id)
        scene = result.get("scene")
        if not scene:
            raise NotFoundError("У анализа нет снимка — условий съёмки нет")
        path = self._folder(analysis_id) / CONDITIONS_FILE
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        if self.weather is None:
            raise NotImplementedYetError("Источник погоды не подключён")
        center = shape(result["area"]).centroid
        moment = dt.datetime.fromisoformat(scene["acquired_at"].replace("Z", "+00:00"))
        reading = self.weather.at(center.x, center.y, moment)
        payload = {"analysis_id": analysis_id, "acquired_at": scene["acquired_at"], **reading}
        if payload.pop("complete", False):
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return payload
