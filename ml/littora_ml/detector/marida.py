from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio

BANDS = ("B01", "B02", "B03", "B04", "B05", "B06", "B07", "B08", "B8A", "B11", "B12")
CLASS_NAMES = {
    0: "unlabeled",
    1: "marine_debris",
    2: "dense_sargassum",
    3: "sparse_sargassum",
    4: "natural_organic_material",
    5: "ship",
    6: "clouds",
    7: "marine_water",
    8: "sediment_laden_water",
    9: "foam",
    10: "turbid_water",
    11: "shallow_water",
    12: "waves",
    13: "cloud_shadows",
    14: "wakes",
    15: "mixed_water",
}
PATCH_SIZE = 256


@dataclass(frozen=True)
class MaridaPatch:
    name: str
    scene: str
    tile: str
    date: dt.date
    image: Path

    @property
    def labels(self) -> Path:
        return self.image.with_name(self.image.stem + "_cl.tif")

    @property
    def confidence(self) -> Path:
        return self.image.with_name(self.image.stem + "_conf.tif")


def parse_scene(scene: str) -> tuple[dt.date, str]:
    date_text, tile = scene.split("_")
    day, month, year = (int(part) for part in date_text.split("-"))
    return dt.date(2000 + year, month, day), tile


def list_patches(root: Path) -> list[MaridaPatch]:
    patches = []
    for folder in sorted((root / "patches").iterdir()):
        if not folder.is_dir():
            continue
        scene = folder.name.removeprefix("S2_")
        day, tile = parse_scene(scene)
        for image in sorted(folder.glob("*.tif")):
            if image.stem.endswith(("_cl", "_conf")):
                continue
            name = image.stem.removeprefix("S2_")
            patches.append(MaridaPatch(name, scene, tile, day, image))
    return patches


def official_splits(root: Path) -> dict[str, str]:
    splits = {}
    for split in ("train", "val", "test"):
        for name in (root / "splits" / f"{split}_X.txt").read_text().split():
            splits[name] = split
    return splits


def read_patch(patch: MaridaPatch) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    with rasterio.open(patch.image) as dataset:
        image = dataset.read().astype(np.float32)
    with rasterio.open(patch.labels) as dataset:
        labels = dataset.read(1).astype(np.uint8)
    with rasterio.open(patch.confidence) as dataset:
        confidence = dataset.read(1).astype(np.uint8)
    return image, labels, confidence


def patch_bounds(patch: MaridaPatch) -> tuple[str, tuple[float, float, float, float]]:
    with rasterio.open(patch.image) as dataset:
        return dataset.crs.to_string(), tuple(dataset.bounds)


def patch_table(root: Path) -> pd.DataFrame:
    splits = official_splits(root)
    rows = []
    for index, patch in enumerate(list_patches(root)):
        crs, bounds = patch_bounds(patch)
        rows.append(
            {
                "index": index,
                "name": patch.name,
                "scene": patch.scene,
                "tile": patch.tile,
                "date": patch.date.isoformat(),
                "official_split": splits.get(patch.name, "none"),
                "crs": crs,
                "west": bounds[0],
                "south": bounds[1],
                "east": bounds[2],
                "north": bounds[3],
            }
        )
    return pd.DataFrame(rows)
