from __future__ import annotations

import datetime as dt
import gzip
import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from app.drift.forcing import ForcingError, OpenMeteoForcing
from app.drift.model import DriftParameters
from littora_ml.common.paths import resolve
from littora_ml.drift_check import tracks as tracks_module
from littora_ml.drift_check.openmeteo import (
    BlockCachedClient,
    BlockStore,
    BudgetExceeded,
    RateLimited,
    Throttle,
    planned_calls,
)
from littora_ml.drift_check.simulate import Setup, forcing_request, simulate_window
from littora_ml.drift_check.windows import (
    Period,
    Window,
    WindowRules,
    assign_splits,
    extract_windows,
    sample_by_split,
    stratified_order,
)

PERIOD_ORDER = {"free": 0, "anchored": 1, "grounding": 2}


@dataclass(frozen=True)
class Queued:
    window: Window
    split: str
    priority: int


def build_setup(config: dict[str, Any]) -> Setup:
    service = DriftParameters()
    grid = config["grid"]
    return Setup(
        hours=int(config["service"]["hours"]),
        hindcast_hours=int(config["service"]["hindcast_hours"]),
        margin_km=float(config["service"]["domain_margin_km"]),
        horizons=tuple(int(value) for value in config["metrics"]["horizons_h"]),
        shares=tuple(float(value) for value in config["metrics"]["envelope_shares"]),
        service=service,
        grid=DriftParameters(
            windages=tuple(float(value) for value in grid["windages"]),
            stokes=tuple(bool(value) for value in grid["stokes"]),
            particles=service.particles,
            step_s=service.step_s,
            diffusivity_m2s=service.diffusivity_m2s,
            point_radius_m=service.point_radius_m,
            seed=service.seed,
        ),
    )


def setup_hash(setup: Setup) -> str:
    text = json.dumps(setup.signature(), sort_keys=True)
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _rules(config: dict[str, Any], source: dict[str, Any], **extra: Any) -> WindowRules:
    windows = config["windows"]
    return WindowRules(
        hours=int(config["service"]["hours"]),
        persistence_h=int(windows["persistence_h"]),
        start_every_h=int(source["start_every_h"]),
        max_gap_h=float(source["max_gap_h"]),
        anchor_tolerance_min=float(windows["anchor_tolerance_min"]),
        min_horizon_h=int(windows["min_horizon_h"]),
        **extra,
    )


def interleave(*parts: list[Queued]) -> list[Queued]:
    merged = []
    for index in range(max((len(part) for part in parts), default=0)):
        merged.extend(part[index] for part in parts if index < len(part))
    return merged


def build_queue(config: dict[str, Any]) -> tuple[list[Queued], dict[str, Any]]:
    sources = config["sources"]
    seed = int(config["seed"])
    earliest = tracks_module.unix_seconds(config["windows"]["forcing_from"])
    boundary = tracks_module.unix_seconds(f"{config['fit_until']}T00:00:00Z")
    census: dict[str, Any] = {}
    parts: dict[int, list[list[Queued]]] = {}

    def add(name: str, items: list[Queued]) -> None:
        parts.setdefault(int(sources[name]["priority"]), []).append(items)

    blacksea = sources["blacksea"]
    periods = tuple(
        Period(
            item["name"],
            tracks_module.unix_seconds(item["start"]),
            tracks_module.unix_seconds(item["end"]),
        )
        for item in blacksea["periods"]
    )
    tracks = tracks_module.load_blacksea(
        resolve(blacksea["folder"]), str(blacksea["platform"]), blacksea["kind"]
    )
    found = extract_windows(tracks, _rules(config, blacksea, periods=periods, earliest=earliest))
    found.sort(key=lambda window: (PERIOD_ORDER.get(window.period, 9), window.t0))
    census["blacksea"] = {"drifters": len(tracks), "windows": len(found)}
    add("blacksea", [Queued(window, "case", blacksea["priority"]) for window in found])

    nautilos = sources["nautilos"]
    tracks = tracks_module.load_nautilos(resolve(nautilos["file"]), nautilos["since"])
    found = extract_windows(tracks, _rules(config, nautilos, earliest=earliest))
    splits = assign_splits(found, boundary)
    census["nautilos"] = {"drifters": len({w.drifter for w in found}), "windows": len(found)}
    add(
        "nautilos",
        [Queued(window, splits[window.id], nautilos["priority"]) for window in found],
    )

    swot = sources["swot"]
    tracks = tracks_module.load_swot(
        resolve(swot["folder"]),
        list(swot["kinds"]),
        float(swot["anchor_gap_min"]) * 60,
        float(swot["max_gap_h"]) * 3600,
    )
    found = extract_windows(tracks, _rules(config, swot, earliest=earliest))
    splits = assign_splits(found, boundary)
    ordered = stratified_order(
        found, len(found), np.random.default_rng(seed), lambda window: (window.drifter,)
    )
    census["swot"] = {"drifters": len({w.drifter for w in found}), "windows": len(found)}
    swot_queue = [Queued(window, splits[window.id], swot["priority"]) for window in ordered]

    med = sources["med"]
    tracks = tracks_module.load_mediterranean(resolve(med["folder"]), med["since"], med["kind"])
    found = extract_windows(tracks, _rules(config, med, earliest=earliest, drogue_known=True))
    splits = assign_splits(found, boundary)
    chosen = sample_by_split(found, splits, int(med["max_windows"]), seed)
    census["med"] = {
        "drifters": len(tracks),
        "windows": len(found),
        "by_split": {
            side: sum(1 for window in found if splits[window.id] == side)
            for side in ("fit", "test", "bridge")
        },
        "sampled": len(chosen),
        "sampled_drifters": len({window.drifter for window in chosen}),
    }
    med_queue = [Queued(window, splits[window.id], med["priority"]) for window in chosen]
    if int(swot["priority"]) == int(med["priority"]):
        add("swot", interleave(swot_queue, med_queue))
    else:
        add("swot", swot_queue)
        add("med", med_queue)
    queue = [item for priority in sorted(parts) for part in parts[priority] for item in part]
    return queue, census


