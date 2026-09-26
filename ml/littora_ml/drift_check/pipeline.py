from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np
import pandas as pd

from littora_ml.common.paths import resolve
from littora_ml.drift_check import tracks as tracks_module
from littora_ml.drift_check.figures import draw_all
from littora_ml.drift_check.report import build_report, write_report
from littora_ml.drift_check.run import (
    build_queue,
    build_setup,
    plan,
    run_history,
    save_catalogue,
    simulate_queue,
)
from littora_ml.drift_check.spread import run_stage


def blacksea_track(config: dict[str, Any]) -> pd.DataFrame:
    source = config["sources"]["blacksea"]
    tracks = tracks_module.load_blacksea(
        resolve(source["folder"]), str(source["platform"]), source["kind"]
    )
    if not tracks:
        return pd.DataFrame(columns=["lon", "lat", "period"])
    track = tracks[0]
    period = np.full(track.size, "", dtype=object)
    for item in source["periods"]:
        start = tracks_module.unix_seconds(item["start"])
        end = tracks_module.unix_seconds(item["end"])
        period[(track.seconds >= start) & (track.seconds < end)] = item["name"]
    return pd.DataFrame({"lon": track.lon, "lat": track.lat, "period": period})


def check(
    config: dict[str, Any],
    stage: str,
    budget: float | None,
    say: Callable[[str], None] = print,
) -> dict[str, Any]:
    if stage == "spread":
        return run_stage(config, say)
    if stage in ("simulate", "all") and budget is None:
        raise ValueError("прогон тратит квоту Open-Meteo, общую с сервисом: нужен явный --budget")
    setup = build_setup(config)
    queue, census = build_queue(config)
    save_catalogue(config, queue, census)
    outcome: dict[str, Any] = {"census": census}
    if stage in ("simulate", "all"):
        outcome["run"] = simulate_queue(config, queue, setup, budget, say)
    remaining = plan(config, queue, setup)
    outcome["plan"] = remaining
    if stage not in ("report", "all"):
        return outcome
    report, frame = build_report(config, queue, census, setup, run_history(config), remaining)
    figures = draw_all(
        report,
        frame,
        blacksea_track(config),
        list(setup.horizons),
        resolve(config["paths"]["figures"]),
    )
    report["figures"] = figures
    outcome["report"] = write_report(config, report)
    outcome["verdict"] = report["verdict"]
    outcome["figures"] = figures
    return outcome
