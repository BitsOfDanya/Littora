from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from shapely.geometry import Point, box, mapping
from shapely.geometry.base import BaseGeometry

from app.analysis.models import (
    ConcentrationModel,
    DetectionOutcome,
    Detector,
    UnavailableConcentrationModel,
    UnavailableDetector,
)
from app.analysis.statuses import STATUS_LABELS, ResultStatus, ValueKind
from app.case.concentration import UNIT
from app.case.repository import CaseRepository
from app.core.errors import AppError, NotFoundError
from app.earth.catalog import CatalogError, Scene, SceneCatalog
from app.earth.raster import (
    QualityShares,
    RasterError,
    RenderedLayer,
    quality_shares,
    render_quality_mask,
    render_true_color,
)

PIPELINE_VERSION = "1"
ANALYSIS_ID = re.compile(r"^[0-9a-f]{16}$")
IMAGE_FILE = "image.png"
MASK_FILE = "mask.png"
RESULT_FILE = "result.json"


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
    ) -> None:
        self.repository = repository
        self.catalog = catalog
        self.storage_dir = storage_dir
        self.detector = detector or UnavailableDetector()
        self.concentration_model = concentration_model or UnavailableConcentrationModel()
        self.quality_reader = quality_reader
        self.true_color = true_color
        self.quality_mask = quality_mask
        self._scene_cache: dict[tuple, tuple[float, list[Scene]]] = {}
        self._lock = threading.Lock()

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

    def analysis_id(self, request: AnalysisRequest, scene: Scene | None, target: str) -> str:
        canonical = {
            "bbox": [round(value, 5) for value in request.bbox],
            "date": request.date.isoformat(),
            "window_days": request.window_days,
            "scene_id": scene.id if scene else None,
            "target": target,
            "pipeline": PIPELINE_VERSION,
        }
        digest = hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()
        return digest[:16]

    def _folder(self, analysis_id: str) -> Path:
        if not ANALYSIS_ID.match(analysis_id):
            raise NotFoundError("Нет такого анализа")
        return self.storage_dir / analysis_id

    def get(self, analysis_id: str) -> dict[str, Any]:
        path = self._folder(analysis_id) / RESULT_FILE
        if not path.exists():
            raise NotFoundError("Нет такого анализа")
        return json.loads(path.read_text(encoding="utf-8"))

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
            result = json.loads(path.read_text(encoding="utf-8"))
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
                }
            )
        return sorted(items, key=lambda item: item["computed_at"], reverse=True)

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

    def run(self, request: AnalysisRequest) -> dict[str, Any]:
        self.validate(request)
        config = self.config
        target = config.target(request.target) if request.target else config.primary_target
        area = box(*request.bbox)
        scene = self._pick_scene(request, area)
        analysis_id = self.analysis_id(request, scene, target.key)
        folder = self._folder(analysis_id)
        if (folder / RESULT_FILE).exists():
            return self.get(analysis_id)

        folder.mkdir(parents=True, exist_ok=True)
        messages: list[str] = []
        quality_payload = None
        layers: dict[str, Any] = {}
        detection = DetectionOutcome(
            status=ResultStatus.INSUFFICIENT_DATA,
            reason=f"нет снимков Sentinel-2 в окне ±{request.window_days} сут",
        )
        concentration = None
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
                if usable:
                    detection = self.detector.detect(scene, area)
                else:
                    detection = DetectionOutcome(
                        status=ResultStatus.INSUFFICIENT_DATA,
                        reason="снимок непригоден: " + ", ".join(reasons),
                    )
            except RasterError as error:
                messages.append(str(error))
                detection = DetectionOutcome(
                    status=ResultStatus.INSUFFICIENT_DATA, reason=f"снимок не читается: {error}"
                )
            concentration = self.concentration_model.estimate(scene, area, detection)
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
            "status": _status(overall),
            "detection": {
                **_status(detection.status),
                "reason": detection.reason,
                "model": detection.model,
                "zones": detection.zones,
            },
            "concentration": {
                **_status(concentration_status),
                "reason": concentration.reason if concentration else "нет снимка",
                "model": concentration.model if concentration else None,
                "value": concentration.value if concentration else None,
                "lower": concentration.lower if concentration else None,
                "upper": concentration.upper if concentration else None,
                "unit": UNIT,
                "value_kind": ValueKind.MODEL_ESTIMATE.value,
            },
            "observations": self._observations(area, request.date, request.window_days),
            "messages": messages,
        }
        (folder / RESULT_FILE).write_text(
            json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        return result
