from __future__ import annotations

import calendar
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from shapely.geometry.base import BaseGeometry

from app.analysis.models import (
    ConcentrationOutcome,
    DetectionOutcome,
    EstimateContext,
    UnavailableConcentrationModel,
)
from app.analysis.statuses import ResultStatus
from app.earth.catalog import Scene


def local_xy(lat: float, lon: float, reference: dict[str, float]) -> tuple[float, float]:
    lat0, lon0 = reference["latitude"], reference["longitude"]
    return (lon - lon0) * 111.32 * math.cos(math.radians(lat0)), (lat - lat0) * 110.57


KM_PER_DEGREE = 110.0


def calendar_day(day) -> int:
    number = day.timetuple().tm_yday
    return number - 1 if calendar.isleap(day.year) and number >= 60 else number


def padded_bbox(south: float, north: float, west: float, east: float, km: float):
    south, north = south - km / KM_PER_DEGREE, north + km / KM_PER_DEGREE
    edge = min(89.9, max(abs(south), abs(north)))
    pad = km / (KM_PER_DEGREE * math.cos(math.radians(edge)))
    return west - pad, south, east + pad, north


def seasonal(day) -> tuple[float, float]:
    angle = 2 * math.pi * (day.timetuple().tm_yday - 1) / 365.25
    return math.sin(angle), math.cos(angle)


@dataclass(frozen=True)
class ProfileModel:
    spec: dict[str, Any]

    @property
    def profile(self) -> str:
        return self.spec["profile"]

    @property
    def target(self) -> str:
        return self.spec["target_key"]

    def _points(self) -> np.ndarray:
        return np.asarray(self.spec["points"], dtype=float)

    def distance_km(self, x: float, y: float) -> float:
        points = self._points()
        return float(np.sqrt((points[:, 0] - x) ** 2 + (points[:, 1] - y) ** 2).min())

    def bounds(self) -> tuple[float, float, float, float]:
        points = self._points()
        lat0, lon0 = self.spec["reference"]["latitude"], self.spec["reference"]["longitude"]
        lats = lat0 + points[:, 1] / 110.57
        lons = lon0 + points[:, 0] / (111.32 * math.cos(math.radians(lat0)))
        return padded_bbox(
            float(lats.min()),
            float(lats.max()),
            float(lons.min()),
            float(lons.max()),
            self.spec["domain"]["max_distance_km"],
        )

    def domain_geometry(self) -> BaseGeometry:
        from shapely.geometry import Point, mapping, shape
        from shapely.ops import transform, unary_union

        radius = float(self.spec["domain"]["max_distance_km"])
        lat0, lon0 = self.spec["reference"]["latitude"], self.spec["reference"]["longitude"]
        scale = 111.32 * math.cos(math.radians(lat0))
        union = unary_union([Point(x, y).buffer(radius, 32) for x, y, *_ in self.spec["points"]])
        lonlat = transform(lambda x, y, z=None: (lon0 + x / scale, lat0 + y / 110.57), union)
        return shape(mapping(lonlat.simplify(0.01)))

    def in_area(self, lat: float, lon: float) -> bool:
        west, south, east, north = self.bounds()
        if not (west <= lon <= east and south <= lat <= north):
            return False
        x, y = local_xy(lat, lon, self.spec["reference"])
        return self.distance_km(x, y) <= self.spec["domain"]["max_distance_km"]

    def in_season(self, day) -> bool:
        season = self.spec["domain"]["season"]
        start, end, doy = season["doy_start"], season["doy_end"], calendar_day(day)
        return start <= doy <= end if start <= end else doy >= start or doy <= end

    def covers(self, lat: float, lon: float, day) -> bool:
        return self.in_area(lat, lon) and self.in_season(day)

    def season_reason(self, day) -> str:
        season = self.spec["domain"]["season"]
        first, last = season["span"]
        return (
            f"дата {day:%d.%m.%Y} вне сезона полевых данных профиля {self.profile}: "
            f"съёмки {first}–{last}, допуск ±{season['margin_days']} дн."
        )

    def features(self, lat: float, lon: float, day) -> dict[str, float]:
        x, y = local_xy(lat, lon, self.spec["reference"])
        sin, cos = seasonal(day)
        return {"x_km": x, "y_km": y, "doy_sin": sin, "doy_cos": cos}

    def predict(self, lat: float, lon: float, day) -> float:
        kind = self.spec["kind"]
        values = self.features(lat, lon, day)
        if kind == "median":
            return float(self.spec["constant"])
        if kind == "idw":
            points = self._points()
            distance = np.sqrt(
                (points[:, 0] - values["x_km"]) ** 2 + (points[:, 1] - values["y_km"]) ** 2
            )
            order = np.argsort(distance)[: self.spec["params"].get("k", 5)]
            weights = 1 / np.maximum(distance[order], 1.0) ** self.spec["params"].get("power", 2)
            logs = np.log1p(points[order, 2])
            return float(np.expm1((weights * logs).sum() / weights.sum()))
        if kind == "tweedie":
            glm = self.spec["glm"]
            row = np.array([values[name] for name in self.spec["features"]])
            z = (row - np.asarray(glm["mean"])) / np.asarray(glm["scale"])
            return float(math.exp(glm["intercept"] + float(np.dot(glm["coef"], z))))
        raise ValueError(f"unsupported model kind {kind}")

    def interval(self, value: float) -> tuple[float, float]:
        quantile = self.spec["conformal"]["log_quantile"]
        log = math.log1p(max(value, 0.0))
        return max(math.expm1(log - quantile), 0.0), math.expm1(log + quantile)


