from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import itertools
import json
import math
import sys
import warnings
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fetch import DATA_DIR, EXTERNAL_DIR, MANIFEST_DIR, format_size, md5_of, open_url

AOI_PATH = DATA_DIR / "aoi" / "russia.geojson"
SCENES_MANIFEST = MANIFEST_DIR / "sentinel2.json"
CROPS_MANIFEST = MANIFEST_DIR / "sentinel2-crops.json"
CROPS_DIR = EXTERNAL_DIR / "sentinel2"
STAC_URL = "https://earth-search.aws.element84.com/v1"
COLLECTION = "sentinel-2-l2a"
BANDS = (
    ("B01", "coastal"),
    ("B02", "blue"),
    ("B03", "green"),
    ("B04", "red"),
    ("B05", "rededge1"),
    ("B06", "rededge2"),
    ("B07", "rededge3"),
    ("B08", "nir"),
    ("B8A", "nir08"),
    ("B11", "swir16"),
    ("B12", "swir22"),
)
SCL_GROUPS = {"nodata": (0,), "cloud": (3, 8, 9, 10), "water": (6,), "snow": (11,)}
GRID_STEP = 6
READ_WORKERS = 6
GDAL_OPTIONS = {
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif",
    "GDAL_HTTP_MAX_RETRY": "5",
    "GDAL_HTTP_RETRY_DELAY": "2",
    "GDAL_HTTP_MULTIPLEX": "YES",
    "VSI_CACHE": "TRUE",
    "GDAL_PAM_ENABLED": "NO",
}


def load_aois() -> dict[str, dict]:
    collection = json.loads(AOI_PATH.read_text(encoding="utf-8"))
    return {feature["id"]: feature for feature in collection["features"]}


def select_aois(aois: dict[str, dict], wanted: list[str] | None, priority: int) -> list[dict]:
    if wanted:
        unknown = [key for key in wanted if key not in aois]
        if unknown:
            raise SystemExit(f"нет таких районов: {', '.join(unknown)}; список — команда list")
        return [aois[key] for key in wanted]
    return [aoi for aoi in aois.values() if aoi["properties"]["priority"] <= priority]


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def post_json(url: str, body: dict) -> dict:
    headers = {"Content-Type": "application/json", "Accept": "application/geo+json"}
    with open_url(url, headers, "POST", json.dumps(body).encode()) as response:
        return json.load(response)


def point_in_ring(x: float, y: float, ring: list[list[float]]) -> bool:
    inside = False
    for (x1, y1), (x2, y2) in itertools.pairwise(ring):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def point_in_geometry(x: float, y: float, geometry: dict) -> bool:
    polygons = geometry["coordinates"]
    if geometry["type"] == "Polygon":
        polygons = [polygons]
    return any(
        point_in_ring(x, y, polygon[0])
        and not any(point_in_ring(x, y, hole) for hole in polygon[1:])
        for polygon in polygons
    )


def covers(geometry: dict, bbox: list[float]) -> bool:
    west, south, east, north = bbox
    points = (
        (west, south),
        (east, south),
        (east, north),
        (west, north),
        ((west + east) / 2, (south + north) / 2),
    )
    return all(point_in_geometry(x, y, geometry) for x, y in points)


def season_windows(years: list[int], months: tuple[int, int]) -> list[tuple[str, str]]:
    first, last = months
    windows = []
    for year in years:
        end_day = (dt.date(year + (last == 12), last % 12 + 1, 1) - dt.timedelta(days=1)).day
        windows.append((f"{year}-{first:02d}-01", f"{year}-{last:02d}-{end_day:02d}"))
    return windows


def search_window(
    bbox: list[float], start: str, end: str, max_cloud: float
) -> tuple[list[dict], int]:
    body = {
        "collections": [COLLECTION],
        "bbox": bbox,
        "datetime": f"{start}T00:00:00Z/{end}T23:59:59Z",
        "query": {"eo:cloud_cover": {"lte": max_cloud}},
        "sortby": [{"field": "properties.eo:cloud_cover", "direction": "asc"}],
        "limit": 100,
    }
    result = post_json(f"{STAC_URL}/search", body)
    return result["features"], result.get("numberMatched", len(result["features"]))


