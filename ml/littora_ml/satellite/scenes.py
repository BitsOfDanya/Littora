from __future__ import annotations

import json
import urllib.request

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds

from app.earth.bands import REFLECTANCE_FLOOR
from app.earth.catalog import build_ssl_context
from app.earth.raster import GDAL_OPTIONS
from littora_ml.detector.l2a import ASSETS, SCL, StacItem, _item
from littora_ml.detector.marida import BANDS

CATALOG = "https://earth-search.aws.element84.com/v1"


def get_item(collection: str, item_id: str, catalog: str = CATALOG) -> StacItem:
    url = f"{catalog}/collections/{collection}/items/{item_id}"
    request = urllib.request.Request(url, headers={"User-Agent": "littora-ml/0.1"})
    with urllib.request.urlopen(request, timeout=60, context=build_ssl_context()) as reply:
        return _item(json.load(reply))


def read_bands(
    item: StacItem, bbox_lonlat: tuple[float, float, float, float]
) -> tuple[np.ndarray, np.ndarray, dict]:
    with rasterio.Env(**GDAL_OPTIONS), rasterio.open(item.hrefs["B02"]) as reference:
        crs = reference.crs
        west, south, east, north = transform_bounds("EPSG:4326", crs, *bbox_lonlat)
        west, south = np.floor(west / 10) * 10, np.floor(south / 10) * 10
        east, north = np.ceil(east / 10) * 10, np.ceil(north / 10) * 10
        transform = reference.transform
    width, height = int((east - west) / 10), int((north - south) / 10)
    image = np.zeros((len(BANDS), height, width), dtype=np.float32)
    for index, band in enumerate(BANDS):
        with rasterio.Env(**GDAL_OPTIONS), rasterio.open(item.hrefs[band]) as dataset:
            window = from_bounds(west, south, east, north, transform=dataset.transform)
            raw = dataset.read(
                1,
                window=window,
                out_shape=(height, width),
                resampling=Resampling.bilinear,
                boundless=True,
                fill_value=0,
            ).astype(np.float32)
        scale, offset = item.scales[band]
        image[index] = np.where(raw > 0, np.maximum(raw * scale + offset, REFLECTANCE_FLOOR), 0.0)
    with rasterio.Env(**GDAL_OPTIONS), rasterio.open(item.hrefs[SCL]) as dataset:
        window = from_bounds(west, south, east, north, transform=dataset.transform)
        scl = dataset.read(
            1,
            window=window,
            out_shape=(height, width),
            resampling=Resampling.nearest,
            boundless=True,
            fill_value=0,
        ).astype(np.uint8)
    grid = {
        "crs": crs.to_string(),
        "transform": [10.0, 0.0, float(west), 0.0, -10.0, float(north)],
        "width": width,
        "height": height,
        "reference_transform": list(transform)[:6],
    }
    return image, scl, grid


__all__ = ["ASSETS", "get_item", "read_bands"]
