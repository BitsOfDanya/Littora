from __future__ import annotations

import datetime as dt
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from shapely.geometry import box

from app.analysis.service import AnalysisService
from app.core.errors import AppError, NotFoundError
from app.drift.service import DRIFT_FILE
from app.earth.catalog import Scene
from app.survey.planner import MODEL_NAME, SurveyOptions, iso, plan, with_clock
from app.survey.ports import Port

SURVEY_FILE = "survey.json"
PASS_SEARCH_DAYS = 10
PASS_GAP = dt.timedelta(minutes=30)
MAX_PASSES = 8


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _read(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _pass_key(scene: Scene) -> tuple:
    return scene.platform, scene.relative_orbit, scene.acquired_at.date()


def _pass(key: tuple, items: list[Scene]) -> dict[str, Any]:
    platform, orbit, day = key
    first = min(items, key=lambda item: item.acquired_at)
    clouds = [item.cloud_cover for item in items if item.cloud_cover is not None]
    orbit_label = f"-R{orbit:03d}" if orbit is not None else ""
    return {
        "id": f"{platform}{orbit_label}-{day:%Y%m%d}",
        "platform": platform,
        "relative_orbit": orbit,
        "acquired_at": iso(first.acquired_at),
        "swath": [
            round(min(item.footprint_bbox[0] for item in items), 4),
            round(max(item.footprint_bbox[2] for item in items), 4),
        ],
        "cloud_cover": round(min(clouds), 1) if clouds else None,
        "scenes": len(items),
    }


class SurveyService:
    def __init__(self, ports: list[Port], now: Callable[[], dt.datetime] = _now) -> None:
        self.ports = ports
        self.now = now

    def _locate(
        self, analysis: AnalysisService, analysis_id: str
    ) -> tuple[dict[str, Any], Path, Path]:
        result = analysis.get(analysis_id)
        folder = analysis.storage_dir / result["id"]
        return result, folder / SURVEY_FILE, folder / DRIFT_FILE

    @staticmethod
    def _inputs(result: dict[str, Any], drift: dict[str, Any] | None) -> dict[str, Any]:
        return {
            "analysis_computed_at": result["computed_at"],
            "drift_computed_at": drift.get("computed_at") if drift else None,
        }

    def passes(
        self, analysis: AnalysisService, result: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], str | None]:
        scene = result.get("scene")
        if scene is None:
            return [], None
        t0 = dt.datetime.fromisoformat(scene["acquired_at"].replace("Z", "+00:00"))
        area = box(*result["request"]["bbox"])
        try:
            found = analysis.search_scenes(
                area, t0 + PASS_GAP, t0 + dt.timedelta(days=PASS_SEARCH_DAYS)
            )
        except AppError as error:
            return [], f"каталог снимков недоступен — пролёты после снимка не показаны: {error}"
        own = (scene["platform"], scene["relative_orbit"], t0.date())
        grouped: dict[tuple, list[Scene]] = {}
        for item in found:
            key = _pass_key(item)
            if item.is_sentinel2 and item.id != scene["id"] and key != own:
                grouped.setdefault(key, []).append(item)
        passes = sorted(
            (_pass(key, items) for key, items in grouped.items()),
            key=lambda item: item["acquired_at"],
        )[:MAX_PASSES]
        if not passes:
            return [], (
                f"в каталоге нет снимков Sentinel-2 района за {PASS_SEARCH_DAYS} сут после t0"
            )
        return passes, None

    def _compute(
        self,
        result: dict[str, Any],
        drift: dict[str, Any] | None,
        options: SurveyOptions,
        passes: list[dict[str, Any]],
        passes_note: str | None,
    ) -> dict[str, Any]:
        now = self.now()
        body = plan(result, drift, self.ports, options, passes, now)
        if passes_note:
            body["messages"].append(passes_note)
        payload = {
            "analysis_id": result["id"],
            "model": MODEL_NAME,
            **body,
            "passes_note": passes_note,
            "computed_at": iso(now),
            "inputs": self._inputs(result, drift),
        }
        return with_clock(payload, now)

    def _save(self, path: Path, payload: dict[str, Any]) -> dict[str, Any]:
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return payload

    def run(
        self, analysis: AnalysisService, analysis_id: str, options: SurveyOptions
    ) -> dict[str, Any]:
        result, path, drift_path = self._locate(analysis, analysis_id)
        drift = _read(drift_path)
        saved = _read(path)
        if (
            saved is not None
            and saved.get("model") == MODEL_NAME
            and saved.get("request") == options.as_dict()
            and saved.get("inputs") == self._inputs(result, drift)
        ):
            return with_clock(saved, self.now())
        passes, note = self.passes(analysis, result)
        return self._save(path, self._compute(result, drift, options, passes, note))

    def cached(self, analysis: AnalysisService, analysis_id: str) -> dict[str, Any]:
        result, path, drift_path = self._locate(analysis, analysis_id)
        saved = _read(path)
        if saved is None:
            raise NotFoundError("План обследования для этого анализа ещё не построен")
        drift = _read(drift_path)
        if saved.get("model") == MODEL_NAME and saved.get("inputs") == self._inputs(result, drift):
            return with_clock(saved, self.now())
        try:
            options = SurveyOptions(**saved.get("request", {}))
        except TypeError:
            options = SurveyOptions()
        payload = self._compute(
            result, drift, options, saved.get("passes", []), saved.get("passes_note")
        )
        return self._save(path, payload)