def describe_item(item: dict, bbox: list[float]) -> dict:
    properties = item["properties"]
    return {
        "id": item["id"],
        "date": properties["datetime"][:10],
        "cloud": round(properties["eo:cloud_cover"], 2),
        "tile": properties.get("grid:code", "").removeprefix("MGRS-"),
        "platform": properties.get("platform"),
        "covers": covers(item["geometry"], bbox),
    }


def command_search(args: argparse.Namespace) -> None:
    aois = select_aois(load_aois(), args.aoi, args.priority)
    windows = season_windows(args.years, (args.months[0], args.months[1]))
    manifest = read_json(SCENES_MANIFEST) or {"aois": {}}
    manifest.update(
        {
            "catalog": STAC_URL,
            "collection": COLLECTION,
            "searched": dt.date.today().isoformat(),
            "windows": windows,
            "max_tile_cloud": args.max_cloud,
        }
    )
    for aoi in aois:
        bbox = aoi["bbox"]
        scenes: list[dict] = []
        matched = 0
        for start, end in windows:
            items, count = search_window(bbox, start, end, args.max_cloud)
            matched += count
            scenes.extend(describe_item(item, bbox) for item in items)
        scenes.sort(key=lambda scene: (not scene["covers"], scene["cloud"], scene["date"]))
        kept = scenes[: args.keep]
        manifest["aois"][aoi["id"]] = {"matched": matched, "scenes": kept}
        full = sum(scene["covers"] for scene in scenes)
        best = f"{kept[0]['date']} облачность тайла {kept[0]['cloud']} %" if kept else "—"
        found = f"найдено {matched:>4}, район целиком в кадре {full:>4}"
        print(f"  {aoi['id']:<14} {found}; лучший: {best}")
    manifest["aois"] = dict(sorted(manifest["aois"].items()))
    write_json(SCENES_MANIFEST, manifest)
    print(f"список сцен: {SCENES_MANIFEST.relative_to(DATA_DIR.parent)}")


def snap_window(window, width: int, height: int):
    from rasterio.windows import Window

    col = math.floor(window.col_off / GRID_STEP) * GRID_STEP
    row = math.floor(window.row_off / GRID_STEP) * GRID_STEP
    right = min(math.ceil((window.col_off + window.width) / GRID_STEP) * GRID_STEP, width)
    bottom = min(math.ceil((window.row_off + window.height) / GRID_STEP) * GRID_STEP, height)
    col, row = max(col, 0), max(row, 0)
    return Window(col, row, right - col, bottom - row)


def read_on_grid(href: str, window, shape: tuple[int, int]):
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.windows import Window

    with rasterio.Env(**GDAL_OPTIONS), rasterio.open(href) as source:
        factor = round(source.res[0] / 10)
        native = Window(
            window.col_off / factor,
            window.row_off / factor,
            window.width / factor,
            window.height / factor,
        )
        return source.read(1, window=native, out_shape=shape, resampling=Resampling.nearest)


def scl_fractions(scl) -> dict[str, float]:
    import numpy as np

    total = scl.size
    return {
        name: round(float(np.isin(scl, codes).sum()) / total, 4)
        for name, codes in SCL_GROUPS.items()
    }


def quicklook(bands, scale: float, offset: float):
    import numpy as np

    rgb = np.stack([bands[3], bands[2], bands[1]])[:, ::2, ::2].astype("float32") * scale + offset
    valid = rgb[0] > offset
    low, high = np.percentile(rgb[:, valid], (2, 98)) if valid.any() else (0.0, 0.3)
    stretched = np.clip((rgb - low) / max(high - low, 1e-6), 0, 1) ** (1 / 1.6)
    return (stretched * 255).astype("uint8")


def band_scaling(item: dict) -> tuple[float, float]:
    band = item["assets"]["red"].get("raster:bands", [{}])[0]
    return band.get("scale", 0.0001), band.get("offset", 0.0)


