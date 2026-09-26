from __future__ import annotations

import datetime as dt
import math
from collections.abc import Sequence
from typing import Any

import numpy as np
import shapely
from scipy.cluster.hierarchy import fcluster, linkage
from shapely.geometry import MultiPoint, Point, box, shape

from app.drift.forcing import Forcing
from app.drift.geo import from_local, rounded, to_local
from app.drift.land import LandMask
from app.drift.model import Trajectories
from app.drift.places import SOURCE_KINDS, Place

HORIZONS_H = (6, 12, 24, 48, 72)
ENVELOPE_SHARE = 0.9
ENVELOPE_MARGIN_M = 150.0
SEGMENT_LINK_M = 2_000.0
SEGMENT_POINTS = 8
NAME_RADIUS_M = 10_000.0
PLACE_SEARCH_DEG = 0.25
ALARM_FROM = 0.4
CAUTION_FROM = 0.1
Z90 = 1.6449
OPEN_SEA_ID = "open-sea"
FIELD_MAX_CELLS = 256


def wilson(successes: int, total: int) -> dict[str, float]:
    if total <= 0:
        return {"value": 0.0, "low": 0.0, "high": 0.0}
    share = successes / total
    z2 = Z90 * Z90
    denominator = 1 + z2 / total
    center = (share + z2 / (2 * total)) / denominator
    half = Z90 * math.sqrt(share * (1 - share) / total + z2 / (4 * total * total)) / denominator
    return {
        "value": round(share, 3),
        "low": round(max(0.0, center - half), 3),
        "high": round(min(1.0, center + half), 3),
    }


def severity(probability: float) -> str:
    if probability >= ALARM_FROM:
        return "alarm"
    if probability >= CAUTION_FROM:
        return "caution"
    return "info"


def median_path(positions: np.ndarray) -> list[list[float]]:
    return [rounded(point) for point in np.median(positions, axis=1)]


def _outline(points: np.ndarray, anchor: Sequence[float]) -> tuple[dict[str, Any], int]:
    if len(points):
        center = np.median(points, axis=0)
        xy = to_local(center, points[:, 0], points[:, 1])
        core = math.ceil(ENVELOPE_SHARE * len(points))
        nearest = np.argsort(np.hypot(xy[:, 0], xy[:, 1]), kind="stable")[:core]
        hull = MultiPoint(xy[nearest]).convex_hull
    else:
        center, core, hull = np.asarray(anchor, dtype=float), 0, Point(0.0, 0.0)
    outline = hull.buffer(ENVELOPE_MARGIN_M, quad_segs=6)
    ring = from_local(center, np.asarray(outline.exterior.coords))
    return {"type": "Polygon", "coordinates": [[rounded(point) for point in ring]]}, core


def _within(points: np.ndarray, bounds: Sequence[float]) -> np.ndarray:
    west, south, east, north = bounds
    lon, lat = points[:, 0], points[:, 1]
    return (lon >= west) & (lon <= east) & (lat >= south) & (lat <= north)


def _clip(polygon: dict[str, Any], bounds: Sequence[float]) -> tuple[dict[str, Any], bool]:
    outline = shape(polygon)
    frame = box(*bounds)
    if frame.covers(outline):
        return polygon, False
    part = outline.intersection(frame)
    if part.is_empty or part.geom_type != "Polygon":
        return polygon, False
    ring = [rounded(point) for point in part.exterior.coords]
    return {"type": "Polygon", "coordinates": [ring]}, True


def envelopes(
    trajectories: Trajectories,
    path: list[list[float]],
    horizons: Sequence[int] = HORIZONS_H,
    cloud: Trajectories | None = None,
    bounds: Sequence[float] | None = None,
) -> list[dict[str, Any]]:
    cloud = trajectories if cloud is None else cloud
    total = trajectories.positions.shape[1]
    items = []
    for horizon in horizons:
        if horizon > trajectories.hours:
            continue
        afloat = int((~trajectories.beached_by(horizon)).sum())
        points = cloud.positions[horizon][~cloud.beached_by(horizon)]
        polygon, _ = _outline(points, path[horizon])
        item = {
            "horizon_h": horizon,
            "median": path[horizon],
            "polygon": polygon,
            "probability": round(math.ceil(ENVELOPE_SHARE * afloat) / total, 3),
            "afloat": round(afloat / total, 3),
        }
        if bounds is not None:
            item["polygon"], item["clipped"] = _clip(polygon, bounds)
            outside = float((~_within(points, bounds)).mean()) if len(points) else 0.0
            item["outside_domain"] = round(outside, 3)
        items.append(item)
    return items