def result_path(work: Path, window_id: str) -> Path:
    return work / "runs" / f"{window_id.replace(':', '__')}.json.gz"


def read_result(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(gzip.decompress(path.read_bytes()))


def write_result(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_bytes(gzip.compress(json.dumps(payload).encode(), 6))
    temporary.replace(path)


def forcing_source(config: dict[str, Any], work: Path, budget: float):
    settings = config["openmeteo"]
    throttle = Throttle(
        per_minute=float(settings["calls_per_minute"]),
        per_hour=float(settings["calls_per_hour"]),
        budget=float(budget),
    )
    client = BlockCachedClient(
        BlockStore(work / "openmeteo.sqlite"),
        throttle,
        block_days=int(settings["block_days"]),
        epoch=dt.date.fromisoformat(settings["block_epoch"]),
        chunk_points=int(settings["chunk_points"]),
        concurrency=int(settings["concurrency"]),
    )
    return OpenMeteoForcing(None, client=client), throttle, client


def plan(config: dict[str, Any], queue: list[Queued], setup: Setup) -> dict[str, Any]:
    settings = config["openmeteo"]
    work = resolve(config["paths"]["work"])
    signature = setup_hash(setup)
    pending = []
    for item in queue:
        saved = read_result(result_path(work, item.window.id))
        if saved is None or saved.get("setup") != signature:
            pending.append(item)
    requests = [forcing_request(item.window, setup) for item in pending]
    calls = planned_calls(
        requests, int(settings["block_days"]), dt.date.fromisoformat(settings["block_epoch"])
    )
    return {"queued": len(queue), "pending": len(pending), "upper_bound_calls": calls}


def simulate_queue(
    config: dict[str, Any],
    queue: list[Queued],
    setup: Setup,
    budget: float,
    report: Callable[[str], None] = print,
) -> dict[str, Any]:
    work = resolve(config["paths"]["work"])
    signature = setup_hash(setup)
    source, throttle, client = forcing_source(config, work, budget)
    done = skipped = failed = 0
    stopped = None
    started = time.monotonic()
    for index, item in enumerate(queue, start=1):
        path = result_path(work, item.window.id)
        saved = read_result(path)
        if saved is not None and saved.get("setup") == signature:
            skipped += 1
            continue
        domain, start, end = forcing_request(item.window, setup)
        try:
            forcing = source.load(domain, start, end)
            payload = simulate_window(item.window, forcing, setup)
        except (BudgetExceeded, RateLimited) as error:
            stopped = str(error)
            break
        except ForcingError as error:
            payload = {"id": item.window.id, "status": "forcing_error", "message": str(error)}
            failed += 1
        payload["setup"] = signature
        write_result(path, payload)
        done += 1
        if done % 10 == 0:
            report(
                f"  {index}/{len(queue)} окон · новых {done} · вызовов Open-Meteo "
                f"{throttle.spent:.0f} · {time.monotonic() - started:.0f} с"
            )
    summary = {
        "finished_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "new": done,
        "cached": skipped,
        "forcing_errors": failed,
        "calls": round(throttle.spent),
        "requests": throttle.requests,
        "minute_limits": client.minute_limits,
        "stopped": stopped,
    }
    with (work / "runs.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(summary, ensure_ascii=False) + "\n")
    return summary


def run_history(config: dict[str, Any]) -> dict[str, Any]:
    path = resolve(config["paths"]["work"]) / "runs.jsonl"
    if not path.exists():
        return {"runs": 0, "calls": 0, "windows": 0}
    entries = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    return {
        "runs": len(entries),
        "calls": sum(entry["calls"] for entry in entries),
        "windows": sum(entry["new"] for entry in entries),
        "minute_limits": sum(entry.get("minute_limits", 0) for entry in entries),
        "last": entries[-1] if entries else None,
    }


def save_catalogue(config: dict[str, Any], queue: list[Queued], census: dict[str, Any]) -> Path:
    work = resolve(config["paths"]["work"])
    work.mkdir(parents=True, exist_ok=True)
    path = work / "windows.json.gz"
    payload = {
        "census": census,
        "windows": [
            {**item.window.to_dict(), "split": item.split, "priority": item.priority}
            for item in queue
        ],
    }
    path.write_bytes(gzip.compress(json.dumps(payload).encode(), 6))
    return path


def load_catalogue(config: dict[str, Any]) -> tuple[list[Queued], dict[str, Any]]:
    path = resolve(config["paths"]["work"]) / "windows.json.gz"
    payload = json.loads(gzip.decompress(path.read_bytes()))
    queue = [
        Queued(Window.from_dict(entry), entry["split"], int(entry["priority"]))
        for entry in payload["windows"]
    ]
    return queue, payload["census"]
