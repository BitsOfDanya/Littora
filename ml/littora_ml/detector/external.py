from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import re
import time
import warnings
import zipfile
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
import shapefile
from affine import Affine
from rasterio.enums import Resampling
from rasterio.errors import RasterioIOError
from rasterio.features import rasterize, shapes
from rasterio.warp import transform_geom
from rasterio.windows import from_bounds
from scipy import ndimage
from shapely import wkt
from shapely.geometry import box, mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from app.analysis.detector import MANIFEST, OnnxDetector, apply_service_masks, sliding
from app.earth.bands import REFLECTANCE_FLOOR
from app.earth.raster import GDAL_OPTIONS
from littora_ml.common.config import load_config
from littora_ml.common.io import file_sha256, read_json, write_json
from littora_ml.common.paths import CASE_CONFIG, EXTERNAL, INTERIM, MODELS, PROCESSED, REPORTS
from littora_ml.detector.evaluation import code_fingerprint
from littora_ml.detector.figures import rgb
from littora_ml.detector.l2a import (
    ALIGNMENT_BANDS,
    SCL,
    Stac,
    StacItem,
    _detail,
    _read_union,
    find_items,
    scene_alignment,
)
from littora_ml.detector.marida import BANDS

UTM = "EPSG:32635"
LONLAT = "EPSG:4326"
TILE = "35SMD"
GRID = 10
WINDOW = 256
ALIGNMENT_WINDOW = 128
READERS = 3
CROP = 40
RING = (10, 30)
DILATION = 1
NEIGHBOURHOOD = (2, 5)
CONTRAST_RING = (3, 10)
CORE = 64
MAX_CLOUD = 0.2
MIN_WATER = 0.5
MIN_VALID = 0.99
MIN_ALIGNMENT = 0.8
WATER = 6
LAND = (4, 5)
CLOUDS = (3, 8, 9, 10)
PIXEL_KM2 = GRID * GRID / 1e6
SIZE_BINS = ((0, 5, "<5 м"), (5, 10, "5–10 м"), (10, 20, "10–20 м"), (20, math.inf, "≥20 м"))
REFERENCE_NM = {"B02": 492, "B03": 560, "B04": 665, "B08": 833}
MATERIALS_2019 = {"cp_bags": "bags", "cp_bottles": "bottles", "cp_reeds": "reeds"}
ORTHO_PIXEL_M = 0.35
ORTHO_SMOOTH_M = 3.0
ORTHO_GREEN = 90
ORTHO_CYAN = 15
ORTHO_AREA_M2 = (200.0, 2000.0)
NATURAL = ("reeds", "wood")
MIX_FROM = "2021-09-04"
WOOD_AREA_M2 = math.pi * 14.0**2
BLOB_SEARCH = (2, 12)
BLOB_SIGMA = 5.0
BLOB_MIN_EXCESS = 0.02
BLOB_MIN_PIXELS = 3
SHIFT_REACH = 1.5
SHIFT_COARSE = 0.5
SHIFT_FINE = 0.1
SHIFT_BORDER = 3
CLIP_FLOOR = 1.5e-4
FLOOR = 1e-4
TRAINING_CACHE = PROCESSED / "detector" / "marida_l2a" / "source.json"
LOG_2021 = (
    ("2021-06-11", "floating", "no", 1),
    ("2021-06-21", "floating", "no", 1),
    ("2021-06-26", "floating", "no", 1),
    ("2021-07-01", "floating", "no", 2),
    ("2021-07-06", "floating", "low", 2),
    ("2021-07-11", "floating", "mid", 2),
    ("2021-07-16", "floating", "mid", 1),
    ("2021-07-21", "floating", "mid/high", 2),
    ("2021-07-26", "floating", "mid/high", 3),
    ("2021-07-31", "floating", "high", 1),
    ("2021-08-05", "floating", "high", 1),
    ("2021-08-10", "floating", "high", 1),
    ("2021-08-15", "submerged", "high", None),
    ("2021-08-20", "submerged", "high", 2),
    ("2021-08-25", "part submerged", "high", 1),
    ("2021-08-30", "part submerged", "low", 1),
    ("2021-09-04", "mix floating", "low", 2),
    ("2021-09-09", "mix part submerged", "mid", 2),
    ("2021-09-14", "mix mostly submerged", "mid", 3),
    ("2021-09-19", "mix mostly submerged", "mid", 1),
    ("2021-09-24", "mostly submerged", "mid/high", 1),
    ("2021-10-04", "mostly submerged", "high", 3),
)
PLP2019 = EXTERNAL / "plp2019" / "PLP2019_dataset"
PLP2021 = EXTERNAL / "plp2021"
PLP2022 = EXTERNAL / "plp2022-2023" / "PLP2022_PLP2023_min_fraction_dataset"
UNPACKED = INTERIM / "plp"
WINDOWS = UNPACKED / "l2a"
ATTEMPTS = 5
HARMONIZED = "sentinel-2-l2a"
HARMONIZED_BASELINE = 4.0
READ_OPTIONS = {
    **GDAL_OPTIONS,
    "GDAL_HTTP_TIMEOUT": "900",
    "GDAL_HTTP_MULTIPLEX": "NO",
    "CPL_VSIL_CURL_NON_CACHED": "/vsicurl/http",
}
OUT = REPORTS / "metrics" / "detector" / "external"
FIGURES = REPORTS / "figures" / "detector" / "external"
SCENE_PATTERN = re.compile(r"S2[ABC]_MSIL1C_\d{8}T\d{6}_N\d{4}_R\d{3}_T\d{2}[A-Z]{3}_\d{8}T\d{6}")
POSITIONS = {
    "PLP2019": "центры пикселей Sentinel-2 с долей покрытия пакетами, бутылками, тростником (%)",
    "PLP2021": (
        "две мишени-круга 28 м: сетка HDPE и деревянные доски; контур HDPE — на ортофото БПЛА "
        "2021-06-11, в остальные даты журнала она стояла на якорях, отдельных координат нет; "
        "у деревянной мишени координат в данных PLP нет, её контур — пятно B08 на снимке той же "
        "даты; с 2021-09-04 по журналу мишени объединены (mix)"
    ),
    "PLP2022-2023": (
        "координат мишеней нет: только снимки S2 L1C и ACOLITE, PlanetScope, фото БПЛА"
    ),
}
PROTOCOL = {
    "imagery": (
        "Sentinel-2 L2A из Earth Search в порядке коллекций сервиса: [analysis].collection из "
        "backend/config/case.toml (sentinel-2-c1-l2a, Collection-1, baseline 05.00), при "
        "отсутствии сцены — [pairing].sentinel2_fallback; тот же прогон повторён в порядке "
        "обучающего кэша [l2a].collections (sentinel-2-l2a первым, исходные baseline 02.xx–03.01) "
        "и приведён в comparison; снимки PLP только для проверки привязки"
    ),
    "domain_shift": (
        "обучающий кэш marida_l2a собран из sentinel-2-l2a с baseline ниже 04.00 "
        "(training_cache_baselines): отрицательные отражения воды там обрезаны до DN 1 "
        "(0,0001); в Collection-1 (baseline 05.00, offset −0,1) они сохраняются, поэтому сервис "
        "и эта проверка поднимают отражения ниже 0,0001 до 0,0001 (REFLECTANCE_FLOOR); доли "
        "отрицательных и обрезанных пикселей B08 по воде записаны для каждого окна"
    ),
    "floor_diagnostic": (
        "контроль: те же окна основной коллекции с повторным подъёмом отражений ниже 0,0001; "
        "после введения REFLECTANCE_FLOOR в сервисе совпадает с основным прогоном"
    ),
    "clean_ring": (
        "в *_clean_ring только мишени, у которых в их фоновом кольце 10–30 пикс. нет ни одного "
        "пикселя не ниже порога: срабатывание там отличается от фона"
    ),
    "roles": (
        "plastic — только пластик (пакеты, бутылки, сетка HDPE); mixed — пластик с природным "
        "материалом (пакеты+тростник 2019, HDPE+дерево с 2021-09-04); natural — только "
        "природный материал (тростник 2019, деревянная мишень 2021): отрицательный контроль, "
        "в долю обнаружения пластика не входит, срабатывание на нём — ложная тревога"
    ),
    "wood_2021": (
        "вторая мишень PLP2021 — деревянные доски, круг 28 м; координат в данных PLP нет, на "
        "снимке 2021-06-11 её нет; контур — связная группа пикселей в 2–12 пикс. от мишени HDPE, "
        "где B08 выше медианы воды кольца 10–30 пикс. больше чем на max(5σ, 0,02), с наибольшей "
        "суммой превышения, на снимке той же даты из основной коллекции; ищется на всех датах "
        "2021, строки-мишени заводятся для дат после 2021-06-11 и до 2021-09-04; площадь — "
        "круг 28 м"
    ),
    "threshold": "замороженный порог detector.json, на этих данных ничего не подбиралось",
    "detected": "максимум вероятности в контуре мишени, расширенном на 1 пикс., не ниже порога",
    "zone_detected": (
        "как в сервисе: связная (8-соседство) группа пикселей не ниже порога размером не меньше "
        "min_pixels касается контура мишени, расширенного на 1 пикс."
    ),
    "postprocessing": (
        "вероятность обнуляется там, где B02 = 0, и вне маски моря sea_mask, если она есть "
        "в detector.json, — так же, как в сервисе"
    ),
    "background_ring": (
        "вода SCL=6 в 10–30 пикс. от мишеней дня (включая деревянную) и не ближе 10 пикс. к "
        "другим мишеням; тревоги — пиксели не ниже порога на км²"
    ),
    "background_window": (
        "вся вода SCL=6 окна 256×256 дальше 10 пикс. от мишеней; кластеры — связные группы "
        "пикселей не ниже порога; в сводку идут окна с долей облаков у мишеней не выше "
        "max_cloud_share"
    ),
    "usable_rule": (
        "данные на всей мишени, доля SCL 3, 8, 9, 10 в окне 64×64 без мишени не выше "
        "max_cloud_share, доля воды SCL=6 в 2–5 пикс. вокруг не ниже min_water_share"
    ),
    "size_m": (
        "сторона квадрата равной площади; площадь — сумма долей покрытия пикселей PLP "
        "(2019), площадь контура на ортофото (HDPE 2021) или круг 28 м (дерево 2021)"
    ),
    "alignment": (
        "корреляция деталей B02, B03, B04, B08 L2A со снимком PLP при целых сдвигах ±1 пикс. "
        "(привязка верна, если лучший сдвиг нулевой и корреляция не ниже min_alignment) и "
        "дробный сдвиг: максимум той же корреляции при сдвигах до ±1,5 пикс. шагом 0,5, затем "
        "0,1 (кубический сплайн); subpixel_shift — смещение содержимого L2A относительно "
        "эталона в пикселях вниз и вправо; так же сравниваются снимки двух коллекций одной даты"
    ),
    "reflectance_offset": (
        "у sentinel-2-c1-l2a применяется объявленный offset −0,1; у sentinel-2-l2a с "
        "baseline ≥ 04.00 COG уже без +1000 (DN сцены 2021-09-04 в версиях 03.01 и 05.00 "
        "совпадают, в sentinel-2-c1-l2a на 1000 выше), поэтому offset не применяется; медианы "
        "B02 и B08 по воде записаны для каждого окна"
    ),
    "zones_2022_2023": (
        "координат мишеней нет, поэтому только тревоги детектора в районе ACOLITE-обработки PLP"
    ),
}


