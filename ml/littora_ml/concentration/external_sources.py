from __future__ import annotations

import csv
import datetime as dt
from collections.abc import Iterable
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from app.case.config import load_case_config
from app.case.records import load_records
from app.case.selection import select_records
from littora_ml.common.paths import CASE_CONFIG, CASE_CSV, EXTERNAL, PROCESSED
from littora_ml.concentration.dataset import selection_table

PROFILE = "S4_visual_GT2_5"
BURGAS_KEY = "seanoe-burgas"
BURGAS_FILE = EXTERNAL / BURGAS_KEY / "107709.txt"
BURGAS_SOURCE = "S4X_BG_BURGAS_SEANOE"
BURGAS_URL = "https://www.seanoe.org/data/00872/98351/data/107709.txt"
BURGAS_LENGTH_KM = 2.25
BURGAS_WIDTH_M = 6.0
BURGAS_AREA_KM2 = BURGAS_LENGTH_KM * BURGAS_WIDTH_M / 1000
BURGAS_DOUBLE_AREA_KM2 = 2 * BURGAS_AREA_KM2
BURGAS_DOUBLE_FLAG = "sampled_area_0027_inferred_from_density_quantum"
BURGAS_ZONE = ZoneInfo("Europe/Sofia")
INTEGER_TOLERANCE = 0.05
EMBLAS_KEY = "emblas2016-russia"
EMBLAS_FILE = EXTERNAL / EMBLAS_KEY / "emblas2016_russia_transects_derived.csv"
EMBLAS_SOURCE = "S4X_RU_EMBLAS2016"
EMBLAS_ZONE = ZoneInfo("Europe/Moscow")
EMBLAS_REPORT = (
    "https://emblasproject.org/wp-content/uploads/2022/03/"
    "EMBLAS-II_NPMS_JOSS_2016_ScReport_ISBN-978-617-7953-60-8-2.pdf"
)
CAMPAIGN_GAP_DAYS = 7
OUTPUT = PROCESSED / "concentration" / "external"
BURGAS_CSV = OUTPUT / "seanoe_burgas.csv"
EMBLAS_CSV = OUTPUT / "emblas2016_russia.csv"

TIME_FIELD = "yyyy-mm-ddThh:mm:ss"
LON_FIELD = "Longitude [degrees_east]"
LAT_FIELD = "Latitude [degrees_north]"
DENSITY_FIELD = "Total_Items [items.km^2]"
CARRIED = ("Cruise", "Station", "Type", TIME_FIELD, LON_FIELD, LAT_FIELD)


def case_columns(path: Path = CASE_CSV) -> list[str]:
    with path.open(encoding="utf-8", newline="") as handle:
        return next(csv.reader(handle))


def read_odv(lines: Iterable[str]) -> list[dict[str, str]]:
    body = [line.rstrip("\r\n") for line in lines if line.strip() and not line.startswith("//")]
    header = body[0].split("\t")
    rows, previous = [], {}
    for line in body[1:]:
        values = line.split("\t")
        row = {}
        for name, value in zip(header, values, strict=False):
            if name not in row:
                row[name] = value.strip()
        for name in CARRIED:
            if not row.get(name):
                row[name] = previous.get(name, "")
        previous = row
        rows.append(row)
    return rows


def campaign_labels(dates: pd.Series, gap_days: int = CAMPAIGN_GAP_DAYS) -> pd.Series:
    days = sorted({dt.date.fromisoformat(str(value)) for value in dates})
    label_of, current = {}, None
    for index, day in enumerate(days):
        if index == 0 or (day - days[index - 1]).days > gap_days:
            current = day.strftime("%Y-%m")
        label_of[day.isoformat()] = current
    return pd.Series([label_of[str(value)] for value in dates], index=dates.index)


def _blank(columns: list[str]) -> dict[str, str]:
    return dict.fromkeys(columns, "")


def _number(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".")


def _whole(densities: Iterable[float], area: float) -> bool:
    return all(abs(value * area - round(value * area)) <= INTEGER_TOLERANCE for value in densities)


def campaign_areas(densities: pd.Series, campaigns: pd.Series) -> dict[str, float | None]:
    areas: dict[str, float | None] = {}
    for campaign, values in densities.groupby(campaigns):
        if _whole(values, BURGAS_AREA_KM2):
            areas[str(campaign)] = BURGAS_AREA_KM2
        elif _whole(values, BURGAS_DOUBLE_AREA_KM2):
            areas[str(campaign)] = BURGAS_DOUBLE_AREA_KM2
        else:
            areas[str(campaign)] = None
    return areas