def beached_by_hour(trajectories: Trajectories) -> list[float]:
    total = trajectories.positions.shape[1]
    return [
        round(float(trajectories.beached_by(hour).sum()) / total, 3)
        for hour in range(trajectories.hours + 1)
    ]


def _nearby(places: Sequence[Place], west: float, south: float, east: float, north: float):
    area = box(
        west - PLACE_SEARCH_DEG,
        south - PLACE_SEARCH_DEG,
        east + PLACE_SEARCH_DEG,
        north + PLACE_SEARCH_DEG,
    )
    return [place for place in places if area.intersects(place.geometry)]


def _local_geometry(place: Place, origin: Sequence[float]):
    return shapely.transform(place.geometry, lambda xy: to_local(origin, xy[:, 0], xy[:, 1]))


def _coast_name(center: np.ndarray, places: Sequence[Place]) -> str:
    lon, lat = float(center[0]), float(center[1])
    best: tuple[float, Place] | None = None
    for place in _nearby(places, lon, lat, lon, lat):
        distance = _local_geometry(place, center).distance(Point(0.0, 0.0))
        if distance <= NAME_RADIUS_M and (best is None or distance < best[0]):
            best = (distance, place)
    if best is not None:
        return f"Берег у места «{best[1].name}»"
    latitude = f"{abs(lat):.3f}".replace(".", ",") + ("° с. ш." if lat >= 0 else "° ю. ш.")
    longitude = f"{abs(lon):.3f}".replace(".", ",") + ("° в. д." if lon >= 0 else "° з. д.")
    return f"Берег {latitude}, {longitude}"


def _segment_path(xy: np.ndarray, origin: np.ndarray) -> list[list[float]]:
    if len(xy) > 1:
        centered = xy - xy.mean(axis=0)
        _, _, axes = np.linalg.svd(centered, full_matrices=False)
        order = np.argsort(centered @ axes[0], kind="stable")
        groups = np.array_split(order, min(SEGMENT_POINTS, len(order)))
        xy = np.array([xy[group].mean(axis=0) for group in groups if group.size])
    path = [rounded(point) for point in from_local(origin, xy)]
    return path if len(path) > 1 else [path[0], path[0]]


