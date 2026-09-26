from __future__ import annotations

import datetime as dt
import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
from shapely.geometry import MultiPoint, Point, shape

from app.drift import products
from app.drift.forcing import Domain, Forcing
from app.drift.geo import from_local, rounded, to_local
from app.drift.land import build_land_mask
from app.drift.model import DriftParameters, GridField, Trajectories, integrate, seed_points
from littora_ml.drift_check.windows import Window

ROUND = 5


@dataclass(frozen=True)
class Setup:
    hours: int
    hindcast_hours: int
    margin_km: float
    horizons: tuple[int, ...]
    shares: tuple[float, ...]
    service: DriftParameters
    grid: DriftParameters

    def signature(self) -> dict[str, Any]:
        def describe(parameters: DriftParameters) -> dict[str, Any]:
            return {
                "windages": list(parameters.windages),
                "stokes": list(parameters.stokes),
                "particles": parameters.particles,
                "step_s": parameters.step_s,
                "diffusivity_m2s": parameters.diffusivity_m2s,
                "point_radius_m": parameters.point_radius_m,
                "seed": parameters.seed,
            }

        return {
            "hours": self.hours,
            "hindcast_hours": self.hindcast_hours,
            "margin_km": self.margin_km,
            "horizons": list(self.horizons),
            "shares": list(self.shares),
            "service": describe(self.service),
            "grid": describe(self.grid),
        }


def forcing_request(window: Window, setup: Setup) -> tuple[Domain, dt.datetime, dt.datetime]:
    lon, lat = (float(value) for value in window.start)
    anchor = window.moment.replace(minute=0, second=0, microsecond=0)
    domain = Domain.around((lon, lat, lon, lat), setup.margin_km)
    return (
        domain,
        anchor - dt.timedelta(hours=setup.hindcast_hours + 1),
        anchor + dt.timedelta(hours=setup.hours + 2),
    )


