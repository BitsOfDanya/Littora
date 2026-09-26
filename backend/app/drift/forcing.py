from __future__ import annotations

import datetime as dt
import gzip
import hashlib
import json
import math
import os
import threading
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from scipy.ndimage import distance_transform_edt

from app.drift.geo import METERS_PER_DEGREE
from app.earth.catalog import USER_AGENT, build_ssl_context

MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
WAVE_MODEL = "meteofrance_wave"
CURRENT_MODEL = "meteofrance_currents"
MARINE_CELL_DEG = 1 / 12
WIND_CELL_DEG = 0.25
MAX_MARINE_POINTS = 200
MAX_WIND_POINTS = 120
CHUNK_POINTS = 60
PARALLEL_REQUESTS = 4
ERA5_LAG_DAYS = 7
GRAVITY = 9.80665
MIN_WAVE_PERIOD_S = 1.0
CURRENT_QUANTUM_MS = 0.05
CURRENTS_LABEL = "Open-Meteo Marine · MeteoFrance SMOC 1/12°"
WAVES_LABEL = "Open-Meteo Marine · MeteoFrance MFWAM 1/12°"
ERA5_LABEL = "Open-Meteo Archive · ERA5 0,25°"
FORECAST_LABEL = "Open-Meteo Forecast · best match"
CURRENTS_CONTENT = (
    "полное поверхностное течение SMOC: эйлерово + волновой (стоксов) дрейф + приливы"
)
STOKES_FORMULA = (
    "Us = 2π³·Hs²/(g·Tm³) — глубоководная монохроматическая волна с амплитудой Hs/2 "
    "(Kenyon 1969; Breivik et al. 2014), направление — куда идут волны"
)


class ForcingError(RuntimeError):
    pass


@dataclass(frozen=True)
class Domain:
    west: float
    south: float
    east: float
    north: float

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        return self.west, self.south, self.east, self.north

    @classmethod
    def around(cls, bounds: Sequence[float], margin_km: float) -> Domain:
        west, south, east, north = bounds
        lat_margin = margin_km * 1000.0 / METERS_PER_DEGREE
        lon_margin = lat_margin / max(math.cos(math.radians((south + north) / 2)), 0.1)
        return cls(
            max(west - lon_margin, -180.0),
            max(south - lat_margin, -85.0),
            min(east + lon_margin, 180.0),
            min(north + lat_margin, 85.0),
        )


@dataclass(frozen=True)
class Forcing:
    start: dt.datetime
    lons: np.ndarray
    lats: np.ndarray
    current: np.ndarray
    stokes: np.ndarray
    wind: np.ndarray
    water: np.ndarray
    provenance: dict[str, Any]

    @property
    def steps(self) -> int:
        return self.wind.shape[0]


