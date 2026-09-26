from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from typing import Any, Protocol

from app.drift.forcing import (
    ARCHIVE_URL,
    ERA5_LABEL,
    ERA5_LAG_DAYS,
    FORECAST_LABEL,
    FORECAST_URL,
    MARINE_URL,
    ForcingError,
    OpenMeteoClient,
)

MARINE_LABEL = "Open-Meteo Marine · best match"


class WeatherSource(Protocol):
    def at(self, lon: float, lat: float, moment: dt.datetime) -> dict[str, Any]: ...


def _hour(moment: dt.datetime) -> dt.datetime:
    moment = moment.astimezone(dt.UTC)
    rounded = moment.replace(minute=0, second=0, microsecond=0)
    return rounded + dt.timedelta(hours=1) if moment.minute >= 30 else rounded


def _stamp(moment: dt.datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M")


def _value(location: dict[str, Any], key: str, stamp: str) -> float | None:
    series = location.get("hourly") or {}
    values = dict(zip(series.get("time") or [], series.get(key) or [], strict=False))
    value = values.get(stamp)
    return float(value) if isinstance(value, int | float) else None


def _location(entry: dict[str, Any]) -> dict[str, Any]:
    locations = entry.get("locations") or []
    if not locations:
        raise ForcingError("Open-Meteo не вернул точку")
    return locations[0]


class OpenMeteoWeather:
    def __init__(
        self,
        client: OpenMeteoClient,
        today: Callable[[], dt.date] | None = None,
    ) -> None:
        self.client = client
        self.today = today or (lambda: dt.datetime.now(dt.UTC).date())

    def _query(self, lon: float, lat: float, day: dt.date, fields: str) -> dict[str, str]:
        return {
            "latitude": f"{lat:.4f}",
            "longitude": f"{lon:.4f}",
            "hourly": fields,
            "start_date": day.isoformat(),
            "end_date": day.isoformat(),
            "timezone": "GMT",
            "wind_speed_unit": "ms",
        }

    def _wind(self, lon: float, lat: float, hour: dt.datetime) -> dict[str, Any] | None:
        archive = hour.date() <= self.today() - dt.timedelta(days=ERA5_LAG_DAYS)
        url, extra, label = (
            (ARCHIVE_URL, {"models": "era5"}, ERA5_LABEL)
            if archive
            else (FORECAST_URL, {}, FORECAST_LABEL)
        )
        query = {**self._query(lon, lat, hour.date(), "wind_speed_10m,wind_direction_10m"), **extra}
        location = _location(self.client.get(url, query))
        speed = _value(location, "wind_speed_10m", _stamp(hour))
        direction = _value(location, "wind_direction_10m", _stamp(hour))
        if speed is None or direction is None:
            return None
        return {"speed_ms": round(speed, 1), "from_deg": round(direction) % 360, "source": label}

    def _waves(self, lon: float, lat: float, hour: dt.datetime) -> dict[str, Any] | None:
        query = self._query(lon, lat, hour.date(), "wave_height,wave_direction,wave_period")
        query.pop("wind_speed_unit")
        query["cell_selection"] = "sea"
        location = _location(self.client.get(MARINE_URL, query))
        height = _value(location, "wave_height", _stamp(hour))
        if height is None:
            return None
        period = _value(location, "wave_period", _stamp(hour))
        direction = _value(location, "wave_direction", _stamp(hour))
        return {
            "height_m": round(height, 2),
            "period_s": round(period, 1) if period is not None else None,
            "from_deg": round(direction) % 360 if direction is not None else None,
            "source": MARINE_LABEL,
        }

    def at(self, lon: float, lat: float, moment: dt.datetime) -> dict[str, Any]:
        hour = _hour(moment)
        messages: list[str] = []
        complete = True
        readings: dict[str, Any] = {}
        for key, read, name in (("wind", self._wind, "ветре"), ("waves", self._waves, "волнении")):
            try:
                readings[key] = read(lon, lat, hour)
            except ForcingError as error:
                readings[key] = None
                complete = False
                messages.append(f"нет данных о {name}: {error}")
                continue
            if readings[key] is None:
                messages.append(f"у Open-Meteo нет данных о {name} на {_stamp(hour)} UTC")
        return {
            "at": hour.isoformat().replace("+00:00", "Z"),
            "point": [round(lon, 5), round(lat, 5)],
            **readings,
            "messages": messages,
            "complete": complete,
        }