def fetch_crop(aoi: dict, scene: dict, limits: argparse.Namespace) -> dict | None:
    import numpy as np
    import rasterio
    from rasterio.warp import transform_bounds
    from rasterio.windows import from_bounds

    with open_url(
        f"{STAC_URL}/collections/{COLLECTION}/items/{scene['id']}",
        {"Accept": "application/geo+json"},
    ) as response:
        item = json.load(response)
    assets = item["assets"]
    with rasterio.Env(**GDAL_OPTIONS):
        with rasterio.open(assets["red"]["href"]) as reference:
            bounds = transform_bounds("EPSG:4326", reference.crs, *aoi["bbox"], densify_pts=21)
            window = snap_window(
                from_bounds(*bounds, transform=reference.transform),
                reference.width,
                reference.height,
            )
            transform = reference.window_transform(window)
            crs = reference.crs
        shape = (int(window.height), int(window.width))
        scl = read_on_grid(assets["scl"]["href"], window, shape)
        fractions = scl_fractions(scl)
        if (
            fractions["cloud"] > limits.max_aoi_cloud
            or fractions["nodata"] > limits.max_nodata
            or fractions["snow"] > limits.max_snow
        ):
            return {"rejected": fractions}
        hrefs = [assets[asset]["href"] for _, asset in BANDS]
        with ThreadPoolExecutor(max_workers=READ_WORKERS) as pool:
            bands = np.stack(list(pool.map(lambda href: read_on_grid(href, window, shape), hrefs)))

    scale, offset = band_scaling(item)
    folder = CROPS_DIR / aoi["id"]
    folder.mkdir(parents=True, exist_ok=True)
    stem = folder / scene["id"]
    profile = {
        "driver": "GTiff",
        "width": shape[1],
        "height": shape[0],
        "crs": crs,
        "transform": transform,
        "compress": "deflate",
        "tiled": True,
        "blockxsize": 512,
        "blockysize": 512,
    }
    with rasterio.open(
        stem.with_suffix(".tif"),
        "w",
        count=len(BANDS),
        dtype="uint16",
        nodata=0,
        predictor=2,
        **profile,
    ) as target:
        target.write(bands)
        for index, (code, _) in enumerate(BANDS, start=1):
            target.set_band_description(index, code)
        target.update_tags(scene=scene["id"], scale=str(scale), offset=str(offset))
    with rasterio.open(
        stem.with_name(f"{scene['id']}_scl.tif"), "w", count=1, dtype="uint8", nodata=0, **profile
    ) as target:
        target.write(scl, 1)
        target.set_band_description(1, "SCL")
    preview = quicklook(bands, scale, offset)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", rasterio.errors.NotGeoreferencedWarning)
        with (
            rasterio.Env(GDAL_PAM_ENABLED="NO"),
            rasterio.open(
                stem.with_suffix(".png"),
                "w",
                driver="PNG",
                width=preview.shape[2],
                height=preview.shape[1],
                count=3,
                dtype="uint8",
            ) as target,
        ):
            target.write(preview)
    properties = item["properties"]
    sidecar = {
        "aoi": aoi["id"],
        "scene": scene["id"],
        "datetime": properties["datetime"],
        "platform": properties.get("platform"),
        "tile": scene["tile"],
        "processing_baseline": properties.get("s2:processing_baseline"),
        "tile_cloud": properties["eo:cloud_cover"],
        "aoi_fractions": fractions,
        "crs": crs.to_string(),
        "transform": list(transform)[:6],
        "width": shape[1],
        "height": shape[0],
        "resolution_m": 10,
        "bands": [code for code, _ in BANDS],
        "resampling": "nearest",
        "reflectance": f"DN * {scale} + {offset}",
        "stac_item": f"{STAC_URL}/collections/{COLLECTION}/items/{scene['id']}",
    }
    write_json(stem.with_suffix(".json"), sidecar)
    return sidecar


def record_crop(sidecar: dict) -> None:
    manifest = read_json(CROPS_MANIFEST) or {"catalog": STAC_URL, "crops": {}}
    folder = CROPS_DIR / sidecar["aoi"]
    raster = folder / f"{sidecar['scene']}.tif"
    manifest["crops"].setdefault(sidecar["aoi"], {})[sidecar["scene"]] = {
        "date": sidecar["datetime"][:10],
        "size": [sidecar["width"], sidecar["height"]],
        "aoi_fractions": sidecar["aoi_fractions"],
        "bytes": raster.stat().st_size,
        "md5": md5_of(raster),
    }
    manifest["crops"] = {
        key: dict(sorted(value.items())) for key, value in sorted(manifest["crops"].items())
    }
    write_json(CROPS_MANIFEST, manifest)


