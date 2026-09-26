"""Acquire matched radiometry diagnostics and a prediction-blind Black Sea review pack."""

import hashlib
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd
import rasterio
import requests
from pyproj import Transformer
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio.warp import reproject, transform_bounds
from rasterio.windows import from_bounds

matplotlib.use("Agg")
import joblib
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml"))
from marida.models import confusion, scores_from_counts

BANDS = ["B01", "B02", "B03", "B04", "B05", "B06", "B07", "B08", "B8A", "B11", "B12"]
ASSETS = [
    "coastal",
    "blue",
    "green",
    "red",
    "rededge1",
    "rededge2",
    "rededge3",
    "nir",
    "nir08",
    "swir16",
    "swir22",
]
STAC = "https://earth-search.aws.element84.com/v1"
COLLECTION = "sentinel-2-c1-l2a"
RAW = ROOT / "data/external/validation-bridge"
OUT = ROOT / "reports/validation_bridge"
PATCHES = ["22-12-20_18QYF_0", "27-1-19_16PCC_28", "20-4-18_30VWH_4", "24-4-19_36JUN_0"]
AOIS = [
    ("novorossiysk", 37.831, 44.660),
    ("sochi", 39.700, 43.550),
    ("batumi", 41.610, 41.665),
    ("sinop", 35.125, 42.065),
    ("burgas", 27.495, 42.460),
    ("constanta", 28.680, 44.150),
]
GDAL = {
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif",
    "GDAL_HTTP_MAX_RETRY": "3",
    "GDAL_HTTP_RETRY_DELAY": "1",
    "GDAL_PAM_ENABLED": "NO",
}


def search(bbox, start, end, key):
    path = RAW / "stac" / f"{key}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "collections": [COLLECTION],
        "bbox": bbox,
        "datetime": f"{start}T00:00:00Z/{end}T23:59:59Z",
        "limit": 100,
    }
    if path.exists():
        return json.loads(path.read_text())["features"]
    r = requests.post(STAC + "/search", json=body, timeout=60)
    r.raise_for_status()
    result = r.json()
    # Earth Search can emit a next link even for a short page; follow it to exhaustion.
    features = list(result["features"])
    page = result
    seen = set()
    while page["features"]:
        next_link = next((l for l in page.get("links", []) if l["rel"] == "next"), None)
        if next_link is None:
            break
        marker = json.dumps(next_link, sort_keys=True)
        assert marker not in seen, "pagination loop"
        seen.add(marker)
        if next_link.get("method", "GET") == "POST":
            next_body = (
                {**body, **next_link.get("body", {})}
                if next_link.get("merge", False)
                else next_link.get("body", body)
            )
            r = requests.post(next_link["href"], json=next_body, timeout=60)
        else:
            r = requests.get(next_link["href"], timeout=60)
        r.raise_for_status()
        page = r.json()
        features.extend(page["features"])
    assert len({i["id"] for i in features}) == len(features), "duplicate page"
    result["features"] = features
    path.write_text(json.dumps(result))
    return result["features"]


def reflectance(raw, valid, meta):
    if "scale" not in meta or "offset" not in meta:
        raise ValueError("Missing radiometric scale/offset")
    values = raw.astype("float32") * meta["scale"] + meta["offset"]
    values[~valid | (raw == meta.get("nodata", 0))] = np.nan
    return values


def read_asset(item, key, profile):
    asset = item["assets"][key]
    meta = asset["raster:bands"][0]
    with rasterio.Env(**GDAL), rasterio.open(asset["href"]) as ds:
        bounds = rasterio.transform.array_bounds(
            profile["height"], profile["width"], profile["transform"]
        )
        sb = transform_bounds(profile["crs"], ds.crs, *bounds, densify_pts=21)
        window = from_bounds(*sb, ds.transform).round_offsets().round_lengths()
        # Expand by one native cell for rounding/reprojection at crop boundaries.
        window = rasterio.windows.Window(
            window.col_off - 1, window.row_off - 1, window.width + 2, window.height + 2
        )
        raw = ds.read(
            1, window=window, boundless=True, fill_value=meta.get("nodata", 0)
        )
        valid = ds.read_masks(1, window=window, boundless=True) > 0
        valid &= raw != meta.get("nodata", ds.nodata)
        if key == "scl":
            values = raw.astype("float32")
        else:
            values = reflectance(raw, valid, meta)
        values[~valid] = np.nan
        dest = np.full((profile["height"], profile["width"]), np.nan, dtype="float32")
        reproject(
            values,
            dest,
            src_transform=ds.window_transform(window),
            src_crs=ds.crs,
            dst_transform=profile["transform"],
            dst_crs=profile["crs"],
            src_nodata=np.nan,
            dst_nodata=np.nan,
            resampling=Resampling.nearest,
        )
    return dest