def beaching_segments(trajectories: Trajectories, places: Sequence[Place]) -> list[dict[str, Any]]:
    total = trajectories.positions.shape[1]
    stranded = np.flatnonzero(np.isfinite(trajectories.beached_at))
    if stranded.size == 0:
        return []
    points = trajectories.positions[-1][stranded]
    hours = trajectories.beached_at[stranded]
    origin = np.median(points, axis=0)
    xy = to_local(origin, points[:, 0], points[:, 1])
    labels = (
        np.ones(1, dtype=int)
        if len(xy) == 1
        else fcluster(linkage(xy, method="single"), SEGMENT_LINK_M, criterion="distance")
    )
    groups = sorted(
        (labels == label for label in np.unique(labels)), key=lambda group: -int(group.sum())
    )
    segments = []
    for index, group in enumerate(groups, start=1):
        members = int(group.sum())
        probability = wilson(members, total)
        timing = hours[group]
        path = _segment_path(xy[group], origin)
        segments.append(
            {
                "id": f"coast-{index}",
                "name": _coast_name(np.median(points[group], axis=0), places),
                "severity": severity(probability["value"]),
                "probability": probability,
                "members": members,
                "window_h": [
                    math.floor(float(np.quantile(timing, 0.1))),
                    math.ceil(float(np.quantile(timing, 0.9))),
                ],
                "path": path,
                "label_at": path[len(path) // 2],
            }
        )
    return segments


def beaching_risk(segments: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not segments or segments[0]["severity"] == "info":
        return None
    return {"segment": segments[0]["name"], "probability": segments[0]["probability"]["value"]}


def source_estimates(
    trajectories: Trajectories, places: Sequence[Place]
) -> tuple[list[dict[str, Any]], list[str]]:
    if trajectories.hours == 0:
        return [], []
    total = trajectories.positions.shape[1]
    flat = trajectories.positions.reshape(-1, 2)
    west, south = flat.min(axis=0)
    east, north = flat.max(axis=0)
    candidates = [
        place for place in _nearby(places, west, south, east, north) if place.kind in SOURCE_KINDS
    ]
    if not candidates:
        return [], []
    first = np.full((len(candidates), total), np.inf)
    enclosing = []
    for index, place in enumerate(candidates):
        inside = shapely.intersects_xy(place.geometry, flat[:, 0], flat[:, 1])
        inside = inside.reshape(trajectories.hours + 1, total)
        if inside[0].any():
            enclosing.append(place.name)
            continue
        later = inside[1:]
        reached = later.any(axis=0)
        first[index, reached] = np.argmax(later, axis=0)[reached] + 1
    earliest = first.min(axis=0)
    owner = first.argmin(axis=0)
    items = []
    for index, place in enumerate(candidates):
        mine = np.isfinite(earliest) & (owner == index)
        members = int(mine.sum())
        if members:
            items.append(
                {
                    "id": place.id,
                    "name": place.name,
                    "kind": place.kind,
                    "position": list(place.anchor),
                    "probability": wilson(members, total),
                    "members": members,
                    "hours_back": round(float(np.median(earliest[mine]))),
                }
            )
    items.sort(key=lambda item: -item["members"])
    rest = total - sum(item["members"] for item in items)
    if items and rest:
        items.append(
            {
                "id": OPEN_SEA_ID,
                "name": "Не определено — открытое море",
                "kind": None,
                "position": None,
                "probability": wilson(rest, total),
                "members": rest,
                "hours_back": None,
            }
        )
    return items, enclosing


def variant_summaries(
    trajectories: Trajectories,
    variant: np.ndarray,
    variants: Sequence[tuple[float, bool]],
    horizons: Sequence[int] = HORIZONS_H,
) -> list[dict[str, Any]]:
    origin = np.median(trajectories.positions[0], axis=0)
    items = []
    for index, (windage, stokes) in enumerate(variants):
        members = variant == index
        displacement = {}
        for horizon in horizons:
            if horizon > trajectories.hours:
                continue
            median = np.median(trajectories.positions[horizon][members], axis=0)
            shift = to_local(origin, [median[0]], [median[1]])[0]
            displacement[str(horizon)] = round(float(np.hypot(*shift)) / 1000.0, 2)
        items.append(
            {
                "windage": windage,
                "stokes": stokes,
                "displacement_km": displacement,
                "beached": round(float(np.isfinite(trajectories.beached_at[members]).mean()), 3),
            }
        )
    return items


def current_field(forcing: Forcing, t0: dt.datetime, land: LandMask) -> dict[str, Any]:
    offset_h = (t0 - forcing.start).total_seconds() / 3600.0
    index = int(np.clip(round(offset_h), 0, forcing.steps - 1))
    total = forcing.current[index] + forcing.stokes[index]
    water = forcing.water
    speed = np.hypot(total[..., 0], total[..., 1])
    currents = forcing.provenance["currents"]["available"]
    waves = forcing.provenance["waves"]["available"]
    if currents:
        label = "Течение SMOC на t0 (с волновым дрейфом, без парусности)"
    elif waves:
        label = "Течений нет: стоксов дрейф волн MFWAM на t0"
    else:
        label = "Нет данных о течениях и волнах: поле нулевое"

    def grid(values: np.ndarray) -> list[list[float | None]]:
        rows = np.where(water, np.round(values, 3), np.nan).tolist()
        return [[None if math.isnan(value) else value for value in row] for row in rows]

    stride = max(1, math.ceil(max(land.land.shape) / FIELD_MAX_CELLS))
    sample = land.land[::stride, ::stride]
    rows, cols = sample.shape
    moment = forcing.start + dt.timedelta(hours=index)
    return {
        "label": label,
        "time": moment.isoformat().replace("+00:00", "Z"),
        "units": "м/с",
        "bounds": [
            round(float(forcing.lons[0]), 5),
            round(float(forcing.lats[0]), 5),
            round(float(forcing.lons[-1]), 5),
            round(float(forcing.lats[-1]), 5),
        ],
        "lons": [round(float(value), 5) for value in forcing.lons],
        "lats": [round(float(value), 5) for value in forcing.lats],
        "u": grid(total[..., 0]),
        "v": grid(total[..., 1]),
        "water": water.tolist(),
        "typical_speed_ms": round(float(np.median(speed[water])), 3) if water.any() else 0.0,
        "mask": {
            "bounds": [
                round(land.west, 5),
                round(land.south, 5),
                round(land.west + cols * stride * land.lon_step, 5),
                round(land.south + rows * stride * land.lat_step, 5),
            ],
            "rows": rows,
            "cols": cols,
            "row_order": "north_to_south",
            "water": "1",
            "data": ["".join("0" if cell else "1" for cell in row) for row in sample[::-1]],
        },
    }
