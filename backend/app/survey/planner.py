from __future__ import annotations

import datetime as dt
import math
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

import numpy as np
from shapely.geometry import shape

from app.analysis.statuses import STATUS_LABELS, ResultStatus
from app.case.solar import daylight_utc
from app.drift.geo import to_local
from app.drift.products import ENVELOPE_MARGIN_M
from app.survey.geo import along, bearing_deg, centroid, distance_km, equivalent_radius_km
from app.survey.ports import Port, nearest_port
from app.survey.route import plan_tour

MODEL_NAME = "littora-survey-2"
VALUE_KIND = "plan"
MAX_TARGETS = 12
CLUSTER_KM = 0.5
MAX_PORT_KM = 250.0
KNOT_KMH = 1.852
SPOT_KM = (1.0, 2.0)
PIXEL_KM2 = 1e-4
COVERAGE_PIXELS = 100
ACCESS_HOURS = 4.0
URGENCY_HOURS = 24.0
SEARCH_DAYS = 3
ROUND_MINUTES = 5
RISKY_SEVERITIES = ("alarm", "caution")
COMPONENTS = (
    "confidence",
    "coverage",
    "persistence",
    "drift_risk",
    "uncertainty",
    "accessibility",
)
WEIGHTS = {
    "confidence": 0.3,
    "coverage": 0.2,
    "persistence": 0.0,
    "drift_risk": 0.2,
    "uncertainty": 0.1,
    "accessibility": 0.2,
}
PLAN_REASON = (
    "расчётный план, а не проверенный маршрут: цели ранжированы по вероятности детектора, "
    "площади, срочности по сценарию дрейфа и удалённости от порта; расстояния по прямой "
    "без обхода берега и фарватеров; погода и допуски судна не учтены"
)
NO_DRIFT_NOTE = (
    "дрейф не рассчитан — срочность и окна по дрейфу не оценены; "
    "рассчитайте дрейф в «Прогнозе» и перестройте план"
)
PAST_NOTE = "окно выхода в прошлом"
RELAXED_NOTES = {
    "beaching": "до выноса на берег успеть ко всем целям нельзя — окно по светлому времени, "
    "искать по треку дрейфа",
    "scenario_end": "до конца сценария дрейфа успеть ко всем целям нельзя — окно по светлому "
    "времени, положение целей после конца сценария не рассчитано",
    "daylight": "маршрут не укладывается в светлое время одного дня — "
    "сократите число целей или повысьте скорость",
}
SCORING = {
    "confidence": "максимальная вероятность детектора в группе зон",
    "coverage": f"площадь группы: lg(1 + пикс.) / lg(1 + {COVERAGE_PIXELS}), не больше 1",
    "persistence": "не оценивается: один снимок; вес 0",
    "drift_risk": "max(вероятность выноса на берег, 1 − часы до ухода на 2 км / "
    f"{URGENCY_HOURS:g}); без дрейфа не оценивается",
    "uncertainty": "польза проверки: 1 − |2p − 1| по средней вероятности; максимальна при p = 0,5",
    "accessibility": f"1 − время перехода от порта / {ACCESS_HOURS:g} ч",
}


class SurveyStatus(StrEnum):
    ESTIMATE = "estimate"
    NO_ZONES = "no_zones"
    INSUFFICIENT_DATA = "insufficient_data"


SURVEY_STATUS_LABELS: dict[SurveyStatus, str] = {
    SurveyStatus.ESTIMATE: "план обследования — расчётный",
    SurveyStatus.NO_ZONES: "нет зон для обследования",
    SurveyStatus.INSUFFICIENT_DATA: STATUS_LABELS[ResultStatus.INSUFFICIENT_DATA],
}


@dataclass(frozen=True)
class SurveyOptions:
    speed_kn: float = 10.0
    uav_range_km: float = 15.0
    route_targets: int = 5
    dwell_min: int = 20
    lead_h: float = 3.0

    @property
    def speed_kmh(self) -> float:
        return self.speed_kn * KNOT_KMH

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DriftTrack:
    track: list[list[float]]
    leaves: dict[float, int | None]
    beaching: dict[str, Any] | None
    beaching_any: float
    radii: list[dict[str, float]]

    @property
    def hours(self) -> int:
        return len(self.track) - 1

    @property
    def deadline_h(self) -> float:
        if self.beaching is not None:
            return float(min(self.beaching["window_h"][0], self.hours))
        return float(self.hours)