def quality(scl):
    return {
        "nodata_fraction": float((~np.isfinite(scl)).mean()),
        "cloud_fraction": float(np.isin(scl, [3, 8, 9, 10, 11]).mean()),
        "water_fraction": float((scl == 6).mean()),
    }


def save_tif(path, array, profile, descriptions=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    if array.ndim == 2:
        array = array[None]
    meta = profile.copy()
    meta.update(
        driver="GTiff",
        count=len(array),
        dtype=array.dtype,
        compress="deflate",
        nodata=np.nan if np.issubdtype(array.dtype, np.floating) else 0,
    )
    with rasterio.open(path, "w", **meta) as dst:
        dst.write(array)
        if descriptions:
            dst.descriptions = tuple(descriptions)


def has_annotations(folder):
    for path in folder.rglob("review.json"):
        if json.loads(path.read_text()).get("status", "pending") != "pending":
            return True
    for path in folder.rglob("annotations.geojson"):
        if json.loads(path.read_text()).get("features"):
            return True
    for path in folder.rglob("labels.tif"):
        with rasterio.open(path) as ds:
            if ds.read().any():
                return True
    return False


def acquire(item, profile, folder):
    folder.mkdir(parents=True, exist_ok=True)
    metadata_path = folder / "stac.json"
    cached_id = (
        json.loads(metadata_path.read_text())["id"] if metadata_path.exists() else None
    )
    if cached_id is not None and cached_id != item["id"] and has_annotations(folder):
        raise ValueError(
            "Cannot replace imagery with existing annotations; use a new chip ID"
        )
    path = folder / "l2a.tif"
    sp = folder / "scl.tif"
    if path.exists() and sp.exists() and cached_id == item["id"]:
        with rasterio.open(path) as ds:
            x = ds.read()
        with rasterio.open(sp) as ds:
            scl = ds.read(1)
        return x, scl
    with ThreadPoolExecutor(max_workers=4) as pool:
        bands = list(
            pool.map(lambda key: read_asset(item, key, profile), ASSETS + ["scl"])
        )
    x = np.stack(bands[:-1])
    scl = bands[-1]
    save_tif(path, x, profile, BANDS)
    save_tif(sp, scl, profile, ["SCL"])
    metadata_path.write_text(json.dumps(item))
    return x, scl


def preview(x, path, title):
    def stretch(a):
        finite = a[np.isfinite(a)]
        low, high = np.quantile(finite, [0.02, 0.98]) if len(finite) else (0, 1)
        return np.clip((np.nan_to_num(a) - low) / max(high - low, 1e-6), 0, 1)

    fig, axes = plt.subplots(1, 2, figsize=(8, 4))
    for ax, channels, label in zip(
        axes, [[3, 2, 1], [7, 3, 2]], ["RGB", "NIR / red / green"]
    ):
        ax.imshow(np.stack([stretch(x[b]) for b in channels], axis=-1))
        ax.set_title(label)
        ax.axis("off")
    fig.suptitle(title, fontsize=10)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=130, bbox_inches="tight")
    plt.close(fig)


