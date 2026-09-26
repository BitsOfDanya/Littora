"""MARIDA raster contract, pixel extraction and label-independent dependency groups."""
from datetime import datetime
from pathlib import Path
import hashlib

import numpy as np
import pandas as pd
import rasterio
from rasterio.warp import transform
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components
from sklearn.metrics.pairwise import haversine_distances

CLASSES = {
    0: "Unlabelled / ignore", 1: "Marine Debris", 2: "Dense Sargassum", 3: "Sparse Sargassum",
    4: "Natural Organic Material", 5: "Ship", 6: "Clouds", 7: "Marine Water",
    8: "Sediment-Laden Water", 9: "Foam", 10: "Turbid Water", 11: "Shallow Water",
    12: "Waves", 13: "Cloud Shadows", 14: "Wakes", 15: "Mixed Water",
}
# Band order verified against the authors' utils/assets.py (s2_mapping).
BANDS = ["B01", "B02", "B03", "B04", "B05", "B06", "B07", "B08", "B8A", "B11", "B12"]
WAVELENGTHS = [440, 490, 560, 665, 705, 740, 783, 842, 865, 1600, 2200]
NATIVE_RESOLUTION = [60, 10, 10, 10, 20, 20, 20, 10, 20, 20, 20]


def digest_array(array):
    return hashlib.sha256(array.tobytes()).hexdigest()


def read_split_files(root):
    rows = []
    for split in ("train", "val", "test"):
        path = root / "splits" / f"{split}_X.txt"
        for patch_id in path.read_text().splitlines():
            if patch_id.strip():
                rows.append({"patch_id": patch_id.strip().removeprefix("S2_"), "original_split": split})
    frame = pd.DataFrame(rows)
    assert frame.patch_id.is_unique, "Repeated patch ID in source split files"
    return frame


def scan_dataset(root, processed):
    paths = sorted(p for p in (root / "patches").rglob("*.tif")
                   if not p.name.endswith(("_cl.tif", "_conf.tif")))
    split = read_split_files(root).set_index("patch_id").original_split
    rows, bands, confidence_counts = [], [], []
    xs, ys, cs, ps, rs, cols = [], [], [], [], [], []
    for i, path in enumerate(paths):
        patch_id = path.stem.removeprefix("S2_")
        date_text, tile, crop = patch_id.split("_")
        date = datetime.strptime(date_text, "%d-%m-%y").date().isoformat()
        label_path = path.with_name(path.stem + "_cl.tif")
        conf_path = path.with_name(path.stem + "_conf.tif")
        with rasterio.open(path) as image, rasterio.open(label_path) as labels, rasterio.open(conf_path) as conf:
            assert image.count == 11 and image.width == image.height == 256, path
            assert labels.count == conf.count == 1
            assert image.crs is not None and image.crs == labels.crs == conf.crs
            assert image.transform == labels.transform == conf.transform
            assert image.shape == labels.shape == conf.shape
            assert np.allclose(image.res, (10, 10))
            x, yf, cf = image.read(), labels.read(1), conf.read(1)
            assert np.isfinite(yf).all() and np.isfinite(cf).all()
            assert np.equal(yf, yf.astype(int)).all() and np.equal(cf, cf.astype(int)).all()
            y, c = yf.astype(np.uint8), cf.astype(np.uint8)
            assert np.isin(y, list(CLASSES)).all() and np.isin(c, [0, 1, 2, 3]).all()
            valid = np.isfinite(x).all(axis=0) & (image.read_masks() > 0).all(axis=0)
            labelled = y > 0
            usable = labelled & valid & (c > 0)
            lon, lat = transform(image.crs, "EPSG:4326", [image.bounds.left + 1280], [image.bounds.bottom + 1280])
            counts = np.bincount(y.ravel(), minlength=16)
            record = dict(patch_index=i, patch_id=patch_id, scene_id="_".join(patch_id.split("_")[:2]),
                date=date, tile=tile, crop=crop, image_path=str(path.relative_to(root)),
                label_path=str(label_path.relative_to(root)), confidence_path=str(conf_path.relative_to(root)),
                original_split=split.loc[patch_id], longitude=lon[0], latitude=lat[0], crs=image.crs.to_string(),
                resolution_x=image.res[0], resolution_y=image.res[1], bands=image.count, dtype=image.dtypes[0],
                nodata=image.nodata, scales=str(image.scales), offsets=str(image.offsets),
                left=image.bounds.left, bottom=image.bounds.bottom, right=image.bounds.right, top=image.bounds.top,
                pixels=y.size, annotated_pixels=int(labelled.sum()), valid_image_pixels=int(valid.sum()),
                usable_pixels=int(usable.sum()), invalid_annotated_pixels=int((labelled & ~valid).sum()),
                labelled_without_confidence=int((labelled & (c == 0)).sum()),
                confidence_without_label=int(((c > 0) & ~labelled).sum()),
                negative_band_values=int((x < 0).sum()), above_one_band_values=int((x > 1).sum()),
                nonfinite_band_values=int((~np.isfinite(x)).sum()),
                image_sha256=digest_array(x), label_sha256=digest_array(y), confidence_sha256=digest_array(c),
                **{f"class_{k}": int(counts[k]) for k in range(16)})
            rows.append(record)
            for k in range(1, 16):
                for level in range(4):
                    n = int(((y == k) & (c == level)).sum())
                    if n:
                        confidence_counts.append(dict(patch_index=i, class_id=k, confidence=level, pixels=n))
            for b, name in enumerate(BANDS):
                values = x[b][np.isfinite(x[b])]
                bands.append(dict(patch_index=i, band=name, n=len(values), min=float(values.min()), max=float(values.max()),
                                  mean=float(values.mean(dtype=np.float64)), std=float(values.std(dtype=np.float64)),
                                  negatives=int((values < 0).sum()), above_one=int((values > 1).sum())))
            rr, cc = np.where(usable)
            xs.append(x[:, usable].T)
            ys.append(y[usable]); cs.append(c[usable]); ps.append(np.full(len(rr), i, dtype=np.uint16))
            rs.append(rr.astype(np.uint16)); cols.append(cc.astype(np.uint16))
        if (i + 1) % 200 == 0:
            print(f"Read {i+1}/{len(paths)} patches", flush=True)
    patches = pd.DataFrame(rows)
    assert set(patches.patch_id) == set(split.index), "Files and official splits differ"
    pixels = dict(x=np.concatenate(xs), y=np.concatenate(ys), confidence=np.concatenate(cs),
                  patch_index=np.concatenate(ps), row=np.concatenate(rs), col=np.concatenate(cols))
    processed.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(processed / "annotated_pixels.npz", **pixels)
    return patches, pd.DataFrame(bands), pd.DataFrame(confidence_counts), pixels