@dataclass
class Group:
    zones: list[dict[str, Any]]
    points: list[list[float]]
    order: int
    position: list[float] = field(default_factory=list)
    drift: DriftTrack | None = None
    shore_km: float | None = None
    port: tuple[float, Port] | None = None
    components: dict[str, float | None] = field(default_factory=dict)
    score: float = 0.0

    @property
    def lead(self) -> dict[str, Any]:
        return self.zones[0]

    @property
    def pixels(self) -> int:
        total = 0
        for zone in self.zones:
            pixels = zone.get("pixels")
            if pixels is None:
                pixels = round(float(zone.get("area_km2") or 0.0) / PIXEL_KM2)
            total += int(pixels)
        return total

    @property
    def area_km2(self) -> float:
        area = sum(float(zone.get("area_km2") or 0.0) for zone in self.zones)
        return area if area > 0 else self.pixels * PIXEL_KM2

    @property
    def probability_max(self) -> float:
        return max(_probability(zone, "probability_max") for zone in self.zones)

    @property
    def probability_mean(self) -> float:
        weights = [max(float(zone.get("pixels") or 1), 1.0) for zone in self.zones]
        values = [_probability(zone, "probability_mean") for zone in self.zones]
        return sum(v * w for v, w in zip(values, weights, strict=True)) / sum(weights)

    def at(self, moment: dt.datetime, t0: dt.datetime) -> list[float]:
        if self.drift is None:
            return list(self.position)
        return along(self.drift.track, (moment - t0).total_seconds() / 3600.0)


class ShoreMask:
    def __init__(self, mask: dict[str, Any]) -> None:
        west, south, east, north = mask["bounds"]
        rows, cols = int(mask["rows"]), int(mask["cols"])
        raw = np.frombuffer("".join(mask["data"]).encode("ascii"), dtype=np.uint8)
        land = (raw != ord(mask["water"])).reshape(rows, cols)
        row, col = np.nonzero(land)
        self.bounds = (west, south, east, north)
        self.cells = np.column_stack(
            [
                west + (col + 0.5) * (east - west) / cols,
                north - (row + 0.5) * (north - south) / rows,
            ]
        )

    def distance_km(self, point: Sequence[float]) -> float | None:
        west, south, east, north = self.bounds
        if not (west <= point[0] <= east and south <= point[1] <= north) or not len(self.cells):
            return None
        xy = to_local(point, self.cells[:, 0], self.cells[:, 1])
        return float(np.hypot(xy[:, 0], xy[:, 1]).min()) / 1000.0


def _probability(zone: dict[str, Any], key: str) -> float:
    value = zone.get(key)
    if value is None:
        value = zone.get("probability_max", zone.get("probability", 0.0))
    return float(value or 0.0)


def _parse(stamp: str) -> dt.datetime:
    return dt.datetime.fromisoformat(stamp.replace("Z", "+00:00"))


