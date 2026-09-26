from __future__ import annotations

import datetime as dt
import json
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from rasterio.enums import Resampling
from rasterio.windows import from_bounds
from scipy.ndimage import uniform_filter

from app.earth.catalog import build_ssl_context
from app.earth.raster import GDAL_OPTIONS
from littora_ml.common.io import write_json
from littora_ml.detector.dataset import CONFIDENCE, IMAGES, LABELS, TABLE, VALID
from littora_ml.detector.marida import BANDS, PATCH_SIZE

ASSETS = {
    "B01": "coastal",
    "B02": "blue",
    "B03": "green",
    "B04": "red",
    "B05": "rededge1",
    "B06": "rededge2",
    "B07": "rededge3",
    "B08": "nir",
    "B8A": "nir08",
    "B11": "swir16",
    "B12": "swir22",
}
SCL = "scl"
REFLECTANCE_FLOOR = 0.0001
HARMONIZED_COLLECTION = "sentinel-2-l2a"
HARMONIZED_BASELINE = 4.0


@dataclass(frozen=True)
class StacItem:
    id: str
    collection: str
    datetime: str
    baseline: str
    cloud_cover: float | None
    hrefs: dict[str, str]
    scales: dict[str, tuple[float, float]]


class Stac:
    def __init__(self, url: str, timeout: float = 60) -> None:
        self.url = url.rstrip("/")
        self.timeout = timeout
        self.context = build_ssl_context()

    def search(self, body: dict) -> list[dict]:
        request = urllib.request.Request(
            f"{self.url}/search",
            data=json.dumps(body).encode(),
            method="POST",
            headers={"Content-Type": "application/json", "User-Agent": "littora-ml/0.1"},
        )
        for attempt in range(4):
            try:
                with urllib.request.urlopen(
                    request, timeout=self.timeout, context=self.context
                ) as r:
                    return json.load(r).get("features", [])
            except OSError:
                time.sleep(2 * (attempt + 1))
        raise RuntimeError("catalog is unreachable")


def _item(feature: dict) -> StacItem:
    hrefs, scales = {}, {}
    for band, key in {**ASSETS, SCL: SCL}.items():
        asset = feature["assets"].get(key)
        if not asset:
            continue
        hrefs[band] = asset["href"]
        raster = (asset.get("raster:bands") or [{}])[0]
        scales[band] = (float(raster.get("scale") or 1.0), float(raster.get("offset") or 0.0))
    properties = feature["properties"]
    baseline = str(properties.get("s2:processing_baseline", ""))
    try:
        harmonized = float(baseline) >= HARMONIZED_BASELINE
    except ValueError:
        harmonized = False
    if feature.get("collection") == HARMONIZED_COLLECTION and harmonized:
        scales = {band: (scale, 0.0) for band, (scale, _) in scales.items()}
    return StacItem(
        id=feature["id"],
        collection=feature.get("collection", ""),
        datetime=properties["datetime"],
        baseline=str(properties.get("s2:processing_baseline", "")),
        cloud_cover=properties.get("eo:cloud_cover"),
        hrefs=hrefs,
        scales=scales,
    )


def find_items(stac: Stac, collections: list[str], tile: str, day: dt.date) -> list[StacItem]:
    items = []
    for collection in collections:
        features = stac.search(
            {
                "collections": [collection],
                "query": {"grid:code": {"eq": f"MGRS-{tile}"}},
                "datetime": f"{day.isoformat()}T00:00:00Z/{day.isoformat()}T23:59:59Z",
                "limit": 20,
            }
        )
        items.extend(_item(feature) for feature in features)
        if items:
            break
    return sorted(items, key=lambda item: item.id)


MAX_GROUP_PIXELS = 1024


def group_patches(rows: pd.DataFrame) -> list[pd.DataFrame]:
    groups: list[list[int]] = []
    extents: list[list[float]] = []
    limit = MAX_GROUP_PIXELS * 10
    for position, row in enumerate(rows.itertuples()):
        placed = False
        for group, extent in zip(groups, extents, strict=True):
            west, south = min(extent[0], row.west), min(extent[1], row.south)
            east, north = max(extent[2], row.east), max(extent[3], row.north)
            if east - west <= limit and north - south <= limit:
                group.append(position)
                extent[:] = [west, south, east, north]
                placed = True
                break
        if not placed:
            groups.append([position])
            extents.append([row.west, row.south, row.east, row.north])
    return [rows.iloc[group] for group in groups]