def assign_strict_split(patches, config):
    coords = np.radians(patches[["latitude", "longitude"]].to_numpy())
    distance = haversine_distances(coords) * 6371.0088
    dates = pd.to_datetime(patches.date).dt.as_unit("ns").astype("int64").to_numpy() / 86400e9
    days = np.abs(dates[:, None] - dates[None, :])
    scene = patches.scene_id.to_numpy()
    hashes = patches.image_sha256.to_numpy()
    same_scene = scene[:, None] == scene[None, :]
    # Centers within 100 km on one date conservatively join neighboring tiles of one acquisition.
    same_day_near = (days == 0) & (distance <= config["same_day_distance_km"])
    spacetime_near = (days <= config["link_days"]) & (distance <= config["link_distance_km"])
    duplicate = hashes[:, None] == hashes[None, :]
    adjacency = same_scene | same_day_near | spacetime_near | duplicate
    _, groups = connected_components(csr_matrix(adjacency), directed=False)
    result = patches.copy()
    result["group"] = [f"M{x:03d}" for x in groups]
    priority = {name: i for i, name in enumerate(config["evaluation"]["split_priority"])}
    destination = result.groupby("group").original_split.agg(lambda x: max(x, key=priority.get))
    result["split"] = result.group.map(destination)
    audit = []
    for version, field in [("official", "original_split"), ("strict", "split")]:
        for a, b in [("train", "val"), ("train", "test"), ("val", "test")]:
            ia, ib = np.where(result[field] == a)[0], np.where(result[field] == b)[0]
            ix = np.ix_(ia, ib)
            audit.append(dict(version=version, first=a, second=b,
                shared_patch_ids=len(set(result.iloc[ia].patch_id) & set(result.iloc[ib].patch_id)),
                shared_scenes=len(set(result.iloc[ia].scene_id) & set(result.iloc[ib].scene_id)),
                shared_groups=len(set(result.iloc[ia].group) & set(result.iloc[ib].group)),
                exact_duplicate_edges=int(duplicate[ix].sum()), same_day_near_edges=int(same_day_near[ix].sum()),
                spacetime_near_edges=int(spacetime_near[ix].sum()), all_dependency_edges=int(adjacency[ix].sum()),
                shared_tiles=len(set(result.iloc[ia].tile) & set(result.iloc[ib].tile))))
    audit = pd.DataFrame(audit)
    assert audit.loc[audit.version == "strict", "all_dependency_edges"].eq(0).all()
    assert set(result.split) == {"train", "val", "test"}
    assert (result.loc[result.original_split == "test", "split"] == "test").all()
    return result, audit
