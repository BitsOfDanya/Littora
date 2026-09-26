from __future__ import annotations

from collections.abc import Sequence
from itertools import pairwise

from app.survey.geo import Point, distance_km

IMPROVEMENT_KM = 1e-9


def _matrix(points: Sequence[Point]) -> list[list[float]]:
    return [[distance_km(a, b) for b in points] for a in points]


def tour_length(tour: Sequence[int], matrix: Sequence[Sequence[float]]) -> float:
    return sum(matrix[a][b] for a, b in pairwise(tour))


def nearest_neighbour(matrix: Sequence[Sequence[float]]) -> list[int]:
    left = set(range(1, len(matrix)))
    tour = [0]
    while left:
        current = tour[-1]
        following = min(left, key=lambda node: (matrix[current][node], node))
        tour.append(following)
        left.remove(following)
    return [*tour, 0]


def two_opt(tour: list[int], matrix: Sequence[Sequence[float]]) -> list[int]:
    best = list(tour)
    improved = True
    while improved:
        improved = False
        for i in range(1, len(best) - 2):
            for k in range(i + 1, len(best) - 1):
                a, b = best[i - 1], best[i]
                c, d = best[k], best[k + 1]
                delta = matrix[a][c] + matrix[b][d] - matrix[a][b] - matrix[c][d]
                if delta < -IMPROVEMENT_KM:
                    best[i : k + 1] = reversed(best[i : k + 1])
                    improved = True
    return best


def plan_tour(start: Point, stops: Sequence[Point]) -> list[int]:
    if not stops:
        return []
    matrix = _matrix([start, *stops])
    tour = two_opt(nearest_neighbour(matrix), matrix)
    return [node - 1 for node in tour[1:-1]]