def iso(moment: dt.datetime | None) -> str | None:
    if moment is None:
        return None
    return moment.astimezone(dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _num(value: float, digits: int = 1) -> str:
    return f"{value:.{digits}f}".replace(".", ",")


def _share(value: float) -> str:
    return f"{round(value * 100)} %"


def _hours(value: float) -> str:
    return f"{_num(value, 0 if value >= 10 or float(value).is_integer() else 1)} ч"


def _plural(count: int, one: str, few: str, many: str) -> str:
    tail, tens = count % 10, count % 100
    if tail == 1 and tens != 11:
        return one
    if 2 <= tail <= 4 and not 12 <= tens <= 14:
        return few
    return many


def _area(km2: float) -> str:
    if km2 < 0.01:
        square_m = round(km2 * 1e6, -1)
        return f"{square_m:,.0f}".replace(",", " ") + " м²"
    return f"{_num(km2, 3)} км²"


def _lower_first(text: str) -> str:
    return text[:1].lower() + text[1:]


def _zones_near(count: int) -> str:
    return f"{count} {_plural(count, 'зона', 'зоны', 'зон')}"


def _round2(value: float) -> float:
    return math.floor(value * 100 + 0.5) / 100


def _ceil_minutes(moment: dt.datetime, step: int = ROUND_MINUTES) -> dt.datetime:
    base = moment.replace(second=0, microsecond=0)
    if base < moment:
        base += dt.timedelta(minutes=1)
    return base + dt.timedelta(minutes=(-base.minute) % step)


def _floor_minutes(moment: dt.datetime, step: int = ROUND_MINUTES) -> dt.datetime:
    base = moment.replace(second=0, microsecond=0)
    return base - dt.timedelta(minutes=base.minute % step)


def _zone_point(zone: dict[str, Any]) -> list[float] | None:
    if zone.get("centroid"):
        return [float(zone["centroid"][0]), float(zone["centroid"][1])]
    if zone.get("geometry"):
        point = shape(zone["geometry"]).centroid
        return [point.x, point.y]
    return None


def _zones(result: dict[str, Any]) -> list[dict[str, Any]]:
    zones = []
    for index, zone in enumerate(z for z in result["detection"]["zones"] if z.get("geometry")):
        point = _zone_point(zone)
        if point is not None:
            zones.append(
                {
                    **zone,
                    "id": zone.get("id") or f"zone-{index + 1}",
                    "point": point,
                    "order": index,
                }
            )
    return zones


def group_zones(zones: list[dict[str, Any]], radius_km: float = CLUSTER_KM) -> list[Group]:
    ordered = sorted(
        zones, key=lambda zone: (-_probability(zone, "probability_max"), zone["order"])
    )
    groups: list[Group] = []
    for zone in ordered:
        home = next(
            (group for group in groups if distance_km(group.points[0], zone["point"]) <= radius_km),
            None,
        )
        if home is None:
            groups.append(Group(zones=[zone], points=[zone["point"]], order=zone["order"]))
        else:
            home.zones.append(zone)
            home.points.append(zone["point"])
    for group in groups:
        weights = [float(zone.get("pixels") or 1) for zone in group.zones]
        group.position = [round(value, 6) for value in centroid(group.points, weights)]
    return groups


def drift_track(forecast: dict[str, Any], base_km: float) -> DriftTrack | None:
    track = [list(map(float, point)) for point in forecast.get("median_path") or []]
    if len(track) < 2:
        return None
    origin = forecast.get("origin") or track[0]
    shifts = [distance_km(origin, point) for point in track]
    leaves = {
        limit: next((hour for hour, shift in enumerate(shifts) if shift > limit), None)
        for limit in SPOT_KM
    }
    risky = [
        segment
        for segment in forecast.get("beaching") or []
        if segment.get("severity") in RISKY_SEVERITIES
    ]
    beaching = None
    if risky:
        segment = risky[0]
        beaching = {
            "name": segment["name"],
            "severity": segment["severity"],
            "probability": segment["probability"]["value"],
            "window_h": list(segment["window_h"]),
        }
    radii = [{"hour": 0, "km": round(base_km, 3)}]
    for envelope in forecast.get("envelopes") or []:
        ring = envelope["polygon"]["coordinates"][0]
        radii.append(
            {"hour": int(envelope["horizon_h"]), "km": round(equivalent_radius_km(ring), 3)}
        )
    return DriftTrack(
        track=track,
        leaves=leaves,
        beaching=beaching,
        beaching_any=float((forecast.get("beaching_any") or {}).get("value", 0.0)),
        radii=radii,
    )


def _base_radius_km(group: Group) -> float:
    return math.sqrt(group.area_km2 / math.pi) + ENVELOPE_MARGIN_M / 1000.0


def _components(group: Group, options: SurveyOptions, has_ports: bool) -> dict[str, float | None]:
    probability = group.probability_mean
    drift = group.drift
    drift_risk = None
    if drift is not None:
        leave = drift.leaves[SPOT_KM[-1]]
        urgency = max(0.0, 1.0 - leave / URGENCY_HOURS) if leave is not None else 0.0
        drift_risk = max(drift.beaching_any, urgency)
    accessibility = None
    if group.port is not None:
        hours = group.port[0] / options.speed_kmh
        accessibility = max(0.0, 1.0 - hours / ACCESS_HOURS)
    elif has_ports:
        accessibility = 0.0
    values = {
        "confidence": group.probability_max,
        "coverage": min(1.0, math.log10(1 + group.pixels) / math.log10(1 + COVERAGE_PIXELS)),
        "persistence": None,
        "drift_risk": drift_risk,
        "uncertainty": 1.0 - abs(2.0 * probability - 1.0),
        "accessibility": accessibility,
    }
    return {key: None if value is None else _round2(value) for key, value in values.items()}


def score_of(components: dict[str, float | None]) -> float:
    total = 0.0
    for key in COMPONENTS:
        total += (components.get(key) or 0.0) * WEIGHTS[key]
    return _round2(total)


def _urgency(drift: DriftTrack | None) -> dict[str, Any]:
    if drift is None:
        return {
            "level": "unknown",
            "label": "не оценена: дрейф не рассчитан",
            "leaves_1km_h": None,
            "leaves_2km_h": None,
            "beaching": None,
            "beaching_any": None,
            "deadline_h": None,
        }
    first, second = (drift.leaves[limit] for limit in SPOT_KM)
    parts = []
    if first is None:
        parts.append(f"остаётся в пределах 1 км все {drift.hours} ч сценария")
    elif second is None:
        parts.append(f"уходит на 1 км за {_hours(first)}, в пределах 2 км до конца сценария")
    else:
        parts.append(f"уходит на 1 км за {_hours(first)}, на 2 км — за {_hours(second)}")
    beach = drift.beaching
    if beach is not None:
        start, end = beach["window_h"]
        span = f"+{start} ч" if start == end else f"+{start}…{end} ч"
        parts.append(f"вынос на берег {span}, p = {_num(beach['probability'], 2)}")
    soon = second is not None and second <= 6
    beaching_soon = beach is not None and beach["window_h"][0] <= URGENCY_HOURS
    if soon or beaching_soon:
        level = "high"
    elif (second is not None and second <= URGENCY_HOURS) or beach is not None:
        level = "medium"
    else:
        level = "low"
    return {
        "level": level,
        "label": "; ".join(parts),
        "leaves_1km_h": first,
        "leaves_2km_h": second,
        "beaching": beach,
        "beaching_any": round(drift.beaching_any, 3),
        "deadline_h": drift.deadline_h,
    }


def _why(group: Group, quality: dict[str, Any] | None, urgency: dict[str, Any]) -> list[str]:
    items = [
        f"вероятность детектора до {_num(group.probability_max, 2)}, "
        f"в среднем {_num(group.probability_mean, 2)}",
        f"площадь {_area(group.area_km2)} ({group.pixels} пикс. по 10 м)"
        + (
            f", {_zones_near(len(group.zones))} в радиусе {_num(CLUSTER_KM, 1)} км"
            if len(group.zones) > 1
            else ""
        ),
    ]
    if quality:
        items.append(
            f"SCL в районе анализа: вода {_share(quality['water'])}, "
            f"облака и тени {_share(quality['cloud'] + quality['shadow'])}"
        )
    if group.shore_km is not None:
        items.append(f"до берега {_num(group.shore_km)} км по маске суши из расчёта дрейфа")
    items.append("срочность: " + urgency["label"])
    return items


def _reason(group: Group, urgency: dict[str, Any]) -> str:
    parts = [
        f"вероятность {_num(group.probability_max, 2)}",
        _area(group.area_km2),
    ]
    if len(group.zones) > 1:
        parts.append(f"{_zones_near(len(group.zones))} рядом")
    if urgency["level"] == "unknown":
        parts.append("дрейф не рассчитан")
    elif urgency["beaching"] is not None:
        start = urgency["beaching"]["window_h"][0]
        parts.append(f"вынос на берег с +{start} ч")
    elif urgency["leaves_2km_h"] is not None:
        parts.append(f"уйдёт на 2 км за {_hours(urgency['leaves_2km_h'])}")
    else:
        parts.append("держится на месте")
    if group.port is not None:
        parts.append(f"{_num(group.port[0])} км от порта {group.port[1].name}")
    return " · ".join(parts)


def _checks(target: dict[str, Any] | None) -> list[str]:
    checks = [
        "подтвердит или снимет детекцию: мусор, пена, водоросли, след судна или блик",
        "образец материала: пластик или природная органика — метка для дообучения модели",
    ]
    if target:
        checks.append(
            f"учёт {target.get('unit', 'шт./км²')} по протоколу кейса: "
            f"{target['title'].lower()}, {target['size_class']}"
        )
    return checks


def _daylight(day: dt.date, point: Sequence[float]) -> tuple[dt.datetime, dt.datetime]:
    window = daylight_utc(day, point[1], point[0])
    if window is None:
        start = dt.datetime.combine(day, dt.time.min, tzinfo=dt.UTC)
        return start, start + dt.timedelta(days=1)
    return window


def _target_window(
    group: Group, t0: dt.datetime, ready: dt.datetime
) -> tuple[dict[str, Any] | None, str | None]:
    drift = group.drift
    deadline = t0 + dt.timedelta(hours=drift.deadline_h) if drift else None
    for offset in range(SEARCH_DAYS + 1):
        sunrise, sunset = _daylight(ready.date() + dt.timedelta(days=offset), group.position)
        start = max(ready, sunrise)
        end = min(sunset, deadline) if deadline else sunset
        if deadline is not None and start >= deadline:
            break
        if start < end:
            if drift is None:
                basis = "светлое время первых суток после готовности снимка; дрейф не рассчитан"
            elif drift.beaching is not None:
                basis = "светлое время до начала выноса на берег по сценарию дрейфа"
            else:
                basis = "светлое время, пока пятно в пределах сценария дрейфа"
            return {"from": iso(start), "to": iso(end), "basis": basis}, None
    if drift is not None and drift.beaching is not None and deadline is not None:
        if deadline <= ready:
            return None, (
                f"вынос на берег начнётся через {_hours(drift.deadline_h)} — раньше, чем "
                f"готовы снимок и анализ; проверять {_lower_first(drift.beaching['name'])}"
            )
        return None, "до выноса на берег светлого времени нет — проверять берег после выноса"
    if drift is not None and deadline is not None and deadline <= ready:
        return None, "сценарий дрейфа кончается раньше, чем готовы снимок и анализ"
    return None, f"светлого времени в ближайшие {SEARCH_DAYS + 1} сут нет"


def _uav(group: Group, options: SurveyOptions) -> dict[str, Any]:
    distances = [
        value
        for value in (group.port[0] if group.port else None, group.shore_km)
        if value is not None
    ]
    closest = min(distances) if distances else None
    if closest is not None and closest <= options.uav_range_km:
        source = "порта" if group.port and closest == group.port[0] else "берега"
        feasible: bool | None = True
        basis = f"{_num(closest)} км от {source} — в радиусе {_num(options.uav_range_km, 0)} км"
    elif group.shore_km is None:
        feasible = None
        basis = "расстояние до берега не оценено: нужна маска суши из расчёта дрейфа"
    else:
        feasible = False
        basis = f"дальше {_num(options.uav_range_km, 0)} км от берега и порта"
    return {"feasible": feasible, "range_km": options.uav_range_km, "basis": basis}


@dataclass
class RouteLeg:
    order: list[int]
    positions: list[list[float]]
    cumulative: list[float]
    arrivals: list[float]
    back_km: float


def _route_leg(
    port: Port,
    groups: list[Group],
    order: list[int] | None,
    moment: dt.datetime,
    t0: dt.datetime,
    options: SurveyOptions,
) -> RouteLeg:
    positions = [group.at(moment, t0) for group in groups]
    if order is None:
        order = plan_tour(port.position, positions)
    cumulative, arrivals = [], []
    travelled = 0.0
    previous: Sequence[float] = port.position
    for visit, index in enumerate(order):
        travelled += distance_km(previous, positions[index])
        previous = positions[index]
        cumulative.append(travelled)
        arrivals.append(travelled / options.speed_kmh + visit * options.dwell_min / 60.0)
    back = distance_km(previous, port.position) if order else 0.0
    return RouteLeg(order, positions, cumulative, arrivals, back)


def _exit_window(
    leg: RouteLeg,
    groups: list[Group],
    t0: dt.datetime,
    ready: dt.datetime,
    options: SurveyOptions,
) -> dict[str, Any] | None:
    if not leg.order:
        return None
    anchor = centroid([groups[index].position for index in leg.order], [1.0] * len(leg.order))
    first = leg.arrivals[0]
    finish = leg.arrivals[-1] + options.dwell_min / 60.0
    visits = [
        (groups[index].drift, arrival)
        for index, arrival in zip(leg.order, leg.arrivals, strict=True)
        if groups[index].drift is not None
    ]
    beaching = [
        (t0 + dt.timedelta(hours=drift.beaching["window_h"][0]), arrival)
        for drift, arrival in visits
        if drift.beaching is not None
    ]
    ends = [(t0 + dt.timedelta(hours=drift.hours), arrival) for drift, arrival in visits]

    def search(bounds: list[tuple[dt.datetime, float]], last: float):
        for offset in range(SEARCH_DAYS + 1):
            day = ready.date() + dt.timedelta(days=offset)
            sunrise, sunset = _daylight(day, anchor)
            low = max(ready, sunrise - dt.timedelta(hours=first))
            high = min(
                [
                    sunset - dt.timedelta(hours=last),
                    *(bound - dt.timedelta(hours=arrival) for bound, arrival in bounds),
                ]
            )
            if low <= high:
                return low, high, sunrise, sunset
        return None

    relaxed = None
    found = search(beaching + ends, finish) if ends else None
    if found is None:
        found = search([], finish)
        if found is not None and ends:
            relaxed = "beaching" if search(beaching, finish) is None else "scenario_end"
    if found is None:
        found = search([], first)
        relaxed = "daylight"
    if found is None:
        return None
    low, high, sunrise, sunset = found
    start, end = _ceil_minutes(low), _floor_minutes(high)
    if start > end:
        start = end = _ceil_minutes(low, 1)
    return {
        "from": iso(start),
        "to": iso(end),
        "departure": iso(start),
        "daylight": [iso(sunrise), iso(sunset)],
        "beaching_at": iso(min(moment for moment, _ in beaching)) if beaching else None,
        "scenario_end": iso(min(moment for moment, _ in ends)) if ends else None,
        "relaxed": relaxed,
    }


def _window_basis(window: dict[str, Any], options: SurveyOptions, has_drift: bool) -> str:
    parts = [f"выход не раньше t0 + {_num(options.lead_h, 0)} ч (снимок и анализ готовы)"]
    parts.append("прибытие к первой цели после восхода")
    if window["relaxed"] == "daylight":
        parts.append("маршрут целиком в светлое время не укладывается")
    else:
        parts.append("последняя проверка до заката")
    if has_drift and window["relaxed"] is None and window["beaching_at"]:
        parts.append("к каждой цели — до выноса на берег и до конца сценария дрейфа")
    elif has_drift and window["relaxed"] is None and window["scenario_end"]:
        parts.append("к каждой цели — до конца сценария дрейфа")
    return "; ".join(parts)


def _groups_with_context(
    zones: list[dict[str, Any]],
    forecasts: dict[str, dict[str, Any]],
    shore: ShoreMask | None,
    ports: list[Port],
) -> list[Group]:
    groups = group_zones(zones)
    for group in groups:
        forecast = next(
            (forecasts[zone["id"]] for zone in group.zones if zone["id"] in forecasts), None
        )
        if forecast is not None:
            group.drift = drift_track(forecast, _base_radius_km(group))
        if shore is not None:
            group.shore_km = shore.distance_km(group.position)
        found = nearest_port(ports, group.position)
        if found is not None and found[0] <= MAX_PORT_KM:
            group.port = found
    return groups


def _empty(
    status: SurveyStatus,
    reason: str,
    request: dict[str, Any],
    *,
    t0: str | None = None,
    ready_at: str | None = None,
    drift: dict[str, Any] | None = None,
    passes: Sequence[dict[str, Any]] = (),
) -> dict[str, Any]:
    return {
        "status": {"status": status.value, "label": SURVEY_STATUS_LABELS[status]},
        "reason": reason,
        "value_kind": VALUE_KIND,
        "request": request,
        "t0": t0,
        "ready_at": ready_at,
        "drift": drift,
        "zones": {"total": 0, "groups": 0, "planned": 0, "limit": MAX_TARGETS},
        "weights": dict(WEIGHTS),
        "scoring": dict(SCORING),
        "port": None,
        "targets": [],
        "route": None,
        "exit_window": None,
        "passes": list(passes),
        "messages": [],
    }


def drift_summary(drift: dict[str, Any] | None) -> dict[str, Any]:
    if drift is None:
        return {
            "used": False,
            "status": None,
            "computed_at": None,
            "hours": None,
            "note": NO_DRIFT_NOTE,
        }
    status = drift["status"]["status"]
    if status != "scenario":
        return {
            "used": False,
            "status": status,
            "computed_at": drift.get("computed_at"),
            "hours": None,
            "note": f"дрейф без сценария ({drift['status']['label']}) — план без срочности",
        }
    return {
        "used": True,
        "status": status,
        "computed_at": drift.get("computed_at"),
        "hours": drift["request"]["hours"],
        "note": "срочность и окна — по сценарию дрейфа, не проверенному на дрифтерах",
    }


def plan(
    result: dict[str, Any],
    drift: dict[str, Any] | None,
    ports: list[Port],
    options: SurveyOptions,
    passes: list[dict[str, Any]] | None = None,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    request = options.as_dict()
    now = now or dt.datetime.now(dt.UTC)
    scene = result.get("scene")
    summary = drift_summary(drift)
    if scene is None:
        return _empty(
            SurveyStatus.INSUFFICIENT_DATA,
            "у анализа нет снимка — нет момента t0 и зон для обследования",
            request,
            drift=summary,
            passes=passes or [],
        )
    t0 = _parse(scene["acquired_at"])
    ready = t0 + dt.timedelta(hours=options.lead_h)
    zones = _zones(result)
    if not zones:
        return _empty(
            SurveyStatus.NO_ZONES,
            "в анализе нет зон детекции — обследовать нечего",
            request,
            t0=scene["acquired_at"],
            ready_at=iso(ready),
            drift=summary,
            passes=passes or [],
        )
    messages: list[str] = []
    scenario = drift if summary["used"] else None
    forecasts = {item["candidate_id"]: item for item in (scenario or {}).get("forecasts", [])}
    mask = ((scenario or {}).get("current_field") or {}).get("mask")
    shore = ShoreMask(mask) if mask else None
    groups = _groups_with_context(zones, forecasts, shore, ports)
    for group in groups:
        group.components = _components(group, options, bool(ports))
        group.score = score_of(group.components)
    groups.sort(key=lambda group: (-group.score, -group.probability_max, group.order))
    selected = groups[:MAX_TARGETS]
    if len(groups) > MAX_TARGETS:
        messages.append(f"групп зон {len(groups)} — в плане {MAX_TARGETS} с наибольшим баллом")
    if summary["used"]:
        missing = sum(1 for group in selected if group.drift is None)
        if missing:
            messages.append(
                f"для {missing} целей дрейф не считался (лимит зон в расчёте дрейфа) — "
                "срочность у них не оценена"
            )
    else:
        messages.append(summary["note"])
    if not ports:
        messages.append("справочник портов не найден — маршрут и доступность не оцениваются")

    route_groups = list(selected[: options.route_targets])
    port_found = None
    if ports:
        anchor = centroid([group.position for group in route_groups], [1.0] * len(route_groups))
        port_found = nearest_port(ports, anchor)
        if port_found is not None and port_found[0] > MAX_PORT_KM:
            messages.append(
                f"ближайший порт в справочнике — {port_found[1].name}, "
                f"{_num(port_found[0], 0)} км: дальше {MAX_PORT_KM:g} км, маршрут не строится"
            )
            port_found = None
    port = port_found[1] if port_found else None
    if port is not None:
        route_groups = [
            group
            for group in route_groups
            if distance_km(port.position, group.position) <= MAX_PORT_KM
        ]

    window = None
    leg = None
    if port is not None and route_groups:
        leg = _route_leg(port, route_groups, None, ready, t0, options)
        window = _exit_window(leg, route_groups, t0, ready, options)
        departure = _parse(window["departure"]) if window else ready
        leg = _route_leg(port, route_groups, None, departure, t0, options)
        window = _exit_window(leg, route_groups, t0, ready, options)
        departure = _parse(window["departure"]) if window else ready
        leg = _route_leg(port, route_groups, leg.order, departure, t0, options)
    departure = _parse(window["departure"]) if window else None
    if window is not None:
        window["basis"] = _window_basis(window, options, summary["used"])
        relaxed_note = RELAXED_NOTES.get(window["relaxed"])
        if relaxed_note:
            messages.append(relaxed_note)
    elif port is not None and route_groups:
        messages.append(f"светлого окна в ближайшие {SEARCH_DAYS + 1} сут не найдено")

    visits: dict[int, tuple[int, float]] = {}
    if leg is not None:
        for visit, (index, arrival) in enumerate(zip(leg.order, leg.arrivals, strict=True)):
            visits[id(route_groups[index])] = (visit + 1, arrival)

    targets = []
    for rank, group in enumerate(selected, start=1):
        urgency = _urgency(group.drift)
        uav = _uav(group, options)
        target_window, window_note = _target_window(group, t0, ready)
        in_route = id(group) in visits
        if in_route:
            method = "vessel"
        elif uav["feasible"]:
            method = "uav"
        else:
            method = "tasking"
        eta = None
        shift = None
        visit = None
        if in_route:
            visit, arrival = visits[id(group)]
            if departure is not None:
                eta = departure + dt.timedelta(hours=arrival)
                shift = distance_km(group.position, group.at(eta, t0))
        drift = group.drift
        spot_until = None
        if drift is not None and drift.leaves[SPOT_KM[-1]] is not None:
            spot_until = iso(t0 + dt.timedelta(hours=drift.leaves[SPOT_KM[-1]]))
        radius = {"base_km": round(_base_radius_km(group), 3), "km_per_day": 0.0}
        drift_payload = None
        if drift is not None:
            last = drift.radii[-1]
            if last["hour"] > 0:
                radius["km_per_day"] = round(
                    max(0.0, last["km"] - drift.radii[0]["km"]) / (last["hour"] / 24.0), 3
                )
            end = drift.track[-1]
            net = distance_km(group.position, end)
            drift_payload = {
                "bearing_deg": round(bearing_deg(group.position, end), 1) if net > 0 else 0.0,
                "km_per_day": round(net / (drift.hours / 24.0), 3),
                "hours": drift.hours,
                "track": [[round(p[0], 5), round(p[1], 5)] for p in drift.track],
                "radii": drift.radii,
            }
        targets.append(
            {
                "id": f"SV-{rank:02d}",
                "rank": rank,
                "score": group.score,
                "zone_ids": [zone["id"] for zone in group.zones],
                "lead_zone": group.lead["id"],
                "position": group.position,
                "observed_at": scene["acquired_at"],
                "area_km2": round(group.area_km2, 4),
                "pixels": group.pixels,
                "probability_max": round(group.probability_max, 4),
                "probability_mean": round(group.probability_mean, 4),
                "components": group.components,
                "reason": _reason(group, urgency),
                "why": _why(group, result.get("quality"), urgency),
                "urgency": urgency,
                "checks": _checks(result.get("target")),
                "window": target_window,
                "window_note": window_note,
                "spot_until": spot_until,
                "nearest_port": {
                    "id": group.port[1].id,
                    "name": group.port[1].name,
                    "distance_km": round(group.port[0], 2),
                }
                if group.port
                else None,
                "shore_km": round(group.shore_km, 2) if group.shore_km is not None else None,
                "uav": uav,
                "method": method,
                "drift": drift_payload,
                "search_radius": radius,
                "visit": visit,
                "eta": iso(eta),
                "shift_at_eta_km": round(shift, 2) if shift is not None else None,
            }
        )

    route = None
    if port is not None and leg is not None and leg.order:
        ids = {id(group): target["id"] for group, target in zip(selected, targets, strict=True)}
        order_ids = [ids[id(route_groups[index])] for index in leg.order]
        path = (
            [list(port.position)]
            + [
                [round(leg.positions[index][0], 5), round(leg.positions[index][1], 5)]
                for index in leg.order
            ]
            + [list(port.position)]
        )
        total = (leg.cumulative[-1] if leg.cumulative else 0.0) + leg.back_km
        route = {
            "port_id": port.id,
            "order": order_ids,
            "path": path,
            "legs": [
                {
                    "target_id": target_id,
                    "cumulative_km": round(cumulative, 2),
                    "arrive_h": round(arrival, 3),
                }
                for target_id, cumulative, arrival in zip(
                    order_ids, leg.cumulative, leg.arrivals, strict=True
                )
            ],
            "one_way_km": round(leg.cumulative[-1], 2),
            "distance_km": round(total, 2),
            "duration_h": round(
                total / options.speed_kmh + len(leg.order) * options.dwell_min / 60.0, 2
            ),
            "speed_kn": options.speed_kn,
            "dwell_min": options.dwell_min,
            "method": "ближайший сосед + 2-opt по прямым расстояниям; позиции целей — "
            "по сценарию дрейфа на момент выхода",
        }
    port_payload = None
    if port is not None:
        port_payload = {
            **port.summary(),
            "distance_km": round(port_found[0], 2) if port_found else None,
        }
    body = {
        "status": {
            "status": SurveyStatus.ESTIMATE.value,
            "label": SURVEY_STATUS_LABELS[SurveyStatus.ESTIMATE],
        },
        "reason": PLAN_REASON,
        "value_kind": VALUE_KIND,
        "request": request,
        "t0": scene["acquired_at"],
        "ready_at": iso(ready),
        "drift": summary,
        "zones": {
            "total": len(zones),
            "groups": len(groups),
            "planned": len(selected),
            "limit": MAX_TARGETS,
        },
        "weights": dict(WEIGHTS),
        "scoring": dict(SCORING),
        "port": port_payload,
        "targets": targets,
        "route": route,
        "exit_window": window,
        "passes": passes or [],
        "messages": messages,
    }
    return with_clock(body, now)


def with_clock(payload: dict[str, Any], now: dt.datetime) -> dict[str, Any]:
    window = payload.get("exit_window")
    messages = [
        message for message in payload.get("messages", []) if not message.startswith(PAST_NOTE)
    ]
    if window is None:
        return {**payload, "messages": messages}
    past = _parse(window["to"]) < now
    if past:
        messages.append(
            f"{PAST_NOTE}: снимок от {_parse(payload['t0']):%d.%m.%Y} — "
            "план показывает, как следовало выйти"
        )
    return {**payload, "exit_window": {**window, "past": past}, "messages": messages}
