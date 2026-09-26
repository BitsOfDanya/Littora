from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.features import geometry_mask
from rasterio.warp import transform_geom

from littora_ml.common.io import file_sha256, write_json
from littora_ml.common.paths import REPORTS
from littora_ml.detector.predict import predict_scene

COLLECTION = "sentinel-2-l2a"
MARGIN_DEGREES = 0.005
PIXEL_KM2 = 1e-4


def _groups(labels: dict[str, Any]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for feature in labels["features"]:
        properties = feature["properties"]
        groups[(properties["aoi"], properties["scene_id"])].append(feature)
    return dict(sorted(groups.items()))


def _bbox(features: list[dict[str, Any]]) -> tuple[float, float, float, float]:
    points = np.array(
        [
            point
            for feature in features
            for ring in (
                [feature["geometry"]["coordinates"]]
                if feature["geometry"]["type"] == "Polygon"
                else feature["geometry"]["coordinates"]
            )
            for point in ring[0]
        ]
    )
    west, south = points.min(axis=0) - MARGIN_DEGREES
    east, north = points.max(axis=0) + MARGIN_DEGREES
    return float(west), float(south), float(east), float(north)


def _polygon_row(feature, probability, mask, dataset, threshold) -> dict[str, Any]:
    geometry = transform_geom("EPSG:4326", dataset.crs, feature["geometry"])
    inside = ~geometry_mask([geometry], probability.shape, dataset.transform, all_touched=False)
    pixels = int(inside.sum())
    alarms = int((mask & inside).sum())
    return {
        "aoi": feature["properties"]["aoi"],
        "scene_id": feature["properties"]["scene_id"],
        "class": feature["properties"]["class"],
        "pixels": pixels,
        "alarm_pixels": alarms,
        "max_probability": float(probability[inside].max()) if pixels else None,
        "any_alarm": bool(alarms),
        "threshold": threshold,
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_class: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row["pixels"]:
            by_class[row["class"]].append(row)
    summary = {}
    for name, members in sorted(by_class.items()):
        pixels = sum(row["pixels"] for row in members)
        alarms = sum(row["alarm_pixels"] for row in members)
        summary[name] = {
            "polygons": len(members),
            "pixels": pixels,
            "area_km2": round(pixels * PIXEL_KM2, 4),
            "alarm_pixels": alarms,
            "alarm_share": alarms / pixels,
            "polygons_with_alarm": sum(row["any_alarm"] for row in members),
            "median_max_probability": float(np.median([row["max_probability"] for row in members])),
        }
    return summary


def negatives_report(run: str, labels_path: Path) -> dict[str, Any]:
    labels = json.loads(labels_path.read_text())
    out_root = REPORTS / "predictions" / "scenes" / "negatives" / run
    rows, scenes = [], []
    for (aoi, scene_id), features in _groups(labels).items():
        bbox = _bbox(features)
        meta = predict_scene(run, COLLECTION, scene_id, bbox, out_root / aoi)
        with rasterio.open(out_root / aoi / "probability.tif") as dataset:
            probability = dataset.read(1)
            mask = probability >= meta["threshold"]
            rows.extend(
                _polygon_row(feature, probability, mask, dataset, meta["threshold"])
                for feature in features
            )
        scenes.append({"aoi": aoi, **meta})
    result = {
        "run": run,
        "labels_sha256": file_sha256(labels_path),
        "collection": COLLECTION,
        "definition": (
            "доля пикселей выше замороженного порога детектора внутри полигонов заведомо "
            "не мусора; порог и постобработка не подбирались на этих данных"
        ),
        "by_class": _summary(rows),
        "scenes": scenes,
        "polygons": rows,
    }
    name = f"black_sea_negatives__{run}.json"
    write_json(REPORTS / "metrics" / "detector" / "external" / name, result)
    return result
