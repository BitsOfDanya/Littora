from __future__ import annotations

import datetime as dt
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from littora_ml.drift_check.tracks import DROGUE_OFF, DROGUE_ON, Track

HOUR_S = 3600
DROGUE_LABELS = {DROGUE_ON: "on", DROGUE_OFF: "off"}


@dataclass(frozen=True)
class Period:
    name: str
    start: int
    end: int


@dataclass(frozen=True)
class WindowRules:
    hours: int = 72
    persistence_h: int = 3
    start_every_h: int = 24
    max_gap_h: float = 3.0
    anchor_tolerance_min: float = 30.0
    min_horizon_h: int = 24
    earliest: int | None = None
    periods: tuple[Period, ...] = field(default_factory=tuple)
    drogue_known: bool = False


@dataclass(frozen=True)
class Window:
    id: str
    source: str
    drifter: str
    kind: str
    drogue: str
    period: str
    t0: int
    horizon: int
    before: np.ndarray
    track: np.ndarray

    @property
    def start(self) -> np.ndarray:
        return self.track[0]

    @property
    def moment(self) -> dt.datetime:
        return dt.datetime.fromtimestamp(self.t0, dt.UTC)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "drifter": self.drifter,
            "kind": self.kind,
            "drogue": self.drogue,
            "period": self.period,
            "t0": self.t0,
            "horizon": self.horizon,
            "before": [float(value) for value in self.before],
            "track": [
                [None if not np.isfinite(value) else round(float(value), 6) for value in point]
                for point in self.track
            ],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Window:
        track = np.array(
            [[np.nan if value is None else value for value in point] for point in payload["track"]],
            dtype=float,
        )
        return cls(
            id=payload["id"],
            source=payload["source"],
            drifter=payload["drifter"],
            kind=payload["kind"],
            drogue=payload["drogue"],
            period=payload["period"],
            t0=int(payload["t0"]),
            horizon=int(payload["horizon"]),
            before=np.asarray(payload["before"], dtype=float),
            track=track,
        )


def resample(track: Track, targets: np.ndarray, max_gap_s: float) -> tuple[np.ndarray, np.ndarray]:
    targets = np.asarray(targets, dtype=np.int64)
    count = track.size
    positions = np.full((targets.size, 2), np.nan)
    if count == 0:
        return positions, np.zeros(targets.size, dtype=bool)
    right = np.searchsorted(track.seconds, targets, side="left")
    clipped = np.minimum(right, count - 1)
    exact = (right < count) & (track.seconds[clipped] == targets)
    left = right - 1
    inside = (left >= 0) & (right < count)
    safe_left = np.clip(left, 0, count - 1)
    gap = np.where(inside, track.seconds[clipped] - track.seconds[safe_left], np.inf)
    between = inside & (gap <= max_gap_s) & ~exact
    weight = np.where(between, (targets - track.seconds[safe_left]) / np.where(between, gap, 1), 0)
    for column, values in enumerate((track.lon, track.lat)):
        interpolated = values[safe_left] + weight * (values[clipped] - values[safe_left])
        filled = np.where(between, interpolated, np.nan)
        positions[:, column] = np.where(exact, values[clipped], filled)
    return positions, exact | between


def nearest_fix(track: Track, moment: int) -> int:
    index = int(np.searchsorted(track.seconds, moment))
    candidates = [value for value in (index - 1, index) if 0 <= value < track.size]
    return min(candidates, key=lambda value: abs(int(track.seconds[value]) - moment))


def drogue_codes(track: Track, targets: np.ndarray) -> np.ndarray:
    index = np.clip(np.searchsorted(track.seconds, targets, side="right") - 1, 0, track.size - 1)
    return track.drogue[index]


def _period(rules: WindowRules, moment: int) -> Period | None:
    for period in rules.periods:
        if period.start <= moment < period.end:
            return period
    return None


