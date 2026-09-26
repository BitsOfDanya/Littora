from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from affine import Affine
from rasterio.features import geometry_mask
from rasterio.warp import transform_geom
from scipy.stats import spearmanr
from shapely.geometry import shape

from littora_ml.common.io import write_json
from littora_ml.common.paths import INTERIM, REGISTRY, REPORTS
from littora_ml.detector.features import spectral_indices
from littora_ml.satellite.scenes import get_item, read_bands
from littora_ml.satellite.sliding import sliding_scores

WATER = 6
MARGIN_DEG = 0.01


def accepted_pairs() -> list[dict[str, Any]]:
    summary = json.loads((REGISTRY / "summary.json").read_text(encoding="utf-8"))
    events = json.loads((REGISTRY / "events.geojson").read_text(encoding="utf-8"))
    geometry = {f["properties"]["event_id"]: f["geometry"] for f in events["features"]}
    return [pair | {"geometry": geometry[pair["event_id"]]} for pair in summary["accepted_pairs"]]


def window_bbox(pair: dict[str, Any]) -> tuple[float, float, float, float]:
    west, south, east, north = shape(pair["geometry"]).bounds
    return west - MARGIN_DEG, south - MARGIN_DEG, east + MARGIN_DEG, north + MARGIN_DEG


def window_cache(pair: dict[str, Any]) -> Path:
    key = {
        "collection": pair["collection"],
        "scene_id": pair["scene_id"],
        "bbox": [round(value, 7) for value in window_bbox(pair)],
        "radius_m": pair.get("footprint_radius_m"),
    }
    digest = hashlib.sha256(json.dumps(key, sort_keys=True).encode()).hexdigest()[:16]
    return INTERIM / "pairs" / f"{pair['event_id'].replace(':', '_')}_{digest}.npz"


def pair_window(pair: dict[str, Any]) -> dict[str, Any]:
    cache = window_cache(pair)
    if cache.exists():
        data = np.load(cache, allow_pickle=False)
        return {"image": data["image"], "scl": data["scl"], "grid": json.loads(str(data["grid"]))}
    bbox = window_bbox(pair)
    item = get_item(pair["collection"], pair["scene_id"])
    image, scl, grid = read_bands(item, bbox)
    cache.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(cache, image=image, scl=scl, grid=np.array(json.dumps(grid)))
    return {"image": image, "scl": scl, "grid": grid}


def footprint_mask(pair: dict[str, Any], grid: dict[str, Any]) -> np.ndarray:
    projected = transform_geom("EPSG:4326", grid["crs"], pair["geometry"])
    return geometry_mask(
        [projected],
        out_shape=(grid["height"], grid["width"]),
        transform=Affine(*grid["transform"]),
        invert=True,
    )


def pair_features(pair: dict[str, Any], scorer=None, threshold: float | None = None) -> dict:
    window = pair_window(pair)
    image, scl, grid = window["image"], window["scl"], window["grid"]
    inside = footprint_mask(pair, grid) & (scl == WATER) & (image[1] != 0)
    indices = spectral_indices(image)
    fdi, ndvi = indices[1][inside], indices[0][inside]
    row = {
        "event_id": pair["event_id"],
        "scene_id": pair["scene_id"],
        "water_pixels": int(inside.sum()),
        "fdi_mean": float(fdi.mean()),
        "fdi_p99": float(np.quantile(fdi, 0.99)),
        "ndvi_mean": float(ndvi.mean()),
        "nir_p99": float(np.quantile(image[7][inside], 0.99)),
    }
    if scorer is not None:
        probability = sliding_scores(image, scorer)[inside]
        row["probability_mean"] = float(probability.mean())
        row["probability_p99"] = float(np.quantile(probability, 0.99))
        row["detected_share"] = float((probability >= threshold).mean()) if threshold else None
    return row


def pair_study(concentration: pd.DataFrame, scorer=None, threshold=None, name: str = "") -> dict:
    rows = []
    for pair in accepted_pairs():
        features = pair_features(pair, scorer, threshold)
        sample = pair["sample_ids"][0]
        match = concentration[concentration["sample_id"] == sample]
        features["concentration"] = float(match["concentration"].iloc[0]) if len(match) else None
        rows.append(features)
    frame = pd.DataFrame(rows)
    correlations = {}
    for column in frame.columns:
        if column in ("event_id", "scene_id", "concentration", "water_pixels"):
            continue
        values = frame[column].astype(float)
        if values.nunique() > 1:
            result = spearmanr(values, frame["concentration"])
            correlations[column] = {
                "spearman": float(result.statistic),
                "p_value": float(result.pvalue),
            }
    study = {
        "detector": name or None,
        "threshold": threshold,
        "events": len(frame),
        "correlations": correlations,
        "rows": frame.to_dict(orient="records"),
    }
    write_json(REPORTS / "metrics" / "concentration" / "satellite_pairs.json", study)
    return study
