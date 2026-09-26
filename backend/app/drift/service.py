from __future__ import annotations

import datetime as dt
import json
import math
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

import numpy as np
from shapely.geometry import shape
from shapely.ops import unary_union

from app.analysis.service import AnalysisService
from app.analysis.statuses import STATUS_LABELS, ResultStatus, ValueKind
from app.core.errors import NotFoundError
from app.drift import products
from app.drift.forcing import CURRENTS_LABEL, WAVES_LABEL, Domain, Forcing, ForcingError
from app.drift.geo import rounded
from app.drift.land import (
    MASK_CELL_M,
    LandMask,
    NestedLand,
    SceneClassReader,
    build_land_mask,
    scene_class_sampler,
)
from app.drift.model import (
    DriftParameters,
    GridField,
    LandLookup,
    NestedField,
    VelocityField,
    integrate,
    seed_points,
)
from app.drift.places import Place
from app.earth.catalog import CatalogError
from app.earth.raster import RasterError

DRIFT_FILE = "drift.json"
FORCING_DIR = "forcing"
MODEL_NAME = "littora-drift-2"
MAX_ZONES = 25
DOMAIN_MARGIN_KM = 50.0
ENVELOPE_MARGIN_KM = 100.0
ENVELOPE_MARINE_POINTS = 120
ENVELOPE_WIND_POINTS = 60
ENVELOPE_MASK_CELL_M = 1_000.0
SCENARIO_REASON = (
    "сценарий, а не проверенный прогноз: ансамбль вариантов парусности и стоксова дрейфа "
    "на ветре, волнах и течениях Open-Meteo; облако 90 % откалибровано по 4 миссиям "
    "NAUTILOS (предметы мусора) и проверено на 1 дрифтере в Чёрном море; независимых "
    "случаев мало; медиана ошибки через 72 ч ≈ 24 км — значимо не лучше неподвижной точки"
)


class DriftStatus(StrEnum):
    SCENARIO = "scenario"
    NO_ZONES = "no_zones"
    INSUFFICIENT_DATA = "insufficient_data"


DRIFT_STATUS_LABELS: dict[DriftStatus, str] = {
    DriftStatus.SCENARIO: "сценарий дрейфа",
    DriftStatus.NO_ZONES: "нет зон для дрейфа",
    DriftStatus.INSUFFICIENT_DATA: STATUS_LABELS[ResultStatus.INSUFFICIENT_DATA],
}


class ForcingSource(Protocol):
    def load(
        self,
        domain: Domain,
        start: dt.datetime,
        end: dt.datetime,
        marine_points: int = ...,
        wind_points: int = ...,
    ) -> Forcing: ...


def _now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


def _labels(forcing: Forcing) -> dict[str, str | None]:
    provenance = forcing.provenance
    return {
        "currents": CURRENTS_LABEL
        if provenance["currents"]["available"]
        else "нет данных SMOC — без течений",
        "wind": provenance["wind"]["source"],
        "waves": f"{WAVES_LABEL} → стоксов дрейф" if provenance["waves"]["available"] else None,
    }


def _gap_notes(provenance: dict[str, Any]) -> list[str]:
    notes = []
    if not provenance["currents"]["available"]:
        notes.append("течений SMOC на эти даты нет — дрейф только от ветра и волн")
    if not provenance["waves"]["available"]:
        notes.append("волн MFWAM на эти даты нет — стоксов дрейф не учтён")
    quantum = provenance["currents"].get("quantum_ms")
    if quantum:
        step = f"{quantum:g}".replace(".", ",")
        notes.append(f"компоненты течения в ответе Open-Meteo квантованы с шагом {step} м/с")
    names = {"currents": "о течениях", "waves": "о волнах", "wind": "о ветре"}
    for key, name in names.items():
        hours = provenance[key].get("filled_hours")
        if hours:
            notes.append(f"{hours} ч окна без данных {name} — взяты ближайшие по времени значения")
    return notes


def _extent(*forcings: Forcing) -> tuple[float, float, float, float]:
    return (
        min(float(forcing.lons[0]) for forcing in forcings),
        min(float(forcing.lats[0]) for forcing in forcings),
        max(float(forcing.lons[-1]) for forcing in forcings),
        max(float(forcing.lats[-1]) for forcing in forcings),
    )