def _read_union(href: str, crs: str, bounds, nearest: bool) -> np.ndarray | None:
    west, south, east, north = bounds
    width = round((east - west) / 10)
    height = round((north - south) / 10)
    with rasterio.Env(**GDAL_OPTIONS), rasterio.open(href) as dataset:
        if dataset.crs.to_string() != crs:
            return None
        window = from_bounds(west, south, east, north, transform=dataset.transform)
        resampling = Resampling.nearest if nearest else Resampling.bilinear
        return dataset.read(
            1,
            window=window,
            out_shape=(height, width),
            resampling=resampling,
            boundless=True,
            fill_value=0,
        )


def extract_group(item: StacItem, rows: pd.DataFrame) -> tuple[np.ndarray, np.ndarray] | None:
    crs = rows.iloc[0]["crs"]
    union = (rows.west.min(), rows.south.min(), rows.east.max(), rows.north.max())
    layers = {}
    for band in (*BANDS, SCL):
        raw = _read_union(item.hrefs[band], crs, union, nearest=band == SCL)
        if raw is None:
            return None
        layers[band] = raw
    images = np.zeros((len(rows), len(BANDS), PATCH_SIZE, PATCH_SIZE), dtype=np.float32)
    scl = np.zeros((len(rows), PATCH_SIZE, PATCH_SIZE), dtype=np.uint8)
    for position, row in enumerate(rows.itertuples()):
        column = round((row.west - union[0]) / 10)
        line = round((union[3] - row.north) / 10)
        window = (slice(line, line + PATCH_SIZE), slice(column, column + PATCH_SIZE))
        for index, band in enumerate(BANDS):
            raw = layers[band][window]
            scale, offset = item.scales[band]
            reflectance = np.maximum(raw * scale + offset, REFLECTANCE_FLOOR)
            images[position, index] = np.where(raw > 0, reflectance, 0.0)
        scl[position] = layers[SCL][window]
    return images, scl


def extract_scene(
    stac: Stac, collections: list[str], scene: str, rows: pd.DataFrame, cache: Path
) -> dict:
    target = cache / f"{scene}.npz"
    if target.exists():
        return json.loads(str(np.load(target, allow_pickle=False)["meta"]))
    first = rows.iloc[0]
    items = find_items(stac, collections, first["tile"], dt.date.fromisoformat(first["date"]))
    images = np.zeros((len(rows), len(BANDS), PATCH_SIZE, PATCH_SIZE), dtype=np.float16)
    scl = np.zeros((len(rows), PATCH_SIZE, PATCH_SIZE), dtype=np.uint8)
    found = np.zeros(len(rows), dtype=bool)
    chosen: list[str] = []
    positions = {name: position for position, name in enumerate(rows["name"])}
    for item in items:
        pending = rows[[not found[positions[name]] for name in rows["name"]]]
        if pending.empty:
            break
        for group in group_patches(pending):
            result = extract_group(item, group)
            if result is None:
                continue
            group_images, group_scl = result
            for offset, name in enumerate(group["name"]):
                position = positions[name]
                if (group_images[offset, 1] != 0).mean() < 0.5:
                    continue
                images[position] = group_images[offset].astype(np.float16)
                scl[position] = group_scl[offset]
                found[position] = True
                if item.id not in chosen:
                    chosen.append(item.id)
    first_item = next((item for item in items if item.id in chosen), None)
    meta = {
        "scene": scene,
        "items": [item.id for item in items],
        "used": chosen,
        "collection": first_item.collection if first_item else None,
        "baseline": first_item.baseline if first_item else None,
        "datetime": first_item.datetime if first_item else None,
        "patches": len(rows),
        "found": int(found.sum()),
    }
    np.savez_compressed(
        target, images=images, scl=scl, found=found, meta=np.array(json.dumps(meta))
    )
    return meta


ALIGNMENT_BANDS = [BANDS.index(name) for name in ("B02", "B03", "B04", "B08")]


def _shifted_corr(reference: np.ndarray, moving: np.ndarray, dy: int, dx: int) -> float:
    ref = reference[:, :, 1:-1, 1:-1]
    mov = moving[:, :, 1 + dy : moving.shape[2] - 1 + dy, 1 + dx : moving.shape[3] - 1 + dx]
    valid = (ref != 0) & (mov != 0)
    if valid.sum() < 100:
        return float("nan")
    return float(np.corrcoef(ref[valid], mov[valid])[0, 1])