def paired():
    inventory = pd.read_csv(
        ROOT / "reports/marida/tables/patch_inventory.csv"
    ).set_index("patch_id")
    model = joblib.load(ROOT / "data/processed/marida_baseline/spectral_forest.joblib")
    metadata = json.loads(
        (ROOT / "data/processed/marida_baseline/model_metadata.json").read_text()
    )
    threshold = next(
        x["threshold"]
        for x in metadata["thresholds"]
        if x["model"] == "spectral_forest"
    )
    splits = pd.read_csv(ROOT / "reports/marida/tables/split_membership.csv").set_index(
        "patch_id"
    )["split"]
    rows = []
    stats = []
    metrics = []
    for patch in PATCHES:
        row = inventory.loc[patch]
        source = ROOT / "data/external/marida" / row.image_path
        with rasterio.open(source) as ds:
            rhorc = ds.read()
            profile = ds.profile
            bounds = transform_bounds(ds.crs, "EPSG:4326", *ds.bounds)
        profile = {k: profile[k] for k in ["height", "width", "crs", "transform"]}
        items = search(list(bounds), row.date, row.date, "pair-" + patch)
        items = [i for i in items if i["properties"]["grid:code"] == "MGRS-" + row.tile]
        if len(items) != 1:
            rows.append(
                {
                    "patch_id": patch,
                    "date": row.date,
                    "tile": row.tile,
                    "match_status": "missing" if not items else "ambiguous",
                    "candidate_count": len(items),
                }
            )
            print("unpaired", patch, len(items), flush=True)
            continue
        item = items[0]
        folder = RAW / "paired" / patch
        l2a, scl = acquire(item, profile, folder)
        with rasterio.open(ROOT / "data/external/marida" / row.label_path) as ds:
            y = ds.read(1).astype("uint8")
        with rasterio.open(ROOT / "data/external/marida" / row.confidence_path) as ds:
            confidence = ds.read(1)
        valid = np.isfinite(rhorc).all(axis=0) & np.isfinite(l2a).all(axis=0)
        use = valid & (y > 0) & (confidence > 0)
        save_tif(folder / "rhorc.tif", rhorc, profile, BANDS)
        save_tif(folder / "reference_labels.tif", y, profile, ["MARIDA class"])
        preview(
            l2a,
            OUT / "figures" / f"paired_{patch}.png",
            f"{patch} — L2A; radiometry diagnostic",
        )
        rows.append(
            dict(
                patch_id=patch,
                date=row.date,
                tile=row.tile,
                match_status="paired",
                candidate_count=1,
                stac_id=item["id"],
                product_uri=item["properties"]["s2:product_uri"],
                satellite_datetime=item["properties"]["datetime"],
                match_method="unique_tile_date_footprint; original_product_id_unavailable",
                source_image=str(source.relative_to(ROOT)),
                paired_folder=str(folder.relative_to(ROOT)),
                common_valid_pixels=int(valid.sum()),
                common_labelled_pixels=int(use.sum()),
                positive_pixels=int(((y == 1) & use).sum()),
                **quality(scl),
            )
        )
        for b, band in enumerate(BANDS):
            for scope, mask in [
                ("all_common_labelled", use),
                ("SCL_water_labelled", use & (scl == 6)),
            ]:
                if not mask.any():
                    continue
                diff = l2a[b, mask] - rhorc[b, mask]
                m = item["assets"][ASSETS[b]]["raster:bands"][0]
                stats.append(
                    {
                        "patch_id": patch,
                        "band": band,
                        "scope": scope,
                        "pixels": int(mask.sum()),
                        "rhorc_median": float(np.median(rhorc[b, mask])),
                        "l2a_median": float(np.median(l2a[b, mask])),
                        "median_l2a_minus_rhorc": float(np.median(diff)),
                        "mean_abs_difference": float(abs(diff).mean()),
                        "scale": m["scale"],
                        "offset": m["offset"],
                    }
                )
        for product, x in [("rhorc", rhorc), ("L2A_stress_only", l2a)]:
            score = model.predict_proba(x[:, use].T)[:, 1]
            counts = confusion(y[use] == 1, score >= threshold)
            metrics.append(
                dict(
                    patch_id=patch,
                    original_split=splits[patch],
                    product=product,
                    threshold=threshold,
                    **counts,
                    **scores_from_counts(**counts),
                )
            )
        print("paired", patch, int(use.sum()), flush=True)
    for name, data in [
        ("radiometry_pairs", rows),
        ("radiometry_differences", stats),
        ("radiometry_stress_metrics", metrics),
    ]:
        pd.DataFrame(data).to_csv(OUT / "tables" / f"{name}.csv", index=False)