def candidate_starts(track: Track, rules: WindowRules) -> np.ndarray:
    step = rules.start_every_h * HOUR_S
    first = int(track.seconds[0]) + rules.persistence_h * HOUR_S
    if rules.earliest is not None:
        first = max(first, rules.earliest)
    last = int(track.seconds[-1]) - rules.min_horizon_h * HOUR_S
    begin = -(-first // step) * step
    if last < begin:
        return np.array([], dtype=np.int64)
    return np.arange(begin, last + 1, step, dtype=np.int64)


def window_at(track: Track, moment: int, rules: WindowRules) -> Window | None:
    period = _period(rules, moment)
    if rules.periods and period is None:
        return None
    anchor = nearest_fix(track, moment)
    tolerance = rules.anchor_tolerance_min * 60
    if abs(int(track.seconds[anchor]) - moment) > tolerance or not track.anchor[anchor]:
        return None
    max_gap = rules.max_gap_h * HOUR_S
    offsets = np.arange(rules.hours + 1, dtype=np.int64) * HOUR_S
    targets = moment + offsets
    positions, valid = resample(track, targets, max_gap)
    before, before_ok = resample(track, np.array([moment - rules.persistence_h * HOUR_S]), max_gap)
    if not valid[0] or not before_ok[0]:
        return None
    if period is not None:
        valid &= targets < period.end
    drogue = "none"
    if rules.drogue_known:
        codes = drogue_codes(track, targets)
        drogue = DROGUE_LABELS.get(int(codes[0]), "unknown")
        valid &= codes == codes[0]
    broken = np.flatnonzero(~valid)
    horizon = int(broken[0] - 1) if broken.size else rules.hours
    if horizon < rules.min_horizon_h:
        return None
    positions[horizon + 1 :] = np.nan
    stamp = dt.datetime.fromtimestamp(moment, dt.UTC).strftime("%Y%m%d%H")
    return Window(
        id=f"{track.source}:{track.drifter}:{stamp}",
        source=track.source,
        drifter=track.drifter,
        kind=track.kind,
        drogue=drogue,
        period=period.name if period is not None else "",
        t0=moment,
        horizon=horizon,
        before=before[0],
        track=positions,
    )


def extract_windows(tracks: Sequence[Track], rules: WindowRules) -> list[Window]:
    windows = []
    for track in tracks:
        if track.size < 2:
            continue
        for moment in candidate_starts(track, rules):
            window = window_at(track, int(moment), rules)
            if window is not None:
                windows.append(window)
    return windows


def year_split(window: Window, first_t0: dict[str, int], boundary: int) -> str:
    drifter_side = "fit" if first_t0[window.drifter] < boundary else "test"
    window_side = "fit" if window.t0 < boundary else "test"
    return drifter_side if drifter_side == window_side else "bridge"


def assign_splits(windows: Sequence[Window], boundary: int) -> dict[str, str]:
    first: dict[str, int] = {}
    for window in windows:
        first[window.drifter] = min(first.get(window.drifter, window.t0), window.t0)
    return {window.id: year_split(window, first, boundary) for window in windows}


def stratified_order(
    windows: Sequence[Window],
    cap: int,
    rng: np.random.Generator,
    key: Callable[[Window], tuple[str, ...]],
) -> list[Window]:
    strata: dict[tuple[str, ...], list[Window]] = defaultdict(list)
    for window in windows:
        strata[key(window)].append(window)
    runs = []
    for name in sorted(strata):
        items = sorted(strata[name], key=lambda window: window.t0)
        offset = int(rng.integers(len(items)))
        runs.append(items[offset:] + items[:offset])
    order = rng.permutation(len(runs))
    chosen: list[Window] = []
    depth = 0
    while len(chosen) < cap and any(depth < len(run) for run in runs):
        for index in order:
            if depth < len(runs[index]) and len(chosen) < cap:
                chosen.append(runs[index][depth])
        depth += 1
    return chosen


def sample_by_split(
    windows: Sequence[Window],
    splits: dict[str, str],
    cap: int,
    seed: int,
) -> list[Window]:
    rng = np.random.default_rng(seed)
    pools = {
        side: [window for window in windows if splits[window.id] == side]
        for side in ("fit", "test")
    }
    test_cap = min(len(pools["test"]), cap // 2)
    fit_cap = min(len(pools["fit"]), cap - test_cap)
    test_cap = min(len(pools["test"]), cap - fit_cap)

    def stratum(window: Window) -> tuple[str, ...]:
        return (window.drifter, window.drogue)

    fit = stratified_order(pools["fit"], fit_cap, rng, stratum)
    test = stratified_order(pools["test"], test_cap, rng, stratum)
    merged = []
    for index in range(max(len(fit), len(test))):
        merged.extend(part[index] for part in (fit, test) if index < len(part))
    return merged
