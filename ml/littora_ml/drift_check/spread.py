from __future__ import annotations

import datetime as dt
import gzip
import hashlib
import json
import math
import multiprocessing
from collections.abc import Callable, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from shapely.geometry import MultiPoint, Point

from app.drift import products
from app.drift.forcing import ForcingError, OpenMeteoForcing
from app.drift.geo import offset, to_local
from app.drift.land import build_land_mask
from app.drift.model import (
    DriftParameters,
    GridField,
    LandLookup,
    Trajectories,
    VelocityField,
    seed_points,
)
from littora_ml.common.io import write_json
from littora_ml.common.paths import resolve
from littora_ml.drift_check.figures import spread_figure
from littora_ml.drift_check.metrics import cluster_resamples, finite_mean, interval, separation_km
from littora_ml.drift_check.openmeteo import BlockCachedClient, BlockStore, Throttle
from littora_ml.drift_check.report import bootstrap_group
from littora_ml.drift_check.run import Queued, build_queue, build_setup
from littora_ml.drift_check.simulate import Setup, forcing_request, spread_km
from littora_ml.drift_check.windows import Window

VERSION = 2
HOUR_S = 3600.0
SETS = ("fit", "test", "blacksea")
SET_LABELS = {
    "fit": "подбор: предметы NAUTILOS и SVP без дрога, 2022–2023",
    "test": "проверка: предметы NAUTILOS и SVP без дрога, 2024",
    "blacksea": "проверка: SVP-B 4401656, Чёрное море, свободный дрейф 2026",
}
BASELINE = "service"
FAMILIES = {
    "service": "как в сервисе",
    "diffusivity": "только K",
    "random_walk": "случайное блуждание скорости",
    "windage": "шире набор парусности",
    "windage+random_walk": "шире парусность + блуждание скорости",
}


class NotCached(ForcingError):
    pass


class CachedOnlyClient(BlockCachedClient):
    def _request(self, url: str, params: dict[str, str]) -> list[dict[str, Any]]:
        raise NotCached("запрос к Open-Meteo запрещён: только кэш")

    def _download_block(
        self,
        url: str,
        rest: dict[str, str],
        signature: str,
        block: dt.date,
        points: list[tuple[str, str]],
    ) -> None:
        raise NotCached(f"форсинга нет в кэше: блок {block.isoformat()}, узлов {len(points)}")


def cached_forcing(store: Path, block_days: int, epoch: dt.date) -> OpenMeteoForcing:
    client = CachedOnlyClient(
        BlockStore(store), Throttle(0.0, 0.0, 0.0), block_days=block_days, epoch=epoch
    )
    return OpenMeteoForcing(None, client=client)


@dataclass(frozen=True)
class Spread:
    name: str
    family: str
    windages: tuple[float, ...]
    stokes: tuple[bool, ...]
    diffusivity_m2s: float
    velocity_noise_ms: float = 0.0
    velocity_decorrelation_h: float = 0.0

    def parameters(self, service: DriftParameters) -> DriftParameters:
        return replace(
            service,
            windages=self.windages,
            stokes=self.stokes,
            diffusivity_m2s=self.diffusivity_m2s,
        )

    def describe(self) -> dict[str, Any]:
        return {
            "windages": list(self.windages),
            "stokes": list(self.stokes),
            "diffusivity_m2s": self.diffusivity_m2s,
            "velocity_noise_ms": self.velocity_noise_ms,
            "velocity_decorrelation_h": self.velocity_decorrelation_h,
        }

    def complexity(self, service: DriftParameters) -> int:
        return (
            int(self.windages != service.windages or self.stokes != service.stokes)
            + int(self.diffusivity_m2s != service.diffusivity_m2s)
            + 2 * int(self.velocity_noise_ms > 0)
        )

    def key(self, setup: Setup) -> str:
        service = setup.service
        text = json.dumps(
            {
                "version": VERSION,
                **self.describe(),
                "particles": service.particles,
                "step_s": service.step_s,
                "point_radius_m": service.point_radius_m,
                "seed": service.seed,
                "hours": setup.hours,
                "hindcast_hours": setup.hindcast_hours,
                "margin_km": setup.margin_km,
                "horizons": list(setup.horizons),
                "envelope_margin_m": products.ENVELOPE_MARGIN_M,
            },
            sort_keys=True,
        )
        return hashlib.sha256(text.encode()).hexdigest()[:16]


def candidate_grid(grid: dict[str, Any], service: DriftParameters) -> list[Spread]:
    base = Spread(BASELINE, "service", service.windages, service.stokes, service.diffusivity_m2s)
    wide = tuple(float(value) for value in grid["wide_windages"])
    walks = [
        (float(sigma), float(tau))
        for sigma in grid["velocity_noise_ms"]
        for tau in grid["velocity_decorrelation_h"]
    ]
    candidates = [base]
    candidates += [
        replace(base, name=f"K{float(value):g}", family="diffusivity", diffusivity_m2s=float(value))
        for value in grid["diffusivity_m2s"]
    ]
    candidates += [
        replace(
            base,
            name=f"rw{sigma:g}_{tau:g}h",
            family="random_walk",
            velocity_noise_ms=sigma,
            velocity_decorrelation_h=tau,
        )
        for sigma, tau in walks
    ]
    candidates.append(replace(base, name="wide", family="windage", windages=wide))
    candidates += [
        replace(
            base,
            name=f"wide+rw{sigma:g}_{tau:g}h",
            family="windage+random_walk",
            windages=wide,
            velocity_noise_ms=sigma,
            velocity_decorrelation_h=tau,
        )
        for sigma, tau in walks
    ]
    return candidates


