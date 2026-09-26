from types import SimpleNamespace

import numpy as np
import pytest
from scipy import ndimage

from littora_ml.common.io import read_json
from littora_ml.common.paths import MODELS
from littora_ml.detector.external import (
    MANIFEST,
    ServiceDetector,
    cover_bounds,
    material_role,
    reflectance_scale,
    subpixel_shift,
    target_statistics,
    wilson,
    wood_blob,
)
from littora_ml.detector.l2a import StacItem


def test_footprint_and_ring_statistics_on_synthetic_window() -> None:
    size = 81
    probability = np.full((size, size), 0.05, dtype=np.float32)
    footprint = np.zeros((size, size), dtype=bool)
    footprint[40, 40] = True
    probability[41, 41] = 0.8
    probability[55, 40] = 0.9
    probability[40, 60] = 0.9
    probability[40, 75] = 0.9
    others = np.zeros_like(footprint)
    others[40, 62] = True
    water = np.ones_like(footprint)
    valid = np.ones_like(footprint)
    stats = target_statistics(probability, footprint, others, water, valid, threshold=0.5)
    assert stats["footprint_pixels"] == 1
    assert stats["search_pixels"] == 9
    assert np.isclose(stats["max_probability"], 0.8)
    assert stats["detected"]
    assert stats["zone_detected"] and stats["zone_pixels"] == 1
    strict = target_statistics(
        probability, footprint, others, water, valid, threshold=0.5, min_pixels=2
    )
    assert strict["detected"] and not strict["zone_detected"]
    distance = np.hypot(*np.indices((size, size)) - 40)
    near_other = np.hypot(*(np.indices((size, size)) - np.array([40, 62])[:, None, None])) < 10
    ring = (distance >= 10) & (distance <= 30) & ~near_other
    assert stats["ring_pixels"] == ring.sum()
    assert stats["ring_alarm_pixels"] == 1
    assert np.isclose(stats["ring_alarms_per_km2"], 1 / (ring.sum() * 1e-4))
    expected = probability[ring].mean()
    assert np.isclose(stats["ring_mean_probability"], expected)
    dry = target_statistics(probability, footprint, others, ~water, valid, threshold=0.95)
    assert not dry["detected"] and dry["ring_pixels"] == 0 and dry["ring_alarms_per_km2"] is None


def test_window_covers_target_on_the_ten_metre_grid() -> None:
    west, south, east, north = cover_bounds((462480.0, 4328860.0, 462510.0, 4328880.0))
    assert (east - west, north - south) == (2560.0, 2560.0)
    assert west % 10 == 0 and north % 10 == 0
    assert west <= 462480 and east >= 462510 and south <= 4328860 and north >= 4328880
    wide = cover_bounds((457580.0, 4320200.0, 460210.0, 4322430.0))
    assert wide[0] <= 457580 and wide[2] >= 460210 and wide[3] - wide[1] >= 2560
    low, high = wilson(0, 10)
    assert np.isclose(low, 0) and 0.2 < high < 0.35
    assert wilson(0, 0) is None


def test_harmonized_l2a_items_skip_the_advertised_offset() -> None:
    def item(collection: str, baseline: str) -> StacItem:
        return StacItem(
            id="scene",
            collection=collection,
            datetime="2022-07-21T09:00:00Z",
            baseline=baseline,
            cloud_cover=0.0,
            hrefs={},
            scales={"B04": (0.0001, -0.1)},
        )

    assert reflectance_scale(item("sentinel-2-l2a", "05.00"), "B04") == (0.0001, 0.0)
    assert reflectance_scale(item("sentinel-2-l2a", "03.01"), "B04") == (0.0001, -0.1)
    assert reflectance_scale(item("sentinel-2-c1-l2a", "05.00"), "B04") == (0.0001, -0.1)


def test_service_masks_follow_the_current_manifest() -> None:
    path = MODELS / "detector" / "service" / MANIFEST
    if not path.exists():
        pytest.skip("нет сервисной модели")
    detector = object.__new__(ServiceDetector)
    detector.manifest = read_json(path)
    detector.model = SimpleNamespace(
        _run=lambda tiles: np.ones((len(tiles), *tiles.shape[2:]), dtype=np.float32)
    )
    image = np.full((11, 96, 96), 0.02, dtype=np.float32)
    image[1, :, :4] = 0
    scl = np.full((96, 96), 6, dtype=np.uint8)
    scl[30:60, 30:60] = 5
    probability = detector.probability(image, scl)
    assert probability.shape == (96, 96)
    assert (probability[:, :4] == 0).all()
    assert probability[45, 45] == 0
    assert probability[10, 80] == 1
    if detector.manifest.get("sea_mask"):
        assert probability[29, 45] == 0


def test_materials_split_into_plastic_mixed_and_natural_controls() -> None:
    assert material_role(["bags"]) == "plastic"
    assert material_role(["bottles", "bags"]) == "plastic"
    assert material_role(["bags", "reeds"]) == "mixed"
    assert material_role(["reeds"]) == "natural"
    assert material_role(["wood"]) == "natural"


def test_wood_blob_is_the_bright_nir_patch_next_to_the_anchor() -> None:
    size = 81
    nir = np.random.default_rng(1).normal(0.01, 0.002, (size, size)).astype(np.float32)
    anchor = np.zeros((size, size), dtype=bool)
    anchor[40:42, 40:43] = True
    nir[46:49, 39:42] = 0.25
    nir[70:73, 10:13] = 0.3
    water = np.ones_like(anchor)
    blob = wood_blob(nir, anchor, water, water)
    assert blob["mask"] is not None and blob["pixels"] == 9
    assert blob["offset_px"] == [6.5, -1.0]
    assert np.isclose(blob["peak_b08_excess"], 0.25 - blob["water_b08"])
    assert not blob["mask"][70:73, 10:13].any()
    quiet = wood_blob(np.full((size, size), 0.01, dtype=np.float32), anchor, water, water)
    assert quiet["mask"] is None


def test_subpixel_shift_recovers_a_known_displacement() -> None:
    noise = np.random.default_rng(2).random((11, 64, 64)).astype(np.float32)
    reference = ndimage.gaussian_filter(noise, (0, 1.2, 1.2)) + 0.05
    image = ndimage.shift(reference, (0, 0.4, -0.3), order=3, mode="nearest")
    check = subpixel_shift(reference, image)
    assert np.allclose(check["subpixel_shift"], [0.4, -0.3], atol=0.11)
    assert check["corr_subpixel"] > 0.95
    assert subpixel_shift(reference, reference)["subpixel_shift"] == [0.0, 0.0]
