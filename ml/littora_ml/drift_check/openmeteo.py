from __future__ import annotations

import datetime as dt
import gzip
import hashlib
import json
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from app.drift.forcing import (
    Domain,
    ForcingError,
    OpenMeteoClient,
    marine_axes,
    wind_axes,
)
from app.earth.catalog import USER_AGENT

LOCATION_KEYS = ("latitude", "longitude", "start_date", "end_date")
MARINE_VARIABLES = 10
WIND_VARIABLES = 2
DAYS_PER_CALL = 14
VARIABLES_PER_CALL = 10
RETRIES = 4


class BudgetExceeded(RuntimeError):
    pass


class RateLimited(RuntimeError):
    pass


def call_weight(locations: int, days: int, variables: int) -> float:
    return locations * max(1.0, days / DAYS_PER_CALL) * max(1.0, variables / VARIABLES_PER_CALL)


def variable_count(params: dict[str, str]) -> int:
    names = [name for name in params.get("hourly", "").split(",") if name]
    models = [name for name in params.get("models", "").split(",") if name]
    return len(names) * max(1, len(models))


@dataclass
class Throttle:
    per_minute: float
    per_hour: float
    budget: float
    spent: float = 0.0
    requests: int = 0
    history: deque[tuple[float, float]] = field(default_factory=deque)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def _window(self, now: float, seconds: float) -> float:
        return sum(weight for moment, weight in self.history if now - moment < seconds)

    def acquire(self, weight: float) -> None:
        with self.lock:
            if self.spent + weight > self.budget:
                raise BudgetExceeded(
                    f"бюджет Open-Meteo {self.budget:.0f} вызовов исчерпан ({self.spent:.0f})"
                )
            while True:
                now = time.monotonic()
                while self.history and now - self.history[0][0] >= 3600:
                    self.history.popleft()
                minute = self._window(now, 60)
                hour = self._window(now, 3600)
                if minute + weight <= self.per_minute and hour + weight <= self.per_hour:
                    break
                if hour + weight > self.per_hour:
                    raise RateLimited("часовой лимит запуска исчерпан — продолжите позже")
                oldest = next(moment for moment, _ in self.history if now - moment < 60)
                time.sleep(max(0.5, 60 - (now - oldest) + 0.5))
            self.history.append((time.monotonic(), weight))
            self.spent += weight
            self.requests += 1


class BlockStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.connection = sqlite3.connect(path, check_same_thread=False, timeout=120)
        with self.lock:
            self.connection.execute("PRAGMA journal_mode=WAL")
            self.connection.execute(
                "CREATE TABLE IF NOT EXISTS series "
                "(key TEXT PRIMARY KEY, fetched_at TEXT, payload BLOB)"
            )
            self.connection.commit()

    def get_many(self, keys: Sequence[str]) -> dict[str, tuple[str, dict[str, Any]]]:
        found: dict[str, tuple[str, dict[str, Any]]] = {}
        with self.lock:
            for start in range(0, len(keys), 500):
                part = list(keys[start : start + 500])
                marks = ",".join("?" * len(part))
                rows = self.connection.execute(
                    f"SELECT key, fetched_at, payload FROM series WHERE key IN ({marks})", part
                ).fetchall()
                for key, fetched_at, payload in rows:
                    found[key] = (fetched_at, json.loads(gzip.decompress(payload)))
        return found

    def has(self, keys: Sequence[str]) -> set[str]:
        present: set[str] = set()
        with self.lock:
            for start in range(0, len(keys), 500):
                part = list(keys[start : start + 500])
                marks = ",".join("?" * len(part))
                rows = self.connection.execute(
                    f"SELECT key FROM series WHERE key IN ({marks})", part
                ).fetchall()
                present.update(row[0] for row in rows)
        return present

    def put_many(self, items: Iterable[tuple[str, str, dict[str, Any]]]) -> None:
        rows = [
            (key, fetched_at, gzip.compress(json.dumps(payload).encode(), 6))
            for key, fetched_at, payload in items
        ]
        with self.lock:
            self.connection.executemany("INSERT OR REPLACE INTO series VALUES (?, ?, ?)", rows)
            self.connection.commit()


def block_starts(start: dt.date, end: dt.date, days: int, epoch: dt.date) -> list[dt.date]:
    first = (start - epoch).days // days
    last = (end - epoch).days // days
    return [epoch + dt.timedelta(days=index * days) for index in range(first, last + 1)]


def series_key(url: str, signature: str, block: dt.date, lat: str, lon: str) -> str:
    text = f"{url}|{signature}|{block.isoformat()}|{lat}|{lon}"
    return hashlib.sha256(text.encode()).hexdigest()