def _burgas_area(area: float | None) -> dict[str, str]:
    if area == BURGAS_AREA_KM2:
        return {
            "transect_length_km": _number(BURGAS_LENGTH_KM),
            "transect_width_m": _number(BURGAS_WIDTH_M),
            "sampled_area_km2": _number(area),
            "calculation_method": (
                "published density retained; items = round(density x 0.0135 km2), "
                "2.25 km x 6 m (Bobchev et al. 2024)"
            ),
        }
    if area == BURGAS_DOUBLE_AREA_KM2:
        return {
            "sampled_area_km2": _number(area),
            "calculation_method": (
                "published density retained; campaign densities are multiples of "
                "37.04 = 1/0.027, so sampled area 0.027 km2 (twice 2.25 km x 6 m) is inferred; "
                "items = round(density x 0.027 km2); length/width split unknown"
            ),
        }
    return {
        "calculation_method": (
            "published density retained; density x 0.0135 or 0.027 km2 is not whole "
            "across the campaign, items left empty"
        ),
    }


def burgas_rows(lines: Iterable[str], columns: list[str] | None = None) -> pd.DataFrame:
    columns = columns or case_columns()
    parsed = read_odv(lines)
    moments = []
    for row in parsed:
        local = dt.datetime.fromisoformat(row[TIME_FIELD]).replace(tzinfo=BURGAS_ZONE)
        moments.append((local, local.astimezone(dt.UTC)))
    densities = pd.Series([float(row[DENSITY_FIELD]) for row in parsed], dtype=float)
    campaigns = campaign_labels(pd.Series([utc.date().isoformat() for _, utc in moments]))
    areas = campaign_areas(densities, campaigns)
    records = []
    for number, (row, (local, utc), density, campaign) in enumerate(
        zip(parsed, moments, densities, campaigns, strict=True), start=1
    ):
        area = areas[campaign]
        items = round(density * area) if area else None
        flags = [
            "all_litter_not_plastic",
            "time_assumed_local_eet_eest_converted_to_utc",
            "position_role_unknown_start_or_middle",
        ]
        if area == BURGAS_DOUBLE_AREA_KM2:
            flags.append(BURGAS_DOUBLE_FLAG)
        if area is None:
            flags.append("items_not_integer_density_times_area")
        station = row["Station"]
        record = _blank(columns)
        record.update(
            {
                "sample_id": f"BGS-{number:04d}",
                "source_id": BURGAS_SOURCE,
                "source_short": (
                    "Floating marine litter monitoring in Burgas Bay 2021-2023, "
                    "IBER-BAS BRIDGE-BS WP5, SEANOE"
                ),
                "source_doi": "10.17882/98351",
                "source_license": "CC BY 4.0 (SEANOE metadata; page text says upon request)",
                "region": "Black Sea (Bulgarian waters, Burgas Bay)",
                "sea_area": "Black Sea",
                "record_type": "transect_density",
                "sampling_method": (
                    "boat-based visual transect (6 m strip, one observer at 2.2 m, 12 km/h), "
                    "floating macro litter >2.5 cm, MSFD protocol"
                ),
                "platform": "small boat",
                "latitude": row[LAT_FIELD],
                "longitude": row[LON_FIELD],
                "date_utc": utc.date().isoformat(),
                "time_start_utc": utc.strftime("%H:%M:%S"),
                "datetime_start_iso": utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "litter_category": "total floating macro litter (>2.5 cm)",
                "litter_item_type": "total floating macro litter",
                "material": "mixed (predominantly plastic)",
                "size_class": ">2.5 cm (macro)",
                "items_count": "" if items is None else str(items),
                "concentration_value_orig": row[DENSITY_FIELD],
                "concentration_unit_orig": "items km-2",
                "concentration_items_km2": _number(density),
                "concentration_basis": "transect",
                **_burgas_area(area),
                "optical_missions_available": "not_verified",
                "notes": (
                    f"BRIDGE-BS WP5, transect {station}, campaign {campaign}; file time "
                    f"{row[TIME_FIELD]} assumed local {local.tzname()}"
                ),
                "source_event_id": f"{row['Cruise']}:{station}:{row[TIME_FIELD]}",
                "event_id": f"S4X:BURGAS:{utc.date().isoformat()}:{station}",
                "position_role": "published_transect_point_role_unknown",
                "target_scope": "all_litter",
                "quality_flags": ";".join(flags),
                "provenance": BURGAS_URL,
                "measurement_profile": PROFILE,
                "reported_concentration_items_km2": _number(density),
                "density_numerator_items": "" if items is None else str(items),
                "source_row_refs": f"107709.txt data row {number}",
            }
        )
        records.append(record)
    return pd.DataFrame(records, columns=columns)


def burgas_items(path: Path = BURGAS_CSV) -> dict[str, object]:
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    campaigns = campaign_labels(frame["date_utc"])
    filled = frame["density_numerator_items"] != ""
    items = pd.to_numeric(frame.loc[filled, "density_numerator_items"])
    area = frame["sampled_area_km2"].replace("", "unknown")
    return {
        "rows": len(frame),
        "rows_with_items": int(filled.sum()),
        "rows_without_items": int((~filled).sum()),
        "sum_items": int(items.sum()),
        "area_km2_by_campaign": {
            str(key): "; ".join(sorted(value.unique())) for key, value in area.groupby(campaigns)
        },
    }