@dataclass
class Target:
    id: str
    campaign: str
    date: str
    footprint: BaseGeometry
    area_m2: float
    material: str
    position_source: str
    role: str = "plastic"
    plp_scene: str | None = None
    state: str | None = None
    biofouling: str | None = None
    sea_state: int | None = None
    located_on: str | None = None
    anchor: bool = True

    @property
    def size_m(self) -> float:
        return math.sqrt(self.area_m2)


@dataclass
class Zone:
    id: str
    campaign: str
    date: str
    bounds: tuple[float, float, float, float]
    plp_scene: str | None
    reference: Path


def _bracketed(text: str) -> list[float]:
    return [float(value) for value in text.strip("{} ").split(",")]


def _encoding(shp: Path) -> str:
    cpg = shp.with_suffix(".cpg")
    text = cpg.read_text(errors="ignore").strip() if cpg.exists() else ""
    digits = re.search(r"\d+", text)
    if text.upper().startswith("OEM") and digits:
        return f"cp{digits.group()}"
    return text.lower() or "utf-8"


def _docx_scenes(path: Path) -> dict[str, str]:
    with zipfile.ZipFile(path) as archive:
        text = re.sub(r"<[^>]+>", " ", archive.read("word/document.xml").decode("utf-8"))
    return {name[11:19]: name for name in SCENE_PATTERN.findall(text)}


def _iso(day: str) -> str:
    return f"{day[:4]}-{day[4:6]}-{day[6:8]}"


def material_role(parts: list[str]) -> str:
    natural = [part in NATURAL for part in parts]
    if all(natural):
        return "natural"
    return "mixed" if any(natural) else "plastic"


def plp2019_targets(root: Path = PLP2019) -> list[Target]:
    scenes = _docx_scenes(next(root.glob("*.docx")))
    targets = []
    for folder in sorted((root / "Vector_Points").iterdir()):
        shp = next(folder.glob("*.shp"), None)
        if shp is None:
            continue
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            reader = shapefile.Reader(str(shp), encoding=_encoding(shp))
        names = [field[0].lower() for field in reader.fields[1:]]
        pixels = defaultdict(list)
        for record, geometry in zip(reader.records(), reader.shapes(), strict=True):
            row = dict(zip(names, list(record), strict=True))
            letter = re.match(r"[A-Za-z]+", str(row["pixel_name"])).group().upper()
            x, y = geometry.points[0]
            cover = {label: float(row.get(key) or 0) for key, label in MATERIALS_2019.items()}
            pixels[letter].append((x, y, cover))
        for letter, cells in sorted(pixels.items()):
            covered = [(x, y, cover) for x, y, cover in cells if sum(cover.values()) > 0]
            if not covered:
                continue
            totals = defaultdict(float)
            for _, _, cover in covered:
                for label, value in cover.items():
                    totals[label] += value
            area = sum(totals.values())
            parts = [
                label
                for label, value in sorted(totals.items(), key=lambda item: -item[1])
                if value >= 0.2 * area
            ]
            footprint = unary_union(
                [box(x - GRID / 2, y - GRID / 2, x + GRID / 2, y + GRID / 2) for x, y, _ in covered]
            )
            targets.append(
                Target(
                    id=f"plp2019_{folder.name}_{letter}",
                    campaign="PLP2019",
                    date=_iso(folder.name),
                    footprint=footprint,
                    area_m2=area,
                    material="+".join(parts),
                    position_source="plp_vector_points",
                    role=material_role(parts),
                    plp_scene=scenes.get(folder.name),
                )
            )
    return targets


def _unpack(archive: Path, member: str) -> Path:
    target = UNPACKED / member
    if not target.exists():
        with zipfile.ZipFile(archive) as source:
            source.extract(member, UNPACKED)
    return target


def ortho_target(path: Path) -> BaseGeometry:
    with rasterio.open(path) as dataset:
        latitude = (dataset.bounds.top + dataset.bounds.bottom) / 2
        metres = (
            dataset.res[0] * 111_320 * math.cos(math.radians(latitude)),
            dataset.res[1] * 110_574,
        )
        factor = max(1, int(ORTHO_PIXEL_M / max(metres)))
        height, width = dataset.height // factor, dataset.width // factor
        image = dataset.read(
            out_shape=(dataset.count, height, width), resampling=Resampling.average
        )
        transform = dataset.transform * Affine.scale(dataset.width / width, dataset.height / height)
        crs = dataset.crs.to_string()
    pixel = (metres[0] * dataset.width / width, metres[1] * dataset.height / height)
    red, green, blue = (image[index].astype(np.float32) for index in range(3))
    inside = image[3] > 0 if image.shape[0] > 3 else np.ones_like(red, dtype=bool)
    smooth = ndimage.uniform_filter(green, max(1, round(ORTHO_SMOOTH_M / pixel[0])))
    bright = inside & (smooth > ORTHO_GREEN) & (blue - red > ORTHO_CYAN)
    labels, count = ndimage.label(bright)
    best, best_contrast = None, -math.inf
    for index in range(1, count + 1):
        component = ndimage.binary_fill_holes(labels == index)
        area = component.sum() * pixel[0] * pixel[1]
        if not ORTHO_AREA_M2[0] <= area <= ORTHO_AREA_M2[1]:
            continue
        near = ndimage.binary_dilation(component, iterations=round(3 / pixel[0]))
        far = ndimage.binary_dilation(component, iterations=round(10 / pixel[0]))
        ring = far & ~near & inside
        if not ring.any():
            continue
        contrast = float(green[component].mean() - green[ring].mean())
        if contrast > best_contrast:
            best, best_contrast = component, contrast
    if best is None:
        raise RuntimeError("мишень на ортофото не найдена")
    polygons = [
        shape(geometry)
        for geometry, value in shapes(best.astype(np.uint8), mask=best, transform=transform)
        if value
    ]
    footprint = max(polygons, key=lambda polygon: polygon.area)
    return shape(transform_geom(crs, UTM, mapping(footprint))).simplify(0.5)