def _detail(stack: np.ndarray) -> np.ndarray:
    smooth = uniform_filter(stack, size=(1, 1, 5, 5), mode="nearest")
    return np.where(stack != 0, stack - smooth + 1e-3, 0.0)


def scene_alignment(original: np.ndarray, converted: np.ndarray) -> dict:
    reference = _detail(original[:, ALIGNMENT_BANDS].astype(np.float32))
    moving = _detail(converted[:, ALIGNMENT_BANDS].astype(np.float32))
    scores = {
        (dy, dx): _shifted_corr(reference, moving, dy, dx) for dy in (-1, 0, 1) for dx in (-1, 0, 1)
    }
    finite = {key: value for key, value in scores.items() if value == value}
    if not finite:
        return {"corr0": None, "best_shift": None, "corr_best": None, "subpixel_shift": None}
    best = max(finite, key=finite.get)
    return {
        "corr0": scores[(0, 0)],
        "best_shift": list(best),
        "corr_best": finite[best],
        "subpixel_shift": subpixel_shift(scores),
    }


def _vertex(before: float, center: float, after: float) -> float | None:
    curvature = before - 2 * center + after
    if not all(value == value for value in (before, center, after)) or curvature >= 0:
        return None
    return float(np.clip((before - after) / (2 * curvature), -1.0, 1.0))


def subpixel_shift(scores: dict[tuple[int, int], float]) -> list[float] | None:
    rows = _vertex(scores[(-1, 0)], scores[(0, 0)], scores[(1, 0)])
    cols = _vertex(scores[(0, -1)], scores[(0, 0)], scores[(0, 1)])
    if rows is None or cols is None:
        return None
    return [round(rows, 3), round(cols, 3)]


def build_l2a_cache(
    marida_cache: Path,
    out_dir: Path,
    catalog: str,
    collections: list[str],
    workers: int = 6,
    min_alignment: float = 0.97,
) -> dict:
    table = pd.read_parquet(marida_cache / TABLE)
    cache = out_dir / "scenes"
    cache.mkdir(parents=True, exist_ok=True)
    stac = Stac(catalog)
    scenes = sorted(table["scene"].unique())

    def run(scene: str) -> dict:
        rows = table[table["scene"] == scene]
        for attempt in range(3):
            try:
                return extract_scene(stac, collections, scene, rows, cache)
            except Exception as error:
                if attempt == 2:
                    return {"scene": scene, "error": str(error), "found": 0, "patches": len(rows)}
                time.sleep(5)
        return {}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        metas = list(pool.map(run, scenes))
    count = len(table)
    images = np.lib.format.open_memmap(
        out_dir / IMAGES,
        mode="w+",
        dtype=np.float16,
        shape=(count, len(BANDS), PATCH_SIZE, PATCH_SIZE),
    )
    scl = np.zeros((count, PATCH_SIZE, PATCH_SIZE), dtype=np.uint8)
    found = np.zeros(count, dtype=bool)
    original = np.load(marida_cache / IMAGES, mmap_mode="r")
    alignment = {}
    for scene in scenes:
        path = cache / f"{scene}.npz"
        if not path.exists():
            continue
        data = np.load(path)
        indices = table.index[table["scene"] == scene].to_numpy()
        scene_found = data["found"]
        check = (
            scene_alignment(np.asarray(original[indices[scene_found]]), data["images"][scene_found])
            if scene_found.any()
            else {"corr0": None, "best_shift": None, "corr_best": None}
        )
        aligned = (
            check["corr0"] is not None
            and check["corr0"] >= min_alignment
            and check["best_shift"] == [0, 0]
        )
        alignment[scene] = {**check, "aligned": aligned}
        images[indices] = data["images"]
        scl[indices] = data["scl"]
        found[indices] = scene_found & aligned
    images.flush()
    labels = np.load(marida_cache / LABELS)
    np.save(out_dir / LABELS, labels)
    np.save(out_dir / CONFIDENCE, np.load(marida_cache / CONFIDENCE))
    valid = (np.asarray(images[:, 1]) != 0) & found[:, None, None]
    np.save(out_dir / VALID, valid)
    np.save(out_dir / "scl.npy", scl)
    table.assign(l2a_found=found).to_parquet(out_dir / TABLE, index=False)
    summary = {
        "variant": "l2a",
        "catalog": catalog,
        "collections": collections,
        "patches": count,
        "patches_found": int(found.sum()),
        "min_alignment": min_alignment,
        "alignment": alignment,
        "scenes": metas,
    }
    write_json(out_dir / "source.json", summary)
    return summary
