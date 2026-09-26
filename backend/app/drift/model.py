from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass
from typing import Protocol

import numpy as np
import shapely
from shapely.geometry.base import BaseGeometry

from app.drift.forcing import Forcing
from app.drift.geo import offset


@dataclass(frozen=True)
class DriftParameters:
    windages: tuple[float, ...] = (0.005, 0.01, 0.02, 0.03)
    stokes: tuple[bool, ...] = (True, False)
    particles: int = 40
    step_s: float = 900.0
    diffusivity_m2s: float = 5.0
    point_radius_m: float = 50.0
    seed: int = 1729
    envelope_noise_ms: float = 0.2
    envelope_decorrelation_h: float = 48.0

    @property
    def variants(self) -> list[tuple[float, bool]]:
        return [(windage, stokes) for windage in self.windages for stokes in self.stokes]

    @property
    def members(self) -> int:
        return len(self.variants) * self.particles

    @property
    def central_windage(self) -> float:
        return float(np.median(self.windages))


class VelocityField(Protocol):
    def velocity(
        self,
        lon: np.ndarray,
        lat: np.ndarray,
        hours: float,
        windage: np.ndarray,
        stokes: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]: ...

    def inside(self, lon: np.ndarray, lat: np.ndarray) -> np.ndarray: ...


class LandLookup(Protocol):
    def is_land(self, lon: np.ndarray, lat: np.ndarray) -> np.ndarray: ...


