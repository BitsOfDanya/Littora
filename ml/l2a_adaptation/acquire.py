"""Acquire a predeclared stratified set of paired MARIDA / Sentinel-2 L2A patches."""

import argparse
import hashlib
import json
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
import requests
from rasterio.warp import transform_bounds

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml"))
from validation_bridge import imagery

RAW = ROOT / "data/external/l2a-adaptation"
OUT = ROOT / "reports/l2a_adaptation"
CACHE = ROOT / "data/processed/l2a_adaptation"
imagery.RAW = RAW
NEGATIVE = [c for c in range(2, 16)]


def inventory():
    p = pd.read_csv(ROOT / "reports/marida/tables/patch_inventory.csv")
    s = pd.read_csv(ROOT / "reports/marida/tables/split_membership.csv")
    return p.merge(
        s[["patch_id", "split", "group"]], on="patch_id", validate="one_to_one"
    )


def scene_lookup(item):
    scene, part = item
    boxes = []
    for r in part.itertuples():
        boxes.append(
            transform_bounds(r.crs, "EPSG:4326", r.left, r.bottom, r.right, r.top)
        )
    boxes = np.array(boxes)
    bbox = [boxes[:, 0].min(), boxes[:, 1].min(), boxes[:, 2].max(), boxes[:, 3].max()]
    first = part.iloc[0]
    try:
        items = imagery.search(bbox, first.date, first.date, "scene-" + scene)
        matched = [
            i for i in items if i["properties"]["grid:code"] == "MGRS-" + first.tile
        ]
        row = {
            "scene_id": scene,
            "date": first.date,
            "tile": first.tile,
            "split": first["split"],
            "group": first.group,
            "match_status": "paired"
            if len(matched) == 1
            else ("missing" if not matched else "ambiguous"),
            "candidate_count": len(matched),
            "stac_id": matched[0]["id"] if len(matched) == 1 else "",
        }
        if len(matched) == 1:
            (RAW / "scenes").mkdir(exist_ok=True)
            (RAW / "scenes" / f"{scene}.json").write_text(json.dumps(matched[0]))
    except (
        requests.RequestException,
        OSError,
        rasterio.errors.RasterioError,
        ValueError,
    ) as exc:
        row = {
            "scene_id": scene,
            "date": first.date,
            "tile": first.tile,
            "split": first["split"],
            "group": first.group,
            "match_status": "request_error",
            "error": str(exc),
            "candidate_count": 0,
        }
    print("scene", scene, row["match_status"], flush=True)
    return row


def select_patches(part):
    selected = list(
        part[part.class_1 > 0]
        .sort_values(["class_1", "patch_id"], ascending=[False, True])
        .head(3)
        .index
    )
    covered = {
        c for c in NEGATIVE if selected and part.loc[selected, f"class_{c}"].sum() > 0
    }
    while len(selected) < min(6, len(part)):
        remaining = part.drop(index=selected).copy()
        remaining["new_classes"] = sum(
            (remaining[f"class_{c}"] > 0).astype(int)
            for c in NEGATIVE
            if c not in covered
        )
        remaining["background_weight"] = sum(
            np.sqrt(remaining[f"class_{c}"]) for c in NEGATIVE
        )
        best = remaining.sort_values(
            ["new_classes", "background_weight", "patch_id"],
            ascending=[False, False, True],
        ).index[0]
        selected.append(best)
        covered.update(c for c in NEGATIVE if part.loc[best, f"class_{c}"] > 0)
    return part.loc[selected].copy()


def prepare():
    p = inventory()
    rows = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        tasks = [
            pool.submit(scene_lookup, entry)
            for entry in p.groupby("scene_id", sort=True)
        ]
        for f in as_completed(tasks):
            rows.append(f.result())
    scenes = pd.DataFrame(rows).sort_values("scene_id")
    scenes.to_csv(OUT / "tables/scene_search.csv", index=False)
    eligible = set(scenes.loc[scenes.match_status == "paired", "scene_id"])
    selected = pd.concat(
        [
            select_patches(part)
            for scene, part in p.groupby("scene_id", sort=True)
            if scene in eligible
        ]
    )
    selected = selected.sort_values(["split", "scene_id", "patch_id"]).reset_index(
        drop=True
    )
    selected["selection_index"] = np.arange(len(selected))
    # Pre-training protocol amendment: cover the missing Foam class in train only.
    if selected.loc[selected["split"] == "train", "class_9"].sum() == 0:
        candidates = p[
            (p["split"] == "train")
            & p.scene_id.isin(eligible)
            & (p.class_9 > 0)
            & ~p.patch_id.isin(selected.patch_id)
        ]
        if not candidates.empty:
            initial = OUT / "tables/selection_initial_189.csv"
            if not initial.exists():
                selected.to_csv(initial, index=False)
            extra = (
                candidates.sort_values(["class_9", "patch_id"], ascending=[False, True])
                .head(1)
                .copy()
            )
            extra["selection_index"] = len(selected)
            selected = pd.concat([selected, extra], ignore_index=True)
    path = OUT / "tables/selected_patches.csv"
    if path.exists():
        assert pd.read_csv(path).patch_id.tolist() == selected.patch_id.tolist(), (
            "Selection changed; create another version"
        )
    else:
        selected.to_csv(path, index=False)
    assert selected.groupby("group")["split"].nunique().max() == 1
    print(
        "Selected",
        len(selected),
        "patches;",
        selected.groupby("split").scene_id.nunique().to_dict(),
        flush=True,
    )


