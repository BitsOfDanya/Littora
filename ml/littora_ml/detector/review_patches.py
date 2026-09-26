from __future__ import annotations

import datetime as dt
import re
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import rasterio
from affine import Affine
from rasterio.warp import transform_geom
from shapely.geometry import mapping, shape

from app.earth.raster import GDAL_OPTIONS
from littora_ml.common.io import write_json
from littora_ml.detector.dataset import CONFIDENCE, IMAGES, LABELS, TABLE, VALID
from littora_ml.detector.l2a import (
    REFLECTANCE_FLOOR,
    SCL,
    Stac,
    StacItem,
    _read_union,
    find_items,
)
from littora_ml.detector.marida import BANDS, PATCH_SIZE
from littora_ml.detector.review_labels import (
    LONLAT,
    Grid,
    ZoneLabel,
    rasterize_reviews,
    read_reviews,
    resolve,
)

TRAIN_LABELS = (
    "likely_debris",
    "ship",
    "structure",
    "wake",
    "foam",
    "slick",
    "plume",
    "land_edge",
    "cloud_edge",
)
MARIDA_CODES = {
    1: 1,
    2: 5,
    3: 5,
    4: 14,
    5: 9,
    6: 7,
    7: 8,
    8: 11,
    9: 6,
}
CONFIDENCE_CODES = {3: 1, 2: 2}
MARGIN = PATCH_SIZE // 8
POINT_RADIUS = 1
SCENE_ID = re.compile(r"^S2[A-D]_(?:T)?(\d{2}[A-Z]{3})_(\d{8})")
GRID_M = 10
MIN_VALID = 0.5


def scene_key(scene_id: str) -> tuple[str, dt.date] | None:
    match = SCENE_ID.match(scene_id)
    if not match:
        return None
    return match.group(1), dt.datetime.strptime(match.group(2), "%Y%m%d").date()


def windows_for(
    points: list[tuple[float, float]], origin: tuple[float, float]
) -> tuple[list[int], list[tuple[float, float]]]:
    size = PATCH_SIZE * GRID_M
    margin = MARGIN * GRID_M
    anchors: list[tuple[float, float]] = []
    owner = []
    for x, y in points:
        found = next(
            (
                position
                for position, (west, north) in enumerate(anchors)
                if west + margin <= x < west + size - margin
                and north - size + margin < y <= north - margin
            ),
            None,
        )
        if found is None:
            west = origin[0] + np.floor((x - size / 2 - origin[0]) / GRID_M) * GRID_M
            north = origin[1] + np.floor((y + size / 2 - origin[1]) / GRID_M) * GRID_M
            anchors.append((float(west), float(north)))
            found = len(anchors) - 1
        owner.append(found)
    return owner, anchors


def _item_grid(item: StacItem) -> tuple[str, Affine]:
    with rasterio.Env(**GDAL_OPTIONS), rasterio.open(item.hrefs["B02"]) as dataset:
        return dataset.crs.to_string(), dataset.transform


def _read_window(item: StacItem, crs: str, bounds: tuple[float, float, float, float]):
    image = np.zeros((len(BANDS), PATCH_SIZE, PATCH_SIZE), dtype=np.float32)
    for index, band in enumerate(BANDS):
        raw = _read_union(item.hrefs[band], crs, bounds, nearest=False)
        if raw is None:
            return None
        scale, offset = item.scales[band]
        reflectance = np.maximum(raw * scale + offset, REFLECTANCE_FLOOR)
        image[index] = np.where(raw > 0, reflectance, 0.0)
    scl = _read_union(item.hrefs[SCL], crs, bounds, nearest=True)
    if scl is None:
        return None
    return image, scl.astype(np.uint8)