def _axis_weights(
    values: np.ndarray, origin: float, step: float, count: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if count == 1:
        zeros = np.zeros(np.shape(values), dtype=int)
        return zeros, zeros, np.zeros(np.shape(values))
    position = np.clip((values - origin) / step, 0, count - 1)
    lower = np.minimum(np.floor(position).astype(int), count - 2)
    return lower, lower + 1, position - lower


class GridField:
    def __init__(self, forcing: Forcing, t0: dt.datetime) -> None:
        self.offset_h = (t0 - forcing.start).total_seconds() / 3600.0
        self.lons = forcing.lons
        self.lats = forcing.lats
        self.lon_step = float(forcing.lons[1] - forcing.lons[0]) if forcing.lons.size > 1 else 1.0
        self.lat_step = float(forcing.lats[1] - forcing.lats[0]) if forcing.lats.size > 1 else 1.0
        self.stack = np.concatenate([forcing.current, forcing.stokes, forcing.wind], axis=-1)

    def components(self, lon: np.ndarray, lat: np.ndarray, hours: float) -> np.ndarray:
        steps, rows, cols, _ = self.stack.shape
        t0, t1, wt = _axis_weights(np.array(hours + self.offset_h), 0.0, 1.0, steps)
        y0, y1, wy = _axis_weights(lat, float(self.lats[0]), self.lat_step, rows)
        x0, x1, wx = _axis_weights(lon, float(self.lons[0]), self.lon_step, cols)
        wy, wx = wy[:, None], wx[:, None]
        result = 0.0
        for time_index, time_weight in ((t0, 1 - wt), (t1, wt)):
            layer = self.stack[int(time_index)]
            south = layer[y0, x0] * (1 - wx) + layer[y0, x1] * wx
            north = layer[y1, x0] * (1 - wx) + layer[y1, x1] * wx
            result = result + (south * (1 - wy) + north * wy) * float(time_weight)
        return result

    def velocity(
        self,
        lon: np.ndarray,
        lat: np.ndarray,
        hours: float,
        windage: np.ndarray,
        stokes: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        parts = self.components(lon, lat, hours)
        east = parts[:, 0] + stokes * parts[:, 2] + windage * parts[:, 4]
        north = parts[:, 1] + stokes * parts[:, 3] + windage * parts[:, 5]
        return east, north

    def inside(self, lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
        return (
            (lon >= self.lons[0])
            & (lon <= self.lons[-1])
            & (lat >= self.lats[0])
            & (lat <= self.lats[-1])
        )


class NestedField:
    def __init__(self, inner: VelocityField, outer: VelocityField) -> None:
        self.inner = inner
        self.outer = outer

    def velocity(
        self,
        lon: np.ndarray,
        lat: np.ndarray,
        hours: float,
        windage: np.ndarray,
        stokes: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        near = self.inner.inside(lon, lat)
        east = np.empty(np.shape(lon))
        north = np.empty(np.shape(lon))
        for part, field in ((near, self.inner), (~near, self.outer)):
            if part.any():
                east[part], north[part] = field.velocity(
                    lon[part], lat[part], hours, windage[part], stokes[part]
                )
        return east, north

    def inside(self, lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
        return self.inner.inside(lon, lat) | self.outer.inside(lon, lat)


@dataclass(frozen=True)
class Trajectories:
    positions: np.ndarray
    beached_at: np.ndarray
    left_domain: np.ndarray

    @property
    def hours(self) -> int:
        return self.positions.shape[0] - 1

    def beached_by(self, hour: float) -> np.ndarray:
        return self.beached_at <= hour

    def subset(self, part: slice) -> Trajectories:
        return Trajectories(self.positions[:, part], self.beached_at[part], self.left_domain[part])


def seed_points(
    geometry: BaseGeometry, count: int, radius_m: float, rng: np.random.Generator
) -> np.ndarray:
    if geometry.area > 0:
        west, south, east, north = geometry.bounds
        found: list[np.ndarray] = []
        total = 0
        for _ in range(64):
            lon = rng.uniform(west, east, count * 4)
            lat = rng.uniform(south, north, count * 4)
            keep = shapely.contains_xy(geometry, lon, lat)
            found.append(np.column_stack([lon[keep], lat[keep]]))
            total += int(keep.sum())
            if total >= count:
                return np.concatenate(found)[:count]
    center = geometry.representative_point() if geometry.area > 0 else geometry.centroid
    radius = radius_m * np.sqrt(rng.uniform(0, 1, count))
    angle = rng.uniform(0, 2 * np.pi, count)
    lon, lat = offset(
        np.full(count, center.x),
        np.full(count, center.y),
        radius * np.cos(angle),
        radius * np.sin(angle),
    )
    return np.column_stack([lon, lat])


def integrate(
    field: VelocityField,
    land: LandLookup,
    start: np.ndarray,
    windage: np.ndarray,
    stokes: np.ndarray,
    hours: int,
    direction: int,
    parameters: DriftParameters,
    rng: np.random.Generator,
    noise_ms: float = 0.0,
    decorrelation_h: float = 0.0,
) -> Trajectories:
    per_hour = max(1, round(3600.0 / parameters.step_s))
    step_s = 3600.0 / per_hour
    spread = np.sqrt(2.0 * parameters.diffusivity_m2s * step_s)
    position = np.array(start, dtype=float)
    count = position.shape[0]
    beached = np.full(count, np.nan)
    left = np.zeros(count, dtype=bool)
    track = np.empty((hours + 1, count, 2))
    track[0] = position
    walk = noise_ms > 0
    if walk:
        if decorrelation_h <= 0:
            raise ValueError("для блуждания скорости нужно время декорреляции больше нуля")
        kicks = rng.spawn(1)[0]
        memory = math.exp(-step_s / (decorrelation_h * 3600.0))
        renewal = noise_ms * math.sqrt(1.0 - memory * memory)
        kick = kicks.standard_normal((count, 2)) * noise_ms
    for hour in range(hours):
        for step in range(per_hour):
            active = np.flatnonzero(np.isnan(beached))
            if active.size == 0:
                break
            elapsed = hour + step / per_hour
            lon, lat = position[active, 0], position[active, 1]
            w, s = windage[active], stokes[active]
            u1, v1 = field.velocity(lon, lat, direction * elapsed, w, s)
            if walk:
                u1 = u1 + kick[active, 0]
                v1 = v1 + kick[active, 1]
            mid_lon, mid_lat = offset(
                lon, lat, direction * u1 * step_s / 2, direction * v1 * step_s / 2
            )
            midpoint = direction * (elapsed + 0.5 / per_hour)
            u2, v2 = field.velocity(mid_lon, mid_lat, midpoint, w, s)
            if walk:
                u2 = u2 + kick[active, 0]
                v2 = v2 + kick[active, 1]
            noise = rng.standard_normal((active.size, 2)) * spread
            next_lon, next_lat = offset(
                lon,
                lat,
                direction * u2 * step_s + noise[:, 0],
                direction * v2 * step_s + noise[:, 1],
            )
            hit = land.is_land(next_lon, next_lat)
            beached[active[hit]] = hour + (step + 1) / per_hour
            moved = active[~hit]
            position[moved, 0] = next_lon[~hit]
            position[moved, 1] = next_lat[~hit]
            left[moved] |= ~field.inside(next_lon[~hit], next_lat[~hit])
            if walk:
                fresh = kicks.standard_normal((active.size, 2))
                kick[active] = memory * kick[active] + renewal * fresh
        track[hour + 1] = position
    return Trajectories(track, beached, left)
