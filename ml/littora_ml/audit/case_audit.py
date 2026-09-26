from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from littora_ml.common.io import file_sha256, write_json
from littora_ml.common.paths import CASE_CSV, REGISTRY, REPORTS

TARGET = "concentration_items_km2"
DENSITY = "transect_density"
FORBIDDEN_PATTERNS = (r"^concentration_", r"^reported_", r"^parent_")
FORBIDDEN_NAMES = (
    "items_count",
    "density_numerator_items",
    "source_object_filtered_items",
    "source_reported_total_items",
    "zero_scope",
)
IDENTIFIERS = (
    "sample_id",
    "event_id",
    "source_event_id",
    "source_row_refs",
    "source_short",
    "source_doi",
    "provenance",
)
SURVEY_ONLY = (
    "sea_state_beaufort",
    "wind_speed_kn",
    "transect_length_km",
    "transect_width_m",
    "sampled_area_km2",
    "platform",
    "time_start_utc",
    "time_end_utc",
    "datetime_start_iso",
    "lat_start",
    "lon_start",
    "lat_end",
    "lon_end",
)
PROFILE_DESCRIPTORS = (
    "source_id",
    "source_license",
    "region",
    "sea_area",
    "record_type",
    "sampling_method",
    "litter_category",
    "litter_item_type",
    "material",
    "size_class",
    "concentration_basis",
    "source_category_code",
    "position_role",
    "target_scope",
    "quality_flags",
    "calculation_method",
    "measurement_profile",
    "notes",
    "optical_missions_available",
    "missions_calendar_eligible",
)
LOCATION_TIME = ("latitude", "longitude", "date_utc")


def load_case(path: Path = CASE_CSV) -> pd.DataFrame:
    return pd.read_csv(path, dtype={"time_start_utc": str, "time_end_utc": str})


def _quantiles(values: pd.Series) -> dict[str, float] | None:
    clean = values.dropna()
    if clean.empty:
        return None
    levels = {"min": 0, "q10": 0.1, "q25": 0.25, "median": 0.5, "q75": 0.75, "q90": 0.9, "max": 1}
    return {name: round(float(clean.quantile(level)), 3) for name, level in levels.items()}


def _flags(series: pd.Series) -> dict[str, int]:
    exploded = series.fillna("").str.split(";").explode()
    counts = exploded[exploded != ""].value_counts()
    return {str(key): int(value) for key, value in counts.items()}


def _bbox(frame: pd.DataFrame) -> list[float]:
    return [
        round(float(frame.longitude.min()), 4),
        round(float(frame.latitude.min()), 4),
        round(float(frame.longitude.max()), 4),
        round(float(frame.latitude.max()), 4),
    ]


