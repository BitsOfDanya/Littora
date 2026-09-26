from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import numpy as np

RULE_FILE = "stability.json"
VIEWS = tuple((turns, mirrored) for turns in range(4) for mirrored in (False, True))
MAX_CROPS = 24
MARGIN_SHARE = 8
BATCH = 8

Window = tuple[slice, slice]


def load_rule(folder: Path) -> dict[str, Any] | None:
    path = folder / RULE_FILE
    if not path.exists():
        return None
    try:
        rule = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return rule if "cutoff" in rule and rule.get("views") == len(VIEWS) else None


def view_votes(
    tiles: np.ndarray, run: Callable[[np.ndarray], np.ndarray], threshold: float
) -> np.ndarray:
    size = tiles.shape[-1]
    votes = np.zeros((len(tiles), size, size), dtype=np.float32)
    for turns, mirrored in VIEWS[1:]:
        view = np.rot90(tiles, turns, axes=(2, 3))
        if mirrored:
            view = view[..., ::-1]
        scores = run(np.ascontiguousarray(view, dtype=np.float32)).reshape(len(tiles), size, size)
        if mirrored:
            scores = scores[..., ::-1]
        votes += np.rot90(scores, -turns, axes=(1, 2)) >= threshold
    return votes


def _start(low: int, high: int, size: int, patch: int, margin: int) -> int | None:
    if high - low > patch - 2 * margin:
        return None
    center = (low + high) // 2
    return int(np.clip(center - patch // 2, 0, max(size - patch, 0)))


def _covers(start: int, span: slice, size: int, patch: int, margin: int) -> bool:
    low = start if start == 0 else start + margin
    high = start + patch if start + patch >= size else start + patch - margin
    return span.start >= low and span.stop <= high


def _inside(
    window: tuple[int, int], box: Window, shape: tuple[int, int], patch: int, margin: int
) -> bool:
    return _covers(window[0], box[0], shape[0], patch, margin) and _covers(
        window[1], box[1], shape[1], patch, margin
    )


def plan_windows(
    bounds: Sequence[Window | None],
    keep: Sequence[int],
    shape: tuple[int, int],
    patch: int,
    max_windows: int = MAX_CROPS,
) -> tuple[list[tuple[int, int]], dict[int, int]]:
    margin = patch // MARGIN_SHARE
    windows: list[tuple[int, int]] = []
    assigned: dict[int, int] = {}
    for index in keep:
        box = bounds[index - 1]
        if box is None:
            continue
        rows, cols = box
        found = next(
            (
                position
                for position, window in enumerate(windows)
                if _inside(window, box, shape, patch, margin)
            ),
            None,
        )
        if found is None and len(windows) < max_windows:
            top = _start(rows.start, rows.stop, shape[0], patch, margin)
            left = _start(cols.start, cols.stop, shape[1], patch, margin)
            if top is None or left is None:
                continue
            windows.append((top, left))
            found = len(windows) - 1
        if found is not None:
            assigned[index] = found
    return windows, assigned


def _tile(image: np.ndarray, top: int, left: int, patch: int) -> np.ndarray:
    tile = np.zeros((image.shape[0], patch, patch), dtype=np.float32)
    part = image[:, top : top + patch, left : left + patch]
    tile[:, : part.shape[1], : part.shape[2]] = part
    return tile


def _percent(value: float) -> str:
    return f"{value * 100:.0f} %"


def zone_stability(
    image: np.ndarray,
    labels: np.ndarray,
    keep: Sequence[int],
    bounds: Sequence[Window | None],
    run: Callable[[np.ndarray], np.ndarray],
    patch: int,
    threshold: float,
    rule: dict[str, Any],
) -> dict[int, dict[str, Any]]:
    windows, assigned = plan_windows(bounds, keep, labels.shape, patch)
    if not windows:
        return {}
    tiles = [_tile(image, top, left, patch) for top, left in windows]
    votes = np.concatenate(
        [
            view_votes(np.stack(tiles[start : start + BATCH]), run, threshold)
            for start in range(0, len(tiles), BATCH)
        ]
    )
    cutoff = float(rule["cutoff"])
    out: dict[int, dict[str, Any]] = {}
    for index, position in assigned.items():
        top, left = windows[position]
        inside = labels[top : top + patch, left : left + patch] == index
        others = votes[position][: inside.shape[0], : inside.shape[1]][inside]
        agreement = float((1 + others).mean() / len(VIEWS))
        entry: dict[str, Any] = {
            "stability": {"agreement": round(agreement, 3), "views": len(VIEWS)},
            "flags": [],
        }
        if rule.get("flag") and agreement < cutoff:
            entry["flags"].append(
                {
                    "kind": "unstable",
                    "label": "неустойчива к поворотам",
                    "evidence": [
                        f"при поворотах и отражениях окна зона выше порога в среднем в "
                        f"{_percent(agreement)} из {len(VIEWS)} видов; у 95 % обломков MARIDA "
                        f"val — не меньше {_percent(cutoff)}"
                    ],
                }
            )
        out[index] = entry
    return out
