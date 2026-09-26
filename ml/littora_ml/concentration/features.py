from __future__ import annotations

import datetime as dt
import itertools
import json
import math
import time
import urllib.parse
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path

import numpy as np
import pandas as pd
import shapefile
from shapely.geometry import LineString, Point
from shapely.ops import nearest_points
from shapely.strtree import STRtree

from app.earth.catalog import build_ssl_context
from littora_ml.audit.case_audit import haversine_km
from littora_ml.common.io import text_sha256
from littora_ml.common.paths import EXTERNAL, INTERIM
from littora_ml.concentration.dataset import reference_time

WEATHER_URL = "https://archive-api.open-meteo.com/v1/archive"
MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"
RIVER_DECAY_KM = 100.0
RIVER_RADIUS_KM = 500.0


def seasonal(table: pd.DataFrame) -> pd.DataFrame:
    day = pd.to_datetime(table["date"]).dt.dayofyear
    angle = 2 * np.pi * (day - 1) / 365.25
    return pd.DataFrame({"doy_sin": np.sin(angle), "doy_cos": np.cos(angle)}, index=table.index)


def local_xy(table: pd.DataFrame) -> pd.DataFrame:
    lat0 = table["latitude"].mean()
    lon0 = table["longitude"].mean()
    x = (table["longitude"] - lon0) * 111.32 * np.cos(np.radians(lat0))
    y = (table["latitude"] - lat0) * 110.57
    return pd.DataFrame({"x_km": x, "y_km": y}, index=table.index)


def _coastline() -> STRtree:
    archive = zipfile.ZipFile(EXTERNAL / "natural-earth" / "ne_10m_coastline.zip")
    reader = shapefile.Reader(
        shp=BytesIO(archive.read("ne_10m_coastline.shp")),
        shx=BytesIO(archive.read("ne_10m_coastline.shx")),
        dbf=BytesIO(archive.read("ne_10m_coastline.dbf")),
    )
    lines = []
    for shape in reader.shapes():
        for start, end in itertools.pairwise([*shape.parts, len(shape.points)]):
            if end - start >= 2:
                lines.append(LineString(shape.points[start:end]))
    return STRtree(lines)


def coast_distance(table: pd.DataFrame) -> pd.Series:
    tree = _coastline()
    geometries = tree.geometries
    distances = []
    for lat, lon in zip(table["latitude"], table["longitude"], strict=True):
        point = Point(lon, lat)
        nearest = geometries[tree.nearest(point)]
        _, on_coast = nearest_points(point, nearest)
        distances.append(float(haversine_km(lat, lon, on_coast.y, on_coast.x)))
    return pd.Series(distances, index=table.index, name="coast_km")


def river_inputs(table: pd.DataFrame) -> pd.DataFrame:
    rivers = pd.read_csv(EXTERNAL / "river-plastic-lebreton2017" / "PlasticRiverInputs.csv")
    rivers = rivers[rivers["i_mid"] > 0]
    lat, lon, emission = rivers["Y"].to_numpy(), rivers["X"].to_numpy(), rivers["i_mid"].to_numpy()
    weighted, nearest, total = [], [], []
    for plat, plon in zip(table["latitude"], table["longitude"], strict=True):
        distance = haversine_km(plat, plon, lat, lon)
        inside = distance <= RIVER_RADIUS_KM
        weighted.append(
            float(np.sum(emission[inside] * np.exp(-distance[inside] / RIVER_DECAY_KM)))
        )
        large = emission >= 1.0
        nearest.append(float(distance[large].min()) if large.any() else RIVER_RADIUS_KM * 4)
        total.append(float(emission[inside].sum()))
    return pd.DataFrame(
        {
            "river_weighted_log": np.log1p(weighted),
            "river_total_500km_log": np.log1p(total),
            "river_nearest_km": nearest,
        },
        index=table.index,
    )


