import json
from pathlib import Path

import numpy as np
from rasterio.transform import from_origin, xy
from rasterio.warp import transform_geom
from shapely.geometry import box, mapping

from littora_ml.detector.review_labels import (
    IGNORE,
    LABEL_CODES,
    Grid,
    rasterize_reviews,
    read_reviews,
    resolve,
    review_masks,
)

CRS = "EPSG:32637"
GRID = Grid(from_origin(400_000, 4_950_000, 10, 10), CRS, 40, 40)
SCENE = "S2B_37TDK_20250904_0_L2A"


def lonlat_square(row: int, col: int, size: int) -> dict:
    west, north = xy(GRID.transform, row, col, offset="ul")
    east, south = xy(GRID.transform, row + size, col + size, offset="ul")
    return transform_geom(CRS, "EPSG:4326", mapping(box(west, south, east, north)))


def pixel_centre(row: int, col: int) -> tuple[float, float]:
    x, y = xy(GRID.transform, row, col)
    point = transform_geom(CRS, "EPSG:4326", {"type": "Point", "coordinates": [x, y]})
    return point["coordinates"]


def record(zone: str, label: str, confidence: int, reviewer: str, at: str, square) -> dict:
    return {
        "id": f"{zone}-{at}",
        "source": "ui",
        "created_at": at,
        "analysis_id": "0123456789abcdef",
        "zone_id": zone,
        "scene_id": SCENE,
        "reviewer": reviewer,
        "label": label,
        "confidence": confidence,
        "geometry": lonlat_square(*square),
    }


def write_store(folder: Path) -> Path:
    folder.mkdir()
    rows = [
        record("zone-1", "unknown", 1, "Vadim", "2026-09-26T10:00:00Z", (5, 5, 3)),
        record("zone-1", "ship", 3, "vadim", "2026-09-26T10:01:00Z", (5, 5, 3)),
        record("zone-2", "likely_debris", 3, "Dania", "2026-09-26T10:02:00Z", (12, 12, 2)),
        record("zone-3", "foam", 2, "a", "2026-09-26T10:03:00Z", (25, 25, 2)),
        record("zone-3", "plume", 2, "b", "2026-09-26T10:04:00Z", (25, 25, 2)),
        record("zone-4", "water", 1, "a", "2026-09-26T10:05:00Z", (30, 5, 2)),
    ]
    other = {**rows[2], "zone_id": "zone-9", "scene_id": "S2A_OTHER", "label": "wake"}
    lines = [json.dumps(row) for row in [*rows, other]]
    (folder / "0123456789abcdef.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return folder


def test_store_reviews_become_hard_negative_masks(tmp_path: Path) -> None:
    masks, conflicts = review_masks(write_store(tmp_path / "reviews"), GRID, scene_id=SCENE)
    assert [conflict.zone_id for conflict in conflicts] == ["zone-3"]
    assert masks.zones == 2
    assert masks.labels[5:8, 5:8].tolist() == [[LABEL_CODES["ship"]] * 3] * 3
    assert masks.hard_negative.sum() == 9
    assert masks.positive.sum() == 4
    assert masks.positive[12:14, 12:14].all()
    assert masks.confidence[5, 5] == 3
    assert masks.labels[25, 25] == IGNORE
    assert masks.labels[30, 5] == IGNORE
    assert masks.counts() == {"likely_debris": 4, "ship": 9}


def test_audit_csv_points_burn_small_windows(tmp_path: Path) -> None:
    lon, lat = pixel_centre(20, 20)
    path = tmp_path / "audit.csv"
    path.write_text(
        "zone_id,aoi,scene_id,date,lon,lat,pixels,probability_max,class,confidence,comment,reviewer\n"
        f"n-001,novorossiysk,{SCENE},2025-09-04,{lon},{lat},4,0.99,water,3,вода,team\n"
        f"n-002,novorossiysk,{SCENE},2025-09-04,{lon},{lat},4,0.99,unknown,1,неясно,team\n",
        encoding="utf-8",
    )
    zones, conflicts = resolve(read_reviews(path))
    assert conflicts == []
    assert [(zone.source, zone.label) for zone in zones] == [("audit", "water")]
    masks = rasterize_reviews(zones, GRID, point_radius=1)
    assert masks.hard_negative.sum() == 9
    assert masks.hard_negative[19:22, 19:22].all()


def test_geojson_export_round_trips_and_contested_pixels_are_ignored(tmp_path: Path) -> None:
    debris = record("zone-1", "likely_debris", 3, "a", "2026-09-26T10:00:00Z", (0, 0, 4))
    ship = record("zone-2", "ship", 3, "a", "2026-09-26T10:01:00Z", (2, 2, 4))
    path = tmp_path / "reviews.geojson"
    features = [
        {
            "type": "Feature",
            "geometry": row["geometry"],
            "properties": {k: v for k, v in row.items() if k != "geometry"},
        }
        for row in (debris, ship)
    ]
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}))
    zones, _ = resolve(read_reviews(path))
    masks = rasterize_reviews(zones, GRID)
    assert masks.labels[0, 0] == LABEL_CODES["likely_debris"]
    assert masks.labels[5, 5] == LABEL_CODES["ship"]
    assert not masks.known[2:4, 2:4].any()
    assert int(np.count_nonzero(masks.known)) == 16 + 16 - 2 * 4
