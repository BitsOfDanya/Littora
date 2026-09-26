from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import threading
from collections import OrderedDict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from app.analysis.service import AnalysisRequest, AnalysisService
from app.analysis.zones import MAX_ZONES
from app.core.errors import AppError, NotFoundError, NotImplementedYetError
from app.earth.catalog import Scene
from app.timeline.change import Coverage, comparable, zone_change

logger = logging.getLogger("littora.timeline")

WINDOW_DAYS = 1
DEFAULT_PASSES = 6
MAX_PASSES = 12
MAX_RANGE_DAYS = 120
MAX_JOBS = 32
MAX_CHANGES = 128
ACTIVE = ("queued", "running")
VALUE_KIND = "detections"
NOTE = (
    "Ряд детекций по пролётам Sentinel-2: число и площадь зон выше порога детектора "
    "на каждом снимке. Это не динамика концентрации, шт./км²."
)


@dataclass(frozen=True)
class TimelineQuery:
    bbox: tuple[float, float, float, float]
    date_from: dt.date
    date_to: dt.date
    aoi_id: str | None = None
    aoi_name: str | None = None
    target: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "bbox": list(self.bbox),
            "date_from": self.date_from.isoformat(),
            "date_to": self.date_to.isoformat(),
            "aoi_id": self.aoi_id,
            "target": self.target,
        }

    def key(self) -> tuple:
        return (
            tuple(round(value, 5) for value in self.bbox),
            self.date_from,
            self.date_to,
            self.target,
        )


@dataclass(frozen=True)
class Pass:
    scene: Scene
    listing: dict[str, Any]


Submit = Callable[[Callable[[], None]], Any]


def _now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


def _rounded(bbox) -> list[float]:
    return [round(float(value), 5) for value in bbox]


def _scene_ref(result: dict[str, Any]) -> dict[str, Any]:
    scene = result.get("scene") or {}
    return {
        "analysis_id": result["id"],
        "scene_id": scene.get("id"),
        "acquired_at": scene.get("acquired_at"),
        "status": result["detection"]["status"],
    }


def _coverage(analysis: AnalysisService, result: dict[str, Any]) -> Coverage | None:
    mask = (result.get("layers") or {}).get("mask")
    if not mask:
        return None
    try:
        path = analysis.layer_path(result["id"], mask["file"])
    except NotFoundError:
        return None
    return Coverage.read(path, mask["corners"])


def summary(result: dict[str, Any]) -> dict[str, Any]:
    detection = result["detection"]
    zones = detection["zones"] if comparable(result) else []
    peaks = [
        float(zone["probability_max"])
        for zone in zones
        if isinstance(zone.get("probability_max"), int | float)
    ]
    concentration = result["concentration"]
    quality = result.get("quality")
    return {
        "id": result["id"],
        "computed_at": result["computed_at"],
        "window_days": result["request"]["window_days"],
        "status": result["status"],
        "detection": {
            "status": detection["status"],
            "label": detection["label"],
            "reason": detection["reason"],
            "model": detection.get("model"),
            "threshold": detection.get("threshold"),
        },
        "zone_count": len(zones) if comparable(result) else None,
        "zones_limited": len(zones) >= MAX_ZONES,
        "retryable": bool(result.get("retryable")),
        "area_km2": (
            round(sum(float(zone.get("area_km2") or 0.0) for zone in zones), 4)
            if comparable(result)
            else None
        ),
        "probability_max": round(max(peaks), 4) if peaks else None,
        "concentration": {
            key: concentration.get(key)
            for key in ("status", "label", "reason", "value", "lower", "upper", "unit")
        },
        "quality": (
            {
                "usable": quality["usable"],
                "reasons": quality["reasons"],
                "cloud": quality.get("cloud"),
                "water": quality.get("water"),
            }
            if quality
            else None
        ),
        "layers": sorted(result.get("layers") or {}),
    }


def _spread(items: list[Pass], limit: int) -> list[Pass]:
    if len(items) <= limit:
        return items
    if limit == 1:
        return items[-1:]
    step = (len(items) - 1) / (limit - 1)
    return [items[round(index * step)] for index in range(limit)]


