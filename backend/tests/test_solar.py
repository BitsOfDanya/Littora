import datetime as dt
import math

import pytest

from app.case.solar import (
    day_fraction,
    daylight_shift_bound_hours,
    daylight_utc,
    daylight_within_utc_day,
    utc_day_shift_bound_hours,
)


def minutes(moment: dt.datetime) -> float:
    return moment.hour * 60 + moment.minute + moment.second / 60


def test_equinox_daylight_in_greenwich_matches_the_almanac() -> None:
    sunrise, sunset = daylight_utc(dt.date(2024, 3, 20), 51.4769, 0.0)
    assert abs(minutes(sunrise) - (6 * 60 + 2)) < 5
    assert abs(minutes(sunset) - (18 * 60 + 14)) < 5


def test_polar_day_has_no_bound() -> None:
    assert daylight_utc(dt.date(2024, 6, 21), 78.2, 15.6) is None
    moment = dt.datetime(2024, 6, 21, 10, tzinfo=dt.UTC)
    assert daylight_shift_bound_hours(moment, dt.date(2024, 6, 21), 78.2, 15.6) is None


def test_day_fraction_accounts_for_leap_years() -> None:
    assert day_fraction(dt.date(2024, 12, 31)) == pytest.approx(2 * math.pi * 365 / 366)
    assert day_fraction(dt.date(2023, 12, 31)) == pytest.approx(2 * math.pi * 364 / 365)
    assert day_fraction(dt.date(2024, 1, 1)) == 0.0


@pytest.mark.parametrize(("hour", "expected"), [(0, 24.0), (9, 15.0), (12, 12.0), (18, 18.0)])
def test_utc_day_bound_is_the_farthest_end_of_the_day(hour: int, expected: float) -> None:
    day = dt.date(2024, 6, 2)
    moment = dt.datetime.combine(day, dt.time(hour), tzinfo=dt.UTC)
    assert utc_day_shift_bound_hours(moment, day) == pytest.approx(expected)


def test_utc_day_bound_grows_with_the_day_shift() -> None:
    day = dt.date(2024, 6, 2)
    moment = dt.datetime(2024, 6, 3, 9, tzinfo=dt.UTC)
    assert utc_day_shift_bound_hours(moment, day) == pytest.approx(33.0)


def test_daylight_is_clipped_to_the_utc_day() -> None:
    day = dt.date(2024, 3, 20)
    start = dt.datetime.combine(day, dt.time.min, tzinfo=dt.UTC)
    intervals = daylight_within_utc_day(day, 0.0, 170.0)
    assert len(intervals) == 2
    for first, last in intervals:
        assert start <= first < last <= start + dt.timedelta(days=1)
    assert intervals[0][0] == start
    assert intervals[-1][1] == start + dt.timedelta(days=1)


@pytest.mark.parametrize(
    ("latitude", "longitude"), [(43.5, 30.0), (0.0, 170.0), (-60.0, -150.0), (65.0, 20.0)]
)
def test_daylight_bound_never_exceeds_the_utc_day_bound(latitude: float, longitude: float) -> None:
    day = dt.date(2024, 6, 2)
    for minute in range(0, 24 * 60, 20):
        moment = dt.datetime.combine(day, dt.time.min, tzinfo=dt.UTC) + dt.timedelta(minutes=minute)
        daylight = daylight_shift_bound_hours(moment, day, latitude, longitude)
        assert daylight is not None
        assert daylight <= utc_day_shift_bound_hours(moment, day) + 1e-9
