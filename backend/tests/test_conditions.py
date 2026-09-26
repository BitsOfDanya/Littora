import datetime as dt

from app.analysis.conditions import OpenMeteoWeather
from app.drift.forcing import ARCHIVE_URL, FORECAST_URL, MARINE_URL, ForcingError


class FakeClient:
    def __init__(self, fail_marine: bool = False) -> None:
        self.urls: list[str] = []
        self.fail_marine = fail_marine

    def get(self, url, params):
        self.urls.append(url)
        times = [f"{params['start_date']}T{hour:02d}:00" for hour in range(24)]
        if url == MARINE_URL:
            if self.fail_marine:
                raise ForcingError("нет связи")
            hourly = {
                "time": times,
                "wave_height": [0.5 + hour / 100 for hour in range(24)],
                "wave_period": [3.0] * 24,
                "wave_direction": [None] * 24,
            }
        else:
            hourly = {
                "time": times,
                "wind_speed_10m": [float(hour) for hour in range(24)],
                "wind_direction_10m": [359.6] * 24,
            }
        return {"locations": [{"hourly": hourly}]}


def weather(client: FakeClient) -> OpenMeteoWeather:
    return OpenMeteoWeather(client, today=lambda: dt.date(2025, 9, 20))


def test_readings_are_taken_at_the_nearest_hour() -> None:
    client = FakeClient()
    moment = dt.datetime(2025, 9, 4, 8, 41, tzinfo=dt.UTC)
    reading = weather(client).at(37.87, 44.69, moment)
    assert reading["at"] == "2025-09-04T09:00:00Z"
    assert reading["wind"] == {"speed_ms": 9.0, "from_deg": 0, "source": reading["wind"]["source"]}
    assert reading["waves"]["height_m"] == 0.59
    assert reading["waves"]["from_deg"] is None
    assert reading["complete"] is True
    assert client.urls == [ARCHIVE_URL, MARINE_URL]


def test_recent_scenes_use_the_forecast_api_and_report_gaps() -> None:
    client = FakeClient(fail_marine=True)
    reading = weather(client).at(37.87, 44.69, dt.datetime(2025, 9, 18, 8, 10, tzinfo=dt.UTC))
    assert client.urls[0] == FORECAST_URL
    assert reading["waves"] is None
    assert reading["complete"] is False
    assert reading["messages"] == ["нет данных о волнении: нет связи"]