def fetch_patch(row):
    folder = RAW / "patches" / row.patch_id
    try:
        item = json.loads((RAW / "scenes" / f"{row.scene_id}.json").read_text())
        source = ROOT / "data/external/marida" / row.image_path
        with rasterio.open(source) as ds:
            profile = {
                k: ds.profile[k] for k in ["height", "width", "crs", "transform"]
            }
        old = ROOT / "data/external/validation-bridge/paired" / row.patch_id
        if not folder.exists() and (old / "l2a.tif").exists():
            folder.mkdir(parents=True)
            for name in ["l2a.tif", "scl.tif", "stac.json"]:
                shutil.copy2(old / name, folder / name)
        x, scl = imagery.acquire(item, profile, folder)
        result = dict(
            patch_id=row.patch_id,
            status="downloaded",
            stac_id=item["id"],
            all_band_valid_fraction=float(np.isfinite(x).all(axis=0).mean()),
            **imagery.quality(scl),
        )
    except (
        requests.RequestException,
        OSError,
        rasterio.errors.RasterioError,
        ValueError,
    ) as exc:
        result = {
            "patch_id": row.patch_id,
            "status": "download_error",
            "error": str(exc),
        }
    print("patch", row.patch_id, result["status"], flush=True)
    return result


def download():
    selected = pd.read_csv(OUT / "tables/selected_patches.csv")
    results = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        tasks = [pool.submit(fetch_patch, row) for row in selected.itertuples()]
        for f in as_completed(tasks):
            results.append(f.result())
            pd.DataFrame(results).to_csv(
                OUT / "tables/download_status.csv", index=False
            )
    assert all(r["status"] == "downloaded" for r in results), (
        "Some requests failed; rerun from cache"
    )


def extract():
    selected = pd.read_csv(OUT / "tables/selected_patches.csv")
    label_counts = [
        {
            "split": role,
            "class_id": cls,
            "source_pixels_before_validity_filter": int(part[f"class_{cls}"].sum()),
        }
        for role, part in selected.groupby("split")
        for cls in range(1, 16)
    ]
    pd.DataFrame(label_counts).to_csv(
        OUT / "tables/selection_label_counts.csv", index=False
    )
    chunks = []
    audit = []
    for row in selected.itertuples():
        folder = RAW / "patches" / row.patch_id
        with rasterio.open(folder / "l2a.tif") as ds:
            l2a = ds.read()
            grid = (ds.crs, ds.transform, ds.shape)
        with rasterio.open(ROOT / "data/external/marida" / row.image_path) as ds:
            rhorc = ds.read()
            assert grid == (ds.crs, ds.transform, ds.shape)
        with rasterio.open(ROOT / "data/external/marida" / row.label_path) as ds:
            y = ds.read(1)
        with rasterio.open(ROOT / "data/external/marida" / row.confidence_path) as ds:
            confidence = ds.read(1)
        valid = np.isfinite(l2a).all(axis=0) & np.isfinite(rhorc).all(axis=0)
        use = valid & (y > 0) & (confidence > 0)
        rr, cc = np.where(use)
        stac = json.loads((folder / "stac.json").read_text())
        assert stac["properties"]["datetime"][:10] == row.date
        assert stac["properties"]["grid:code"] == "MGRS-" + row.tile
        chunks.append(
            {
                "l2a": l2a[:, use].T,
                "rhorc": rhorc[:, use].T,
                "y": y[use],
                "confidence": confidence[use],
                "patch_index": np.repeat(row.selection_index, use.sum()).astype(
                    "int32"
                ),
                "row": rr,
                "col": cc,
            }
        )
        audit.append(
            {
                "patch_id": row.patch_id,
                "split": row.split,
                "group": row.group,
                "stac_id": stac["id"],
                "valid_labelled_pixels": int(use.sum()),
                "positive_pixels": int(((y == 1) & use).sum()),
                "excluded_labelled_pixels": int(
                    ((y > 0) & (confidence > 0) & ~valid).sum()
                ),
            }
        )
    frame = pd.DataFrame(audit)
    assert frame.groupby("stac_id")["split"].nunique().max() == 1
    frame.to_csv(OUT / "tables/pixel_audit.csv", index=False)
    arrays = {
        key: np.concatenate([chunk[key] for chunk in chunks]) for key in chunks[0]
    }
    np.savez_compressed(CACHE / "paired_pixels.npz", **arrays)
    print(
        "Extracted",
        len(arrays["y"]),
        "pixels, debris",
        int((arrays["y"] == 1).sum()),
        flush=True,
    )
    paths = list((RAW / "patches").rglob("*")) + list((RAW / "scenes").glob("*.json"))
    pd.DataFrame(
        [
            {
                "path": str(p.relative_to(ROOT)),
                "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            }
            for p in paths
            if p.is_file()
        ]
    ).to_csv(OUT / "tables/acquisition_hashes.csv", index=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["prepare", "download", "extract", "all"])
    args = parser.parse_args()
    for path in [RAW, CACHE, OUT / "tables"]:
        path.mkdir(parents=True, exist_ok=True)
    if args.stage in ["prepare", "all"]:
        prepare()
    if args.stage in ["download", "all"]:
        download()
    if args.stage in ["extract", "all"]:
        extract()


if __name__ == "__main__":
    main()