def haversine_km(lat1, lon1, lat2, lon2) -> np.ndarray:
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = (
        np.sin((lat2 - lat1) / 2) ** 2
        + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * 6371.0088 * np.arcsin(np.sqrt(a))


def spatial_clusters(frame: pd.DataFrame, radius_km: float) -> int:
    points = frame[["latitude", "longitude"]].to_numpy()
    parent = list(range(len(points)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for i in range(len(points)):
        distances = haversine_km(points[i, 0], points[i, 1], points[:, 0], points[:, 1])
        for j in np.nonzero(distances <= radius_km)[0]:
            root_i, root_j = find(i), find(int(j))
            if root_i != root_j:
                parent[root_j] = root_i
    return len({find(index) for index in range(len(points))})


def nearest_neighbour_km(frame: pd.DataFrame) -> dict[str, float] | None:
    points = frame[["latitude", "longitude"]].to_numpy()
    if len(points) < 2:
        return None
    nearest = []
    for i in range(len(points)):
        distances = haversine_km(points[i, 0], points[i, 1], points[:, 0], points[:, 1])
        distances[i] = np.inf
        nearest.append(float(distances.min()))
    return _quantiles(pd.Series(nearest))


def source_summary(frame: pd.DataFrame) -> list[dict[str, Any]]:
    rows = []
    for source, group in frame.groupby("source_id"):
        rows.append(
            {
                "source_id": source,
                "rows": len(group),
                "events": group.event_id.nunique(),
                "record_types": group.record_type.value_counts().to_dict(),
                "profiles": group.measurement_profile.value_counts().to_dict(),
                "target_scopes": group.target_scope.value_counts().to_dict(),
                "methods": group.sampling_method.value_counts().to_dict(),
                "size_classes": group.size_class.value_counts().to_dict(),
                "license": sorted(group.source_license.unique()),
                "dates": [group.date_utc.min(), group.date_utc.max()],
                "survey_days": group.date_utc.nunique(),
                "bbox": _bbox(group),
            }
        )
    return rows


def profile_summary(frame: pd.DataFrame, pairs: dict[str, dict]) -> list[dict[str, Any]]:
    density = frame[frame.record_type == DENSITY]
    rows = []
    keys = ["source_id", "measurement_profile", "target_scope", "material", "size_class"]
    for key, group in density.groupby(keys):
        values = group[TARGET]
        events = group.event_id.unique()
        decisions: dict[str, int] = {}
        for event in events:
            decision = pairs.get(event, {}).get("reason_code", "not_in_registry")
            decisions[decision] = decisions.get(decision, 0) + 1
        rows.append(
            {
                **dict(zip(keys, key, strict=True)),
                "rows": len(group),
                "events": len(events),
                "rows_per_event": round(len(group) / len(events), 3),
                "concentration_present": int(values.notna().sum()),
                "concentration_missing": int(values.isna().sum()),
                "zeros": int((values == 0).sum()),
                "concentration_items_km2": _quantiles(values),
                "mean": round(float(values.mean()), 3) if values.notna().any() else None,
                "coefficient_of_variation": round(float(values.std() / values.mean()), 3)
                if values.notna().sum() > 1 and values.mean()
                else None,
                "sampled_area_km2": _quantiles(group.sampled_area_km2),
                "dates": [group.date_utc.min(), group.date_utc.max()],
                "survey_days": group.date_utc.nunique(),
                "months": sorted(group.date_utc.str[:7].unique()),
                "bbox": _bbox(group),
                "clusters_25km": spatial_clusters(group, 25),
                "clusters_100km": spatial_clusters(group, 100),
                "nearest_neighbour_km": nearest_neighbour_km(group),
                "time_known": int(group.time_start_utc.notna().sum()),
                "position_roles": group.position_role.value_counts().to_dict(),
                "quality_flags": _flags(group.quality_flags),
                "calculation_methods": group.calculation_method.value_counts().to_dict(),
                "satellite_pairing": dict(sorted(decisions.items())),
            }
        )
    return rows


def _numeric_evidence(frame: pd.DataFrame, column: str) -> dict[str, Any] | None:
    rows = frame[frame[TARGET].notna() & frame[column].notna()]
    if len(rows) < 5 or not pd.api.types.is_numeric_dtype(rows[column]):
        return None
    target = rows[TARGET].to_numpy(dtype=float)
    values = rows[column].to_numpy(dtype=float)
    scale = np.maximum(np.abs(target), 1e-9)
    equal = float(np.mean(np.abs(values - target) <= 1e-6 * scale + 1e-9))
    rho = spearmanr(values, target).statistic if np.ptp(values) > 0 else 0.0
    return {"rows": len(rows), "equal_share": round(equal, 3), "spearman": round(float(rho), 3)}


def _ratio_evidence(frame: pd.DataFrame, numerator: str) -> dict[str, Any] | None:
    rows = frame[frame[TARGET].notna() & frame[numerator].notna() & frame.sampled_area_km2.gt(0)]
    if len(rows) < 5:
        return None
    ratio = rows[numerator] / rows.sampled_area_km2
    relative = (ratio - rows[TARGET]).abs() / rows[TARGET].abs().clip(lower=1e-9)
    return {
        "rows": len(rows),
        "reproduces_target_within_1pct": round(float((relative <= 0.01).mean()), 3),
    }


def leakage_audit(frame: pd.DataFrame) -> dict[str, Any]:
    density = frame[frame.record_type == DENSITY]
    columns: dict[str, dict[str, Any]] = {}
    for column in frame.columns:
        evidence = _numeric_evidence(density, column) if column != TARGET else None
        by_rule = column in FORBIDDEN_NAMES or any(
            re.search(pattern, column) for pattern in FORBIDDEN_PATTERNS
        )
        by_data = bool(
            evidence and (evidence["equal_share"] >= 0.5 or abs(evidence["spearman"]) >= 0.9)
        )
        if column == TARGET:
            role = "target"
        elif by_rule or by_data:
            role = "forbidden_leakage"
        elif column in IDENTIFIERS:
            role = "identifier"
        elif column in SURVEY_ONLY:
            role = "survey_only"
        elif column in PROFILE_DESCRIPTORS:
            role = "profile_descriptor"
        elif column in LOCATION_TIME:
            role = "allowed_predictor"
        else:
            role = "unclassified"
        entry: dict[str, Any] = {"role": role}
        if evidence:
            entry["evidence"] = evidence
        if by_rule:
            entry["rule"] = "name"
        if by_data and not by_rule:
            entry["rule"] = "data"
        columns[column] = entry
    for numerator in ("density_numerator_items", "items_count", "source_reported_total_items"):
        ratio = _ratio_evidence(density, numerator)
        if ratio:
            columns[numerator].setdefault("evidence", {})["ratio_to_area"] = ratio
    roles: dict[str, list[str]] = {}
    for column, entry in columns.items():
        roles.setdefault(entry["role"], []).append(column)
    return {"target": TARGET, "roles": roles, "columns": columns}


def pair_index() -> dict[str, dict]:
    path = REGISTRY / "events.geojson"
    if not path.exists():
        return {}
    events = json.loads(path.read_text(encoding="utf-8"))
    return {
        feature["properties"]["event_id"]: feature["properties"] for feature in events["features"]
    }


def run_audit(csv_path: Path = CASE_CSV, out_dir: Path = REPORTS / "audit") -> dict[str, Any]:
    frame = load_case(csv_path)
    pairs = pair_index()
    density = frame[frame.record_type == DENSITY]
    audit = {
        "dataset": {
            "file": csv_path.name,
            "sha256": file_sha256(csv_path),
            "rows": len(frame),
            "columns": len(frame.columns),
            "events": frame.event_id.nunique(),
            "sources": frame.source_id.nunique(),
        },
        "record_types": frame.record_type.value_counts().to_dict(),
        "target_scopes": frame.target_scope.value_counts().to_dict(),
        "measurement_profiles": frame.measurement_profile.value_counts().to_dict(),
        "size_classes": frame.size_class.value_counts().to_dict(),
        "materials": frame.material.value_counts().to_dict(),
        "sampling_methods": frame.sampling_method.value_counts().to_dict(),
        "quality_flags": _flags(frame.quality_flags),
        "zero_scope": frame.zero_scope.dropna().value_counts().to_dict(),
        "concentration": {
            "density_rows": len(density),
            "present": int(density[TARGET].notna().sum()),
            "missing": int(density[TARGET].isna().sum()),
            "zeros": int((density[TARGET] == 0).sum()),
            "item_rows_with_concentration": int(
                frame[frame.record_type != DENSITY][TARGET].notna().sum()
            ),
        },
        "events_per_source": frame.groupby("source_id").event_id.nunique().to_dict(),
        "rows_per_event": _quantiles(frame.groupby("event_id").size()),
        "sources": source_summary(frame),
        "profiles": profile_summary(frame, pairs),
        "leakage": leakage_audit(frame),
    }
    write_json(out_dir / "case_audit.json", audit)
    table = pd.DataFrame(
        [
            {
                key: value
                for key, value in row.items()
                if not isinstance(value, dict | list) or key in ("dates",)
            }
            | {
                "median": (row["concentration_items_km2"] or {}).get("median"),
                "q90": (row["concentration_items_km2"] or {}).get("q90"),
                "dates": " .. ".join(row["dates"]),
            }
            for row in audit["profiles"]
        ]
    )
    table.to_csv(out_dir / "profiles.csv", index=False)
    return audit
