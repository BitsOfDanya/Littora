from __future__ import annotations

import csv
import io
from typing import Any

from app.analysis.statuses import ValueKind

CSV_COLUMNS = [
    "feature",
    "id",
    "value_kind",
    "status",
    "value",
    "unit",
    "lower",
    "upper",
    "target",
    "measurement_profile",
    "date",
    "scene_id",
    "longitude",
    "latitude",
    "note",
]


def _area_properties(result: dict[str, Any]) -> dict[str, Any]:
    scene = result.get("scene") or {}
    quality = result.get("quality") or {}
    concentration = result["concentration"]
    return {
        "feature": "request_area",
        "analysis_id": result["id"],
        "value_kind": ValueKind.REQUEST_AREA.value,
        "aoi_id": result["request"].get("aoi_id"),
        "aoi_name": result["request"].get("aoi_name"),
        "request_date": result["request"]["date"],
        "window_days": result["request"]["window_days"],
        "target": result["target"]["key"],
        "target_title": result["target"]["title"],
        "unit": result["target"]["unit"],
        "scene_id": scene.get("id"),
        "platform": scene.get("platform"),
        "acquired_at": scene.get("acquired_at"),
        "tile_cloud": scene.get("cloud_cover"),
        "quality_water": quality.get("water"),
        "quality_cloud": quality.get("cloud"),
        "quality_shadow": quality.get("shadow"),
        "quality_nodata": quality.get("nodata"),
        "quality_bright_water": quality.get("bright_water"),
        "quality_usable": quality.get("usable"),
        "status": result["status"]["status"],
        "status_label": result["status"]["label"],
        "detection_status": result["detection"]["status"],
        "detection_reason": result["detection"]["reason"],
        "detector": result["detection"]["model"],
        "concentration_status": concentration["status"],
        "concentration_reason": concentration["reason"],
        "concentration_model": concentration["model"],
        "concentration": concentration["value"],
        "concentration_lower": concentration["lower"],
        "concentration_upper": concentration["upper"],
        "pipeline_version": result["pipeline_version"],
        "computed_at": result["computed_at"],
    }


def to_geojson(result: dict[str, Any]) -> dict[str, Any]:
    features = [
        {
            "type": "Feature",
            "id": f"area-{result['id']}",
            "geometry": result["area"],
            "properties": _area_properties(result),
        }
    ]
    for index, zone in enumerate(result["detection"].get("zones", []), start=1):
        features.append(
            {
                "type": "Feature",
                "id": zone.get("id", f"zone-{index}"),
                "geometry": zone.get("geometry"),
                "properties": {
                    **{k: v for k, v in zone.items() if k != "geometry"},
                    "feature": "zone",
                    "value_kind": ValueKind.MODEL_ESTIMATE.value,
                },
            }
        )
    for observation in result.get("observations", []):
        features.append(
            {
                "type": "Feature",
                "id": observation["id"],
                "geometry": observation["geometry"],
                "properties": {**observation["properties"], "feature": "field_observation"},
            }
        )
    return {"type": "FeatureCollection", "features": features}


def _representative(geometry: dict[str, Any] | None) -> tuple[float | None, float | None]:
    if not geometry:
        return None, None
    coordinates = geometry.get("coordinates")
    kind = geometry.get("type")
    if kind == "Point":
        points = [coordinates]
    elif kind == "LineString":
        points = coordinates
    elif kind == "Polygon" and coordinates:
        points = coordinates[0][:-1] or coordinates[0]
    else:
        return None, None
    if not points:
        return None, None
    lon = sum(point[0] for point in points) / len(points)
    lat = sum(point[1] for point in points) / len(points)
    return round(lon, 6), round(lat, 6)


def _zone_note(zone: dict[str, Any]) -> str:
    parts = [flag["label"] for flag in zone.get("flags") or []]
    stability = zone.get("stability")
    if stability:
        agreement, views = stability["agreement"], stability["views"]
        parts.append(f"согласие поворотов {agreement:.2f}, видов {views}")
    return "; ".join(parts)


def to_csv(result: dict[str, Any]) -> str:
    rows = []
    area = _area_properties(result)
    lon, lat = _representative(result["area"])
    rows.append(
        {
            "feature": "request_area",
            "id": result["id"],
            "value_kind": ValueKind.REQUEST_AREA.value,
            "status": area["status_label"],
            "value": area["concentration"],
            "unit": area["unit"],
            "lower": area["concentration_lower"],
            "upper": area["concentration_upper"],
            "target": area["target"],
            "measurement_profile": "",
            "date": area["acquired_at"] or area["request_date"],
            "scene_id": area["scene_id"],
            "longitude": lon,
            "latitude": lat,
            "note": f"{result['detection']['reason']}; {result['concentration']['reason']}",
        }
    )
    for index, zone in enumerate(result["detection"].get("zones", []), start=1):
        zone_lon, zone_lat = _representative(zone.get("geometry"))
        rows.append(
            {
                "feature": "zone",
                "id": zone.get("id", f"zone-{index}"),
                "value_kind": ValueKind.MODEL_ESTIMATE.value,
                "status": zone.get("status_label", ""),
                "value": zone.get("concentration"),
                "unit": area["unit"],
                "lower": zone.get("lower"),
                "upper": zone.get("upper"),
                "target": area["target"],
                "measurement_profile": "",
                "date": area["acquired_at"],
                "scene_id": area["scene_id"],
                "longitude": zone_lon,
                "latitude": zone_lat,
                "note": _zone_note(zone),
            }
        )
    for observation in result.get("observations", []):
        props = observation["properties"]
        obs_lon, obs_lat = _representative(observation["geometry"])
        rows.append(
            {
                "feature": "field_observation",
                "id": props["sample_id"],
                "value_kind": ValueKind.MEASUREMENT.value,
                "status": "измерение",
                "value": props["concentration"],
                "unit": props["unit"],
                "lower": "",
                "upper": "",
                "target": props["target_key"] or "",
                "measurement_profile": props["measurement_profile"],
                "date": props["date"],
                "scene_id": props.get("pair_scene_id") or "",
                "longitude": obs_lon,
                "latitude": obs_lat,
                "note": f"{props['reason']}; сдвиг {props.get('delta_days')} сут",
            }
        )
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: "" if value is None else value for key, value in row.items()})
    return buffer.getvalue()
