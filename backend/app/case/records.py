from __future__ import annotations

import csv
import datetime as dt
from dataclasses import dataclass
from pathlib import Path


def parse_float(value: str | None) -> float | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_time(value: str | None) -> dt.time | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        return dt.time.fromisoformat(text)
    except ValueError:
        return None


@dataclass(frozen=True)
class CaseRecord:
    fields: dict[str, str]

    def text(self, name: str) -> str:
        return (self.fields.get(name) or "").strip()

    def number(self, name: str) -> float | None:
        return parse_float(self.fields.get(name))

    @property
    def sample_id(self) -> str:
        return self.text("sample_id")

    @property
    def event_id(self) -> str:
        return self.text("event_id")

    @property
    def source_id(self) -> str:
        return self.text("source_id")

    @property
    def record_type(self) -> str:
        return self.text("record_type")

    @property
    def profile(self) -> str:
        return self.text("measurement_profile")

    @property
    def scope(self) -> str:
        return self.text("target_scope")

    @property
    def flags(self) -> tuple[str, ...]:
        return tuple(flag for flag in self.text("quality_flags").split(";") if flag)

    @property
    def date(self) -> dt.date | None:
        text = self.text("date_utc")
        return dt.date.fromisoformat(text) if text else None

    @property
    def time_start(self) -> dt.time | None:
        return parse_time(self.fields.get("time_start_utc"))

    @property
    def time_end(self) -> dt.time | None:
        return parse_time(self.fields.get("time_end_utc"))

    @property
    def observed_at(self) -> dt.datetime | None:
        day, start, end = self.date, self.time_start, self.time_end
        if day is None or start is None:
            return None
        begin = dt.datetime.combine(day, start, tzinfo=dt.UTC)
        if end is None:
            return begin
        finish = dt.datetime.combine(day, end, tzinfo=dt.UTC)
        if finish < begin:
            finish += dt.timedelta(days=1)
        return begin + (finish - begin) / 2

    @property
    def position(self) -> tuple[float, float] | None:
        lon, lat = self.number("longitude"), self.number("latitude")
        return None if lon is None or lat is None else (lon, lat)

    @property
    def segment(self) -> tuple[tuple[float, float], tuple[float, float]] | None:
        values = [self.number(name) for name in ("lon_start", "lat_start", "lon_end", "lat_end")]
        if any(value is None for value in values):
            return None
        lon_start, lat_start, lon_end, lat_end = values
        if (lon_start, lat_start) == (lon_end, lat_end):
            return None
        return (lon_start, lat_start), (lon_end, lat_end)

    @property
    def published_concentration(self) -> float | None:
        return self.number("concentration_items_km2")

    @property
    def items(self) -> float | None:
        return self.number("density_numerator_items")

    @property
    def area_km2(self) -> float | None:
        return self.number("sampled_area_km2")


def load_records(path: Path) -> list[CaseRecord]:
    with path.open(encoding="utf-8", newline="") as handle:
        return [CaseRecord(dict(row)) for row in csv.DictReader(handle)]
