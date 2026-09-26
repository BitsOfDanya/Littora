from __future__ import annotations

import calendar
import datetime as dt
import math

SUN_ZENITH_AT_HORIZON_DEG = 90.833


def day_fraction(day: dt.date) -> float:
    days_in_year = 366 if calendar.isleap(day.year) else 365
    return 2 * math.pi / days_in_year * (day.timetuple().tm_yday - 1)


def utc_day(day: dt.date) -> tuple[dt.datetime, dt.datetime]:
    start = dt.datetime.combine(day, dt.time.min, tzinfo=dt.UTC)
    return start, start + dt.timedelta(days=1)


def daylight_utc(
    day: dt.date, latitude: float, longitude: float
) -> tuple[dt.datetime, dt.datetime] | None:
    gamma = day_fraction(day)
    equation_of_time = 229.18 * (
        0.000075
        + 0.001868 * math.cos(gamma)
        - 0.032077 * math.sin(gamma)
        - 0.014615 * math.cos(2 * gamma)
        - 0.040849 * math.sin(2 * gamma)
    )
    declination = (
        0.006918
        - 0.399912 * math.cos(gamma)
        + 0.070257 * math.sin(gamma)
        - 0.006758 * math.cos(2 * gamma)
        + 0.000907 * math.sin(2 * gamma)
        - 0.002697 * math.cos(3 * gamma)
        + 0.00148 * math.sin(3 * gamma)
    )
    phi = math.radians(latitude)
    cosine = math.cos(math.radians(SUN_ZENITH_AT_HORIZON_DEG)) / (
        math.cos(phi) * math.cos(declination)
    ) - math.tan(phi) * math.tan(declination)
    if not -1 <= cosine <= 1:
        return None
    hour_angle = math.degrees(math.acos(cosine))
    midnight = utc_day(day)[0]
    sunrise = 720 - 4 * (longitude + hour_angle) - equation_of_time
    sunset = 720 - 4 * (longitude - hour_angle) - equation_of_time
    return midnight + dt.timedelta(minutes=sunrise), midnight + dt.timedelta(minutes=sunset)


def daylight_within_utc_day(
    day: dt.date, latitude: float, longitude: float
) -> list[tuple[dt.datetime, dt.datetime]] | None:
    start, end = utc_day(day)
    intervals = []
    for offset in (-1, 0, 1):
        window = daylight_utc(day + dt.timedelta(days=offset), latitude, longitude)
        if window is None:
            return None
        sunrise, sunset = max(window[0], start), min(window[1], end)
        if sunrise < sunset:
            intervals.append((sunrise, sunset))
    return intervals or None


def _farthest_hours(moment: dt.datetime, intervals: list[tuple[dt.datetime, dt.datetime]]) -> float:
    return max(max(abs(moment - first), abs(last - moment)) for first, last in intervals) / (
        dt.timedelta(hours=1)
    )


def utc_day_shift_bound_hours(moment: dt.datetime, day: dt.date) -> float:
    return _farthest_hours(moment, [utc_day(day)])


def daylight_shift_bound_hours(
    moment: dt.datetime, day: dt.date, latitude: float, longitude: float
) -> float | None:
    intervals = daylight_within_utc_day(day, latitude, longitude)
    if intervals is None:
        return None
    return _farthest_hours(moment, intervals)
