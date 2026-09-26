from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import rasterio
from affine import Affine

from app.analysis.zones import mask_zones
from littora_ml.common.io import write_json
from littora_ml.detector.inference import TrainedDetector, run_postprocessing, run_threshold
from littora_ml.detector.postprocess import SCL_EXCLUDED, sea_mask
from littora_ml.satellite.scenes import get_item, read_bands
from littora_ml.satellite.sliding import sliding_scores


def predict_scene(
    run: str, collection: str, scene_id: str, bbox: tuple[float, float, float, float], out: Path
) -> dict:
    detector = TrainedDetector(run)
    _, tta = run_threshold(run)
    choice = run_postprocessing(run)
    threshold = choice["threshold"]
    item = get_item(collection, scene_id)
    image, scl, grid = read_bands(item, bbox)
    probability = sliding_scores(image, detector.scorer(tta))
    probability[image[1] == 0] = 0
    if choice.get("scl"):
        probability[np.isin(scl, SCL_EXCLUDED)] = 0
    probability[~sea_mask(scl)] = 0
    transform = Affine(*grid["transform"])
    mask = probability >= threshold
    out.mkdir(parents=True, exist_ok=True)
    profile = {
        "driver": "GTiff",
        "height": grid["height"],
        "width": grid["width"],
        "count": 1,
        "crs": grid["crs"],
        "transform": transform,
        "compress": "deflate",
    }
    with rasterio.open(out / "probability.tif", "w", dtype="float32", **profile) as dataset:
        dataset.write(probability.astype(np.float32), 1)
    with rasterio.open(out / "mask.tif", "w", dtype="uint8", **profile) as dataset:
        dataset.write(mask.astype(np.uint8), 1)
    zones = mask_zones(mask, probability, transform, grid["crs"], choice.get("min_pixels", 1))
    features = [
        {
            "type": "Feature",
            "id": zone["id"],
            "geometry": zone["geometry"],
            "properties": {k: v for k, v in zone.items() if k != "geometry"},
        }
        for zone in zones
    ]
    (out / "zones.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False)
    )
    meta = {
        "run": run,
        "scene_id": scene_id,
        "collection": collection,
        "bbox": list(bbox),
        "threshold": threshold,
        "tta": tta,
        "pixels": int(probability.size),
        "detected_pixels": int(mask.sum()),
        "zones": len(zones),
    }
    write_json(out / "meta.json", meta)
    return meta