def _outside_note(forecasts: list[dict[str, Any]], margin_km: float) -> str | None:
    worst: tuple[float, int] | None = None
    for forecast in forecasts:
        for envelope in forecast["envelopes"]:
            share = envelope.get("outside_domain", 0.0)
            if share > 0 and (worst is None or (share, envelope["horizon_h"]) > worst):
                worst = (share, envelope["horizon_h"])
    if worst is None:
        return None
    share, horizon = worst
    return (
        f"облако 90 % выходит за область данных форсинга (±{margin_km:g} км): через {horizon} ч "
        f"за её пределами до {share:.0%} частиц облака — там ветер и течения взяты с края, "
        "контур обрезан по её границе"
    )


def _wind_summary(field: GridField, origins: np.ndarray, hours: int) -> tuple[int, float]:
    samples = np.concatenate(
        [
            field.components(origins[:, 0], origins[:, 1], float(hour))[:, 4:6]
            for hour in range(hours + 1)
        ]
    )
    east, north = samples.mean(axis=0)
    from_deg = round((math.degrees(math.atan2(-east, -north)) + 360.0) % 360.0) % 360
    return from_deg, round(float(np.hypot(samples[:, 0], samples[:, 1]).mean()), 1)


class DriftService:
    def __init__(
        self,
        forcing: ForcingSource,
        places: list[Place] | None = None,
        scene_classes: SceneClassReader | None = scene_class_sampler,
        parameters: DriftParameters | None = None,
    ) -> None:
        self.forcing = forcing
        self.places = places or []
        self.scene_classes = scene_classes
        self.parameters = parameters or DriftParameters()

    def _locate(self, analysis: AnalysisService, analysis_id: str) -> tuple[dict[str, Any], Path]:
        result = analysis.get(analysis_id)
        return result, analysis.storage_dir / result["id"] / DRIFT_FILE

    def cached(self, analysis: AnalysisService, analysis_id: str) -> dict[str, Any]:
        _, path = self._locate(analysis, analysis_id)
        if not path.exists():
            raise NotFoundError("Дрейф для этого анализа ещё не рассчитан")
        saved = json.loads(path.read_text(encoding="utf-8"))
        if saved.get("model") != MODEL_NAME:
            raise NotFoundError("Дрейф рассчитан прежней версией модели — рассчитайте заново")
        return saved

    def run(
        self,
        analysis: AnalysisService,
        analysis_id: str,
        hours: int = 72,
        hindcast_hours: int = 48,
    ) -> dict[str, Any]:
        result, path = self._locate(analysis, analysis_id)
        request = {"hours": hours, "hindcast_hours": hindcast_hours}
        if path.exists():
            saved = json.loads(path.read_text(encoding="utf-8"))
            envelope = (saved.get("forcing") or {}).get("envelope") or {}
            if (
                saved.get("request") == request
                and saved.get("model") == MODEL_NAME
                and envelope.get("available", True)
            ):
                return saved
        payload = self._compute(analysis, result, request)
        if payload["status"]["status"] != DriftStatus.INSUFFICIENT_DATA:
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return payload

    def method(self, hours: int) -> dict[str, Any]:
        parameters = self.parameters
        return {
            "model": MODEL_NAME,
            "velocity": "u = u_теч + s·u_Стокс + α·U10; u_теч = SMOC − оценка Стокса; s ∈ {1, 0}",
            "integration": f"RK2 (средняя точка), шаг {parameters.step_s:g} с, выход каждый час",
            "windage": list(parameters.windages),
            "stokes": list(parameters.stokes),
            "variants": len(parameters.variants),
            "particles_per_variant": parameters.particles,
            "members_per_zone": parameters.members,
            "diffusivity_m2s": parameters.diffusivity_m2s,
            "diffusion": "случайное блуждание σ = √(2·K·Δt); K порядка Окубо (1971) "
            "для масштаба ячейки форсинга ~8–18 км",
            "seed": parameters.seed,
            "seeding": "равномерно внутри контура зоны; точечная зона — круг "
            f"{parameters.point_radius_m:g} м",
            "beaching": "частица, шагнувшая на сушу, остаётся в последней точке на воде",
            "envelope": "выпуклая оболочка 90 % частиц на плаву, ближайших к их медиане, "
            f"+ {products.ENVELOPE_MARGIN_M:g} м — по отдельному прогону с разбросом скорости; "
            "медианный путь, выброс на берег, источники, probability и afloat — по основному "
            "прогону",
            "envelope_spread": "к скорости каждой частицы добавлено случайное блуждание "
            "(процесс Орнштейна — Уленбека) по каждой компоненте: "
            f"σ = {parameters.envelope_noise_ms:g} м/с, "
            f"τ = {parameters.envelope_decorrelation_h:g} ч; подобрано по доле реальных "
            "положений дрифтеров внутри облаков 50 % и 90 % через 24, 48 и 72 ч",
            "envelope_noise_ms": parameters.envelope_noise_ms,
            "envelope_decorrelation_h": parameters.envelope_decorrelation_h,
            "envelope_calibration": "облако 90 % откалибровано по 4 миссиям NAUTILOS "
            "(предметы мусора, 2022–2023) и проверено на 2 миссиях 2024 г. и 1 дрифтере "
            "в Чёрном море; независимых случаев мало (reports/metrics/drift/spread.json)",
            "envelope_domain_margin_km": ENVELOPE_MARGIN_KM,
            "envelope_forcing": f"прогон с разбросом: до ±{DOMAIN_MARGIN_KM:g} км — "
            f"основная сетка, дальше до ±{ENVELOPE_MARGIN_KM:g} км — грубая (не больше "
            f"{ENVELOPE_MARINE_POINTS} узлов моря и {ENVELOPE_WIND_POINTS} узлов ветра), берег "
            "там — по сетке Open-Meteo Marine; за пределами области ветер и течения взяты "
            "с края, контур обрезан по её границе, доля частиц облака за ней — outside_domain",
            "probability": "0,9 × доля частиц основного прогона на плаву: вероятность оказаться "
            "в контуре, если облако откалибровано",
            "probability_interval": "интервал Уилсона 90 % по частицам: только разброс "
            "ансамбля, без ошибки ветра и течений",
            "coast_segments": f"точки выноса ближе {products.SEGMENT_LINK_M:g} м — один участок",
            "sources": "доля обратных траекторий, вошедших в район порта или устья реки "
            "из справочника мест, по первому входу назад во времени; район, где зона "
            "уже находится на t0, источником не считается",
            "horizons_h": [horizon for horizon in products.HORIZONS_H if horizon <= hours],
            "domain_margin_km": DOMAIN_MARGIN_KM,
            "zones_limit": MAX_ZONES,
        }

    def _payload(
        self,
        result: dict[str, Any],
        request: dict[str, int],
        status: DriftStatus,
        reason: str,
        **fields: Any,
    ) -> dict[str, Any]:
        return {
            "analysis_id": result["id"],
            "model": MODEL_NAME,
            "status": {"status": status.value, "label": DRIFT_STATUS_LABELS[status]},
            "reason": reason,
            "value_kind": ValueKind.SCENARIO.value,
            "request": request,
            "computed_at": _now(),
            "zones": fields.get("zones", {"total": 0, "computed": 0, "limit": MAX_ZONES}),
            "run": fields.get("run"),
            "forcing": fields.get("forcing"),
            "method": self.method(request["hours"]),
            "current_field": fields.get("current_field"),
            "forecasts": fields.get("forecasts", []),
            "messages": fields.get("messages", []),
        }

    def _land_sampler(self, analysis: AnalysisService, scene: dict[str, Any], domain: Domain):
        if self.scene_classes is None:
            return None, None
        try:
            item = analysis.catalog.get(scene["collection"], scene["id"])
            return self.scene_classes(item, domain, MASK_CELL_M), None
        except (CatalogError, RasterError) as error:
            return None, f"маска суши по снимку недоступна ({error}) — берег по сетке Open-Meteo"

    def _cloud(
        self,
        area: tuple[float, float, float, float],
        anchor: dt.datetime,
        t0: dt.datetime,
        hours: int,
        forcing: Forcing,
        land: LandMask,
    ) -> tuple[VelocityField, LandLookup, tuple[float, float, float, float], dict[str, Any]]:
        domain = Domain.around(area, ENVELOPE_MARGIN_KM)
        field = GridField(forcing, t0)
        try:
            wide = self.forcing.load(
                domain,
                anchor - dt.timedelta(hours=1),
                anchor + dt.timedelta(hours=hours + 2),
                marine_points=ENVELOPE_MARINE_POINTS,
                wind_points=ENVELOPE_WIND_POINTS,
            )
        except ForcingError as error:
            info = {
                "available": False,
                "margin_km": DOMAIN_MARGIN_KM,
                "reason": str(error),
                "bounds": [round(value, 5) for value in _extent(forcing)],
            }
            return field, land, _extent(forcing), info
        coast = build_land_mask(
            domain, wide, None, np.empty((0, 2)), None, cell_m=ENVELOPE_MASK_CELL_M
        )
        bounds = _extent(forcing, wide)
        info = {
            "available": True,
            "margin_km": ENVELOPE_MARGIN_KM,
            "bounds": [round(value, 5) for value in bounds],
            "grid": wide.provenance.get("grid"),
            "wind": wide.provenance["wind"]["source"],
            "fetched_at": wide.provenance["fetched_at"],
            "land": coast.provenance,
        }
        return NestedField(field, GridField(wide, t0)), NestedLand(land, coast), bounds, info

    def _compute(
        self, analysis: AnalysisService, result: dict[str, Any], request: dict[str, int]
    ) -> dict[str, Any]:
        hours, hindcast = request["hours"], request["hindcast_hours"]
        scene = result.get("scene")
        if scene is None:
            return self._payload(
                result,
                request,
                DriftStatus.INSUFFICIENT_DATA,
                "у анализа нет снимка — нет момента t0 для дрейфа",
            )
        zones = [zone for zone in result["detection"]["zones"] if zone.get("geometry")]
        selected = zones[:MAX_ZONES]
        counts = {"total": len(zones), "computed": len(selected), "limit": MAX_ZONES}
        if not zones:
            return self._payload(
                result,
                request,
                DriftStatus.NO_ZONES,
                "в анализе нет зон детекции — дрейф не рассчитывается",
                zones=counts,
            )
        geometries = [shape(zone["geometry"]) for zone in selected]
        t0 = dt.datetime.fromisoformat(scene["acquired_at"].replace("Z", "+00:00"))
        anchor = t0.replace(minute=0, second=0, microsecond=0)
        area = unary_union(geometries).bounds
        domain = Domain.around(area, DOMAIN_MARGIN_KM)
        try:
            forcing = self.forcing.load(
                domain,
                anchor - dt.timedelta(hours=hindcast + 1),
                anchor + dt.timedelta(hours=hours + 2),
            )
        except ForcingError as error:
            return self._payload(
                result,
                request,
                DriftStatus.INSUFFICIENT_DATA,
                f"нет данных ветра, волн или течений: {error}",
                zones=counts,
            )
        parameters = self.parameters
        rng = np.random.default_rng(parameters.seed)
        seeds = [
            seed_points(geometry, parameters.particles, parameters.point_radius_m, rng)
            for geometry in geometries
        ]
        messages = _gap_notes(forcing.provenance)
        sampler, problem = self._land_sampler(analysis, scene, domain)
        if problem:
            messages.append(problem)
        land = build_land_mask(
            domain, forcing, sampler, np.concatenate(seeds), scene["id"] if sampler else None
        )
        variants = parameters.variants
        per_zone = parameters.members
        variant = np.tile(np.repeat(np.arange(len(variants)), parameters.particles), len(seeds))
        windage = np.array([value for value, _ in variants])[variant]
        stokes = np.array([1.0 if flag else 0.0 for _, flag in variants])[variant]
        start = np.concatenate([np.tile(points, (len(variants), 1)) for points in seeds])
        field = GridField(forcing, t0)
        forward = integrate(
            field,
            land,
            start,
            windage,
            stokes,
            hours,
            1,
            parameters,
            np.random.default_rng(parameters.seed + 1),
        )
        backward = integrate(
            field,
            land,
            start,
            windage,
            stokes,
            hindcast,
            -1,
            parameters,
            np.random.default_rng(parameters.seed + 2),
        )
        cloud_field, cloud_land, bounds, cloud_info = self._cloud(
            area, anchor, t0, hours, forcing, land
        )
        cloud = integrate(
            cloud_field,
            cloud_land,
            start,
            windage,
            stokes,
            hours,
            1,
            parameters,
            np.random.default_rng(parameters.seed + 1),
            parameters.envelope_noise_ms,
            parameters.envelope_decorrelation_h,
        )
        if not cloud_info["available"]:
            messages.append(
                f"форсинг на расширенной области ±{ENVELOPE_MARGIN_KM:g} км для облака 90 % "
                f"не загружен ({cloud_info['reason']}) — облако считается на области "
                f"±{DOMAIN_MARGIN_KM:g} км; повторный расчёт попробует снова"
            )
        labels = _labels(forcing)
        run_at = forcing.provenance["fetched_at"]
        issued_at = _now()
        forecasts = []
        enclosed: dict[str, int] = {}
        for index, (zone, geometry) in enumerate(zip(selected, geometries, strict=True)):
            part = slice(index * per_zone, (index + 1) * per_zone)
            ahead, behind = forward.subset(part), backward.subset(part)
            path = products.median_path(ahead.positions)
            segments = products.beaching_segments(ahead, self.places)
            sources, enclosing = products.source_estimates(behind, self.places)
            for name in enclosing:
                enclosed[name] = enclosed.get(name, 0) + 1
            origin = zone.get("centroid") or [geometry.centroid.x, geometry.centroid.y]
            forecasts.append(
                {
                    "candidate_id": zone.get("id") or f"zone-{index + 1}",
                    "issued_at": issued_at,
                    "forcing": {**labels, "run_at": run_at},
                    "windage_ratio": parameters.central_windage,
                    "origin": rounded(origin),
                    "median_path": path,
                    "envelopes": products.envelopes(
                        ahead, path, cloud=cloud.subset(part), bounds=bounds
                    ),
                    "beaching_risk": products.beaching_risk(segments),
                    "hindcast_path": products.median_path(behind.positions)[::-1],
                    "beached_by_hour": products.beached_by_hour(ahead),
                    "beaching": segments,
                    "beaching_any": products.wilson(
                        int(np.isfinite(ahead.beached_at).sum()), per_zone
                    ),
                    "sources": sources,
                    "variants": products.variant_summaries(ahead, variant[part], variants),
                    "members": per_zone,
                    "left_domain": round(float(ahead.left_domain.mean()), 3),
                }
            )
        origins = np.array([forecast["origin"] for forecast in forecasts])
        wind_from, wind_speed = _wind_summary(field, origins, hours)
        if len(zones) > MAX_ZONES:
            messages.append(
                f"дрейф рассчитан для {MAX_ZONES} зон с наибольшей вероятностью из {len(zones)}"
            )
        for name, count in enclosed.items():
            messages.append(
                f"зон внутри района «{name}» на t0: {count} из {len(selected)} — "
                "этот район им источником не приписывается"
            )
        if not self.places:
            messages.append("справочник мест не найден — источники не оцениваются")
        if forward.left_domain.any():
            messages.append(
                f"{forward.left_domain.mean():.0%} частиц основного прогона вышли за область "
                "форсинга — дальше ветер и течения взяты с её края"
            )
        outside = _outside_note(forecasts, cloud_info["margin_km"])
        if outside:
            messages.append(outside)
        return self._payload(
            result,
            request,
            DriftStatus.SCENARIO,
            SCENARIO_REASON,
            zones=counts,
            run={
                "t0": scene["acquired_at"],
                "run_at": run_at,
                "issued_at": issued_at,
                "ensemble_size": per_zone,
                "windage_ratio": parameters.central_windage,
                "windage_ratios": list(parameters.windages),
                "wind_from_deg": wind_from,
                "wind_speed_ms": wind_speed,
                "wind_window_h": [0, hours],
                "hours": hours,
                "hindcast_hours": hindcast,
                "currents": labels["currents"],
                "wind": labels["wind"],
                "waves": labels["waves"],
                "model": MODEL_NAME,
            },
            forcing={**forcing.provenance, "land": land.provenance, "envelope": cloud_info},
            current_field=products.current_field(forcing, t0, land),
            forecasts=forecasts,
            messages=messages,
        )