def plp2021_targets(root: Path = PLP2021) -> list[Target]:
    archive = root / "20210611.zip"
    with zipfile.ZipFile(archive) as source:
        members = source.namelist()
    ortho = next(name for name in members if name.endswith("_ortho.tif"))
    scene = next((found.group() for found in map(SCENE_PATTERN.search, members) if found), None)
    footprint = ortho_target(_unpack(archive, ortho))
    ortho_day = _iso(Path(ortho).name[:8])
    targets = []
    for day, state, biofouling, sea_state in LOG_2021:
        same = day == ortho_day
        mixed = day >= MIX_FROM
        targets.append(
            Target(
                id=f"plp2021_{day.replace('-', '')}_{'mix' if mixed else 'hdpe'}",
                campaign="PLP2021",
                date=day,
                footprint=footprint,
                area_m2=float(footprint.area),
                material="HDPE+wood mix" if mixed else "HDPE mesh",
                position_source="plp_ortho_same_day" if same else f"plp_ortho_{ortho_day}_moored",
                role="mixed" if mixed else "plastic",
                plp_scene=scene if same else None,
                state=state,
                biofouling=biofouling,
                sea_state=sea_state,
            )
        )
    return targets


def _l2w_grid(path: Path) -> tuple[tuple[float, float, float, float], dict[str, str]]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with rasterio.open(path) as dataset:
            tags = dataset.tags()
            variables = [name.split(":")[-1] for name in dataset.subdatasets]
    xs = _bracketed(tags["NC_GLOBAL#xrange"])
    ys = _bracketed(tags["NC_GLOBAL#yrange"])
    bounds = (min(xs), min(ys), max(xs), max(ys))
    chosen = {}
    for band, nm in REFERENCE_NM.items():
        options = [name for name in variables if name.startswith("rhos_")]
        chosen[band] = min(options, key=lambda name: abs(int(name.split("_")[1]) - nm))
    return bounds, chosen


def plp2022_zones(root: Path = PLP2022) -> list[Zone]:
    zones = []
    for folder in sorted(root.iterdir()):
        s2 = next(folder.glob("*_S2"), None)
        if s2 is None:
            continue
        reference = next(s2.glob("L2W/*_L2W.nc"), None)
        if reference is None:
            continue
        found = [SCENE_PATTERN.search(path.name) for path in s2.glob("*.zip")]
        bounds, _ = _l2w_grid(reference)
        zones.append(
            Zone(
                id=f"plp{folder.name[:4]}_{folder.name}_zone",
                campaign="PLP2022" if folder.name.startswith("2022") else "PLP2023",
                date=_iso(folder.name),
                bounds=bounds,
                plp_scene=next((match.group() for match in found if match), None),
                reference=reference,
            )
        )
    return zones


def target_table(targets: list[Target]) -> pd.DataFrame:
    rows = []
    for target in targets:
        lonlat = shape(transform_geom(UTM, LONLAT, mapping(target.footprint)))
        center = lonlat.centroid
        rows.append(
            {
                "target_id": target.id,
                "campaign": target.campaign,
                "date": target.date,
                "plp_scene": target.plp_scene,
                "lon": round(center.x, 6),
                "lat": round(center.y, 6),
                "size_m": round(target.size_m, 2),
                "area_m2": round(target.area_m2, 1),
                "material": target.material,
                "role": target.role,
                "position_source": target.position_source,
                "located_on_scene": target.located_on,
                "state": target.state,
                "biofouling": target.biofouling,
                "sea_state": target.sea_state,
                "footprint_wkt": wkt.dumps(lonlat, rounding_precision=6),
            }
        )
    return pd.DataFrame(rows)


def _snap(value: float) -> float:
    return math.floor(value / GRID) * GRID


def _ceil(value: float) -> float:
    return math.ceil(value / GRID) * GRID


def cover_bounds(
    bounds: tuple[float, float, float, float], pixels: int = WINDOW
) -> tuple[float, float, float, float]:
    west, south, east, north = bounds
    cx, cy = _snap((west + east) / 2), _snap((south + north) / 2)
    half = pixels * GRID / 2
    return (
        _snap(min(west, cx - half)),
        _snap(min(south, cy - half)),
        _ceil(max(east, cx + half)),
        _ceil(max(north, cy + half)),
    )


def _shape(bounds: tuple[float, float, float, float]) -> tuple[int, int]:
    return round((bounds[3] - bounds[1]) / GRID), round((bounds[2] - bounds[0]) / GRID)


def _transform(bounds: tuple[float, float, float, float]) -> Affine:
    return Affine(GRID, 0, bounds[0], 0, -GRID, bounds[3])


def _subset(window: tuple, bounds: tuple) -> tuple[slice, slice]:
    column = round((bounds[0] - window[0]) / GRID)
    line = round((window[3] - bounds[3]) / GRID)
    height, width = _shape(bounds)
    return slice(line, line + height), slice(column, column + width)


def _read_band(href: str, bounds: tuple, nearest: bool) -> np.ndarray | None:
    resampling = Resampling.nearest if nearest else Resampling.bilinear
    for attempt in range(ATTEMPTS):
        try:
            with rasterio.Env(**READ_OPTIONS), rasterio.open(href) as dataset:
                if dataset.crs.to_string() != UTM:
                    return None
                return dataset.read(
                    1,
                    window=from_bounds(*bounds, transform=dataset.transform),
                    out_shape=_shape(bounds),
                    resampling=resampling,
                    boundless=True,
                    fill_value=0,
                )
        except RasterioIOError:
            if attempt == ATTEMPTS - 1:
                raise
            time.sleep(10 * (attempt + 1))
    return None


def _baseline(item: StacItem) -> float:
    try:
        return float(item.baseline)
    except ValueError:
        return 0.0


def reflectance_scale(item: StacItem, band: str) -> tuple[float, float]:
    scale, offset = item.scales[band]
    if item.collection == HARMONIZED and _baseline(item) >= HARMONIZED_BASELINE:
        return scale, 0.0
    return scale, offset


def _raw_window(
    item: StacItem, bounds: tuple[float, float, float, float]
) -> tuple[np.ndarray, np.ndarray] | None:
    west, south, east, north = (int(value) for value in bounds)
    cached = WINDOWS / f"{item.id}_{west}_{south}_{east}_{north}_dn.npz"
    if cached.exists():
        stored = np.load(cached)
        return (stored["raw"], stored["scl"]) if stored["found"] else None
    names = [*BANDS, SCL]
    with ThreadPoolExecutor(max_workers=READERS) as pool:
        layers = list(
            pool.map(lambda band: _read_band(item.hrefs[band], bounds, band == SCL), names)
        )
    cached.parent.mkdir(parents=True, exist_ok=True)
    if any(layer is None for layer in layers):
        np.savez_compressed(cached, found=False)
        return None
    raw, scl = np.stack(layers[:-1]), layers[-1].astype(np.uint8)
    np.savez_compressed(cached, found=True, raw=raw, scl=scl)
    return raw, scl


def read_window(
    item: StacItem, bounds: tuple[float, float, float, float]
) -> tuple[np.ndarray, np.ndarray] | None:
    window = _raw_window(item, bounds)
    if window is None:
        return None
    raw, scl = window
    image = np.zeros(raw.shape, dtype=np.float32)
    for index, band in enumerate(BANDS):
        scale, offset = reflectance_scale(item, band)
        reflectance = np.maximum(raw[index] * scale + offset, REFLECTANCE_FLOOR)
        image[index] = np.where(raw[index] > 0, reflectance, 0.0)
    return image, scl


