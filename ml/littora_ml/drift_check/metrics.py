from __future__ import annotations

from collections.abc import Callable, Sequence

import numpy as np

from app.drift.geo import EARTH_RADIUS_M, offset, to_local

EARTH_RADIUS_KM = EARTH_RADIUS_M / 1000.0
HOUR_S = 3600.0


def haversine_km(first: np.ndarray, second: np.ndarray) -> np.ndarray:
    first, second = np.asarray(first, dtype=float), np.asarray(second, dtype=float)
    lon1, lat1 = np.radians(first[..., 0]), np.radians(first[..., 1])
    lon2, lat2 = np.radians(second[..., 0]), np.radians(second[..., 1])
    term = (
        np.sin((lat2 - lat1) / 2) ** 2
        + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(term, 0.0, 1.0)))


def separation_km(predicted: np.ndarray, observed: np.ndarray) -> np.ndarray:
    return haversine_km(predicted, observed)


def liu_weisberg(
    predicted: np.ndarray, observed: np.ndarray, horizon: int, tolerance: float = 1.0
) -> float:
    predicted = np.asarray(predicted, dtype=float)[: horizon + 1]
    observed = np.asarray(observed, dtype=float)[: horizon + 1]
    if observed.shape[0] < horizon + 1 or not np.all(np.isfinite(observed)):
        return float("nan")
    distances = separation_km(predicted[1:], observed[1:])
    lengths = np.cumsum(haversine_km(observed[:-1], observed[1:]))
    total = float(lengths.sum())
    if total <= 0:
        return float("nan")
    return max(0.0, 1.0 - float(distances.sum()) / total / tolerance)


def persistence_path(
    before: np.ndarray, start: np.ndarray, hours: int, persistence_h: float
) -> np.ndarray:
    shift = to_local(start, [before[0]], [before[1]])[0]
    east, north = -shift / (persistence_h * HOUR_S)
    elapsed = np.arange(hours + 1) * HOUR_S
    lon, lat = offset(
        np.full(hours + 1, float(start[0])),
        np.full(hours + 1, float(start[1])),
        east * elapsed,
        north * elapsed,
    )
    return np.column_stack([lon, lat])


def stationary_path(start: np.ndarray, hours: int) -> np.ndarray:
    return np.tile(np.asarray(start, dtype=float), (hours + 1, 1))


def cluster_resamples(
    clusters: Sequence[str], repeats: int, rng: np.random.Generator
) -> list[np.ndarray]:
    labels, inverse = np.unique(np.asarray(clusters), return_inverse=True)
    members = [np.flatnonzero(inverse == index) for index in range(labels.size)]
    samples = []
    for _ in range(repeats):
        picks = rng.integers(labels.size, size=labels.size)
        samples.append(np.concatenate([members[pick] for pick in picks]))
    return samples


def interval(
    samples: Sequence[np.ndarray],
    statistic: Callable[[np.ndarray], float],
    confidence: float,
) -> list[float] | None:
    values = np.array([statistic(sample) for sample in samples], dtype=float)
    values = values[np.isfinite(values)]
    if values.size < max(10, len(samples) // 2):
        return None
    tail = (1.0 - confidence) / 2
    return [float(np.quantile(values, tail)), float(np.quantile(values, 1.0 - tail))]


def distribution(values: np.ndarray) -> dict[str, float | None]:
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if values.size == 0:
        return {"median": None, "q25": None, "q75": None, "p90": None, "mean": None}
    return {
        "median": float(np.median(values)),
        "q25": float(np.quantile(values, 0.25)),
        "q75": float(np.quantile(values, 0.75)),
        "p90": float(np.quantile(values, 0.9)),
        "mean": float(np.mean(values)),
    }


def finite_median(values: np.ndarray) -> float:
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    return float(np.median(values)) if values.size else float("nan")


def finite_mean(values: np.ndarray) -> float:
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    return float(np.mean(values)) if values.size else float("nan")


def skill_vs(model: np.ndarray, reference: np.ndarray) -> float:
    reference_median = finite_median(reference)
    if not reference_median > 0:
        return float("nan")
    return 1.0 - finite_median(model) / reference_median


def share_better(model: np.ndarray, reference: np.ndarray) -> float:
    valid = np.isfinite(model) & np.isfinite(reference)
    if not valid.any():
        return float("nan")
    return float(np.mean(model[valid] < reference[valid]))


def significance(ci: Sequence[float] | None, null: float) -> str:
    if not ci:
        return "интервала нет"
    if ci[0] > null:
        return "значимо лучше"
    if ci[1] < null:
        return "значимо хуже"
    return "не значимо"