def holdout():
    rows = []
    audit = []
    features = []
    for area, lon, lat in AOIS:
        epsg = 32600 + int((lon + 180) // 6) + 1
        tx = Transformer.from_crs(4326, epsg, always_xy=True)
        x, y = tx.transform(lon, lat)
        x = np.floor(x / 10) * 10
        y = np.floor(y / 10) * 10
        profile = {
            "height": 256,
            "width": 256,
            "crs": f"EPSG:{epsg}",
            "transform": from_origin(x - 1280, y + 1280, 10, 10),
        }
        bbox = transform_bounds(
            profile["crs"],
            "EPSG:4326",
            *rasterio.transform.array_bounds(256, 256, profile["transform"]),
        )
        for month, last in [("06", "30"), ("09", "30")]:
            key = f"{area}-2025-{month}"
            items = search(list(bbox), f"2025-{month}-01", f"2025-{month}-{last}", key)
            items = sorted(
                (i for i in items if i["properties"]["eo:cloud_cover"] <= 20),
                key=lambda i: (i["properties"]["datetime"], i["id"]),
            )
            selected = None
            folder = RAW / "blacksea_holdout" / key
            for item in items:
                scl = read_asset(item, "scl", profile)
                q = quality(scl)
                ok = (
                    q["nodata_fraction"] == 0
                    and q["cloud_fraction"] <= 0.10
                    and q["water_fraction"] >= 0.60
                )
                row = dict(
                    chip_id=key,
                    stac_id=item["id"],
                    **q,
                    accepted=False,
                    reason="SCL_quality",
                )
                if ok:
                    image, scl = acquire(item, profile, folder)
                    row["all_band_valid_fraction"] = float(
                        np.isfinite(image).all(axis=0).mean()
                    )
                    ok = bool(np.isfinite(image).all())
                    row.update(
                        accepted=ok, reason="accepted" if ok else "spectral_nodata"
                    )
                audit.append(row)
                if ok:
                    selected = item
                    break
            if selected is None:
                rows.append(
                    {
                        "chip_id": key,
                        "area": area,
                        "review_status": "no_eligible_scene",
                        "training_allowed": False,
                    }
                )
                continue
            labels = folder / "labels.tif"
            # Never overwrite a person's existing annotation when reacquiring images.
            if not labels.exists():
                save_tif(
                    labels,
                    np.zeros((256, 256), dtype="uint8"),
                    profile,
                    ["0=ignore; pending independent review"],
                )
            annotation = folder / "annotations.geojson"
            if not annotation.exists():
                annotation.write_text(
                    json.dumps({"type": "FeatureCollection", "features": []})
                )
            preview(
                image,
                OUT / "figures" / f"{key}.png",
                key + " | unlabelled reserved holdout",
            )
            rows.append(
                dict(
                    chip_id=key,
                    area=area,
                    longitude=lon,
                    latitude=lat,
                    date=selected["properties"]["datetime"][:10],
                    satellite_datetime=selected["properties"]["datetime"],
                    stac_id=selected["id"],
                    product_uri=selected["properties"]["s2:product_uri"],
                    folder=str(folder.relative_to(ROOT)),
                    preview=f"figures/{key}.png",
                    review_status="pending_two_reviewers",
                    split="reserved_holdout",
                    training_allowed=False,
                    reference_pixels=0,
                    model_predictions_computed=False,
                    **quality(scl),
                )
            )
            west, south, east, north = bbox
            features.append(
                {
                    "type": "Feature",
                    "id": key,
                    "properties": {
                        "chip_id": key,
                        "split": "reserved_holdout",
                        "date": selected["properties"]["datetime"][:10],
                    },
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [
                                [west, south],
                                [east, south],
                                [east, north],
                                [west, north],
                                [west, south],
                            ]
                        ],
                    },
                }
            )
            print("holdout", key, selected["id"], flush=True)
    pd.DataFrame(rows).to_csv(OUT / "tables/blacksea_holdout_registry.csv", index=False)
    pd.DataFrame(audit).to_csv(OUT / "tables/blacksea_scene_selection.csv", index=False)
    (OUT / "blacksea_holdout_footprints.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, indent=2)
    )


def main():
    (OUT / "tables").mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    paired()
    holdout()
    checks = []
    for p in RAW.rglob("*"):
        if p.is_file():
            checks.append(
                {
                    "path": str(p.relative_to(ROOT)),
                    "bytes": p.stat().st_size,
                    "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                }
            )
    pd.DataFrame(checks).to_csv(OUT / "tables/imagery_hashes.csv", index=False)


if __name__ == "__main__":
    main()