class TimelineService:
    def __init__(self, submit: Submit | None = None) -> None:
        self._jobs: dict[str, dict[str, Any]] = {}
        self._queries: dict[str, tuple] = {}
        self._changes: OrderedDict[tuple, dict[str, Any]] = OrderedDict()
        self._lock = threading.Lock()
        self._executor = None if submit else ThreadPoolExecutor(1, "littora-timeline")
        self._submit = submit or self._executor.submit

    def target_key(self, analysis: AnalysisService, query: TimelineQuery) -> str:
        config = analysis.config
        if query.target is None:
            return config.primary_target.key
        target = config.target(query.target)
        if target is None:
            raise AppError(f"Нет целевой величины «{query.target}»")
        return target.key

    def validate(self, analysis: AnalysisService, query: TimelineQuery) -> str:
        if analysis.detector.name is None:
            raise NotImplementedYetError("Детектор не подключён — пролёты анализировать нечем")
        target = self.target_key(analysis, query)
        analysis.validate(
            AnalysisRequest(
                bbox=query.bbox,
                date=min(query.date_to, dt.date.today()),
                window_days=WINDOW_DAYS,
                target=target,
            )
        )
        return target

    def saved(
        self, analysis: AnalysisService, query: TimelineQuery, passes: list[Pass]
    ) -> dict[str, dict[str, Any]]:
        scenes = {item.scene.id: item.scene for item in passes}
        target = self.target_key(analysis, query)
        bbox = _rounded(query.bbox)
        chosen: dict[str, str] = {}
        for item in analysis.history():
            scene = scenes.get(item["scene_id"] or "")
            request = item["request"]
            if scene is None or scene.id in chosen or request.get("target") != target:
                continue
            if item["stale"] or _rounded(request["bbox"]) != bbox:
                continue
            chosen[scene.id] = item["id"]
        return {scene_id: analysis.get(analysis_id) for scene_id, analysis_id in chosen.items()}

    def change(
        self, analysis: AnalysisService, before: dict[str, Any], after: dict[str, Any]
    ) -> dict[str, Any]:
        key = (before["id"], before["computed_at"], after["id"], after["computed_at"])
        with self._lock:
            if key in self._changes:
                self._changes.move_to_end(key)
                return self._changes[key]
        difference = zone_change(
            before["detection"]["zones"],
            after["detection"]["zones"],
            before_coverage=_coverage(analysis, before),
            after_coverage=_coverage(analysis, after),
        )
        with self._lock:
            self._changes[key] = difference
            while len(self._changes) > MAX_CHANGES:
                self._changes.popitem(last=False)
        return difference

    def series(
        self, analysis: AnalysisService, query: TimelineQuery, passes: list[Pass]
    ) -> dict[str, Any]:
        target_key = self.target_key(analysis, query)
        target = analysis.config.target(target_key)
        saved = self.saved(analysis, query, passes)
        items = []
        previous: dict[str, Any] | None = None
        for item in passes:
            result = saved.get(item.scene.id)
            change = None
            if result is not None and comparable(result):
                if previous is not None:
                    difference = self.change(analysis, previous, result)
                    change = {
                        "before": _scene_ref(previous),
                        "counts": difference["counts"],
                        "area_km2": difference["area_km2"],
                    }
                previous = result
            items.append(
                {
                    "scene": item.listing,
                    "analysis": summary(result) if result is not None else None,
                    "change": change,
                }
            )
        analysed = [entry for entry in items if entry["analysis"] is not None]
        return {
            "request": query.as_dict(),
            "target": {"key": target.key, "title": target.title},
            "models": {
                "detector": analysis.detector.name,
                "concentration": analysis.concentration_model.name,
            },
            "value_kind": VALUE_KIND,
            "note": NOTE,
            "summary": {
                "passes": len(items),
                "usable": sum(1 for item in passes if item.listing["usability"] == "usable"),
                "analysed": len(analysed),
                "comparable": sum(
                    1 for entry in analysed if entry["analysis"]["zone_count"] is not None
                ),
            },
            "passes": items,
            "run": self.latest(query),
            "limits": {
                "default_passes": DEFAULT_PASSES,
                "max_passes": MAX_PASSES,
                "max_range_days": MAX_RANGE_DAYS,
                "window_days": WINDOW_DAYS,
            },
        }

    def compare(self, analysis: AnalysisService, before_id: str, after_id: str) -> dict[str, Any]:
        before = analysis.get(before_id)
        after = analysis.get(after_id)
        payload: dict[str, Any] = {
            "before": _scene_ref(before),
            "after": _scene_ref(after),
            "value_kind": VALUE_KIND,
        }
        reason = None
        if _rounded(before["request"]["bbox"]) != _rounded(after["request"]["bbox"]):
            reason = "анализы сделаны по разным районам"
        elif before["request"]["target"] != after["request"]["target"]:
            reason = "у анализов разные целевые величины"
        elif not comparable(before) or not comparable(after):
            reason = "по одной из дат недостаточно данных для детекции"
        if reason:
            return {**payload, "comparable": False, "reason": reason}
        difference = self.change(analysis, before, after)
        return {**payload, "comparable": True, "reason": None, **difference}

    def choose(
        self,
        passes: list[Pass],
        saved: dict[str, dict[str, Any]],
        scene_ids: list[str] | None,
        limit: int,
    ) -> list[Pass]:
        if scene_ids:
            wanted = set(scene_ids)
            unknown = wanted - {item.scene.id for item in passes}
            if unknown:
                raise AppError("Пролётов нет в периоде: " + ", ".join(sorted(unknown)))
            return [item for item in passes if item.scene.id in wanted][:limit]
        open_passes = [
            item
            for item in passes
            if item.scene.id not in saved or saved[item.scene.id].get("retryable")
        ]
        usable = [item for item in open_passes if item.listing["usability"] == "usable"]
        if len(usable) < limit:
            partial = [item for item in open_passes if item.listing["usability"] == "partial"]
            partial = sorted(partial, key=lambda item: item.listing["cloud_cover"])
            usable = usable + partial[: limit - len(usable)]
        pool = sorted(usable, key=lambda item: (item.scene.acquired_at, item.scene.id))
        return _spread(pool, limit)

    def start(
        self,
        analysis: AnalysisService,
        query: TimelineQuery,
        passes: list[Pass],
        scene_ids: list[str] | None = None,
        limit: int = DEFAULT_PASSES,
    ) -> dict[str, Any]:
        target = self.validate(analysis, query)
        saved = self.saved(analysis, query, passes)
        chosen = self.choose(passes, saved, scene_ids, limit)
        canonical = {
            "query": [list(query.key()[0]), query.date_from.isoformat(), query.date_to.isoformat()],
            "target": target,
            "scenes": [item.scene.id for item in chosen],
        }
        job_id = hashlib.sha256(json.dumps(canonical).encode()).hexdigest()[:12]
        with self._lock:
            existing = self._jobs.get(job_id)
            if existing and existing["status"] in ACTIVE:
                return self._snapshot(existing)
            job = {
                "id": job_id,
                "status": "queued" if chosen else "done",
                "request": query.as_dict(),
                "items": [
                    {
                        "scene_id": item.scene.id,
                        "acquired_at": item.listing["acquired_at"],
                        "state": "pending",
                        "analysis_id": None,
                        "status": None,
                        "message": None,
                    }
                    for item in chosen
                ],
                "current_scene_id": None,
                "created_at": _now(),
                "started_at": None,
                "finished_at": None if chosen else _now(),
                "message": None if chosen else "все пригодные пролёты периода уже проанализированы",
            }
            self._jobs.pop(job_id, None)
            self._jobs[job_id] = job
            self._queries[job_id] = query.key()
            self._trim()
        if chosen:
            self._submit(lambda: self._run(analysis, query, job_id, chosen, saved))
        return self.job(job_id)

    def job(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise NotFoundError("Нет такого запуска")
            return self._snapshot(job)

    def latest(self, query: TimelineQuery) -> dict[str, Any] | None:
        key = query.key()
        with self._lock:
            matches = [
                job for job_id, job in self._jobs.items() if self._queries.get(job_id) == key
            ]
            return self._snapshot(matches[-1]) if matches else None

    def _run(
        self,
        analysis: AnalysisService,
        query: TimelineQuery,
        job_id: str,
        chosen: list[Pass],
        saved: dict[str, dict[str, Any]],
    ) -> None:
        self._update(job_id, status="running", started_at=_now())
        for index, item in enumerate(chosen):
            self._update(job_id, current_scene_id=item.scene.id)
            self._item(job_id, index, state="running")
            cached = saved.get(item.scene.id)
            if cached and cached.get("retryable"):
                cached = None
            try:
                result = cached or analysis.run(
                    AnalysisRequest(
                        bbox=query.bbox,
                        date=item.scene.acquired_at.date(),
                        window_days=WINDOW_DAYS,
                        aoi_id=query.aoi_id,
                        aoi_name=query.aoi_name,
                        scene_id=item.scene.id,
                        target=query.target,
                    )
                )
            except AppError as error:
                self._item(job_id, index, state="failed", message=error.message)
                continue
            except Exception:
                logger.exception("timeline pass %s failed", item.scene.id)
                self._item(job_id, index, state="failed", message="внутренняя ошибка анализа")
                continue
            self._item(
                job_id,
                index,
                state="cached" if cached else "done",
                analysis_id=result["id"],
                status=result["status"],
            )
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            failed = sum(1 for entry in job["items"] if entry["state"] == "failed")
            job["status"] = "failed" if failed == len(job["items"]) else "done"
            job["current_scene_id"] = None
            job["finished_at"] = _now()
            if failed:
                job["message"] = f"не удалось проанализировать пролётов: {failed}"

    def _update(self, job_id: str, **fields: Any) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None:
                job.update(fields)

    def _item(self, job_id: str, index: int, **fields: Any) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None:
                job["items"][index].update(fields)

    def _trim(self) -> None:
        finished = [job for job in self._jobs.values() if job["status"] not in ACTIVE]
        while len(self._jobs) > MAX_JOBS and finished:
            stale = finished.pop(0)
            self._jobs.pop(stale["id"], None)
            self._queries.pop(stale["id"], None)

    @staticmethod
    def _snapshot(job: dict[str, Any]) -> dict[str, Any]:
        items = [dict(entry) for entry in job["items"]]
        finished = ("done", "cached", "failed")
        return {
            **{key: value for key, value in job.items() if key != "items"},
            "total": len(items),
            "completed": sum(1 for entry in items if entry["state"] in finished),
            "failed": sum(1 for entry in items if entry["state"] == "failed"),
            "items": items,
        }
