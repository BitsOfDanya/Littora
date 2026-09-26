from __future__ import annotations

from collections.abc import Callable

import numpy as np

PATCH = 256
STRIDE = 192


def _starts(size: int) -> list[int]:
    if size <= PATCH:
        return [0]
    starts = list(range(0, size - PATCH, STRIDE))
    starts.append(size - PATCH)
    return sorted(set(starts))


def sliding_scores(
    image: np.ndarray, scorer: Callable[[np.ndarray], np.ndarray], batch: int = 8
) -> np.ndarray:
    channels, height, width = image.shape
    padded_height, padded_width = max(height, PATCH), max(width, PATCH)
    canvas = np.zeros((channels, padded_height, padded_width), dtype=np.float32)
    canvas[:, :height, :width] = image
    weight = np.zeros((padded_height, padded_width), dtype=np.float32)
    total = np.zeros_like(weight)
    ramp = np.minimum(np.arange(PATCH) + 1, np.arange(PATCH)[::-1] + 1).astype(np.float32)
    window_weight = np.minimum(np.outer(ramp, ramp), 32.0)
    positions = [
        (row, column) for row in _starts(padded_height) for column in _starts(padded_width)
    ]
    for start in range(0, len(positions), batch):
        chunk = positions[start : start + batch]
        tiles = np.stack([canvas[:, r : r + PATCH, c : c + PATCH] for r, c in chunk])
        scores = scorer(tiles)
        for (r, c), score in zip(chunk, scores, strict=True):
            total[r : r + PATCH, c : c + PATCH] += score * window_weight
            weight[r : r + PATCH, c : c + PATCH] += window_weight
    return (total / np.maximum(weight, 1e-6))[:height, :width]
