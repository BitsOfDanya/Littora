from __future__ import annotations

import datetime as dt

import pandas as pd

from app.case.data import load_case_data
from app.case.selection import Selection
from littora_ml.common.paths import CASE_CONFIG, DATA

COLUMNS = [
    "sample_id",
    "event_id",
    "source_id",
    "measurement_profile",
    "target_key",
    "latitude",
    "longitude",
    "date",
    "observed_at",
    "concentration",
]


def modeling_table() -> pd.DataFrame:
    return selection_table(load_case_data(CASE_CONFIG, DATA).selections)


def selection_table(selections: list[Selection]) -> pd.DataFrame:
    rows = []
    for selection in selections:
        if not selection.accepted:
            continue
        record = selection.record
        lon, lat = record.position
        observed = record.observed_at
        rows.append(
            {
                "sample_id": record.sample_id,
                "event_id": record.event_id,
                "source_id": record.source_id,
                "measurement_profile": record.profile,
                "target_key": selection.target_key,
                "latitude": lat,
                "longitude": lon,
                "date": record.date.isoformat(),
                "observed_at": observed.isoformat() if observed else None,
                "concentration": record.published_concentration,
            }
        )
    table = pd.DataFrame(rows, columns=COLUMNS).sort_values("sample_id").reset_index(drop=True)
    if table["event_id"].duplicated().any():
        raise ValueError("one accepted record per event is expected")
    return table


def survey_day_groups(table: pd.DataFrame) -> pd.Series:
    return table["measurement_profile"] + ":" + table["date"]


def reference_time(row: pd.Series) -> dt.datetime:
    observed = row["observed_at"]
    if isinstance(observed, str) and observed:
        return dt.datetime.fromisoformat(observed)
    return dt.datetime.combine(dt.date.fromisoformat(row["date"]), dt.time(12), tzinfo=dt.UTC)