class FieldConcentrationModel:
    def __init__(self, models: list[ProfileModel]) -> None:
        self.models = models
        self.name = "field-profiles:" + "+".join(sorted(model.profile for model in models))
        specs = sorted((model.spec for model in models), key=lambda spec: spec["profile"])
        self.fingerprint = hashlib.sha256(
            json.dumps(specs, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()[:16]

    @classmethod
    def load(cls, directory: Path):
        files = sorted(directory.glob("*.json")) if directory.exists() else []
        models = [ProfileModel(json.loads(path.read_text(encoding="utf-8"))) for path in files]
        return cls(models) if models else UnavailableConcentrationModel()

    def domains(self) -> dict[str, Any]:
        from shapely.geometry import mapping

        features = []
        for model in self.models:
            spec = model.spec
            season = spec["domain"]["season"]
            window = f"{season['span'][0]}–{season['span'][1]} ±{season['margin_days']} сут"
            lower, upper = model.interval(float(spec.get("constant") or 0))
            features.append(
                {
                    "type": "Feature",
                    "geometry": mapping(model.domain_geometry()),
                    "properties": {
                        "profile": model.profile,
                        "target": model.target,
                        "model": spec["model"],
                        "value": round(float(spec.get("constant") or 0), 1),
                        "lower": round(lower, 1),
                        "upper": round(upper, 1),
                        "max_distance_km": spec["domain"]["max_distance_km"],
                        "season": window,
                        "points": len(spec["points"]),
                    },
                }
            )
        return {"type": "FeatureCollection", "features": features}

    def estimate(
        self,
        scene: Scene,
        area: BaseGeometry,
        detection: DetectionOutcome,
        context: EstimateContext | None = None,
    ) -> ConcentrationOutcome:
        centroid = area.centroid
        lat, lon = centroid.y, centroid.x
        target = context.target if context else None
        candidates = [model for model in self.models if target in (None, model.target)]
        day = context.day if context else scene.acquired_at.date()
        model = next((model for model in candidates if model.covers(lat, lon, day)), None)
        if model is None:
            nearby = [model for model in candidates if model.in_area(lat, lon)]
            profiles = ", ".join(m.profile for m in candidates) or "нет моделей для этой цели"
            reason = f"район вне области полевых данных профилей ({profiles})"
            return ConcentrationOutcome(
                status=ResultStatus.CONCENTRATION_UNAVAILABLE,
                reason=nearby[0].season_reason(day) if nearby else reason,
            )
        value = model.predict(lat, lon, day)
        lower, upper = model.interval(value)
        return ConcentrationOutcome(
            status=ResultStatus.RESEARCH_ESTIMATE,
            reason=f"{model.spec['reason']}; по снимку концентрация не выводится",
            model=f"{model.profile}:{model.spec['model']}",
            value=round(value, 2),
            lower=round(lower, 2),
            upper=round(upper, 2),
            profile=model.profile,
            coverage=model.spec["conformal"]["empirical"],
        )