def footprint_mask(geometry: BaseGeometry, bounds: tuple) -> np.ndarray:
    height, width = _shape(bounds)
    mask = rasterize(
        [(geometry, 1)], out_shape=(height, width), transform=_transform(bounds), fill=0
    ).astype(bool)
    if not mask.any():
        point = geometry.representative_point()
        row = int((bounds[3] - point.y) // GRID)
        column = int((point.x - bounds[0]) // GRID)
        if 0 <= row < height and 0 <= column < width:
            mask[row, column] = True
    return mask


def zone_sizes(probability: np.ndarray, threshold: float) -> tuple[np.ndarray, np.ndarray]:
    labels, _ = ndimage.label(probability >= threshold, structure=np.ones((3, 3)))
    return labels, np.bincount(labels.ravel())


def count_zones(mask: np.ndarray, min_pixels: int) -> tuple[int, int]:
    labels, count = ndimage.label(mask, structure=np.ones((3, 3)))
    sizes = np.bincount(labels.ravel())[1:]
    return int(count), int((sizes >= min_pixels).sum())


def target_statistics(
    probability: np.ndarray,
    footprint: np.ndarray,
    others: np.ndarray,
    water: np.ndarray,
    valid: np.ndarray,
    threshold: float,
    ring: tuple[int, int] = RING,
    dilation: int = DILATION,
    min_pixels: int = 1,
) -> dict:
    grown = ndimage.binary_dilation(footprint, structure=np.ones((3, 3)), iterations=dilation)
    labels, sizes = zone_sizes(probability, threshold)
    touched = {int(label) for label in labels[grown & valid] if label}
    distance = ndimage.distance_transform_edt(~footprint)
    clear = (
        ndimage.distance_transform_edt(~others) >= ring[0]
        if others.any()
        else np.ones_like(footprint)
    )
    background = (distance >= ring[0]) & (distance <= ring[1]) & water & valid & clear
    alarms = int((probability[background] >= threshold).sum())
    area = background.sum() * PIXEL_KM2
    inside = probability[grown & valid]
    return {
        "footprint_pixels": int(footprint.sum()),
        "search_pixels": int((grown & valid).sum()),
        "max_probability": float(inside.max()) if inside.size else None,
        "detected": bool(inside.size and inside.max() >= threshold),
        "above_threshold_pixels": int((inside >= threshold).sum()),
        "zone_detected": any(sizes[label] >= min_pixels for label in touched),
        "zone_pixels": int(max((sizes[label] for label in touched), default=0)),
        "ring_pixels": int(background.sum()),
        "ring_mean_probability": float(probability[background].mean()) if area else None,
        "ring_alarm_pixels": alarms,
        "ring_alarms_per_km2": alarms / area if area else None,
    }


def nir_contrast(
    nir: np.ndarray, footprint: np.ndarray, others: np.ndarray, water: np.ndarray
) -> dict:
    grown = ndimage.binary_dilation(footprint, structure=np.ones((3, 3)), iterations=DILATION)
    near = ndimage.binary_dilation(others, structure=np.ones((3, 3)), iterations=CONTRAST_RING[0])
    around = _neighbourhood(footprint, *CONTRAST_RING) & water & ~near
    if not around.any():
        return {"nir_contrast": None, "nir_contrast_sigma": None}
    level = float(np.median(nir[around]))
    spread = 1.4826 * float(np.median(np.abs(nir[around] - level)))
    contrast = float(nir[grown].max()) - level
    return {
        "nir_contrast": contrast,
        "nir_contrast_sigma": contrast / spread if spread > 0 else None,
    }


def _neighbourhood(footprint: np.ndarray, low: int, high: int) -> np.ndarray:
    distance = ndimage.distance_transform_edt(~footprint)
    return (distance >= low) & (distance <= high)


def _core(footprint: np.ndarray, size: int = CORE) -> np.ndarray:
    rows, columns = np.nonzero(footprint)
    center = (int(rows.mean()), int(columns.mean()))
    core = np.zeros_like(footprint)
    core[
        max(0, center[0] - size // 2) : center[0] + size // 2,
        max(0, center[1] - size // 2) : center[1] + size // 2,
    ] = True
    return core


def quality(footprint: np.ndarray, scl: np.ndarray, valid: np.ndarray) -> dict:
    grown = ndimage.binary_dilation(footprint, structure=np.ones((3, 3)), iterations=DILATION)
    core = _core(footprint) & ~grown & valid
    around = _neighbourhood(footprint, *NEIGHBOURHOOD) & valid
    cloud = float(np.isin(scl[core], CLOUDS).mean()) if core.any() else 1.0
    water = float((scl[around] == WATER).mean()) if around.any() else 0.0
    has_data = bool(valid[grown].all())
    reason = None
    if not has_data:
        reason = "no_data"
    elif cloud > MAX_CLOUD:
        reason = "clouds"
    elif water < MIN_WATER:
        reason = "not_over_water"
    return {
        "cloud_share": cloud,
        "water_share": water,
        "footprint_scl": sorted({int(value) for value in scl[footprint]}),
        "usable": reason is None,
        "reason": reason,
    }


def _reference_l2w(path: Path, bounds: tuple) -> np.ndarray:
    grid, variables = _l2w_grid(path)
    height, width = _shape(grid)
    stack = np.zeros((len(BANDS), height, width), dtype=np.float32)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with rasterio.open(f'netcdf:"{path}":lat') as dataset:
            latitude = dataset.read(1)
    flip = latitude[0, 0] < latitude[-1, 0]
    for band, variable in variables.items():
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            with rasterio.open(f'netcdf:"{path}":{variable}') as dataset:
                values = dataset.read(1).astype(np.float32)
        values = np.where(np.isfinite(values) & (values < 1e30) & (values > 0), values, 0)
        stack[BANDS.index(band)] = values[::-1] if flip else values
    return stack[(slice(None), *_subset(grid, bounds))]


def _reference_l1c(archive: Path, bounds: tuple) -> np.ndarray:
    with zipfile.ZipFile(archive) as source:
        members = source.namelist()
    height, width = _shape(bounds)
    stack = np.zeros((len(BANDS), height, width), dtype=np.float32)
    for band in REFERENCE_NM:
        member = next(name for name in members if re.search(rf"IMG_DATA/.*_{band}\.jp2$", name))
        raw = _read_union(f"/vsizip/{archive}/{member}", UTM, bounds, nearest=False)
        stack[BANDS.index(band)] = raw.astype(np.float32) / 10_000
    return stack


def _shift_score(
    fixed: np.ndarray, moving: np.ndarray, present: np.ndarray, dy: float, dx: float
) -> float:
    offset = (0, -dy, -dx)
    shifted = ndimage.shift(moving, offset, order=3, mode="nearest", prefilter=False)
    covered = ndimage.shift(present, offset, order=1, mode="constant", cval=0.0) > 0.999
    inner = (
        slice(None),
        slice(SHIFT_BORDER, -SHIFT_BORDER),
        slice(SHIFT_BORDER, -SHIFT_BORDER),
    )
    valid = (fixed != 0)[inner] & covered[inner]
    if valid.sum() < 100:
        return float("nan")
    return float(np.corrcoef(fixed[inner][valid], shifted[inner][valid])[0, 1])


def subpixel_shift(reference: np.ndarray, image: np.ndarray) -> dict:
    fixed = _detail(reference[None][:, ALIGNMENT_BANDS].astype(np.float32))[0]
    detail = _detail(image[None][:, ALIGNMENT_BANDS].astype(np.float32))[0]
    moving = ndimage.spline_filter(detail, order=3, mode="nearest")
    present = ndimage.binary_erosion(
        detail != 0, structure=np.ones((1, 3, 3), dtype=bool), iterations=2
    ).astype(np.float32)
    center, best = (0.0, 0.0), None
    for step, reach in ((SHIFT_COARSE, SHIFT_REACH), (SHIFT_FINE, SHIFT_COARSE)):
        offsets = np.arange(-reach, reach + step / 2, step)
        scores = {}
        for dy in offsets:
            for dx in offsets:
                key = (round(center[0] + dy, 2), round(center[1] + dx, 2))
                if max(abs(key[0]), abs(key[1])) <= SHIFT_REACH:
                    scores[key] = _shift_score(fixed, moving, present, *key)
        finite = {key: value for key, value in scores.items() if value == value}
        if not finite:
            return {"subpixel_shift": None, "corr_subpixel": None, "subpixel_shift_m": None}
        center = max(finite, key=finite.get)
        best = finite[center]
    return {
        "subpixel_shift": [float(center[0]), float(center[1])],
        "corr_subpixel": best,
        "subpixel_shift_m": round(GRID * math.hypot(*center), 1),
    }


def alignment_check(reference: np.ndarray, image: np.ndarray) -> dict:
    check = scene_alignment(reference[None], image[None])
    check["aligned"] = bool(
        check["corr0"] is not None
        and check["corr0"] >= MIN_ALIGNMENT
        and check["best_shift"] == [0, 0]
    )
    return {**check, **subpixel_shift(reference, image)}


@dataclass(frozen=True)
class Reference:
    kind: str
    path: Path

    def load(self, bounds: tuple) -> tuple[tuple, np.ndarray]:
        if self.kind == "plp_l1c":
            area = cover_bounds(bounds, ALIGNMENT_WINDOW)
            return area, _reference_l1c(self.path, area)
        grid, _ = _l2w_grid(self.path)
        return grid, _reference_l2w(self.path, grid)


def _inside(outer: tuple, inner: tuple) -> bool:
    return (
        outer[0] <= inner[0]
        and outer[1] <= inner[1]
        and inner[2] <= outer[2]
        and inner[3] <= outer[3]
    )


class ServiceDetector:
    def __init__(self, folder: Path) -> None:
        self.folder = folder
        text = (folder / MANIFEST).read_bytes()
        self.manifest_sha256 = hashlib.sha256(text).hexdigest()
        self.manifest = json.loads(text)
        self.sha256 = file_sha256(folder / self.manifest["file"])
        self.model = OnnxDetector(folder, self.manifest)
        if file_sha256(folder / self.manifest["file"]) != self.sha256:
            raise RuntimeError("модель сервиса изменилась во время загрузки")
        self.threshold = float(self.manifest["threshold"])
        self.min_pixels = int(self.manifest.get("min_pixels", 1))

    def probability(self, image: np.ndarray, scl: np.ndarray) -> np.ndarray:
        manifest = self.manifest
        probability = sliding(image, self.model._run, manifest["patch"], manifest["stride"])
        return apply_service_masks(probability, image, scl, manifest)

    def unchanged(self) -> bool:
        return (
            file_sha256(self.folder / MANIFEST) == self.manifest_sha256
            and file_sha256(self.folder / self.manifest["file"]) == self.sha256
        )

    def provenance(self) -> dict:
        manifest = self.manifest
        return {
            "manifest": MANIFEST,
            "manifest_sha256": self.manifest_sha256,
            "name": manifest["name"],
            "file": manifest["file"],
            "onnx_sha256": self.sha256,
            "threshold": self.threshold,
            "patch": manifest["patch"],
            "stride": manifest["stride"],
            "scl_filter": manifest["scl_filter"],
            "sea_mask": manifest.get("sea_mask"),
            "min_pixels": self.min_pixels,
            "files_unchanged_after_run": self.unchanged(),
        }


class FlooredDetector:
    def __init__(self, detector: ServiceDetector, floor: float = FLOOR) -> None:
        self.detector = detector
        self.floor = floor
        self.threshold = detector.threshold
        self.min_pixels = detector.min_pixels

    def probability(self, image: np.ndarray, scl: np.ndarray) -> np.ndarray:
        floored = np.where(image != 0, np.maximum(image, self.floor), 0).astype(np.float32)
        return self.detector.probability(floored, scl)


def _pick(
    stac: Stac, collections: list[str], day: str, bounds: tuple, masks: list[np.ndarray]
) -> tuple[tuple[StacItem, np.ndarray, np.ndarray, list[str]] | None, str]:
    items = find_items(stac, collections, TILE, dt.date.fromisoformat(day))
    reason = "no_scene"
    for item in items:
        try:
            window = read_window(item, bounds)
        except RasterioIOError:
            reason = "read_error"
            continue
        if window is None:
            continue
        image, scl = window
        if all(mask.any() and (image[1][mask] != 0).mean() >= MIN_VALID for mask in masks):
            return (item, image, scl, [candidate.id for candidate in items]), ""
    return None, reason


def mask_polygon(mask: np.ndarray, bounds: tuple) -> BaseGeometry:
    return unary_union(
        [
            shape(geometry)
            for geometry, value in shapes(
                mask.astype(np.uint8), mask=mask, transform=_transform(bounds)
            )
            if value
        ]
    )


def wood_blob(nir: np.ndarray, anchor: np.ndarray, water: np.ndarray, valid: np.ndarray) -> dict:
    distance = ndimage.distance_transform_edt(~anchor)
    ring = (distance >= RING[0]) & (distance <= RING[1]) & water & valid
    if not ring.any():
        return {"mask": None}
    level = float(np.median(nir[ring]))
    spread = 1.4826 * float(np.median(np.abs(nir[ring] - level)))
    limit = max(BLOB_SIGMA * spread, BLOB_MIN_EXCESS)
    excess = nir - level
    search = (distance >= BLOB_SEARCH[0]) & (distance <= BLOB_SEARCH[1]) & valid
    labels, count = ndimage.label(search & (excess > limit), structure=np.ones((3, 3)))
    result = {"mask": None, "water_b08": level, "b08_limit": limit}
    if not count:
        return result
    sums = ndimage.sum(excess, labels, range(1, count + 1))
    blob = labels == int(np.argmax(sums)) + 1
    rows, columns = np.nonzero(blob)
    centre = [float(value.mean()) for value in np.nonzero(anchor)]
    result.update(
        pixels=int(blob.sum()),
        peak_b08_excess=float(excess[blob].max()),
        offset_px=[round(rows.mean() - centre[0], 1), round(columns.mean() - centre[1], 1)],
    )
    if blob.sum() >= BLOB_MIN_PIXELS:
        result["mask"] = blob
    return result


def locate_wood(
    targets: list[Target], stac: Stac, collections: list[str]
) -> tuple[list[Target], list[dict]]:
    found, log = [], []
    first = min(target.date for target in targets if target.campaign == "PLP2021")
    for target in targets:
        if target.campaign != "PLP2021":
            continue
        expected = first < target.date < MIX_FROM
        bounds = cover_bounds(target.footprint.bounds)
        anchor = footprint_mask(target.footprint, bounds)
        picked, reason = _pick(stac, collections, target.date, bounds, [anchor])
        entry = {"date": target.date, "expected": expected, "scene_id": None, "found": False}
        if picked is None:
            log.append({**entry, "reason": reason})
            continue
        item, image, scl, _ = picked
        valid = image[1] != 0
        blob = wood_blob(image[BANDS.index("B08")], anchor, scl == WATER, valid)
        mask = blob.pop("mask")
        log.append({**entry, "scene_id": item.id, "found": mask is not None, **blob})
        if mask is None or not expected:
            continue
        found.append(
            Target(
                id=f"plp2021_{target.date.replace('-', '')}_wood",
                campaign="PLP2021",
                date=target.date,
                footprint=mask_polygon(mask, bounds),
                area_m2=WOOD_AREA_M2,
                material="wood (natural)",
                position_source="s2_b08_blob_same_scene",
                role="natural",
                state=target.state,
                biofouling=target.biofouling,
                sea_state=target.sea_state,
                located_on=item.id,
                anchor=False,
            )
        )
    return found, log


def _scene_fields(item: StacItem | None, candidates: list[str]) -> dict:
    return {
        "scene_id": item.id if item else None,
        "collection": item.collection if item else None,
        "baseline": item.baseline if item else None,
        "advertised_offset": item.scales["B04"][1] if item else None,
        "applied_offset": reflectance_scale(item, "B04")[1] if item else None,
        "tile_cloud_cover": item.cloud_cover if item else None,
        "candidates": candidates,
    }


def water_levels(image: np.ndarray, water: np.ndarray) -> dict:
    levels = {
        f"water_median_{band.lower()}": float(np.median(image[BANDS.index(band)][water]))
        if water.any()
        else None
        for band in ("B02", "B08")
    }
    nir = image[BANDS.index("B08")][water]
    levels["water_b08_negative_share"] = float((nir < 0).mean()) if nir.size else None
    levels["water_b08_floor_share"] = (
        float(((nir > 0) & (nir <= CLIP_FLOOR)).mean()) if nir.size else None
    )
    return levels


def _crop(array: np.ndarray, footprint: np.ndarray, size: int = CROP) -> np.ndarray:
    rows, columns = np.nonzero(footprint)
    top = int(rows.mean()) - size // 2
    left = int(columns.mean()) - size // 2
    top = min(max(0, top), footprint.shape[0] - size)
    left = min(max(0, left), footprint.shape[1] - size)
    return array[..., top : top + size, left : left + size]


@dataclass
class Run:
    variant: str
    collections: list[str]
    frame: pd.DataFrame
    backgrounds: list[dict]
    alignment: dict
    zones: list[dict]
    crops: dict
    windows: dict


def evaluate_targets(
    targets: list[Target],
    detector: ServiceDetector,
    stac: Stac,
    collections: list[str],
    references: dict[str, Reference],
) -> tuple[list[dict], list[dict], dict, dict, dict]:
    rows, backgrounds, alignment, crops, windows = [], [], {}, {}, {}
    by_day = defaultdict(list)
    for target in targets:
        by_day[(target.campaign, target.date)].append(target)
    for (campaign, day), group in sorted(by_day.items(), key=lambda item: item[0][1]):
        anchors = unary_union([target.footprint for target in group if target.anchor])
        bounds = cover_bounds(anchors.bounds)
        masks = {target.id: footprint_mask(target.footprint, bounds) for target in group}
        picked, reason = _pick(stac, collections, day, bounds, list(masks.values()))
        if picked is None:
            for target in group:
                rows.append(
                    {
                        "target_id": target.id,
                        **_scene_fields(None, []),
                        "usable": False,
                        "reason": reason,
                    }
                )
            continue
        item, image, scl, candidates = picked
        windows[day] = (image, scl)
        valid = image[1] != 0
        water = scl == WATER
        probability = detector.probability(image, scl)
        reference = references.get(day)
        if reference is not None:
            area, original = reference.load(anchors.bounds)
            if _inside(bounds, area):
                alignment[day] = {
                    "campaign": campaign,
                    "scene_id": item.id,
                    "collection": item.collection,
                    "baseline": item.baseline,
                    "reference": reference.kind,
                    "pixels": list(_shape(area)),
                    **alignment_check(original, image[(slice(None), *_subset(bounds, area))]),
                }
        everything = np.any(list(masks.values()), axis=0)
        for target in group:
            footprint = masks[target.id]
            others = everything & ~footprint
            stats = target_statistics(
                probability,
                footprint,
                others,
                water,
                valid,
                detector.threshold,
                min_pixels=detector.min_pixels,
            )
            rows.append(
                {
                    "target_id": target.id,
                    **_scene_fields(item, candidates),
                    **quality(footprint, scl, valid),
                    **stats,
                    **nir_contrast(image[BANDS.index("B08")], footprint, others, water & valid),
                    "aligned": alignment.get(day, {}).get("aligned"),
                }
            )
            crops[target.id] = {
                "image": _crop(image, footprint),
                "probability": _crop(probability, footprint),
                "footprint": _crop(footprint, footprint),
                "others": _crop(others, footprint),
            }
        distance = ndimage.distance_transform_edt(~everything)
        ring = (distance >= RING[0]) & (distance <= RING[1]) & water & valid
        area = ring.sum() * PIXEL_KM2
        alarms = int((probability[ring] >= detector.threshold).sum())
        sea = (distance >= RING[0]) & water & valid
        sea_alarms = probability[sea] >= detector.threshold
        clusters, service_zones = count_zones(
            (probability >= detector.threshold) & sea, detector.min_pixels
        )
        backgrounds.append(
            {
                "campaign": campaign,
                "date": day,
                "scene_id": item.id,
                "collection": item.collection,
                "baseline": item.baseline,
                "ring_pixels": int(ring.sum()),
                "ring_km2": area,
                "ring_alarm_pixels": alarms,
                "ring_alarms_per_km2": alarms / area if area else None,
                "ring_mean_probability": float(probability[ring].mean()) if area else None,
                "window_water_km2": float(sea.sum() * PIXEL_KM2),
                "window_alarm_pixels": int(sea_alarms.sum()),
                "window_alarm_clusters": clusters,
                "window_zones": service_zones,
                "window_max_probability": float(probability[sea].max()) if sea.any() else None,
                "cloud_share": float(np.isin(scl[_core(everything)], CLOUDS).mean()),
                "window_cloud_share": float(np.isin(scl[valid], CLOUDS).mean()),
                **water_levels(image, water & valid),
            }
        )
    return rows, backgrounds, alignment, crops, windows


def evaluate_zones(
    zones: list[Zone], detector: ServiceDetector, stac: Stac, collections: list[str]
) -> tuple[list[dict], dict]:
    rows, windows = [], {}
    for zone in zones:
        bounds = cover_bounds(zone.bounds)
        inner = np.zeros(_shape(bounds), dtype=bool)
        inner[_subset(bounds, zone.bounds)] = True
        picked, reason = _pick(stac, collections, zone.date, bounds, [inner])
        if picked is None:
            rows.append(
                {
                    "zone_id": zone.id,
                    "date": zone.date,
                    **_scene_fields(None, []),
                    "usable": False,
                    "reason": reason,
                }
            )
            continue
        item, image, scl, candidates = picked
        windows[zone.date] = (image, scl)
        valid = (image[1] != 0) & inner
        probability = detector.probability(image, scl)
        water = valid & (scl == WATER)
        offshore = valid & ~np.isin(scl, LAND)
        alarm = (probability >= detector.threshold) & offshore
        components, service_zones = count_zones(alarm, detector.min_pixels)
        cloud = float(np.isin(scl[valid], CLOUDS).mean())
        area = water.sum() * PIXEL_KM2
        original = _reference_l2w(zone.reference, zone.bounds)
        rows.append(
            {
                "zone_id": zone.id,
                "campaign": zone.campaign,
                "date": zone.date,
                "plp_scene": zone.plp_scene,
                **_scene_fields(item, candidates),
                "bounds_utm35n": list(zone.bounds),
                "cloud_share": cloud,
                "usable": cloud <= MAX_CLOUD,
                "reason": None if cloud <= MAX_CLOUD else "clouds",
                "water_km2": area,
                "max_probability_offshore": float(probability[offshore].max())
                if offshore.any()
                else None,
                "alarm_pixels_offshore": int(alarm.sum()),
                "alarm_components_offshore": components,
                "zones_offshore": service_zones,
                "alarm_pixels_water": int((alarm & water).sum()),
                "alarms_per_km2_water": float((alarm & water).sum() / area) if area else None,
                **water_levels(image, water),
                "alignment": alignment_check(
                    original, image[(slice(None), *_subset(bounds, zone.bounds))]
                ),
            }
        )
    return rows, windows


def wilson(successes: int, total: int, z: float = 1.96) -> list[float] | None:
    if total == 0:
        return None
    rate = successes / total
    denominator = 1 + z * z / total
    center = (rate + z * z / (2 * total)) / denominator
    half = z * math.sqrt(rate * (1 - rate) / total + z * z / (4 * total * total)) / denominator
    return [max(0.0, center - half), min(1.0, center + half)]


def _size_class(size: float) -> str:
    return next(label for low, high, label in SIZE_BINS if low <= size < high)


def detection_rates(group: pd.DataFrame) -> dict:
    total = len(group)
    detected = int(group["detected"].astype(bool).sum()) if total else 0
    zones = int(group["zone_detected"].astype(bool).sum()) if total else 0
    return {
        "targets": total,
        "detected": detected,
        "detection_rate": detected / total if total else None,
        "detection_rate_ci95": wilson(detected, total),
        "zone_detected": zones,
        "zone_detection_rate": zones / total if total else None,
        "median_max_probability": float(group["max_probability"].median()) if total else None,
        "max_max_probability": float(group["max_probability"].max()) if total else None,
        "median_ring_mean_probability": float(group["ring_mean_probability"].median())
        if total
        else None,
    }


def summarize(frame: pd.DataFrame, key: str) -> dict:
    return {str(name): detection_rates(group) for name, group in frame.groupby(key, sort=True)}


def background_summary(backgrounds: list[dict]) -> dict:
    frame = pd.DataFrame(backgrounds)
    clear = frame[frame["cloud_share"] <= MAX_CLOUD]
    ring_km2 = float(clear["ring_km2"].sum())
    water_km2 = float(clear["window_water_km2"].sum())
    return {
        "windows": len(clear),
        "ring_km2": ring_km2,
        "alarm_pixels": int(clear["ring_alarm_pixels"].sum()),
        "alarms_per_km2": float(clear["ring_alarm_pixels"].sum() / ring_km2) if ring_km2 else None,
        "windows_with_alarms": int((clear["ring_alarm_pixels"] > 0).sum()),
        "median_ring_mean_probability": float(clear["ring_mean_probability"].median()),
        "window_water_km2": water_km2,
        "window_alarm_pixels": int(clear["window_alarm_pixels"].sum()),
        "window_alarm_clusters": int(clear["window_alarm_clusters"].sum()),
        "window_alarms_per_km2": float(clear["window_alarm_pixels"].sum() / water_km2)
        if water_km2
        else None,
        "window_clusters_per_100_km2": float(100 * clear["window_alarm_clusters"].sum() / water_km2)
        if water_km2
        else None,
        "window_zones": int(clear["window_zones"].sum()),
        "window_zones_per_100_km2": float(100 * clear["window_zones"].sum() / water_km2)
        if water_km2
        else None,
    }


def run_summary(run: Run) -> dict:
    frame = run.frame
    usable = frame[frame["usable"].astype(bool)]
    plastic = usable[usable["role"] != "natural"]
    natural = usable[usable["role"] == "natural"]
    zones = [row for row in run.zones if row["usable"]]
    return {
        "variant": run.variant,
        "collections": run.collections,
        "collections_used": dict(Counter(usable["collection"])),
        "baselines_used": dict(Counter(usable["baseline"])),
        "targets": len(frame),
        "usable": len(usable),
        "excluded": frame.loc[~frame["usable"].astype(bool), "reason"].value_counts().to_dict(),
        "plastic": detection_rates(usable[usable["role"] == "plastic"]),
        "mixed": detection_rates(usable[usable["role"] == "mixed"]),
        "plastic_or_mixed": detection_rates(plastic),
        "natural_controls": detection_rates(natural),
        "plastic_or_mixed_clean_ring": detection_rates(plastic[plastic["ring_alarm_pixels"] == 0]),
        "natural_controls_clean_ring": detection_rates(natural[natural["ring_alarm_pixels"] == 0]),
        "by_size": summarize(plastic, "size_class"),
        "by_material": summarize(usable, "material"),
        "by_campaign": summarize(plastic, "campaign"),
        "by_position_source": summarize(plastic, "position_source"),
        "by_state_2021": summarize(plastic[plastic["campaign"] == "PLP2021"], "state"),
        "background": background_summary(run.backgrounds),
        "zones_2022_2023": {
            "dates": len(run.zones),
            "usable": len(zones),
            "alarm_components_offshore": sum(row["alarm_components_offshore"] for row in zones),
            "zones_offshore": sum(row["zones_offshore"] for row in zones),
            "water_km2": sum(row["water_km2"] for row in zones),
            "max_probability_offshore": max(
                (row["max_probability_offshore"] or 0.0 for row in zones), default=None
            ),
        },
    }


def wood_summary(log: list[dict]) -> dict:
    expected = [entry for entry in log if entry["expected"]]
    located = [entry for entry in expected if entry["found"]]
    return {
        "expected_dates": len(expected),
        "located": len(located),
        "not_located": [entry["date"] for entry in expected if not entry["found"]],
        "found_outside_period": [
            entry["date"] for entry in log if entry["found"] and not entry["expected"]
        ],
        "median_pixels": float(np.median([entry["pixels"] for entry in located]))
        if located
        else None,
        "median_offset_px": [
            float(np.median([entry["offset_px"][axis] for entry in located])) for axis in (0, 1)
        ]
        if located
        else None,
        "median_peak_b08_excess": float(np.median([entry["peak_b08_excess"] for entry in located]))
        if located
        else None,
    }


COMPARED = (
    "scene_id",
    "collection",
    "baseline",
    "usable",
    "reason",
    "max_probability",
    "detected",
    "zone_detected",
    "ring_mean_probability",
)
LEVELS = (
    "scene_id",
    "baseline",
    "water_median_b02",
    "water_median_b08",
    "water_b08_negative_share",
    "water_b08_floor_share",
)


def collection_pair(service: tuple, legacy: tuple) -> dict:
    image, scl = service
    other, _ = legacy
    valid = (image[1] != 0) & (other[1] != 0)
    water = valid & (scl == WATER)
    nir = BANDS.index("B08")
    correlations = [
        float(np.corrcoef(image[band][valid], other[band][valid])[0, 1])
        for band in range(len(BANDS))
    ]
    return {
        "pixel_corr_median_band": float(np.nanmedian(correlations)),
        "pixel_corr_b08": correlations[nir],
        "water_b08_difference_median": float(np.median(image[nir][water] - other[nir][water]))
        if water.any()
        else None,
        **subpixel_shift(other, image),
    }


def compare_runs(service: Run, legacy: Run, pair: bool = True) -> dict:
    keys = ["target_id", "date", "role", "material", "size_m"]
    fields = list(COMPARED)
    merged = service.frame[keys + fields].merge(
        legacy.frame[["target_id", *fields]], on="target_id", suffixes=("", "_legacy")
    )
    targets = [
        {
            **{key: record[key] for key in keys},
            "service": {field: record[field] for field in fields},
            "legacy": {field: record[f"{field}_legacy"] for field in fields},
        }
        for record in merged.to_dict(orient="records")
    ]
    both = merged[merged["usable"].astype(bool) & merged["usable_legacy"].astype(bool)]
    changed = both[both["detected"].astype(bool) != both["detected_legacy"].astype(bool)]
    levels = {
        "service": {row["date"]: row for row in service.backgrounds + service.zones},
        "legacy": {row["date"]: row for row in legacy.backgrounds + legacy.zones},
    }
    windows = []
    for day in sorted(service.windows.keys() & legacy.windows.keys() if pair else []):
        windows.append(
            {
                "date": day,
                **{
                    f"{name}_{key}": levels[name].get(day, {}).get(key)
                    for name in ("service", "legacy")
                    for key in LEVELS
                },
                **collection_pair(service.windows[day], legacy.windows[day]),
            }
        )
    return {
        "variant": legacy.variant,
        "collections": legacy.collections,
        "summary": run_summary(legacy),
        "changed_detection": [
            {
                "target_id": row["target_id"],
                "service": {"max_probability": row["max_probability"], "detected": row["detected"]},
                "legacy": {
                    "max_probability": row["max_probability_legacy"],
                    "detected": row["detected_legacy"],
                },
            }
            for row in changed.to_dict(orient="records")
        ],
        "windows": windows,
        "alignment": legacy.alignment if pair else None,
        "targets": targets,
        "zones": [
            {
                key: row.get(key)
                for key in (
                    "zone_id",
                    "date",
                    "scene_id",
                    "collection",
                    "baseline",
                    "usable",
                    "max_probability_offshore",
                    "alarm_components_offshore",
                    "zones_offshore",
                )
            }
            for row in legacy.zones
        ],
        "scenes": sorted(
            {row["scene_id"] for row in legacy.backgrounds + legacy.zones if row.get("scene_id")}
        ),
    }


def _examples(frame: pd.DataFrame) -> list[pd.Series]:
    usable = frame[frame["usable"].astype(bool)].assign(
        clean=lambda rows: rows["ring_alarm_pixels"] == 0
    )
    hdpe = usable[usable["material"] == "HDPE mesh"].sort_values(["clean", "max_probability"])
    subsets = (
        hdpe,
        hdpe[hdpe["position_source"] == "plp_ortho_same_day"],
        usable[usable["material"] == "HDPE+wood mix"].sort_values("max_probability"),
        usable[usable["material"] == "wood (natural)"].sort_values("max_probability"),
    )
    chosen = [subset.iloc[-1] for subset in subsets if not subset.empty]
    small = usable[(usable["campaign"] == "PLP2019") & (usable["role"] != "natural")]
    small = small.sort_values("size_m")
    if not small.empty:
        chosen.extend([small.iloc[-1], small.iloc[0]])
    unique = {row["target_id"]: row for row in chosen}
    return list(unique.values())[:6]


def plp_figure(
    frame: pd.DataFrame, crops: dict, threshold: float, collections: list[str], path: Path
) -> Path:
    chosen = _examples(frame)
    count = max(1, len(chosen))
    figure, axes = plt.subplots(2, count, figsize=(3.1 * count, 7.2), squeeze=False)
    for column, row in enumerate(chosen):
        crop = crops[row["target_id"]]
        grown = ndimage.binary_dilation(
            crop["footprint"], structure=np.ones((3, 3)), iterations=DILATION
        )
        control = row["role"] == "natural"
        state = f" · {row['state']}" if isinstance(row["state"], str) else ""
        tag = " · контроль" if control else ""
        axes[0][column].imshow(rgb(crop["image"]), interpolation="nearest")
        axes[0][column].set_title(
            f"{row['date']} · {row['material']}{tag}\n"
            f"{row['size_m']:.1f} м ({row['area_m2']:.0f} м²){state}\n{row['baseline']}",
            fontsize=8,
        )
        axes[1][column].imshow(
            crop["probability"], vmin=0, vmax=1, cmap="magma", interpolation="nearest"
        )
        if control:
            verdict = "ложная тревога" if row["detected"] else "без срабатывания"
        else:
            verdict = "обнаружена" if row["detected"] else "не обнаружена"
        axes[1][column].set_xlabel(
            f"max p {row['max_probability']:.3f} · {verdict}\n"
            f"в кольце 10–30 пикс. выше порога: {row['ring_alarm_pixels']}",
            fontsize=8,
        )
        for axis in axes[:, column]:
            axis.contour(grown, levels=[0.5], colors=["#22e0e0"], linewidths=0.8)
            if crop["others"].any():
                axis.contour(
                    crop["others"],
                    levels=[0.5],
                    colors=["white"],
                    linewidths=0.6,
                    linestyles="dashed",
                )
            axis.set_xticks([])
            axis.set_yticks([])
    figure.suptitle(
        f"PLP, Sentinel-2 L2A ({' → '.join(collections)}): RGB и вероятность сервиса, окно "
        f"{CROP * GRID} м, порог {threshold:.3f}; голубой — мишень + {DILATION} пикс., "
        f"пунктир — другие мишени дня",
        fontsize=9,
    )
    figure.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=110)
    plt.close(figure)
    return path


def data_inventory(wood: list[dict]) -> dict:
    zip2021 = sorted(path.name for path in PLP2021.glob("*.zip"))
    return {
        "PLP2019": {
            "vector_dates": sorted(
                _iso(path.name) for path in (PLP2019 / "Vector_Points").iterdir() if path.is_dir()
            ),
            "acolite_l2w_subsets": sorted(
                path.name for path in (PLP2019 / "S2_satellite_images_nc").glob("*.nc")
            ),
            "uav_photos": len(list((PLP2019 / "UAV_photos").glob("*"))),
            "positions": POSITIONS["PLP2019"],
        },
        "PLP2021": {
            "archives_present": zip2021,
            "log_dates": [row[0] for row in LOG_2021],
            "positions": POSITIONS["PLP2021"],
            "wood_located_dates": [entry["date"] for entry in wood if entry["found"]],
        },
        "PLP2022-2023": {
            "s2_dates": [_iso(path.parent.name) for path in sorted(PLP2022.glob("*/*_S2"))],
            "planetscope_dates": [
                _iso(path.parent.name) for path in sorted(PLP2022.glob("*/*_PS"))
            ],
            "positions": POSITIONS["PLP2022-2023"],
        },
    }


def service_collections(case: dict) -> list[str]:
    order = [case["analysis"]["collection"], case["pairing"]["sentinel2_fallback"]]
    return list(dict.fromkeys(order))


def training_baselines(path: Path = TRAINING_CACHE) -> dict | None:
    if not path.exists():
        return None
    scenes = read_json(path).get("scenes", [])
    counts = Counter(
        f"{scene['collection']} {scene['baseline']}"
        for scene in scenes
        if scene.get("collection") and scene.get("baseline")
    )
    return dict(sorted(counts.items()))


def evaluate_run(
    variant: str,
    table: pd.DataFrame,
    targets: list[Target],
    zones: list[Zone],
    detector: ServiceDetector | FlooredDetector,
    stac: Stac,
    collections: list[str],
    references: dict[str, Reference],
) -> Run:
    rows, backgrounds, alignment, crops, windows = evaluate_targets(
        targets, detector, stac, collections, references
    )
    zone_rows, zone_windows = evaluate_zones(zones, detector, stac, collections)
    frame = table.drop(columns=["footprint_wkt"]).merge(pd.DataFrame(rows), on="target_id")
    frame["size_class"] = frame["size_m"].map(_size_class)
    return Run(
        variant,
        collections,
        frame,
        backgrounds,
        alignment,
        zone_rows,
        crops,
        windows | zone_windows,
    )


def run_plp(
    config_path: str = "configs/detector/data.toml",
    model: Path = MODELS / "detector" / "service",
    collections: list[str] | None = None,
) -> dict:
    config = load_config(config_path)
    case = load_config(CASE_CONFIG)
    catalog = config["l2a"]["catalog"]
    service = list(collections) if collections else service_collections(case)
    legacy = list(config["l2a"]["collections"])
    detector = ServiceDetector(model)
    stac = Stac(catalog)
    hdpe = plp2021_targets()
    wood, wood_log = locate_wood(hdpe, stac, service)
    targets = plp2019_targets() + hdpe + wood
    table = target_table(targets)
    OUT.mkdir(parents=True, exist_ok=True)
    table.to_csv(OUT / "plp_targets.csv", index=False)
    references = {
        _iso(re.search(r"_(\d{8})_", path.name).group(1)): Reference("plp_acolite_l2w", path)
        for path in sorted((PLP2019 / "S2_satellite_images_nc").glob("*_L2W_AOI.nc"))
    }
    references["2021-06-11"] = Reference("plp_l1c", PLP2021 / "20210611.zip")
    zones = plp2022_zones()
    context = (table, targets, zones)
    primary = evaluate_run("service", *context, detector, stac, service, references)
    comparison = {}
    if legacy != service:
        other = evaluate_run("legacy_collection", *context, detector, stac, legacy, references)
        comparison["legacy_collection"] = compare_runs(primary, other)
    floored = FlooredDetector(detector)
    other = evaluate_run("service_floor", *context, floored, stac, service, {})
    comparison["service_floor"] = compare_runs(primary, other, pair=False)
    figure = plp_figure(
        primary.frame, primary.crops, detector.threshold, service, FIGURES / "plp.png"
    )
    result = {
        "name": "plp",
        "description": "внешняя проверка детектора на мишенях Plastic Litter Project (Лесбос)",
        "data": data_inventory(wood_log),
        "protocol": {
            **PROTOCOL,
            "window_pixels": WINDOW,
            "footprint_dilation_pixels": DILATION,
            "background_ring_pixels": list(RING),
            "max_cloud_share": MAX_CLOUD,
            "min_water_share": MIN_WATER,
            "min_alignment": MIN_ALIGNMENT,
            "wood_search_pixels": list(BLOB_SEARCH),
            "wood_sigma": BLOB_SIGMA,
            "wood_min_b08_excess": BLOB_MIN_EXCESS,
            "wood_min_pixels": BLOB_MIN_PIXELS,
            "subpixel_reach_pixels": SHIFT_REACH,
            "subpixel_step_pixels": SHIFT_FINE,
        },
        "provenance": {
            "catalog": catalog,
            "collections": service,
            "collections_source": "--collections"
            if collections
            else "backend/config/case.toml: [analysis].collection, [pairing].sentinel2_fallback",
            "comparison_collections": legacy if "legacy_collection" in comparison else None,
            "config": config["_path"],
            "config_sha256": config["_sha256"],
            "service_config": case["_path"],
            "service_config_sha256": case["_sha256"],
            "code_fingerprint": code_fingerprint(),
            "detector": detector.provenance(),
            "training_cache_baselines": training_baselines(),
            "scenes": sorted(
                {
                    row["scene_id"]
                    for row in primary.backgrounds + primary.zones
                    if row.get("scene_id")
                }
            ),
        },
        "figure": str(figure.relative_to(REPORTS.parent)),
        "summary": {**run_summary(primary), "wood_2021": wood_summary(wood_log)},
        "alignment": primary.alignment,
        "wood_2021": wood_log,
        "targets": primary.frame.to_dict(orient="records"),
        "backgrounds": primary.backgrounds,
        "zones": primary.zones,
        "comparison": comparison,
    }
    write_json(OUT / "plp.json", result)
    return result