def scene_patches(
    stac: Stac, collections: list[str], scene_id: str, zones: list[ZoneLabel]
) -> dict[str, Any]:
    key = scene_key(scene_id)
    if key is None:
        return {"scene": scene_id, "error": "не разобран идентификатор снимка"}
    tile, day = key
    items = find_items(stac, collections, tile, day)
    if not items:
        return {"scene": scene_id, "error": "снимок не найден"}
    crs, transform = _item_grid(items[0])
    projected = [shape(transform_geom(LONLAT, crs, mapping(zone.geometry))) for zone in zones]
    points = [(geometry.centroid.x, geometry.centroid.y) for geometry in projected]
    owner, anchors = windows_for(points, (transform.c, transform.f))
    patches = []
    used: list[str] = []
    for position, (west, north) in enumerate(anchors):
        bounds = (west, north - PATCH_SIZE * GRID_M, west + PATCH_SIZE * GRID_M, north)
        result, source = None, None
        for item in items:
            candidate = _read_window(item, crs, bounds)
            if candidate is not None and (candidate[0][1] != 0).mean() >= MIN_VALID:
                result, source = candidate, item
                break
        if result is None or source is None:
            continue
        if source.id not in used:
            used.append(source.id)
        image, scl = result
        grid = Grid(Affine(GRID_M, 0, west, 0, -GRID_M, north), crs, PATCH_SIZE, PATCH_SIZE)
        inside = [zone for zone, index in zip(zones, owner, strict=True) if index == position]
        masks = rasterize_reviews(inside, grid, point_radius=POINT_RADIUS)
        labels = np.vectorize(lambda code: MARIDA_CODES.get(int(code), 0))(masks.labels)
        confidence = np.vectorize(lambda code: CONFIDENCE_CODES.get(int(code), 0))(masks.confidence)
        valid = image[1] != 0
        labels = np.where(valid, labels, 0).astype(np.uint8)
        patches.append(
            {
                "name": f"{scene_id}_{position}",
                "image": image,
                "scl": scl,
                "labels": labels,
                "confidence": confidence.astype(np.uint8),
                "valid": valid,
                "bounds": bounds,
                "zones": len(inside),
                "labeled_pixels": int((labels > 0).sum()),
            }
        )
    return {
        "scene": scene_id,
        "items": used,
        "collection": items[0].collection,
        "baseline": items[0].baseline,
        "crs": crs,
        "tile": tile,
        "date": day.isoformat(),
        "zones": len(zones),
        "patches": patches,
    }


def build_review_cache(
    reviews: Path,
    out_dir: Path,
    catalog: str,
    collections: list[str],
    min_confidence: int = 2,
    workers: int = 4,
) -> dict[str, Any]:
    zones, conflicts = resolve(read_reviews(reviews), min_confidence)
    chosen = [zone for zone in zones if zone.label in TRAIN_LABELS and zone.scene_id]
    by_scene: dict[str, list[ZoneLabel]] = defaultdict(list)
    for zone in chosen:
        by_scene[zone.scene_id].append(zone)
    stac = Stac(catalog)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(
            pool.map(
                lambda scene: scene_patches(stac, collections, scene, by_scene[scene]),
                sorted(by_scene),
            )
        )
    rows, images, scl, labels, confidence, valid = [], [], [], [], [], []
    for result in results:
        for patch in result.get("patches", []):
            west, south, east, north = patch["bounds"]
            rows.append(
                {
                    "name": patch["name"],
                    "scene": result["scene"],
                    "tile": result["tile"],
                    "date": result["date"],
                    "official_split": "train",
                    "crs": result["crs"],
                    "west": west,
                    "south": south,
                    "east": east,
                    "north": north,
                    "l2a_found": True,
                }
            )
            images.append(patch["image"].astype(np.float16))
            scl.append(patch["scl"])
            labels.append(patch["labels"])
            confidence.append(patch["confidence"])
            valid.append(patch["valid"])
    if not rows:
        raise SystemExit("ни одного окна с отметками команды не прочитано")
    out_dir.mkdir(parents=True, exist_ok=True)
    table = pd.DataFrame(rows)
    table.insert(0, "index", np.arange(len(table)))
    table.to_parquet(out_dir / TABLE, index=False)
    np.save(out_dir / IMAGES, np.stack(images))
    np.save(out_dir / LABELS, np.stack(labels))
    np.save(out_dir / CONFIDENCE, np.stack(confidence))
    np.save(out_dir / VALID, np.stack(valid))
    np.save(out_dir / "scl.npy", np.stack(scl))
    summary = {
        "variant": "review",
        "source": reviews.name,
        "catalog": catalog,
        "collections": collections,
        "min_confidence": min_confidence,
        "labels": sorted(TRAIN_LABELS),
        "zones_used": len(chosen),
        "zones_by_label": dict(Counter(zone.label for zone in chosen)),
        "conflicts": len(conflicts),
        "patches": len(rows),
        "labeled_pixels": int(sum(int((item > 0).sum()) for item in labels)),
        "scenes": [
            {key: value for key, value in result.items() if key != "patches"}
            | {"patches": len(result.get("patches", []))}
            for result in results
        ],
    }
    write_json(out_dir / "source.json", summary)
    return summary