def stokes_drift(
    height: np.ndarray, period: np.ndarray, direction_from: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    period = np.maximum(np.asarray(period, dtype=float), MIN_WAVE_PERIOD_S)
    speed = 2 * np.pi**3 * np.square(np.asarray(height, dtype=float)) / (GRAVITY * period**3)
    toward = np.radians(np.asarray(direction_from, dtype=float) + 180.0)
    return speed * np.sin(toward), speed * np.cos(toward)


def _toward(speed: np.ndarray, direction: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    angle = np.radians(direction)
    return speed * np.sin(angle), speed * np.cos(angle)


def _axis(low: float, high: float, step: float, offset: float) -> np.ndarray:
    first = math.floor((low - offset) / step) * step + offset
    count = math.ceil((high - first) / step - 1e-9) + 1
    return np.round(first + step * np.arange(max(count, 1)), 6)


def marine_axes(
    domain: Domain, max_points: int = MAX_MARINE_POINTS
) -> tuple[np.ndarray, np.ndarray, float]:
    for stride in range(1, 13):
        step = MARINE_CELL_DEG * stride
        lats = _axis(domain.south, domain.north, step, MARINE_CELL_DEG / 2)
        lons = _axis(domain.west, domain.east, step, MARINE_CELL_DEG / 2)
        if lats.size * lons.size <= max_points:
            return lats, lons, step
    raise ForcingError("область дрейфа слишком велика для сетки форсинга")


def wind_axes(
    lats: np.ndarray, lons: np.ndarray, max_points: int = MAX_WIND_POINTS
) -> tuple[np.ndarray, np.ndarray]:
    for stride in range(1, 9):
        step = WIND_CELL_DEG * stride
        wind_lats = _axis(lats[0] - step, lats[-1] + step, step, 0.0)
        wind_lons = _axis(lons[0] - step, lons[-1] + step, step, 0.0)
        if wind_lats.size * wind_lons.size <= max_points:
            return wind_lats, wind_lons
    raise ForcingError("область дрейфа слишком велика для сетки ветра")


def hourly(start: dt.datetime, end: dt.datetime) -> list[dt.datetime]:
    count = int((end - start).total_seconds() // 3600) + 1
    return [start + dt.timedelta(hours=index) for index in range(count)]


def _weights(axis: np.ndarray, targets: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if axis.size == 1:
        zeros = np.zeros(targets.size, dtype=int)
        return zeros, zeros, np.zeros(targets.size)
    position = np.interp(targets, axis, np.arange(axis.size))
    lower = np.minimum(np.floor(position).astype(int), axis.size - 2)
    return lower, lower + 1, position - lower


def regrid(
    values: np.ndarray,
    source: tuple[np.ndarray, np.ndarray],
    target: tuple[np.ndarray, np.ndarray],
) -> np.ndarray:
    y0, y1, wy = _weights(source[0], target[0])
    x0, x1, wx = _weights(source[1], target[1])
    wy, wx = wy[:, None], wx[None, :]
    rows0, rows1 = y0[:, None], y1[:, None]
    cols0, cols1 = x0[None, :], x1[None, :]
    south = values[:, rows0, cols0] * (1 - wx) + values[:, rows0, cols1] * wx
    north = values[:, rows1, cols0] * (1 - wx) + values[:, rows1, cols1] * wx
    return south * (1 - wy) + north * wy


def _fill_time(values: np.ndarray) -> np.ndarray:
    filled = values.copy()
    steps = np.arange(values.shape[0])
    for column in range(values.shape[1]):
        valid = np.isfinite(values[:, column])
        if valid.any() and not valid.all():
            filled[:, column] = np.interp(steps, steps[valid], values[valid, column])
    return filled


def _fill_space(values: np.ndarray, valid: np.ndarray) -> np.ndarray:
    if not valid.any():
        return np.zeros_like(values)
    if valid.all():
        return values
    rows, cols = distance_transform_edt(~valid, return_distances=False, return_indices=True)
    return values[:, rows, cols]


def _quantized(east: np.ndarray, north: np.ndarray, quantum: float) -> bool:
    values = np.concatenate([east, north]) / quantum
    return bool(values.size) and bool(np.all(np.abs(values - np.rint(values)) < 0.15))


def _gap_hours(values: np.ndarray, water: np.ndarray) -> int:
    if not water.any():
        return 0
    return int((~np.isfinite(values[:, water])).all(axis=1).sum())


class OpenMeteoClient:
    def __init__(self, cache_dir: Path | None, timeout: float = 60.0) -> None:
        self.cache_dir = cache_dir
        self.timeout = timeout
        self.context = build_ssl_context()

    def _download(self, address: str) -> list[dict[str, Any]]:
        request = urllib.request.Request(
            address, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
        )
        try:
            with urllib.request.urlopen(
                request, timeout=self.timeout, context=self.context
            ) as reply:
                payload = json.load(reply)
        except urllib.error.HTTPError as error:
            if error.code == 429:
                raise ForcingError(
                    "Open-Meteo ограничил частоту запросов — повторите через минуту"
                ) from error
            try:
                reason = json.load(error).get("reason", error.reason)
            except (ValueError, OSError, AttributeError):
                reason = error.reason
            raise ForcingError(f"Open-Meteo ответил {error.code}: {reason}") from error
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as error:
            raise ForcingError(f"Open-Meteo недоступен: {error}") from error
        return payload if isinstance(payload, list) else [payload]

    def get(self, url: str, params: dict[str, str]) -> dict[str, Any]:
        address = f"{url}?{urllib.parse.urlencode(params, safe=',:')}"
        path = None
        if self.cache_dir is not None:
            key = hashlib.sha256(address.encode()).hexdigest()
            path = self.cache_dir / f"{key}.json.gz"
            if path.exists():
                return json.loads(gzip.decompress(path.read_bytes()))
        entry = {
            "url": url,
            "fetched_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
            "locations": self._download(address),
        }
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
            temporary.write_bytes(gzip.compress(json.dumps(entry).encode(), 6))
            temporary.replace(path)
        return entry


def _matrix(locations: list[dict[str, Any]], key: str, times: list[dt.datetime]) -> np.ndarray:
    columns = []
    for location in locations:
        series = location.get("hourly") or {}
        stamps = {
            dt.datetime.fromisoformat(stamp).replace(tzinfo=dt.UTC): index
            for index, stamp in enumerate(series.get("time", []))
        }
        missing = [moment for moment in times if moment not in stamps]
        if missing:
            raise ForcingError(f"ответ Open-Meteo не покрывает {missing[0]:%Y-%m-%d %H:%M} UTC")
        raw = series.get(key)
        values = np.array(raw if raw is not None else [None] * len(stamps), dtype=float)
        columns.append(values[[stamps[moment] for moment in times]])
    return np.column_stack(columns)


def _model_key(name: str, model: str) -> str:
    return f"{name}_{model}"


class OpenMeteoForcing:
    def __init__(
        self,
        cache_dir: Path | None,
        timeout: float = 60.0,
        today: Callable[[], dt.date] | None = None,
        client: OpenMeteoClient | None = None,
    ) -> None:
        self.client = client or OpenMeteoClient(cache_dir, timeout)
        self.today = today or (lambda: dt.datetime.now(dt.UTC).date())

    def _fetch(
        self,
        url: str,
        params: dict[str, str],
        lats: np.ndarray,
        lons: np.ndarray,
    ) -> tuple[list[dict[str, Any]], str]:
        grid_lats, grid_lons = np.meshgrid(lats, lons, indexing="ij")
        points = list(zip(grid_lats.ravel(), grid_lons.ravel(), strict=True))
        chunks = [points[i : i + CHUNK_POINTS] for i in range(0, len(points), CHUNK_POINTS)]

        def fetch(chunk: list[tuple[float, float]]) -> dict[str, Any]:
            query = {
                "latitude": ",".join(f"{lat:.4f}" for lat, _ in chunk),
                "longitude": ",".join(f"{lon:.4f}" for _, lon in chunk),
                **params,
            }
            return self.client.get(url, query)

        with ThreadPoolExecutor(PARALLEL_REQUESTS) as pool:
            entries = list(pool.map(fetch, chunks))
        locations = [location for entry in entries for location in entry["locations"]]
        if len(locations) != len(points):
            raise ForcingError("Open-Meteo вернул не все точки сетки")
        return locations, max(entry["fetched_at"] for entry in entries)

    def _wind_source(self, end: dt.datetime) -> tuple[str, dict[str, str], str]:
        if end.date() <= self.today() - dt.timedelta(days=ERA5_LAG_DAYS):
            return ARCHIVE_URL, {"models": "era5"}, ERA5_LABEL
        return FORECAST_URL, {}, FORECAST_LABEL

    def load(
        self,
        domain: Domain,
        start: dt.datetime,
        end: dt.datetime,
        marine_points: int = MAX_MARINE_POINTS,
        wind_points: int = MAX_WIND_POINTS,
    ) -> Forcing:
        times = hourly(start, end)
        dates = {"start_date": start.date().isoformat(), "end_date": end.date().isoformat()}
        common = {**dates, "timezone": "GMT", "wind_speed_unit": "ms"}
        lats, lons, step = marine_axes(domain, marine_points)
        marine, marine_fetched = self._fetch(
            MARINE_URL,
            {
                "hourly": "wave_height,wave_direction,wave_period,"
                "ocean_current_velocity,ocean_current_direction",
                "models": f"{WAVE_MODEL},{CURRENT_MODEL}",
                "cell_selection": "nearest",
                **common,
            },
            lats,
            lons,
        )
        wind_lats, wind_lons = wind_axes(lats, lons, wind_points)
        wind_url, wind_params, wind_label = self._wind_source(end)
        winds, wind_fetched = self._fetch(
            wind_url,
            {"hourly": "wind_speed_10m,wind_direction_10m", **wind_params, **common},
            wind_lats,
            wind_lons,
        )
        shape = (len(times), lats.size, lons.size)
        height = _matrix(marine, _model_key("wave_height", WAVE_MODEL), times)
        period = _matrix(marine, _model_key("wave_period", WAVE_MODEL), times)
        direction = _matrix(marine, _model_key("wave_direction", WAVE_MODEL), times)
        speed = _matrix(marine, _model_key("ocean_current_velocity", CURRENT_MODEL), times)
        heading = _matrix(marine, _model_key("ocean_current_direction", CURRENT_MODEL), times)
        waves_valid = np.isfinite(height) & np.isfinite(period) & np.isfinite(direction)
        currents_valid = np.isfinite(speed) & np.isfinite(heading)
        waves_available = bool(waves_valid.any())
        currents_available = bool(currents_valid.any())
        sea_known = waves_available or currents_available
        water_flat = (
            waves_valid.any(axis=0) | currents_valid.any(axis=0)
            if sea_known
            else np.ones(lats.size * lons.size, dtype=bool)
        )
        current_gaps = _gap_hours(np.where(currents_valid, speed, np.nan), water_flat)
        wave_gaps = _gap_hours(np.where(waves_valid, height, np.nan), water_flat)

        def field(u: np.ndarray, v: np.ndarray, valid: np.ndarray) -> np.ndarray:
            u = _fill_time(np.where(valid, u, np.nan)).reshape(shape)
            v = _fill_time(np.where(valid, v, np.nan)).reshape(shape)
            known = valid.any(axis=0).reshape(shape[1:])
            return np.stack([_fill_space(u, known), _fill_space(v, known)], axis=-1)

        stokes = field(*stokes_drift(height, period, direction), waves_valid)
        current_east, current_north = _toward(speed, heading)
        coarse = _quantized(
            current_east[currents_valid], current_north[currents_valid], CURRENT_QUANTUM_MS
        )
        total = field(current_east, current_north, currents_valid)
        current = total - stokes if currents_available else np.zeros_like(stokes)

        wind_speed = _matrix(winds, "wind_speed_10m", times)
        wind_direction = _matrix(winds, "wind_direction_10m", times)
        wind_valid = np.isfinite(wind_speed) & np.isfinite(wind_direction)
        if not wind_valid.any():
            raise ForcingError("нет данных о ветре на это окно")
        wind_gaps = _gap_hours(
            np.where(wind_valid, wind_speed, np.nan), np.ones(wind_speed.shape[1], dtype=bool)
        )
        wind_shape = (len(times), wind_lats.size, wind_lons.size)
        east, north = _toward(wind_speed, wind_direction + 180.0)
        wind_known = wind_valid.any(axis=0).reshape(wind_shape[1:])

        def wind_component(values: np.ndarray) -> np.ndarray:
            filled = _fill_time(np.where(wind_valid, values, np.nan)).reshape(wind_shape)
            return regrid(_fill_space(filled, wind_known), (wind_lats, wind_lons), (lats, lons))

        wind = np.stack([wind_component(east), wind_component(north)], axis=-1)
        provenance = {
            "currents": {
                "available": currents_available,
                "source": CURRENTS_LABEL,
                "content": CURRENTS_CONTENT,
                "filled_hours": current_gaps if currents_available else None,
                "quantum_ms": CURRENT_QUANTUM_MS if coarse else None,
            },
            "waves": {
                "available": waves_available,
                "source": WAVES_LABEL,
                "stokes": STOKES_FORMULA,
                "filled_hours": wave_gaps if waves_available else None,
            },
            "wind": {"available": True, "source": wind_label, "filled_hours": wind_gaps},
            "grid": {
                "bounds": [round(value, 5) for value in domain.bounds],
                "marine_step_deg": round(step, 6),
                "wind_step_deg": round(float(wind_lats[1] - wind_lats[0]), 6)
                if wind_lats.size > 1
                else WIND_CELL_DEG,
                "marine_points": int(lats.size * lons.size),
                "wind_points": int(wind_lats.size * wind_lons.size),
                "water_points": int(water_flat.sum()),
                "sea_mask": "по наличию данных Open-Meteo Marine в узле"
                if sea_known
                else "нет данных Open-Meteo Marine — море не определено",
            },
            "window": {
                "start": start.isoformat().replace("+00:00", "Z"),
                "end": end.isoformat().replace("+00:00", "Z"),
            },
            "fetched_at": max(marine_fetched, wind_fetched),
        }
        return Forcing(
            start=start,
            lons=lons,
            lats=lats,
            current=current,
            stokes=stokes,
            wind=wind,
            water=water_flat.reshape(shape[1:]),
            provenance=provenance,
        )
