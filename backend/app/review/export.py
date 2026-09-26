from __future__ import annotations

import csv
import io
from typing import Any

from shapely.geometry import shape

CSV_COLUMNS = [
    "source",
    "review_id",
    "created_at",
    "analysis_id",
    "zone_id",
    "aoi_id",
    "scene_id",
    "date",
    "label",
    "label_title",
    "confidence",
    "comment",
    "reviewer",
    "probability_max",
    "probability_mean",
    "threshold",
    "model_fingerprint",
    "pixels",
    "area_km2",
    "longitude",
    "latitude",
    "geometry_wkt",
]
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
TEXT_COLUMNS = ("comment", "reviewer")


def _geometry(record: dict[str, Any]):
    try:
        return shape(record["geometry"]) if record.get("geometry") else None
    except (KeyError, TypeError, ValueError):
        return None


def _text(value: Any) -> Any:
    if isinstance(value, str) and value.startswith(FORMULA_PREFIXES):
        return "'" + value
    return value


def to_geojson(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": record["id"],
                "geometry": record.get("geometry"),
                "properties": {key: value for key, value in record.items() if key != "geometry"},
            }
            for record in records
        ],
    }


def to_csv(records: list[dict[str, Any]]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for record in records:
        geometry = _geometry(record)
        centroid = record.get("centroid") or (
            [round(geometry.centroid.x, 6), round(geometry.centroid.y, 6)] if geometry else None
        )
        row = {
            **{column: record.get(column) for column in CSV_COLUMNS},
            "review_id": record["id"],
            "longitude": centroid[0] if centroid else None,
            "latitude": centroid[1] if centroid else None,
            "geometry_wkt": geometry.wkt if geometry else None,
        }
        for column in TEXT_COLUMNS:
            row[column] = _text(row[column])
        writer.writerow({key: "" if value is None else value for key, value in row.items()})
    return buffer.getvalue()
