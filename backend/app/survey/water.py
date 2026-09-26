from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import Any, Protocol

import numpy as np
from affine import Affine
from rasterio.errors import CRSError
from rasterio.warp import transform as transform_points
from rasterio.warp import transform_bounds
from scipy.ndimage import distance_transform_edt
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra

from app.drift.geo import METERS_PER_DEGREE
from app.survey.geo import Point, distance_km

SCL_LAND = (4, 5)
SCL_WATER = (6, 10)
SCL_BLOCK_M = 200.0
ROUTE_CELL_M = 250.0
MAX_ROUTE_CELLS = 250_000
MARGIN_KM = 5.0
MARGIN_SHARES = (0.5, 1.5)
MAX_SNAP_KM = 10.0
SAMPLES_PER_CELL = 3
UNKNOWN, WATER, LAND = 0, 1, 2
STEPS = ((0, 1), (1, 0), (1, 1), (1, -1))


class Sampler(Protocol):
    label: str

    def sample(self, lon: np.ndarray, lat: np.ndarray) -> np.ndarray: ...


@dataclass(frozen=True)
class Passage:
    path: list[list[float]]
    km: float
    over_land: bool | None
    detour: bool


def _rounded(point: Point) -> list[float]:
    return [round(float(point[0]), 5), round(float(point[1]), 5)]


def straight(a: Point, b: Point, over_land: bool | None = None) -> Passage:
    return Passage([_rounded(a), _rounded(b)], distance_km(a, b), over_land, False)