def effective_diffusivity(spread: Spread) -> float:
    walk = spread.velocity_noise_ms**2 * spread.velocity_decorrelation_h * HOUR_S
    return round(spread.diffusivity_m2s + walk, 1)


def ou_variance(sigma_ms: float, tau_h: float, hours: float) -> float:
    tau = tau_h * HOUR_S
    ratio = hours * HOUR_S / tau
    return 2.0 * sigma_ms * sigma_ms * tau * tau * (ratio - 1.0 + math.exp(-ratio))


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
        memory = math.exp(-step_s / (decorrelation_h * HOUR_S))
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


def run_ensemble(
    field: VelocityField,
    land: LandLookup,
    points: np.ndarray,
    spread: Spread,
    service: DriftParameters,
    hours: int,
) -> Trajectories:
    parameters = spread.parameters(service)
    variants = parameters.variants
    variant = np.repeat(np.arange(len(variants)), parameters.particles)
    windage = np.array([value for value, _ in variants])[variant]
    stokes = np.array([1.0 if flag else 0.0 for _, flag in variants])[variant]
    return integrate(
        field,
        land,
        np.tile(points, (len(variants), 1)),
        windage,
        stokes,
        hours,
        1,
        parameters,
        np.random.default_rng(parameters.seed + 1),
        spread.velocity_noise_ms,
        spread.velocity_decorrelation_h,
    )


def required_core(
    points: np.ndarray,
    anchor: Sequence[float],
    target: Sequence[float],
    margin_m: float = products.ENVELOPE_MARGIN_M,
) -> float:
    if not len(points):
        xy = to_local(anchor, [target[0]], [target[1]])[0]
        return 0.0 if math.hypot(xy[0], xy[1]) <= margin_m else math.inf
    center = np.median(points, axis=0)
    xy = to_local(center, points[:, 0], points[:, 1])
    ordered = xy[np.argsort(np.hypot(xy[:, 0], xy[:, 1]), kind="stable")]
    goal = Point(*to_local(center, [target[0]], [target[1]])[0])

    def reaches(core: int) -> bool:
        return MultiPoint(ordered[:core]).convex_hull.distance(goal) <= margin_m

    if not reaches(len(ordered)):
        return math.inf
    low, high = 1, len(ordered)
    while low < high:
        middle = (low + high) // 2
        if reaches(middle):
            high = middle
        else:
            low = middle + 1
    return float(low)


def coverage_flags(core: np.ndarray, afloat: np.ndarray, share: float) -> np.ndarray:
    core = np.asarray(core, dtype=float)
    afloat = np.asarray(afloat, dtype=float)
    flags = (core <= np.ceil(share * afloat)).astype(float)
    flags[np.isnan(core)] = np.nan
    return flags


def window_record(window: Window, trajectories: Trajectories, horizons: Sequence[int]):
    path = np.asarray(products.median_path(trajectories.positions), dtype=float)
    cells: dict[str, Any] = {}
    for horizon in horizons:
        if horizon > window.horizon or horizon > trajectories.hours:
            continue
        observed = window.track[horizon]
        if not np.all(np.isfinite(observed)):
            continue
        alive = ~trajectories.beached_by(horizon)
        points = trajectories.positions[horizon][alive]
        core = required_core(points, path[horizon], observed)
        cells[str(horizon)] = {
            "core": None if math.isinf(core) else int(core),
            "afloat": int(alive.sum()),
            "separation_km": round(float(separation_km(path[horizon], observed)), 4),
            "spread_km": round(spread_km(points), 4),
            "median": [float(value) for value in path[horizon]],
        }
    return {
        "members": int(trajectories.positions.shape[1]),
        "beached": round(float(np.isfinite(trajectories.beached_at).mean()), 4),
        "horizons": cells,
    }


@dataclass(frozen=True)
class Job:
    window: Window
    path: Path
    store: Path
    block_days: int
    epoch: dt.date
    setup: Setup
    spreads: tuple[Spread, ...]


_SOURCES: dict[Path, OpenMeteoForcing] = {}


def read_cache(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"records": {}}
    return json.loads(gzip.decompress(path.read_bytes()))