def command_fetch(args: argparse.Namespace) -> None:
    if importlib.util.find_spec("rasterio") is None:
        raise SystemExit("нужен rasterio: pip install -r scripts/data/requirements.txt")
    listed = read_json(SCENES_MANIFEST).get("aois", {})
    for aoi in select_aois(load_aois(), args.aoi, args.priority):
        candidates = [
            scene for scene in listed.get(aoi["id"], {}).get("scenes", []) if scene["covers"]
        ]
        if not candidates:
            print(f"  {aoi['id']:<14} нет сцен в списке — сначала search")
            continue
        sidecars = [read_json(path) for path in (CROPS_DIR / aoi["id"]).glob("*.json")]
        taken = {sidecar["datetime"][:10] for sidecar in sidecars}
        for scene in candidates[: args.tries]:
            if len(taken) >= args.scenes:
                break
            if scene["date"] in taken:
                continue
            try:
                result = fetch_crop(aoi, scene, args)
            except Exception as error:
                print(f"  {aoi['id']:<14} {scene['id']}: ошибка чтения ({error})", file=sys.stderr)
                continue
            if "rejected" in result:
                share = result["rejected"]
                reason = f"облака {share['cloud']:.0%}, лёд {share['snow']:.0%}"
                print(f"  {aoi['id']:<14} {scene['date']} пропуск: {reason}")
                continue
            record_crop(result)
            taken.add(scene["date"])
            share = result["aoi_fractions"]
            raster = CROPS_DIR / aoi["id"] / f"{scene['id']}.tif"
            size = f"{result['width']}×{result['height']} px"
            fractions = f"вода {share['water']:.0%}, облака {share['cloud']:.0%}"
            weight = format_size(raster.stat().st_size)
            print(f"  {aoi['id']:<14} {scene['date']} сохранён: {size}, {fractions}, {weight}")


def command_list(args: argparse.Namespace) -> None:
    listed = read_json(SCENES_MANIFEST).get("aois", {})
    crops = read_json(CROPS_MANIFEST).get("crops", {})
    for aoi in select_aois(load_aois(), None, args.priority):
        properties = aoi["properties"]
        scenes = listed.get(aoi["id"], {}).get("scenes", [])
        counts = f"сцен в списке {len(scenes):>3}, вырезано {len(crops.get(aoi['id'], {})):>2}"
        print(
            f"  {aoi['id']:<14} {properties['priority']}  {properties['sea_name']:<24} "
            f"{counts}  {properties['name']}"
        )


def build_parser() -> argparse.ArgumentParser:
    today = dt.date.today()
    parser = argparse.ArgumentParser(
        description="Сцены Sentinel-2 L2A по районам data/aoi/russia.geojson."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    listing = commands.add_parser("list", help="районы и что по ним есть")
    listing.add_argument("--priority", type=int, default=3)
    listing.set_defaults(handler=command_list)

    search = commands.add_parser("search", help="найти сцены в каталоге Earth Search")
    search.add_argument("--aoi", action="append", help="район (можно несколько); по умолчанию все")
    search.add_argument(
        "--priority", type=int, default=3, help="только районы с приоритетом не ниже"
    )
    search.add_argument("--years", type=int, nargs="+", default=[today.year - 1, today.year])
    search.add_argument("--months", type=int, nargs=2, default=[6, 9], metavar=("FIRST", "LAST"))
    search.add_argument("--max-cloud", type=float, default=30.0, help="облачность тайла, %%")
    search.add_argument(
        "--keep", type=int, default=20, help="сколько сцен хранить в списке на район"
    )
    search.set_defaults(handler=command_search)

    fetch = commands.add_parser("fetch", help="вырезать район из сцен списка (нужен rasterio)")
    fetch.add_argument("--aoi", action="append", help="район (можно несколько); по умолчанию все")
    fetch.add_argument(
        "--priority", type=int, default=3, help="только районы с приоритетом не ниже"
    )
    fetch.add_argument("--scenes", type=int, default=1, help="сколько чистых сцен нужно на район")
    fetch.add_argument("--tries", type=int, default=10, help="сколько кандидатов пробовать")
    fetch.add_argument(
        "--max-aoi-cloud", type=float, default=0.10, help="доля облаков и теней в районе"
    )
    fetch.add_argument("--max-snow", type=float, default=0.20, help="доля снега и льда в районе")
    fetch.add_argument("--max-nodata", type=float, default=0.01, help="доля пикселей без данных")
    fetch.set_defaults(handler=command_fetch)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