def run_members(
    field: GridField,
    land: Any,
    points: np.ndarray,
    parameters: DriftParameters,
    hours: int,
) -> tuple[Trajectories, np.ndarray]:
    variants = parameters.variants
    variant = np.repeat(np.arange(len(variants)), parameters.particles)
    windage = np.array([value for value, _ in variants])[variant]
    stokes = np.array([1.0 if flag else 0.0 for _, flag in variants])[variant]
    start = np.tile(points, (len(variants), 1))
    trajectories = integrate(
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
    return trajectories, variant


def envelope_polygon(points: np.ndarray, anchor: Sequence[float], share: float):
    if len(points):
        center = np.median(points, axis=0)
        xy = to_local(center, points[:, 0], points[:, 1])
        core = math.ceil(share * len(points))
        nearest = np.argsort(np.hypot(xy[:, 0], xy[:, 1]), kind="stable")[:core]
        hull = MultiPoint(xy[nearest]).convex_hull
    else:
        center, hull = np.asarray(anchor, dtype=float), Point(0.0, 0.0)
    outline = hull.buffer(products.ENVELOPE_MARGIN_M, quad_segs=6)
    ring = from_local(center, np.asarray(outline.exterior.coords))
    return shape({"type": "Polygon", "coordinates": [[rounded(point) for point in ring]]})


def spread_km(points: np.ndarray) -> float:
    if not len(points):
        return 0.0
    center = np.median(points, axis=0)
    xy = to_local(center, points[:, 0], points[:, 1])
    return float(np.median(np.hypot(xy[:, 0], xy[:, 1]))) / 1000.0


def _path(values: np.ndarray) -> list[list[float]]:
    return [[round(float(lon), ROUND), round(float(lat), ROUND)] for lon, lat in values]


def wind_along(field: GridField, track: np.ndarray, horizon: int) -> dict[str, float]:
    speeds = []
    for hour in range(horizon + 1):
        point = track[hour]
        if not np.all(np.isfinite(point)):
            continue
        parts = field.components(np.array([point[0]]), np.array([point[1]]), float(hour))
        speeds.append(float(np.hypot(parts[0, 4], parts[0, 5])))
    return {
        "mean_ms": round(float(np.mean(speeds)), 3) if speeds else None,
        "t0_ms": round(speeds[0], 3) if speeds else None,
    }


def ensemble_summary(trajectories: Trajectories, window: Window, setup: Setup) -> dict[str, Any]:
    path = products.median_path(trajectories.positions)
    horizons = tuple(h for h in setup.horizons if h <= trajectories.hours)
    service_envelopes = {
        item["horizon_h"]: shape(item["polygon"])
        for item in products.envelopes(trajectories, path, horizons)
    }
    cover: dict[str, dict[str, bool | None]] = {}
    spread: dict[str, float] = {}
    afloat: dict[str, float] = {}
    for horizon in horizons:
        observed = window.track[horizon]
        alive = ~trajectories.beached_by(horizon)
        points = trajectories.positions[horizon][alive]
        afloat[str(horizon)] = round(float(alive.mean()), 3)
        spread[str(horizon)] = round(spread_km(points), 3)
        if not np.all(np.isfinite(observed)):
            cover[str(horizon)] = {f"{share:g}": None for share in setup.shares}
            continue
        target = Point(float(observed[0]), float(observed[1]))
        entry: dict[str, bool | None] = {}
        for share in setup.shares:
            polygon = (
                service_envelopes[horizon]
                if math.isclose(share, products.ENVELOPE_SHARE)
                else envelope_polygon(points, path[horizon], share)
            )
            entry[f"{share:g}"] = bool(polygon.covers(target))
        cover[str(horizon)] = entry
    return {
        "median": path,
        "cover": cover,
        "spread_km": spread,
        "afloat": afloat,
        "beached": round(float(np.isfinite(trajectories.beached_at).mean()), 3),
        "left_domain": round(float(trajectories.left_domain.mean()), 3),
    }


def simulate_window(window: Window, forcing: Forcing, setup: Setup) -> dict[str, Any]:
    domain, _, _ = forcing_request(window, setup)
    provenance = forcing.provenance
    base = {
        "id": window.id,
        "forcing": {
            "currents": bool(provenance["currents"]["available"]),
            "waves": bool(provenance["waves"]["available"]),
            "wind": provenance["wind"]["source"],
            "marine_step_deg": provenance["grid"]["marine_step_deg"],
            "quantum_ms": provenance["currents"].get("quantum_ms"),
            "filled_hours": {
                key: provenance[key].get("filled_hours") for key in ("currents", "waves", "wind")
            },
        },
    }
    if not (provenance["currents"]["available"] and provenance["waves"]["available"]):
        return {**base, "status": "no_marine_forcing"}
    service = setup.service
    lon, lat = (float(value) for value in window.start)
    rng = np.random.default_rng(service.seed)
    points = seed_points(Point(lon, lat), service.particles, service.point_radius_m, rng)
    land = build_land_mask(domain, forcing, None, points, None)
    field = GridField(forcing, window.moment)
    ensemble, _ = run_members(field, land, points, service, setup.hours)
    grid, variant = run_members(field, land, points, setup.grid, setup.hours)
    paths = [
        _path(np.median(grid.positions[:, variant == index], axis=1))
        for index in range(len(setup.grid.variants))
    ]
    return {
        **base,
        "status": "ok",
        "land_share": land.provenance["land_share"],
        "ensemble": ensemble_summary(ensemble, window, setup),
        "grid": {
            "variants": [[windage, stokes] for windage, stokes in setup.grid.variants],
            "paths": paths,
            "beached": [
                round(float(np.isfinite(grid.beached_at[variant == index]).mean()), 3)
                for index in range(len(setup.grid.variants))
            ],
        },
        "wind": wind_along(field, window.track, window.horizon),
    }