class BlockCachedClient(OpenMeteoClient):
    def __init__(
        self,
        store: BlockStore,
        throttle: Throttle,
        block_days: int = DAYS_PER_CALL,
        epoch: dt.date = dt.date(2021, 12, 27),
        chunk_points: int = 60,
        concurrency: int = 2,
        timeout: float = 60.0,
    ) -> None:
        super().__init__(None, timeout)
        self.store = store
        self.throttle = throttle
        self.block_days = block_days
        self.epoch = epoch
        self.chunk_points = chunk_points
        self.gate = threading.Semaphore(concurrency)
        self.minute_limits = 0

    def _request(self, url: str, params: dict[str, str]) -> list[dict[str, Any]]:
        address = f"{url}?{urllib.parse.urlencode(params, safe=',:')}"
        request = urllib.request.Request(
            address, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
        )
        for attempt in range(RETRIES + 1):
            try:
                with (
                    self.gate,
                    urllib.request.urlopen(
                        request, timeout=self.timeout, context=self.context
                    ) as reply,
                ):
                    payload = json.load(reply)
                return payload if isinstance(payload, list) else [payload]
            except urllib.error.HTTPError as error:
                try:
                    reason = str(json.load(error).get("reason", error.reason))
                except (ValueError, OSError, AttributeError):
                    reason = str(error.reason)
                if error.code == 429 and "Minutely" in reason and attempt < RETRIES:
                    self.minute_limits += 1
                    time.sleep(65)
                    continue
                if error.code == 429:
                    raise RateLimited(f"Open-Meteo: {reason}") from error
                if error.code >= 500 and attempt < RETRIES:
                    time.sleep(10 * (attempt + 1))
                    continue
                raise ForcingError(f"Open-Meteo ответил {error.code}: {reason}") from error
            except (urllib.error.URLError, TimeoutError, OSError, ValueError) as error:
                if attempt < RETRIES:
                    time.sleep(10 * (attempt + 1))
                    continue
                raise ForcingError(f"Open-Meteo недоступен: {error}") from error
        raise ForcingError("Open-Meteo недоступен")

    def _download_block(
        self,
        url: str,
        rest: dict[str, str],
        signature: str,
        block: dt.date,
        points: list[tuple[str, str]],
    ) -> None:
        end = block + dt.timedelta(days=self.block_days - 1)
        variables = variable_count(rest)
        for start in range(0, len(points), self.chunk_points):
            chunk = points[start : start + self.chunk_points]
            params = {
                "latitude": ",".join(lat for lat, _ in chunk),
                "longitude": ",".join(lon for _, lon in chunk),
                "start_date": block.isoformat(),
                "end_date": end.isoformat(),
                **rest,
            }
            self.throttle.acquire(call_weight(len(chunk), self.block_days, variables))
            locations = self._request(url, params)
            if len(locations) != len(chunk):
                raise ForcingError("Open-Meteo вернул не все точки блока")
            fetched_at = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
            self.store.put_many(
                (
                    series_key(url, signature, block, lat, lon),
                    fetched_at,
                    {"hourly": location.get("hourly") or {}},
                )
                for (lat, lon), location in zip(chunk, locations, strict=True)
            )

    def get(self, url: str, params: dict[str, str]) -> dict[str, Any]:
        lats = params["latitude"].split(",")
        lons = params["longitude"].split(",")
        start = dt.date.fromisoformat(params["start_date"])
        end = dt.date.fromisoformat(params["end_date"])
        rest = {key: value for key, value in params.items() if key not in LOCATION_KEYS}
        signature = urllib.parse.urlencode(sorted(rest.items()))
        points = list(zip(lats, lons, strict=True))
        blocks = block_starts(start, end, self.block_days, self.epoch)
        keys = {
            (block, point): series_key(url, signature, block, *point)
            for block in blocks
            for point in points
        }
        present = self.store.has(list(keys.values()))
        for block in blocks:
            missing = list(
                dict.fromkeys(point for point in points if keys[(block, point)] not in present)
            )
            if missing:
                self._download_block(url, rest, signature, block, missing)
        found = self.store.get_many(list(keys.values()))
        first, last = start.isoformat(), end.isoformat()
        locations = []
        stamps = []
        for point in points:
            merged: dict[str, list[Any]] = {}
            for block in blocks:
                fetched_at, payload = found[keys[(block, point)]]
                stamps.append(fetched_at)
                hourly = payload["hourly"]
                for name, values in hourly.items():
                    merged.setdefault(name, []).extend(values)
            times = merged.get("time", [])
            keep = [index for index, stamp in enumerate(times) if first <= stamp[:10] <= last]
            locations.append(
                {
                    "latitude": float(point[0]),
                    "longitude": float(point[1]),
                    "hourly": {name: [values[i] for i in keep] for name, values in merged.items()},
                }
            )
        return {"url": url, "fetched_at": max(stamps), "locations": locations}


def domain_points(domain: Domain) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    lats, lons, _ = marine_axes(domain)
    wind_lats, wind_lons = wind_axes(lats, lons)

    def grid(rows: np.ndarray, cols: np.ndarray) -> list[tuple[str, str]]:
        return [(f"{lat:.4f}", f"{lon:.4f}") for lat in rows for lon in cols]

    return grid(lats, lons), grid(wind_lats, wind_lons)


def planned_calls(
    requests: Iterable[tuple[Domain, dt.datetime, dt.datetime]],
    block_days: int,
    epoch: dt.date,
) -> dict[str, int]:
    marine: set[tuple[dt.date, str, str]] = set()
    wind: set[tuple[dt.date, str, str]] = set()
    for domain, start, end in requests:
        marine_points, wind_points = domain_points(domain)
        for block in block_starts(start.date(), end.date(), block_days, epoch):
            marine.update((block, *point) for point in marine_points)
            wind.update((block, *point) for point in wind_points)
    return {"marine": len(marine), "wind": len(wind), "total": len(marine) + len(wind)}