def write_cache(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_bytes(gzip.compress(json.dumps(payload).encode(), 6))
    temporary.replace(path)


def evaluate_job(job: Job) -> tuple[str, str, int]:
    window, setup = job.window, job.setup
    saved = read_cache(job.path)
    missing = [spread for spread in job.spreads if spread.key(setup) not in saved["records"]]
    if not missing:
        return window.id, "ok", 0
    source = _SOURCES.get(job.store)
    if source is None:
        source = _SOURCES[job.store] = cached_forcing(job.store, job.block_days, job.epoch)
    domain, start, end = forcing_request(window, setup)
    try:
        forcing = source.load(domain, start, end)
    except NotCached:
        return window.id, "not_cached", 0
    except ForcingError:
        return window.id, "forcing_error", 0
    provenance = forcing.provenance
    if not (provenance["currents"]["available"] and provenance["waves"]["available"]):
        return window.id, "no_marine_forcing", 0
    service = setup.service
    lon, lat = (float(value) for value in window.start)
    points = seed_points(
        Point(lon, lat),
        service.particles,
        service.point_radius_m,
        np.random.default_rng(service.seed),
    )
    land = build_land_mask(domain, forcing, None, points, None)
    field = GridField(forcing, window.moment)
    for spread in missing:
        trajectories = run_ensemble(field, land, points, spread, service, setup.hours)
        saved["records"][spread.key(setup)] = window_record(window, trajectories, setup.horizons)
    saved["id"] = window.id
    write_cache(job.path, saved)
    return window.id, "ok", len(missing)


@dataclass(frozen=True)
class Entry:
    item: Queued
    set: str
    group: str

    @property
    def window(self) -> Window:
        return self.item.window


def scope(item: Queued) -> str | None:
    window = item.window
    if window.source == "nautilos" and item.split in ("fit", "test"):
        return item.split
    if window.source == "med" and window.drogue == "off" and item.split in ("fit", "test"):
        return item.split
    if window.source == "blacksea" and window.period == "free":
        return "blacksea"
    return None


def block_labels(moments: Sequence[int], block_h: float) -> list[str]:
    if not len(moments):
        return []
    first = min(moments)
    return [f"block{int((moment - first) // (block_h * HOUR_S))}" for moment in moments]


def entries_for(queue: Sequence[Queued], block_h: float) -> list[Entry]:
    chosen = [(item, scope(item)) for item in queue]
    chosen = [(item, name) for item, name in chosen if name is not None]
    blacksea = [item.window.t0 for item, name in chosen if name == "blacksea"]
    blocks = dict(zip(blacksea, block_labels(blacksea, block_h), strict=True))
    entries = []
    for item, name in chosen:
        window = item.window
        group = (
            blocks[window.t0]
            if name == "blacksea"
            else bootstrap_group(window.source, window.drifter)
        )
        entries.append(Entry(item, name, group))
    return entries


def cache_path(work: Path, window_id: str) -> Path:
    return work / f"{window_id.replace(':', '__')}.json.gz"


def simulate(
    entries: Sequence[Entry],
    spreads: Sequence[Spread],
    setup: Setup,
    config: dict[str, Any],
    say: Callable[[str], None],
) -> dict[str, str]:
    settings = config["spread"]
    work = resolve(settings["work"])
    store = resolve(config["paths"]["work"]) / "openmeteo.sqlite"
    openmeteo = config["openmeteo"]
    jobs = [
        Job(
            entry.window,
            cache_path(work, entry.window.id),
            store,
            int(openmeteo["block_days"]),
            dt.date.fromisoformat(openmeteo["block_epoch"]),
            setup,
            tuple(spreads),
        )
        for entry in entries
    ]
    status: dict[str, str] = {}
    fresh = 0
    context = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(int(settings["jobs"]), mp_context=context) as pool:
        for index, (window_id, outcome, count) in enumerate(
            pool.map(evaluate_job, jobs, chunksize=4), start=1
        ):
            status[window_id] = outcome
            fresh += count
            if index % 50 == 0 or index == len(jobs):
                say(f"  {index}/{len(jobs)} окон · новых прогонов {fresh}")
    return status


def candidate_frame(
    entries: Sequence[Entry],
    spread: Spread,
    setup: Setup,
    work: Path,
    center: Spread | None = None,
) -> pd.DataFrame:
    key = spread.key(setup)
    rows = []
    for entry in entries:
        records = read_cache(cache_path(work, entry.window.id))["records"]
        record = records[key]
        base = records[center.key(setup)] if center else record
        row: dict[str, Any] = {
            "id": entry.window.id,
            "set": entry.set,
            "group": entry.group,
            "item": entry.window.drifter,
            "source": entry.window.source,
            "t0": entry.window.t0,
            "beached": float(base["beached"]),
        }
        for horizon in setup.horizons:
            cell = record["horizons"].get(str(horizon))
            if cell is None:
                row[f"core{horizon}"] = np.nan
                row[f"afloat{horizon}"] = np.nan
                row[f"sep{horizon}"] = np.nan
                row[f"spread{horizon}"] = np.nan
                continue
            reference = base["horizons"][str(horizon)]
            core = math.inf if cell["core"] is None else float(cell["core"])
            if center and cell["afloat"] == 0:
                core = required_core(
                    np.empty((0, 2)), reference["median"], entry.window.track[horizon]
                )
            row[f"core{horizon}"] = core
            row[f"afloat{horizon}"] = float(cell["afloat"])
            row[f"sep{horizon}"] = float(reference["separation_km"])
            row[f"spread{horizon}"] = float(cell["spread_km"])
        rows.append(row)
    return pd.DataFrame(rows)


@dataclass(frozen=True)
class Bootstrap:
    repeats: int
    confidence: float
    seed: int
    min_groups: int

    def unit(self, frame: pd.DataFrame) -> str | None:
        for column in ("group", "item"):
            if frame[column].nunique() >= self.min_groups:
                return column
        return None

    def samples(self, frame: pd.DataFrame) -> tuple[str | None, list[np.ndarray] | None]:
        unit = self.unit(frame)
        if unit is None:
            return None, None
        rng = np.random.default_rng(self.seed)
        return unit, cluster_resamples(frame[unit].to_numpy(), self.repeats, rng)


def leave_one_out(frame: pd.DataFrame, values: np.ndarray) -> list[float] | None:
    groups = frame["group"].to_numpy()
    labels = np.unique(groups)
    if labels.size < 2:
        return None
    means = [finite_mean(values[groups != label]) for label in labels]
    means = [value for value in means if np.isfinite(value)]
    return [float(min(means)), float(max(means))] if means else None


def by_group(frame: pd.DataFrame, values: np.ndarray) -> dict[str, float]:
    groups = frame["group"].to_numpy()
    result = {}
    for label in np.unique(groups):
        mean = finite_mean(values[groups == label])
        if np.isfinite(mean):
            result[str(label)] = mean
    return result


def summarize_set(
    frame: pd.DataFrame,
    horizons: Sequence[int],
    shares: Sequence[float],
    curve: Sequence[float],
    bootstrap: Bootstrap,
) -> dict[str, Any]:
    unit, samples = bootstrap.samples(frame)
    result: dict[str, Any] = {
        "windows": len(frame),
        "items": int(frame["item"].nunique()),
        "groups": int(frame["group"].nunique()),
        "bootstrap_unit": unit,
        "beached_share": float(frame["beached"].mean()) if len(frame) else None,
        "horizons": {},
    }
    errors = []
    for horizon in horizons:
        core = frame[f"core{horizon}"].to_numpy(dtype=float)
        afloat = frame[f"afloat{horizon}"].to_numpy(dtype=float)
        valid = ~np.isnan(core)
        separation = frame[f"sep{horizon}"].to_numpy(dtype=float)
        spread = frame[f"spread{horizon}"].to_numpy(dtype=float)
        if not valid.any():
            result["horizons"][str(horizon)] = {"windows": 0}
            continue
        cell: dict[str, Any] = {
            "windows": int(valid.sum()),
            "items": int(frame.loc[valid, "item"].nunique()),
            "groups": int(frame.loc[valid, "group"].nunique()),
            "coverage": {},
        }
        part_samples = samples if unit and frame.loc[valid, unit].nunique() >= 2 else None
        for share in shares:
            flags = coverage_flags(core, afloat, share)
            groups = by_group(frame, flags)
            value = finite_mean(flags)
            errors.append(abs(value - share))
            cell["coverage"][f"{share:g}"] = {
                "nominal": share,
                "value": value,
                "ci": interval(
                    part_samples, lambda index, f=flags: finite_mean(f[index]), bootstrap.confidence
                )
                if part_samples
                else None,
                "leave_one_group_out": leave_one_out(frame, flags),
                "by_group": groups,
                "group_weighted": float(np.mean(list(groups.values()))) if groups else None,
            }
        median_separation = float(np.nanmedian(separation[valid]))
        median_spread = float(np.nanmedian(spread[valid]))
        cell["separation_km"] = {
            "median": median_separation,
            "ci": interval(
                part_samples,
                lambda index, d=separation: float(np.nanmedian(d[index])),
                bootstrap.confidence,
            )
            if part_samples
            else None,
        }
        cell["spread_km"] = median_spread
        cell["spread_to_error"] = (
            median_spread / median_separation if median_separation > 0 else None
        )
        cell["curve"] = {
            f"{share:g}": finite_mean(coverage_flags(core, afloat, share)) for share in curve
        }
        result["horizons"][str(horizon)] = cell
    result["calibration_error"] = float(np.mean(errors)) if errors else None
    return result


def selection_table(
    frames: dict[str, pd.DataFrame],
    spreads: Sequence[Spread],
    service: DriftParameters,
    horizons: Sequence[int],
    shares: Sequence[float],
) -> dict[str, dict[str, Any]]:
    table = {}
    for spread in spreads:
        frame = frames[spread.name]
        errors = []
        separation = {}
        for horizon in horizons:
            core = frame[f"core{horizon}"].to_numpy(dtype=float)
            if np.isnan(core).all():
                continue
            afloat = frame[f"afloat{horizon}"].to_numpy(dtype=float)
            errors += [
                abs(finite_mean(coverage_flags(core, afloat, share)) - share) for share in shares
            ]
            separation[horizon] = float(np.nanmedian(frame[f"sep{horizon}"]))
        table[spread.name] = {
            "error": float(np.mean(errors)) if errors else math.inf,
            "separation": separation,
            "complexity": spread.complexity(service),
            "family": spread.family,
        }
    return table


def eligible(
    table: dict[str, dict[str, Any]], name: str, tolerance: float, baseline: str = BASELINE
) -> bool:
    separation = table[name]["separation"]
    return all(
        separation.get(horizon, math.inf) <= value * (1.0 + tolerance)
        for horizon, value in table[baseline]["separation"].items()
    )


def select(
    table: dict[str, dict[str, Any]],
    tolerance: float,
    baseline: str = BASELINE,
    families: Sequence[str] | None = None,
) -> str | None:
    ranked = sorted(
        (
            name
            for name in table
            if eligible(table, name, tolerance, baseline)
            and (families is None or table[name]["family"] in families)
        ),
        key=lambda name: (round(table[name]["error"], 9), table[name]["complexity"], name),
    )
    return ranked[0] if ranked else None


def subset(frames: dict[str, pd.DataFrame], mask_of: Callable[[pd.DataFrame], np.ndarray]):
    return {name: frame[mask_of(frame)].reset_index(drop=True) for name, frame in frames.items()}


def census(entries: Sequence[Entry], status: dict[str, str]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name in SETS:
        chosen = [entry for entry in entries if entry.set == name]
        counts: dict[str, int] = {}
        for entry in chosen:
            key = f"{entry.window.source}:{status.get(entry.window.id, 'not_run')}"
            counts[key] = counts.get(key, 0) + 1
        result[name] = {
            "queued": len(chosen),
            "used": sum(1 for entry in chosen if status.get(entry.window.id) == "ok"),
            "skipped_not_cached": sum(
                1 for entry in chosen if status.get(entry.window.id) == "not_cached"
            ),
            "by_status": counts,
        }
    return result


def envelope_only(name: str) -> str:
    return f"{name}:envelopes"


def backend_change(chosen: Spread, service: DriftParameters) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    if chosen.windages != service.windages or chosen.stokes != service.stokes:
        fields["envelope_windages"] = {
            "now": None,
            "proposed": list(chosen.windages),
            "meaning": "парусность вариантов прогона для огибающих",
        }
    if chosen.diffusivity_m2s != service.diffusivity_m2s:
        fields["envelope_diffusivity_m2s"] = {
            "now": None,
            "proposed": chosen.diffusivity_m2s,
            "meaning": "K случайного блуждания положения в прогоне для огибающих, м²/с "
            f"(основной прогон остаётся с diffusivity_m2s = {service.diffusivity_m2s:g})",
        }
    if chosen.velocity_noise_ms > 0:
        fields["envelope_noise_ms"] = {
            "now": None,
            "proposed": chosen.velocity_noise_ms,
            "meaning": "σ случайного блуждания скорости (процесс Орнштейна — Уленбека) по каждой "
            "компоненте, м/с",
        }
        fields["envelope_decorrelation_h"] = {
            "now": None,
            "proposed": chosen.velocity_decorrelation_h,
            "meaning": "время декорреляции τ этого блуждания, ч",
        }
    overrides = []
    if "envelope_windages" in fields:
        overrides.append("windages=parameters.envelope_windages")
    if "envelope_diffusivity_m2s" in fields:
        overrides.append("diffusivity_m2s=parameters.envelope_diffusivity_m2s")
    spread_parameters = (
        f"replace(parameters, {', '.join(overrides)})" if overrides else "parameters"
    )
    noise = (
        ", parameters.envelope_noise_ms, parameters.envelope_decorrelation_h"
        if chosen.velocity_noise_ms > 0
        else ""
    )
    change: dict[str, Any] = {
        "mode": "огибающие считаются по отдельному прогону с разбросом; медианный путь, выброс "
        "на берег, источники и обратный прогон остаются на текущем ансамбле без изменений",
        "model.py": {"DriftParameters": fields},
        "service.py": [
            f"после forward: spread = integrate(field, land, start, windage, stokes, hours, 1, "
            f"{spread_parameters}, np.random.default_rng(parameters.seed + 1){noise})",
            'в прогнозе зоны: "envelopes": products.envelopes(spread.subset(part), path) '
            "вместо products.envelopes(ahead, path)",
            "DriftService.method(): описать огибающие по прогону с разбросом и новые параметры; "
            "SCENARIO_REASON больше не говорит, что с дрифтерами не сверялось, — ссылка на "
            "reports/metrics/drift/spread.json",
        ],
        "reference": "littora_ml.drift_check.spread.integrate и run_ensemble",
    }
    if chosen.velocity_noise_ms > 0:
        change["model.py"]["integrate"] = [
            "новые аргументы noise_ms: float = 0.0, decorrelation_h: float = 0.0",
            "если noise_ms > 0: kicks = rng.spawn(1)[0]; kick = σ·N(0, 1) на частицу и "
            "компоненту в момент старта",
            "на каждом шаге RK2 kick[active] прибавляется к скорости на обеих стадиях (u1, v1 и "
            "u2, v2)",
            "после шага kick[active] = e^(−Δt/τ)·kick[active] + σ·√(1 − e^(−2Δt/τ))·N(0, 1)",
            "rng.spawn не расходует основной поток: при noise_ms = 0 integrate() даёт те же "
            "траектории бит в бит (проверено тестом)",
        ]
    return change


def _triple(summary: dict[str, Any], horizons: Sequence[int], pick: Callable[[dict], Any]) -> str:
    values = []
    for horizon in horizons:
        cell = summary["horizons"].get(str(horizon), {})
        value = pick(cell) if cell.get("windows") else None
        values.append("—" if value is None else value)
    return "/".join(values)


def _coverage_text(summary: dict[str, Any], horizons: Sequence[int], share: str) -> str:
    return _triple(summary, horizons, lambda cell: f"{cell['coverage'][share]['value'] * 100:.0f}")


def _separation_text(summary: dict[str, Any], horizons: Sequence[int]) -> str:
    return _triple(summary, horizons, lambda cell: f"{cell['separation_km']['median']:.1f}")


def _size_text(summary: dict[str, Any], name: str) -> str:
    groups = summary["groups"]
    unit = "блоков по 72 ч" if name == "blacksea" else "миссий/дрифтеров"
    return f"{summary['windows']} окон, {summary['items']} предм./дрифт., {groups} {unit}"


def variant_label(name: str, chosen: str | None) -> str:
    if name == BASELINE:
        return "сервис"
    if name == envelope_only(chosen or ""):
        return f"{chosen} только для огибающих (рекомендация)"
    if name.endswith(":envelopes"):
        return f"{name.split(':')[0]} только для огибающих"
    if name == chosen:
        return f"{chosen} во всём ансамбле"
    return name


def verdict_lines(
    evaluation: dict[str, Any],
    variants: Sequence[str],
    horizons: Sequence[int],
    chosen: str | None,
) -> list[str]:
    hours = "/".join(str(horizon) for horizon in horizons)
    lines = []
    for name in SETS:
        summaries = evaluation.get(name)
        if not summaries:
            lines.append(f"{SET_LABELS[name]}: нет окон с форсингом в кэше")
            continue
        base = summaries[BASELINE]
        lines.append(f"{SET_LABELS[name]} ({_size_text(base, name)}), {hours} ч:")
        for variant in variants:
            summary = summaries[variant]
            lines.append(
                f"  {variant_label(variant, chosen)}: в огибающей 90 % "
                f"{_coverage_text(summary, horizons, '0.9')} %, в 50 % "
                f"{_coverage_text(summary, horizons, '0.5')} %; медиана ошибки "
                f"{_separation_text(summary, horizons)} км; ошибка калибровки "
                f"{summary['calibration_error']:.3f}; частиц на берегу "
                f"{summary['beached_share']:.0%}"
            )
    return lines


def assemble(
    config: dict[str, Any],
    setup: Setup,
    entries: Sequence[Entry],
    status: dict[str, str],
    spreads: Sequence[Spread],
    candidates: list[dict[str, Any]],
    table: dict[str, dict[str, Any]],
    chosen: str | None,
    alternative: str | None,
    stability: dict[str, str | None],
    evaluation: dict[str, Any],
    tolerance: float,
) -> dict[str, Any]:
    settings = config["spread"]
    metrics = config["metrics"]
    service = setup.service
    horizons = list(setup.horizons)
    named = {spread.name: spread for spread in spreads}
    variants = list(evaluation["fit"])
    windows = census(entries, status)
    ranking = sorted(
        (name for name in table if eligible(table, name, tolerance)),
        key=lambda name: (table[name]["error"], table[name]["complexity"], name),
    )
    recommended = envelope_only(chosen) if chosen else None
    report: dict[str, Any] = {
        "name": "drift_spread",
        "created_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "config": {"path": config["_path"], "sha256": config["_sha256"], "section": "spread"},
        "question": "какой разброс ансамбля делает огибающие 50 % и 90 % сервиса честными: "
        "доля реальных положений внутри ≈ номиналу через 24, 48 и 72 ч без роста медианной "
        "ошибки",
        "method": {
            "ensemble": f"как в сервисе: {service.particles} частиц на вариант α × Стокс, старт — "
            f"круг {service.point_radius_m:g} м, RK2, шаг {service.step_s:g} с, seed "
            f"{service.seed}; форсинг — те же запросы OpenMeteoForcing, область ± "
            f"{setup.margin_km:g} км, маска суши по сетке Open-Meteo",
            "forcing": "только кэш Open-Meteo, собранный drift check (openmeteo.sqlite): клиент "
            "без сети, окно без кэша пропускается и считается в windows.*.skipped_not_cached",
            "diffusivity": "случайное блуждание положения σ = √(2KΔt), как integrate() сервиса",
            "random_walk": "u′ — процесс Орнштейна — Уленбека на частицу и компоненту: "
            "u′(0) ~ N(0, σ²), u′(t + Δt) = e^(−Δt/τ)·u′(t) + σ·√(1 − e^(−2Δt/τ))·ξ; "
            "прибавляется к скорости (течение + Стокс + α·ветер) на обеих стадиях RK2; "
            "дисперсия смещения по оси 2σ²τ²(t/τ − 1 + e^(−t/τ)): рост ∝ t при t ≪ τ и "
            "диффузия с K = σ²τ при t ≫ τ",
            "envelope": "контур сервиса: выпуклая оболочка доли q частиц на плаву, ближайших к "
            f"их медиане, + {products.ENVELOPE_MARGIN_M:g} м (products.envelopes)",
            "coverage": "для окна ищется наименьшее k, при котором оболочка k ближайших к медиане "
            "частиц (+ 150 м) накрывает реальную точку (оболочки вложены — двоичный поиск); окно "
            "покрыто огибающей q, если k ≤ ⌈q·n⌉, n — частиц на плаву; при q = 0,9 это ровно "
            "polygon.covers() контура сервиса",
            "calibration_error": "среднее |покрытие − номинал| по горизонтам "
            f"{'/'.join(str(h) for h in horizons)} ч и q = "
            f"{', '.join(f'{share:g}' for share in setup.shares)}",
            "separation": "расстояние от медианы всех частиц (median_path сервиса) до реальной "
            "точки",
            "selection": "только окна подбора (2022–2023): минимум calibration_error среди "
            "настроек, у которых медиана расстояния на каждом горизонте не больше, чем у "
            f"сервиса, × (1 + {tolerance:g}); при равенстве — меньше изменённых параметров. "
            "Окна проверки (2024) и Чёрное море посчитаны один раз и только для сервиса, "
            "выбранной настройки и лучшей настройки «только K»",
            "envelopes_only": "вариант «:envelopes» — огибающие из прогона с разбросом, медианный "
            "путь и выброс на берег из текущего ансамбля (как предлагается встроить в сервис): "
            "покрытие то же, что у настройки, медиана ошибки и доля частиц на берегу — как у "
            "сервиса; если на плаву не осталось частиц, контур строится вокруг медианы сервиса. "
            "Этот режим добавлен после проверки, когда стало видно, что разброс во всём ансамбле "
            "двигает медиану на Чёрном море; на покрытие и выбор настройки он не влияет",
            "intervals": f"{float(metrics['confidence']):.0%} бутстреп, {metrics['bootstrap']} "
            "повторов, по группам целиком: миссия NAUTILOS (дрифтер для SVP), если групп не "
            f"меньше {metrics['min_groups']}, иначе по предметам (bootstrap_unit = item: предметы "
            "одной миссии дрейфуют рядом, такой интервал уже настоящего); для Чёрного моря "
            f"группа — блок {settings['block_h']} ч по времени старта (один дрифтер, окна "
            "перекрываются); leave_one_group_out — размах покрытия без одной миссии или блока; "
            "меньше пяти групп и предметов — интервала нет",
        },
        "windows": windows,
        "grid": {key: value for key, value in settings["grid"].items()},
        "candidates": candidates,
        "selection": {
            "baseline": BASELINE,
            "chosen": chosen,
            "recommended": recommended,
            "chosen_parameters": named[chosen].describe() if chosen else None,
            "alternative_one_parameter": alternative,
            "alternative_parameters": named[alternative].describe() if alternative else None,
            "ranking": [
                {
                    "name": name,
                    "calibration_error": table[name]["error"],
                    "separation_km": {str(h): v for h, v in table[name]["separation"].items()},
                }
                for name in ranking[:12]
            ],
            "leave_one_mission_out": {
                label: {
                    "chosen": name,
                    "effective_diffusivity_m2s": effective_diffusivity(named[name])
                    if name
                    else None,
                }
                for label, name in stability.items()
            },
        },
        "variants": {name: variant_label(name, chosen) for name in variants},
        "evaluation": {name: evaluation.get(name) for name in SETS},
    }
    if chosen:
        parameters = named[chosen]
        report["recommendation"] = {
            "variant": recommended,
            "setting": chosen,
            "parameters": parameters.describe(),
            "effective_diffusivity_m2s": effective_diffusivity(parameters),
            "backend": backend_change(parameters, service),
            "single_ensemble": f"{chosen} во всём ансамбле тоже проходит критерий на подборе, "
            f"но двигает медианный путь и выброс на берег (см. evaluation.*.{chosen} и "
            "caveats), поэтому разброс предлагается только для огибающих",
            "alternative_one_parameter": {
                "variant": envelope_only(alternative),
                "backend": backend_change(named[alternative], service),
                "note": "одно число без изменения integrate(), но диффузия растёт как √t: на 24 ч "
                "огибающие уже широкие, на 72 ч — всё ещё узкие; см. evaluation",
            }
            if alternative and alternative != BASELINE
            else None,
        }
    report["caveats"] = spread_caveats(report, chosen, horizons)
    report["verdict"] = verdict_lines(report["evaluation"], variants, horizons, chosen)
    return report


def _cell(summary: dict[str, Any] | None, horizon: str) -> dict[str, Any]:
    cell = (summary or {}).get("horizons", {}).get(horizon, {})
    return cell if cell.get("windows") else {}


def spread_caveats(
    report: dict[str, Any], chosen: str | None, horizons: Sequence[int]
) -> list[str]:
    windows = report["windows"]
    evaluation = report["evaluation"]
    notes = []
    skipped = {name: windows[name]["skipped_not_cached"] for name in SETS}
    if any(skipped.values()):
        notes.append(
            "окна без форсинга в кэше пропущены (новых запросов к Open-Meteo нет): "
            + ", ".join(f"{name} {count}" for name, count in skipped.items() if count)
            + "; это SVP без дрога из Средиземного моря — подбор и проверка на мусоре держатся "
            "только на предметах NAUTILOS"
        )
    top = str(max(horizons))
    fit_base = (evaluation.get("fit") or {}).get(BASELINE)
    test_base = (evaluation.get("test") or {}).get(BASELINE)
    cell = _cell(fit_base, top)
    if cell:
        notes.append(
            f"мало независимых случаев: подбор — {fit_base['groups']} миссии NAUTILOS "
            f"({fit_base['items']} предм.), на {top} ч — {cell['windows']} окон из "
            f"{cell['groups']} миссий; проверка 2024 — {(test_base or {}).get('groups', 0)} "
            f"миссии ({(test_base or {}).get('items', 0)} предм.), для них интервала нет; "
            "интервалы по предметам уже настоящих, размах leave_one_group_out честнее"
        )
    if chosen:
        recommended = envelope_only(chosen)
        checked = _cell((evaluation.get("test") or {}).get(recommended), top)
        before, after = _cell(fit_base, top), _cell(test_base, top)
        if checked and before and after:
            outer = checked["coverage"]["0.9"]["value"]
            inner = checked["coverage"]["0.5"]["value"]
            verdict = (
                "шире нужного"
                if outer > 0.95 and inner > 0.55
                else "уже нужного"
                if outer < 0.85 and inner < 0.45
                else "близки к номиналу"
            )
            notes.append(
                f"на проверке 2024 огибающие {verdict}: в 90 % {outer:.0%}, в 50 % {inner:.0%} "
                f"на {top} ч; медиана ошибки сервиса там "
                f"{after['separation_km']['median']:.1f} км против "
                f"{before['separation_km']['median']:.1f} км на подборе; одна постоянная σ не "
                "подстраивается под погоду и течения, при малых ошибках контур будет с запасом, "
                "при больших — узким"
            )
        lines = []
        for name in SETS:
            base, single = (
                (evaluation.get(name) or {}).get(BASELINE),
                (evaluation.get(name) or {}).get(chosen),
            )
            if not base or not single:
                continue
            pairs = [
                f"{_cell(base, str(h))['separation_km']['median']:.1f} → "
                f"{_cell(single, str(h))['separation_km']['median']:.1f}"
                for h in horizons
                if _cell(base, str(h)) and _cell(single, str(h))
            ]
            lines.append(
                f"{name}: медиана ошибки {', '.join(pairs)} км, частиц на берегу "
                f"{base['beached_share']:.0%} → {single['beached_share']:.0%}"
            )
        if lines:
            notes.append(
                f"если включить {chosen} во всём ансамбле, меняются медианный путь и выброс на "
                "берег: "
                + "; ".join(lines)
                + ". Сдвиг медианы — не физика: частицы упираются в грубую маску суши у старта "
                "и застывают, медиана всех частиц тянется к старту (где предмет стоял у берега, "
                "это помогает, где уходил — мешает); вероятности выброса "
                "(beaching_segments, ALARM_FROM = 0,4) с дрифтерами не сверялись. Поэтому "
                "рекомендация — разброс только для огибающих"
            )
    notes += [
        "одной σ нельзя сразу попасть в 50 % и 90 % на 72 ч: ошибка тяжелее хвостом, чем облако "
        "частиц; критерий — среднее отклонение по обоим уровням",
        "Чёрное море — один SVP-B с дрогом 15 м, не предмет мусора; взят только свободный дрейф, "
        "волочение якоря и мель исключены; окна перекрываются (старт каждые 6 ч)",
        "форсинг — реанализ ERA5 и архивные SMOC/MFWAM; для свежих снимков сервис берёт прогноз "
        "ветра, там ошибка больше и покрытие будет ниже",
        "обратный прогон (hindcast) и зоны-полигоны (не точка) с данными не сверялись",
    ]
    return notes


def run_stage(config: dict[str, Any], say: Callable[[str], None] = print) -> dict[str, Any]:
    settings = config["spread"]
    metrics = config["metrics"]
    setup = build_setup(config)
    service = setup.service
    horizons = list(setup.horizons)
    shares = list(setup.shares)
    curve = [float(value) for value in settings["curve_shares"]]
    tolerance = float(settings["separation_tolerance"])
    work = resolve(settings["work"])
    bootstrap = Bootstrap(
        int(metrics["bootstrap"]),
        float(metrics["confidence"]),
        int(config["seed"]),
        int(metrics["min_groups"]),
    )
    queue, _ = build_queue(config)
    entries = entries_for(queue, float(settings["block_h"]))
    spreads = candidate_grid(settings["grid"], service)
    named = {spread.name: spread for spread in spreads}
    fit_entries = [entry for entry in entries if entry.set == "fit"]
    say(f"подбор: {len(fit_entries)} окон × {len(spreads)} настроек разброса, только кэш")
    status = simulate(fit_entries, spreads, setup, config, say)
    fit_ok = [entry for entry in fit_entries if status[entry.window.id] == "ok"]
    fit_frames = {spread.name: candidate_frame(fit_ok, spread, setup, work) for spread in spreads}
    table = selection_table(fit_frames, spreads, service, horizons, shares)
    chosen = select(table, tolerance)
    alternative = select(table, tolerance, families=("service", "diffusivity"))
    stability = {}
    for label in sorted(fit_frames[BASELINE]["group"].unique()):
        reduced = subset(fit_frames, lambda frame, g=label: frame["group"].to_numpy() != g)
        stability[label] = select(
            selection_table(reduced, spreads, service, horizons, shares), tolerance
        )
    finalists = list(dict.fromkeys(name for name in (BASELINE, chosen, alternative) if name))
    check_entries = [entry for entry in entries if entry.set != "fit"]
    say(f"проверка: {len(check_entries)} окон × {len(finalists)} настроек ({', '.join(finalists)})")
    status.update(simulate(check_entries, [named[name] for name in finalists], setup, config, say))
    check_ok = [entry for entry in check_entries if status[entry.window.id] == "ok"]
    candidates = [
        {
            "name": spread.name,
            "family": spread.family,
            "parameters": spread.describe(),
            "members": len(spread.parameters(service).variants) * service.particles,
            "eligible": eligible(table, spread.name, tolerance),
            "fit": summarize_set(fit_frames[spread.name], horizons, shares, curve, bootstrap),
        }
        for spread in spreads
    ]
    variants: list[tuple[str, Spread, Spread | None]] = [(BASELINE, named[BASELINE], None)]
    if chosen and chosen != BASELINE:
        variants += [
            (envelope_only(chosen), named[chosen], named[BASELINE]),
            (chosen, named[chosen], None),
        ]
    if alternative and alternative not in (BASELINE, chosen):
        variants.append((envelope_only(alternative), named[alternative], named[BASELINE]))
    evaluation: dict[str, Any] = {}
    for name in SETS:
        part = [entry for entry in fit_ok + check_ok if entry.set == name]
        evaluation[name] = (
            {
                label: summarize_set(
                    candidate_frame(part, spread, setup, work, center),
                    horizons,
                    shares,
                    curve,
                    bootstrap,
                )
                for label, spread, center in variants
            }
            if part
            else None
        )
    report = assemble(
        config,
        setup,
        entries,
        status,
        spreads,
        candidates,
        table,
        chosen,
        alternative,
        stability,
        evaluation,
        tolerance,
    )
    report["figure"] = spread_figure(report, horizons, resolve(settings["figure"]))
    path = write_json(resolve(settings["report"]), report)
    return {
        "report": str(path.relative_to(resolve("."))),
        "figure": report["figure"],
        "verdict": report["verdict"],
        "census": report["windows"],
    }
