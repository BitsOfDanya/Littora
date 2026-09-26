import numpy as np

from littora_ml.detector.c1_check import object_metrics, patch_objects
from littora_ml.detector.l2a import subpixel_shift
from littora_ml.detector.review_patches import scene_key, windows_for


def test_zone_one_pixel_off_still_hits_the_object() -> None:
    labels = np.zeros((10, 10), dtype=np.uint8)
    labels[4, 4] = 1
    labels[8, 8] = 7
    decision = np.zeros((10, 10), dtype=bool)
    decision[5, 5] = True
    decision[8, 7] = True
    decision[0, 0] = True
    assert patch_objects(decision, labels).tolist() == [1, 1, 1, 1]


def test_zone_two_pixels_off_is_a_miss() -> None:
    labels = np.zeros((10, 10), dtype=np.uint8)
    labels[4, 4] = 1
    decision = np.zeros((10, 10), dtype=bool)
    decision[6, 6] = True
    assert patch_objects(decision, labels).tolist() == [0, 0, 0, 1]


def test_object_metrics_ignore_zones_on_unlabeled_water() -> None:
    metrics = object_metrics(np.array([3, 1, 2, 4]))
    assert metrics["precision"] == 0.75
    assert metrics["recall"] == 0.5


def test_subpixel_shift_follows_the_correlation_peak() -> None:
    offsets = [(dy, dx) for dy in (-1, 0, 1) for dx in (-1, 0, 1)]
    scores = {(dy, dx): 1.0 - 0.1 * ((dy + 0.3) ** 2 + dx**2) for dy, dx in offsets}
    assert subpixel_shift(scores) == [-0.3, 0.0]


def test_nearby_reviewed_zones_share_one_window() -> None:
    owner, anchors = windows_for([(1000.0, 5000.0), (1100.0, 5050.0), (9000.0, 5000.0)], (0.0, 0.0))
    assert owner == [0, 0, 1]
    assert all(west % 10 == 0 and north % 10 == 0 for west, north in anchors)


def test_scene_ids_of_both_collections_are_understood() -> None:
    assert scene_key("S2C_36TYR_20250522_0_L2A")[0] == "36TYR"
    assert scene_key("S2B_T37TDK_20250904T083254_L2A")[1].isoformat() == "2025-09-04"
    assert scene_key("unknown") is None
