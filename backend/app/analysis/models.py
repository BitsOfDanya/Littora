from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any, Protocol

from shapely.geometry.base import BaseGeometry

from app.analysis.statuses import ResultStatus
from app.earth.catalog import Scene


@dataclass(frozen=True)
class DetectionOutcome:
    status: ResultStatus
    reason: str
    model: str | None = None
    zones: list[dict[str, Any]] = field(default_factory=list)
    layer: Any = None
    threshold: float | None = None
    retryable: bool = False
    extra_layers: dict[str, Any] = field(default_factory=dict)
    timings: dict[str, float] = field(default_factory=dict)
    pixels: bytes | None = None
    zones_total: int | None = None


@dataclass(frozen=True)
class ConcentrationOutcome:
    status: ResultStatus
    reason: str
    model: str | None = None
    value: float | None = None
    lower: float | None = None
    upper: float | None = None
    profile: str | None = None
    coverage: float | None = None


@dataclass(frozen=True)
class EstimateContext:
    target: str
    day: dt.date


class Detector(Protocol):
    name: str | None

    def detect(self, scene: Scene, area: BaseGeometry) -> DetectionOutcome: ...


class ConcentrationModel(Protocol):
    name: str | None

    def estimate(
        self,
        scene: Scene,
        area: BaseGeometry,
        detection: DetectionOutcome,
        context: EstimateContext | None = None,
    ) -> ConcentrationOutcome: ...


class UnavailableDetector:
    name = None

    def detect(self, scene: Scene, area: BaseGeometry) -> DetectionOutcome:
        return DetectionOutcome(
            status=ResultStatus.INSUFFICIENT_DATA,
            reason="модель детектора не подключена",
        )


class UnavailableConcentrationModel:
    name = None

    def estimate(
        self,
        scene: Scene,
        area: BaseGeometry,
        detection: DetectionOutcome,
        context: EstimateContext | None = None,
    ) -> ConcentrationOutcome:
        return ConcentrationOutcome(
            status=ResultStatus.CONCENTRATION_UNAVAILABLE,
            reason="модель концентрации не подключена; перенос на снимки не подтверждён",
        )