class OpenMeteo:
    def __init__(self, cache: Path) -> None:
        self.cache = cache
        self.cache.mkdir(parents=True, exist_ok=True)
        self.context = build_ssl_context()

    def _get(self, url: str, params: dict) -> dict:
        key = urllib.parse.urlencode(sorted(params.items()))
        host = url.split("//")[1].split(".")[0]
        path = self.cache / f"{host}_{text_sha256(key)[:20]}.json"
        if path.exists():
            cached = json.loads(path.read_text())
            if cached.get("request") == key:
                return cached["response"]
        request = f"{url}?{key}"
        for attempt in range(5):
            try:
                with urllib.request.urlopen(request, timeout=60, context=self.context) as reply:
                    response = json.load(reply)
                break
            except OSError:
                time.sleep(3 * (attempt + 1))
        else:
            raise RuntimeError(f"open-meteo unreachable: {request}")
        path.write_text(json.dumps({"request": key, "response": response}))
        return response

    def hourly(self, url: str, lat: float, lon: float, day: dt.date, variables: list[str], **extra):
        params = {
            "latitude": round(lat, 3),
            "longitude": round(lon, 3),
            "start_date": (day - dt.timedelta(days=3)).isoformat(),
            "end_date": day.isoformat(),
            "hourly": ",".join(variables),
            **extra,
        }
        data = self._get(url, params)["hourly"]
        times = pd.to_datetime(data["time"]).tz_localize("UTC")
        return pd.DataFrame({name: data[name] for name in variables}, index=times, dtype=float)


def _window_stats(series: pd.Series, moment: dt.datetime, hours: int) -> float:
    window = series[(series.index > moment - dt.timedelta(hours=hours)) & (series.index <= moment)]
    return float(window.mean()) if window.notna().any() else math.nan


def _at(series: pd.Series, moment: dt.datetime) -> float:
    if series.dropna().empty:
        return math.nan
    stamp = pd.Timestamp(moment)
    return float(np.interp(stamp.value, series.index.asi8, series.interpolate().bfill().ffill()))


def weather(
    table: pd.DataFrame, cache: Path = INTERIM / "concentration" / "open-meteo"
) -> pd.DataFrame:
    client = OpenMeteo(cache)

    def one(row: pd.Series) -> dict:
        moment = reference_time(row)
        day = moment.date()
        wind = client.hourly(
            WEATHER_URL,
            row["latitude"],
            row["longitude"],
            day,
            ["wind_speed_10m"],
            models="era5",
            wind_speed_unit="ms",
        )["wind_speed_10m"]
        waves = client.hourly(
            MARINE_URL, row["latitude"], row["longitude"], day, ["wave_height"], models="era5_ocean"
        )["wave_height"]
        return {
            "wind_now": _at(wind, moment),
            "wind_24h": _window_stats(wind, moment, 24),
            "wind_72h": _window_stats(wind, moment, 72),
            "wind_max_72h": float(wind[wind.index <= moment].tail(72).max()),
            "wave_now": _at(waves, moment),
            "wave_24h": _window_stats(waves, moment, 24),
        }

    with ThreadPoolExecutor(max_workers=6) as pool:
        rows = list(pool.map(one, (row for _, row in table.iterrows())))
    return pd.DataFrame(rows, index=table.index)


FEATURE_GROUPS = {
    "spatial": ["x_km", "y_km"],
    "season": ["doy_sin", "doy_cos"],
    "geography": ["coast_km", "river_weighted_log", "river_total_500km_log", "river_nearest_km"],
    "weather": ["wind_now", "wind_24h", "wind_72h", "wind_max_72h", "wave_now", "wave_24h"],
}

FEATURE_SOURCES = {
    "spatial": {
        "case_columns": ["latitude", "longitude"],
        "external": None,
        "service_input": "центр района запроса",
    },
    "season": {
        "case_columns": ["date_utc"],
        "external": None,
        "service_input": "дата снимка или запроса",
    },
    "geography": {
        "case_columns": ["latitude", "longitude"],
        "external": "Natural Earth 10m coastline; Lebreton et al. 2017, PlasticRiverInputs",
        "service_input": "центр района запроса",
    },
    "weather": {
        "case_columns": ["latitude", "longitude", "date_utc", "time_start_utc", "time_end_utc"],
        "external": "Open-Meteo archive: ERA5 wind_speed_10m, ERA5-Ocean wave_height",
        "service_input": "центр района и время снимка",
    },
}

OBSERVED_AT = (
    "observed_at — середина интервала time_start_utc…time_end_utc, без времени — date_utc "
    "12:00 UTC. Это момент наблюдения, по нему берётся ветер и волнение за 72 ч до него. "
    "Значение не зависит от числа предметов, площади и концентрации; в сервисе его заменяет "
    "время снимка. В аудите time_* помечены survey_only как параметры рейса; как метка "
    "времени для погодных признаков они допущены явно, сами в модель не подаются."
)


def build_features(table: pd.DataFrame) -> pd.DataFrame:
    parts = [table]
    local = pd.concat([local_xy(group) for _, group in table.groupby("measurement_profile")]).loc[
        table.index
    ]
    parts += [local, seasonal(table), coast_distance(table).to_frame(), river_inputs(table)]
    parts.append(weather(table))
    return pd.concat(parts, axis=1)