class SceneWater:
    label = "SCL снимка анализа: 4–5 — суша, 6 и 10 — вода"

    def __init__(self, scl: np.ndarray, affine: Affine, crs: str) -> None:
        factor = max(1, round(SCL_BLOCK_M / max(abs(affine.a), 1e-9)))
        rows, cols = scl.shape
        block_rows, block_cols = math.ceil(rows / factor), math.ceil(cols / factor)
        padded = np.zeros((block_rows * factor, block_cols * factor), dtype=np.uint8)
        padded[:rows, :cols] = scl
        blocks = padded.reshape(block_rows, factor, block_cols, factor)
        land = np.isin(blocks, SCL_LAND).sum(axis=(1, 3))
        water = np.isin(blocks, SCL_WATER).sum(axis=(1, 3))
        self.state = np.where(
            land + water == 0, UNKNOWN, np.where(land > water, LAND, WATER)
        ).astype(np.uint8)
        self.affine = affine * Affine.scale(factor, factor)
        self.crs = crs
        left, top = affine * (0, 0)
        right, bottom = affine * (cols, rows)
        self.bounds = transform_bounds(
            crs, "EPSG:4326", min(left, right), min(top, bottom), max(left, right), max(top, bottom)
        )

    def sample(self, lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
        result = np.full(lon.shape, UNKNOWN, dtype=np.uint8)
        west, south, east, north = self.bounds
        near = (lon >= west) & (lon <= east) & (lat >= south) & (lat <= north)
        if not near.any():
            return result
        xs, ys = transform_points("EPSG:4326", self.crs, lon[near].tolist(), lat[near].tolist())
        cols, rows = ~self.affine * (np.asarray(xs), np.asarray(ys))
        cols, rows = np.floor(cols).astype(int), np.floor(rows).astype(int)
        height, width = self.state.shape
        inside = (rows >= 0) & (rows < height) & (cols >= 0) & (cols < width)
        values = np.full(rows.shape, UNKNOWN, dtype=np.uint8)
        values[inside] = self.state[rows[inside], cols[inside]]
        result[near] = values
        return result


def scene_water(path: Path) -> SceneWater | None:
    if not path.exists():
        return None
    try:
        with np.load(path, allow_pickle=False) as data:
            scl = np.asarray(data["scl"], dtype=np.uint8)
            affine = Affine(*np.asarray(data["transform"], dtype=float).tolist()[:6])
            crs = str(data["crs"])
        if scl.ndim != 2 or not scl.size:
            return None
        return SceneWater(scl, affine, crs)
    except (KeyError, ValueError, OSError, TypeError, CRSError):
        return None


class MaskWater:
    label = "маска суши из расчёта дрейфа"

    def __init__(self, mask: dict[str, Any]) -> None:
        self.bounds = tuple(float(value) for value in mask["bounds"])
        rows, cols = int(mask["rows"]), int(mask["cols"])
        raw = np.frombuffer("".join(mask["data"]).encode("ascii"), dtype=np.uint8)
        self.land = (raw != ord(mask["water"])).reshape(rows, cols)

    def sample(self, lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
        west, south, east, north = self.bounds
        rows, cols = self.land.shape
        col = np.floor((lon - west) / (east - west) * cols).astype(int)
        row = np.floor((north - lat) / (north - south) * rows).astype(int)
        inside = (row >= 0) & (row < rows) & (col >= 0) & (col < cols)
        result = np.full(lon.shape, UNKNOWN, dtype=np.uint8)
        result[inside] = np.where(self.land[row[inside], col[inside]], LAND, WATER)
        return result


def mask_water(mask: dict[str, Any] | None) -> MaskWater | None:
    if not mask:
        return None
    try:
        return MaskWater(mask)
    except (KeyError, ValueError, TypeError, ZeroDivisionError):
        return None


def _pair(array: np.ndarray, dr: int, dc: int) -> tuple[np.ndarray, np.ndarray]:
    rows, cols = array.shape
    head = array[: rows - dr, max(0, -dc) : cols - max(0, dc)]
    tail = array[dr:, max(0, dc) : cols - max(0, -dc)]
    return head, tail


class _Grid:
    def __init__(self, a: Point, b: Point, km: float, share: float) -> None:
        margin_m = max(MARGIN_KM, km * share) * 1000.0
        middle = math.radians((a[1] + b[1]) / 2)
        cos = max(math.cos(middle), 0.1)
        lat_pad = margin_m / METERS_PER_DEGREE
        lon_pad = lat_pad / cos
        self.west = min(a[0], b[0]) - lon_pad
        self.south = min(a[1], b[1]) - lat_pad
        width_m = (max(a[0], b[0]) + lon_pad - self.west) * METERS_PER_DEGREE * cos
        height_m = (max(a[1], b[1]) + lat_pad - self.south) * METERS_PER_DEGREE
        self.cell_m = max(ROUTE_CELL_M, math.sqrt(width_m * height_m / MAX_ROUTE_CELLS))
        self.lat_step = self.cell_m / METERS_PER_DEGREE
        self.lon_step = self.lat_step / cos
        self.dy = self.cell_m
        self.dx = self.lon_step * METERS_PER_DEGREE * cos
        self.rows = max(1, math.ceil(height_m / self.cell_m))
        self.cols = max(1, math.ceil(width_m / self.dx))
        lats = self.south + (np.arange(self.rows) + 0.5) * self.lat_step
        lons = self.west + (np.arange(self.cols) + 0.5) * self.lon_step
        self.lons, self.lats = np.meshgrid(lons, lats)

    def cell(self, point: Point) -> tuple[int, int]:
        row = int(np.clip(math.floor((point[1] - self.south) / self.lat_step), 0, self.rows - 1))
        col = int(np.clip(math.floor((point[0] - self.west) / self.lon_step), 0, self.cols - 1))
        return row, col

    def center(self, row: int, col: int) -> list[float]:
        return [
            self.west + (col + 0.5) * self.lon_step,
            self.south + (row + 0.5) * self.lat_step,
        ]

    def open_around(self, passable: np.ndarray, land: np.ndarray, point: Point) -> None:
        row, col = self.cell(point)
        passable[row, col] = True
        if not land[row, col]:
            return
        reach = distance_transform_edt(land, sampling=(self.dy, self.dx))[row, col] + self.cell_m
        if reach > MAX_SNAP_KM * 1000.0:
            return
        rows = (np.arange(self.rows) - row)[:, None] * self.dy
        cols = (np.arange(self.cols) - col)[None, :] * self.dx
        passable |= np.hypot(rows, cols) <= reach

    def clear(self, passable: np.ndarray, a: Point, b: Point) -> bool:
        span = math.hypot((b[0] - a[0]) / self.lon_step, (b[1] - a[1]) / self.lat_step)
        count = max(2, math.ceil(span * SAMPLES_PER_CELL) + 1)
        t = np.linspace(0.0, 1.0, count)
        lon = a[0] + (b[0] - a[0]) * t
        lat = a[1] + (b[1] - a[1]) * t
        rows = np.clip(np.floor((lat - self.south) / self.lat_step).astype(int), 0, self.rows - 1)
        cols = np.clip(np.floor((lon - self.west) / self.lon_step).astype(int), 0, self.cols - 1)
        return bool(passable[rows, cols].all())

    def search(self, passable: np.ndarray, a: Point, b: Point) -> list[list[float]] | None:
        index = np.arange(self.rows * self.cols).reshape(self.rows, self.cols)
        heads, tails, weights = [], [], []
        for dr, dc in STEPS:
            ok_head, ok_tail = _pair(passable, dr, dc)
            valid = ok_head & ok_tail
            if dr and dc:
                valid &= _pair(passable, dr, 0)[1][:, max(0, -dc) : self.cols - max(0, dc)]
                valid &= _pair(passable, 0, dc)[1][: self.rows - dr, :]
            head, tail = _pair(index, dr, dc)
            heads.append(head[valid])
            tails.append(tail[valid])
            weights.append(np.full(int(valid.sum()), math.hypot(dr * self.dy, dc * self.dx)))
        size = self.rows * self.cols
        graph = coo_matrix(
            (np.concatenate(weights), (np.concatenate(heads), np.concatenate(tails))),
            shape=(size, size),
        ).tocsr()
        start = int(index[self.cell(a)])
        end = int(index[self.cell(b)])
        distances, previous = dijkstra(
            graph, directed=False, indices=start, return_predecessors=True
        )
        if not np.isfinite(distances[end]):
            return None
        chain = [end]
        while chain[-1] != start:
            chain.append(int(previous[chain[-1]]))
        chain.reverse()
        return [self.center(*divmod(node, self.cols)) for node in chain[1:-1]]

    def smooth(self, passable: np.ndarray, points: list[list[float]]) -> list[list[float]]:
        kept = [points[0]]
        i = 0
        while i < len(points) - 1:
            j = i + 1
            while j + 1 < len(points) and self.clear(passable, points[i], points[j + 1]):
                j += 1
            kept.append(points[j])
            i = j
        return kept


class Router:
    def __init__(self, sources: Sequence[Sampler]) -> None:
        self.sources = list(sources)
        self.cache: dict[tuple[float, ...], Passage] = {}

    @property
    def label(self) -> str:
        return "; вне неё — ".join(source.label for source in self.sources)

    def state(self, lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
        state = np.full(lon.shape, UNKNOWN, dtype=np.uint8)
        for source in self.sources:
            free = state == UNKNOWN
            if not free.any():
                break
            state[free] = source.sample(lon[free], lat[free])
        return state

    def leg(self, a: Point, b: Point) -> Passage:
        key = (round(a[0], 6), round(a[1], 6), round(b[0], 6), round(b[1], 6))
        if key not in self.cache:
            self.cache[key] = self._leg(a, b)
        return self.cache[key]

    def _leg(self, a: Point, b: Point) -> Passage:
        km = distance_km(a, b)
        if km <= 0:
            return straight(a, b)
        passage = straight(a, b)
        for share in MARGIN_SHARES:
            grid = _Grid(a, b, km, share)
            state = self.state(grid.lons, grid.lats)
            if not (state != UNKNOWN).any():
                return passage
            land = state == LAND
            passable = ~land
            for point in (a, b):
                grid.open_around(passable, land, point)
            if grid.clear(passable, a, b):
                return straight(a, b, False)
            cells = grid.search(passable, a, b)
            if cells is None:
                passage = straight(a, b, True)
                continue
            path = grid.smooth(passable, [list(a), *cells, list(b)])
            length = sum(distance_km(p, q) for p, q in pairwise(path))
            return Passage([_rounded(point) for point in path], length, False, True)
        return passage