def _moment(day: str, clock: str) -> dt.datetime:
    return dt.datetime.combine(dt.date.fromisoformat(day), dt.time.fromisoformat(clock))


def emblas_rows(frame: pd.DataFrame, columns: list[str] | None = None) -> pd.DataFrame:
    columns = columns or case_columns()
    records = []
    for number, row in enumerate(frame.itertuples(index=False), start=1):
        flags = [
            "all_litter_not_plastic",
            "reconstructed_from_report_tables",
            "station_mapping_inferred",
            "external_test_only",
        ]
        day = str(row.date)
        start = end = ""
        if "/" in day:
            day = day.split("/")[0]
            flags.append("date_range_first_day_used")
        window = row.window_local if isinstance(row.window_local, str) else ""
        if window:
            first, last = (part.strip() for part in window.split("-"))
            begin = _moment(day, first).replace(tzinfo=EMBLAS_ZONE).astimezone(dt.UTC)
            finish = _moment(day, last).replace(tzinfo=EMBLAS_ZONE).astimezone(dt.UTC)
            start, end = begin.strftime("%H:%M:%S"), finish.strftime("%H:%M:%S")
            flags.append("time_window_assumed_local_msk_converted_to_utc")
        width_m = float(row.width_km) * 1000
        if width_m >= 50:
            flags.append("wide_strip_small_items_underdetected")
        label = str(row.transect).split(" ")[0]
        record = _blank(columns)
        record.update(
            {
                "sample_id": f"EMB-{number:04d}",
                "source_id": EMBLAS_SOURCE,
                "source_short": str(row.survey),
                "source_license": "not stated",
                "region": "Black Sea (Russian waters)",
                "sea_area": "Black Sea",
                "record_type": "transect_density",
                "sampling_method": (
                    f"ship-based visual transect ({width_m:.0f} m strip), floating macro litter "
                    ">2.5 cm, JRC categories"
                ),
                "platform": str(row.survey).split(", ")[-1],
                "latitude": _number(row.lat_mid),
                "longitude": _number(row.lon_mid),
                "lat_start": _number(row.lat_start),
                "lon_start": _number(row.lon_start),
                "lat_end": _number(row.lat_end),
                "lon_end": _number(row.lon_end),
                "date_utc": day,
                "time_start_utc": start,
                "time_end_utc": end,
                "datetime_start_iso": f"{day}T{start}Z" if start else day,
                "litter_category": "total floating macro litter (>2.5 cm)",
                "litter_item_type": "total floating macro litter",
                "material": "mixed (predominantly plastic)",
                "size_class": ">2.5 cm (macro)",
                "items_count": str(int(row.items)),
                "concentration_value_orig": _number(row.density_items_km2),
                "concentration_unit_orig": "items km-2",
                "concentration_items_km2": _number(row.density_items_km2),
                "concentration_basis": "transect (derived midpoint)",
                "transect_length_km": _number(row.length_km),
                "transect_width_m": _number(width_m),
                "sampled_area_km2": _number(row.area_km2),
                "optical_missions_available": "not_verified",
                "notes": f"{row.transect}; external test only, never used for training",
                "source_event_id": str(row.transect),
                "event_id": f"S4X:EMBLAS2016:{label}",
                "position_role": "derived_transect_midpoint",
                "target_scope": "all_litter",
                "quality_flags": ";".join(flags),
                "provenance": (
                    f"reconstructed from report tables; station mapping inferred; {EMBLAS_REPORT}"
                ),
                "calculation_method": "published density, items and area from report table",
                "measurement_profile": PROFILE,
                "reported_concentration_items_km2": _number(row.density_items_km2),
                "density_numerator_items": str(int(row.items)),
                "source_row_refs": "Table VII.2.7; Tables 6-7, 9",
            }
        )
        records.append(record)
    return pd.DataFrame(records, columns=columns)


def write_case_csv(frame: pd.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    return path


def model_rows(path: Path) -> tuple[pd.DataFrame, dict]:
    records = load_records(path)
    selections = select_records(records, load_case_config(CASE_CONFIG))
    checks: dict[str, int] = {}
    reasons: dict[str, int] = {}
    for selection in selections:
        checks[selection.check.status.value] = checks.get(selection.check.status.value, 0) + 1
        reasons[selection.reason.value] = reasons.get(selection.reason.value, 0) + 1
    return selection_table(selections), {"selection": reasons, "concentration_check": checks}


def prepare_sources() -> dict[str, Path]:
    paths = {}
    if BURGAS_FILE.exists():
        with BURGAS_FILE.open(encoding="utf-8") as handle:
            paths["burgas"] = write_case_csv(burgas_rows(handle), BURGAS_CSV)
    if EMBLAS_FILE.exists():
        frame = emblas_rows(pd.read_csv(EMBLAS_FILE))
        paths["emblas"] = write_case_csv(frame, EMBLAS_CSV)
    return paths
