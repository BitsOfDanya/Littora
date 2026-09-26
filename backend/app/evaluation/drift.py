import json
import logging
import math
import threading
from pathlib import Path
from typing import Any

from app.drift.forcing import CURRENTS_LABEL, ERA5_LABEL, FORECAST_LABEL, WAVES_LABEL
from app.drift.model import DriftParameters
from app.drift.service import DRIFT_STATUS_LABELS, SCENARIO_REASON, DriftService, DriftStatus
from app.schemas.drift import (
    MAX_HINDCAST_HOURS,
    MAX_HOURS,
    DriftCalibration,
    DriftCoverageHorizon,
    DriftCoverageSet,
    DriftErrorHorizon,
    DriftErrorSet,
    DriftSkill,
    DriftValidation,
)
from app.schemas.models import DriftForcing, DriftMethod

logger = logging.getLogger("littora")

DRIFT_METRICS = Path("metrics") / "drift"
DRIFTERS_FILE = "drifters.json"
SPREAD_FILE = "spread.json"
ERROR_CLASSES = ("litter_items", "blacksea")
COVERAGE_SETS = {
    "fit": "подбор · предметы NAUTILOS, 2022–2023",
    "test": "проверка · предметы NAUTILOS, 2024",
    "blacksea": "проверка · дрифтер SVP-B, Чёрное море",
}
NOMINAL = "0.9"

_lock = threading.Lock()
_cache: dict[Path, tuple[tuple[int, int], Any]] = {}


def _read(path: Path) -> Any:
    try:
        stat = path.stat()
    except OSError:
        return None
    stamp = (stat.st_mtime_ns, stat.st_size)
    with _lock:
        cached = _cache.get(path)
        if cached and cached[0] == stamp:
            return cached[1]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        logger.warning("artifact %s skipped: %s", path.name, error)
        return None
    with _lock:
        _cache[path] = (stamp, payload)
    return payload


def _interval(values: Any) -> list[float] | None:
    if isinstance(values, list) and len(values) == 2:
        return [float(value) for value in values]
    return None


def _skill(block: Any) -> DriftSkill | None:
    if not isinstance(block, dict) or block.get("value") is None:
        return None
    return DriftSkill(
        value=float(block["value"]), ci=_interval(block.get("ci")), verdict=block.get("verdict")
    )


def _horizon_keys(horizons: dict[str, Any]) -> list[str]:
    return sorted(horizons, key=int)


def _errors(payload: dict[str, Any]) -> list[DriftErrorSet]:
    sets = []
    for key in ERROR_CLASSES:
        block = payload["classes"][key]
        horizons = []
        for name in _horizon_keys(block["all"]["horizons"]):
            methods = block["all"]["horizons"][name]["methods"]
            service = methods["service_median"]
            horizons.append(
                DriftErrorHorizon(
                    horizon_h=int(name),
                    windows=int(service["windows"]),
                    drifters=int(service["drifters"]),
                    groups=int(service["groups"]),
                    service_km=float(service["separation_km"]["median"]),
                    service_ci_km=_interval(service["separation_km"].get("median_ci")),
                    stationary_km=float(methods["stationary"]["separation_km"]["median"]),
                    persistence_km=float(methods["persistence"]["separation_km"]["median"]),
                    skill_vs_stationary=_skill(service.get("skill_vs_stationary")),
                )
            )
        sets.append(DriftErrorSet(key=key, label=str(block["label"]), horizons=horizons))
    return sets


def _calibration(payload: dict[str, Any], parameters: DriftParameters) -> DriftCalibration | None:
    recommendation = payload["recommendation"]
    chosen = recommendation["parameters"]
    noise = float(chosen["velocity_noise_ms"])
    decorrelation = float(chosen["velocity_decorrelation_h"])
    if not (
        math.isclose(noise, parameters.envelope_noise_ms)
        and math.isclose(decorrelation, parameters.envelope_decorrelation_h)
    ):
        logger.warning("drift spread report does not match the service envelope parameters")
        return None
    variant = str(recommendation["variant"])
    baseline = str(payload["selection"]["baseline"])
    sets = []
    for key, label in COVERAGE_SETS.items():
        results = payload["evaluation"].get(key)
        if not isinstance(results, dict) or variant not in results or baseline not in results:
            continue
        after, before = results[variant], results[baseline]
        horizons = []
        for name in _horizon_keys(after["horizons"]):
            calibrated = after["horizons"][name]["coverage"][NOMINAL]
            horizons.append(
                DriftCoverageHorizon(
                    horizon_h=int(name),
                    windows=int(after["horizons"][name]["windows"]),
                    before=float(before["horizons"][name]["coverage"][NOMINAL]["value"]),
                    after=float(calibrated["value"]),
                    after_ci=_interval(calibrated.get("ci")),
                )
            )
        sets.append(
            DriftCoverageSet(
                key=key,
                label=label,
                windows=int(after["windows"]),
                drifters=int(after["items"]),
                groups=int(after["groups"]),
                horizons=horizons,
            )
        )
    effective = recommendation.get("effective_diffusivity_m2s")
    return DriftCalibration(
        variant=variant,
        noise_ms=noise,
        decorrelation_h=decorrelation,
        effective_diffusivity_m2s=float(effective) if effective is not None else None,
        nominal=float(NOMINAL),
        sets=sets,
    )


def drift_validation(reports_dir: Path, parameters: DriftParameters) -> DriftValidation | None:
    folder = reports_dir / DRIFT_METRICS
    sources: list[str] = []
    errors: list[DriftErrorSet] = []
    calibration = None
    drifters = _read(folder / DRIFTERS_FILE)
    if isinstance(drifters, dict):
        try:
            errors = _errors(drifters)
            sources.append(f"reports/{(DRIFT_METRICS / DRIFTERS_FILE).as_posix()}")
        except (KeyError, TypeError, ValueError) as error:
            logger.warning("artifact %s skipped: %s", DRIFTERS_FILE, error)
    spread = _read(folder / SPREAD_FILE)
    if isinstance(spread, dict):
        try:
            calibration = _calibration(spread, parameters)
        except (KeyError, TypeError, ValueError) as error:
            logger.warning("artifact %s skipped: %s", SPREAD_FILE, error)
        if calibration is not None:
            sources.append(f"reports/{(DRIFT_METRICS / SPREAD_FILE).as_posix()}")
    if not errors and calibration is None:
        return None
    return DriftValidation(errors=errors, calibration=calibration, sources=sources)


def drift_method(service: DriftService, reports_dir: Path | None = None) -> DriftMethod:
    method = service.method(MAX_HOURS)
    return DriftMethod(
        model=method["model"],
        status=DriftStatus.SCENARIO,
        label=DRIFT_STATUS_LABELS[DriftStatus.SCENARIO],
        reason=SCENARIO_REASON,
        velocity=method["velocity"],
        integration=method["integration"],
        windages=method["windage"],
        stokes=method["stokes"],
        particles=method["particles_per_variant"],
        members=method["members_per_zone"],
        diffusivity_m2s=method["diffusivity_m2s"],
        horizons_h=method["horizons_h"],
        max_hours=MAX_HOURS,
        max_hindcast_hours=MAX_HINDCAST_HOURS,
        forcing=DriftForcing(
            currents=CURRENTS_LABEL, waves=WAVES_LABEL, wind=[ERA5_LABEL, FORECAST_LABEL]
        ),
        envelope=method["envelope"],
        envelope_spread=method["envelope_spread"],
        envelope_domain_margin_km=method["envelope_domain_margin_km"],
        validation=drift_validation(reports_dir, service.parameters) if reports_dir else None,
    )
