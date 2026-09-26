import datetime as dt

import numpy as np
import pytest
from affine import Affine
from rasterio.warp import transform as warp_transform
from shapely.geometry import box, shape

from app.analysis import detector as detector_module
from app.analysis.composites import PLASTIC_NIR, Coverage, fdi
from app.analysis.detector import OnnxDetector, sea_mask, sliding
from app.analysis.export import _zone_note
from app.analysis.models import UnavailableDetector
from app.analysis.pixels import read_pixel
from app.analysis.stability import plan_windows
from app.analysis.statuses import ResultStatus
from app.analysis.zones import mask_zones
from app.earth.bands import BandStack
from tests.fakes import make_scene

TRANSFORM = Affine(10, 0, 600000, 0, -10, 4830000)
CRS = "EPSG:32635"


def test_sliding_window_reassembles_the_image() -> None:
    image = np.random.default_rng(0).random((3, 300, 420)).astype(np.float32)
    result = sliding(image, lambda tiles: tiles[:, 0], patch=256, stride=192)
    assert result.shape == (300, 420)
    assert np.allclose(result, image[0], atol=1e-5)


def test_zones_are_connected_components_in_wgs84() -> None:
    mask = np.zeros((50, 50), dtype=bool)
    mask[5:8, 5:8] = True
    mask[30, 30] = True
    probability = np.where(mask, 0.9, 0.0)
    zones = mask_zones(mask, probability, TRANSFORM, CRS)
    assert [zone["pixels"] for zone in zones] == [9, 1]
    assert zones[0]["area_km2"] == 0.0009
    lon, lat = shape(zones[0]["geometry"]).centroid.coords[0]
    assert 27 < lon < 29 and 43 < lat < 44
    assert len(mask_zones(mask, probability, TRANSFORM, CRS, min_pixels=2)) == 1


def fake_detector(threshold: float = 0.5, max_pixels: int = 10_000_000) -> OnnxDetector:
    detector = object.__new__(OnnxDetector)
    detector.manifest = {
        "name": "fake-raunet",
        "patch": 256,
        "stride": 192,
        "threshold": threshold,
        "scl_filter": True,
        "min_pixels": 1,
        "max_pixels": max_pixels,
    }
    detector.name = "fake-raunet"
    detector.calibration = None
    detector.vessels = None
    detector.stability = None
    detector._run = lambda tiles: (tiles[:, 7] > 0.05).astype(np.float32) * 0.9
    return detector


def stack_with_target() -> BandStack:
    image = np.full((11, 120, 120), 0.02, dtype=np.float32)
    image[7, 40:44, 60:63] = 0.08
    image[7, 100:103, 10:12] = 0.08
    scl = np.full((120, 120), 6, dtype=np.uint8)
    scl[100:110, 0:20] = 9
    return BandStack(image, scl, CRS, TRANSFORM)


def test_detector_reports_zones_outside_masked_clouds(monkeypatch) -> None:
    monkeypatch.setattr(detector_module, "grid_size", lambda scene, area: (120, 120))
    monkeypatch.setattr(detector_module, "read_band_stack", lambda scene, area: stack_with_target())
    outcome = fake_detector().detect(make_scene("S2A", dt.date(2024, 6, 2)), box(27, 43, 28, 44))
    assert outcome.status is ResultStatus.DETECTED
    assert [zone["pixels"] for zone in outcome.zones] == [12]
    assert outcome.layer.png.startswith(b"\x89PNG")
    assert outcome.threshold == 0.5


def test_large_areas_are_refused(monkeypatch) -> None:
    monkeypatch.setattr(detector_module, "grid_size", lambda scene, area: (5000, 5000))
    outcome = fake_detector(max_pixels=1_000_000).detect(
        make_scene("S2A", dt.date(2024, 6, 2)), box(27, 43, 28, 44)
    )
    assert outcome.status is ResultStatus.INSUFFICIENT_DATA
    assert "10×10 км" in outcome.reason


def test_missing_manifest_means_no_detector(tmp_path) -> None:
    assert isinstance(OnnxDetector.load(tmp_path), UnavailableDetector)


def test_sea_mask_keeps_objects_in_water_and_drops_land(monkeypatch) -> None:
    stack = stack_with_target()
    stack.scl[40:44, 60:63] = 7
    assert sea_mask(stack.scl, -2, 100)[42, 61]
    island = np.full((120, 120), 6, dtype=np.uint8)
    island[20:60, 20:60] = 5
    assert not sea_mask(island, -2, 100)[40, 40]
    stack.scl[0:60, 50:80] = 5
    monkeypatch.setattr(detector_module, "grid_size", lambda scene, area: (120, 120))
    monkeypatch.setattr(detector_module, "read_band_stack", lambda scene, area: stack)
    detector = fake_detector()
    detector.manifest["sea_mask"] = {"classes": [6, 10], "grow": -2, "max_hole": 100}
    outcome = detector.detect(make_scene("S2A", dt.date(2024, 6, 2)), box(27, 43, 28, 44))
    assert outcome.status is ResultStatus.NOT_DETECTED
    assert outcome.zones == []


def test_zones_carry_scene_class_shares() -> None:
    mask = np.zeros((20, 20), dtype=bool)
    mask[2:6, 2:4] = True
    scl = np.full((20, 20), 6, dtype=np.uint8)
    scl[2:4, 2:4] = 10
    [zone] = mask_zones(mask, np.where(mask, 0.8, 0.0), TRANSFORM, CRS, scl=scl)
    assert zone["scl"] == {"water": 0.5, "cloud": 0.5}
    assert "scl" not in mask_zones(mask, np.where(mask, 0.8, 0.0), TRANSFORM, CRS)[0]


def detect_with(detector: OnnxDetector, stack: BandStack, monkeypatch):
    monkeypatch.setattr(detector_module, "grid_size", lambda scene, area: (120, 120))
    monkeypatch.setattr(detector_module, "read_band_stack", lambda scene, area: stack)
    return detector.detect(make_scene("S2A", dt.date(2024, 6, 2)), box(27, 43, 28, 44))


def test_calibration_changes_shown_probability_not_decisions(monkeypatch) -> None:
    plain = detect_with(fake_detector(threshold=0.3), stack_with_target(), monkeypatch)
    calibrated_detector = fake_detector(threshold=0.3)
    calibrated_detector.calibration = {"method": "temperature", "temperature": 1.6}
    calibrated = detect_with(calibrated_detector, stack_with_target(), monkeypatch)
    assert [zone["pixels"] for zone in calibrated.zones] == [zone["pixels"] for zone in plain.zones]
    assert calibrated.zones[0]["probability_max"] < plain.zones[0]["probability_max"]
    assert calibrated.threshold > plain.threshold


def test_bright_swir_zone_is_flagged_as_likely_vessel(monkeypatch) -> None:
    stack = stack_with_target()
    stack.image[9, 40:44, 60:63] = 0.2
    detector = fake_detector()
    detector.vessels = {"window": 20, "swir_peak": 0.04, "visible_contrast": 0.1}
    outcome = detect_with(detector, stack, monkeypatch)
    zone = outcome.zones[0]
    assert zone["features"]["swir_peak"] == pytest.approx(0.2)
    assert [flag["kind"] for flag in zone["flags"]] == ["vessel"]


def test_dim_zone_is_not_flagged(monkeypatch) -> None:
    detector = fake_detector()
    detector.vessels = {"window": 20, "swir_peak": 0.04, "visible_contrast": 0.1}
    outcome = detect_with(detector, stack_with_target(), monkeypatch)
    assert outcome.zones[0]["flags"] == []


STABILITY = {"cutoff": 0.85, "views": 8, "flag": True}


def test_zone_seen_in_every_orientation_is_stable(monkeypatch) -> None:
    detector = fake_detector()
    detector.stability = STABILITY
    zone = detect_with(detector, stack_with_target(), monkeypatch).zones[0]
    assert zone["stability"] == {"agreement": 1.0, "views": 8}
    assert zone["flags"] == []


def test_zone_seen_only_in_half_of_the_views_is_flagged(monkeypatch) -> None:
    left = (np.arange(256) < 128)[None, None, :]
    detector = fake_detector()
    detector.stability = STABILITY
    detector._run = lambda tiles: ((tiles[:, 7] > 0.05) & left).astype(np.float32) * 0.9
    zone = detect_with(detector, stack_with_target(), monkeypatch).zones[0]
    assert zone["stability"]["agreement"] == pytest.approx(0.5)
    assert [flag["kind"] for flag in zone["flags"]] == ["unstable"]


def test_stability_is_shown_without_a_flag_when_the_rule_is_off(monkeypatch) -> None:
    left = (np.arange(256) < 128)[None, None, :]
    detector = fake_detector()
    detector.stability = {**STABILITY, "flag": False}
    detector._run = lambda tiles: ((tiles[:, 7] > 0.05) & left).astype(np.float32) * 0.9
    zone = detect_with(detector, stack_with_target(), monkeypatch).zones[0]
    assert zone["stability"]["agreement"] == pytest.approx(0.5)
    assert zone["flags"] == []


def test_nearby_zones_share_one_window_and_huge_zones_are_skipped() -> None:
    bounds = [
        (slice(500, 504), slice(500, 504)),
        (slice(520, 530), slice(510, 515)),
        (slice(0, 400), slice(0, 10)),
        (slice(1500, 1502), slice(1500, 1502)),
    ]
    windows, assigned = plan_windows(bounds, [1, 2, 3, 4], (2000, 2000), 256)
    assert len(windows) == 2
    assert assigned[1] == assigned[2] == 0
    assert 3 not in assigned
    assert assigned[4] == 1
    windows, assigned = plan_windows(bounds, [1, 4], (2000, 2000), 256, max_windows=1)
    assert list(assigned) == [1]


def test_zone_note_in_csv_lists_flags_and_stability() -> None:
    zone = {
        "flags": [{"kind": "unstable", "label": "неустойчива к поворотам", "evidence": []}],
        "stability": {"agreement": 0.5, "views": 8},
    }
    assert _zone_note(zone) == "неустойчива к поворотам; согласие поворотов 0.50, видов 8"
    assert _zone_note({}) == ""


def test_fdi_follows_biermann_baseline() -> None:
    image = np.zeros((11, 1, 1), dtype=np.float32)
    image[3], image[5], image[7], image[9] = 0.02, 0.03, 0.08, 0.02
    expected = 0.08 - (0.03 + (0.02 - 0.03) * (832.8 - 664.6) / (1613.7 - 664.6) * 10)
    assert float(fdi(image)[0, 0]) == pytest.approx(expected, rel=1e-5)


def test_coverage_is_linear_between_water_and_plastic() -> None:
    image = np.full((11, 41, 41), 0.02, dtype=np.float32)
    image[7] = 0.02
    image[7, 20, 20] = 0.02 + 0.5 * (PLASTIC_NIR - 0.02)
    sea = np.ones((41, 41), dtype=bool)
    estimate = Coverage(image, sea).zone(np.pad(np.ones((1, 1), bool), 20))
    assert estimate["mean"] == pytest.approx(0.5, abs=0.02)
    assert estimate["low"] < estimate["mean"] < estimate["high"]
    assert estimate["area_m2"] == pytest.approx(50, abs=2)


def test_detection_carries_composites_coverage_and_timings(monkeypatch) -> None:
    outcome = detect_with(fake_detector(), stack_with_target(), monkeypatch)
    assert set(outcome.extra_layers) == {"false_color", "fdi", "ndvi", "coverage"}
    assert outcome.zones[0]["coverage"]["mean"] > 0
    assert {"read_s", "inference_s", "tiles", "pixels"} <= set(outcome.timings)


def test_pixel_probe_reads_values_and_zone(monkeypatch, tmp_path) -> None:
    outcome = detect_with(fake_detector(), stack_with_target(), monkeypatch)
    path = tmp_path / "pixels.npz"
    path.write_bytes(outcome.pixels)
    xs, ys = warp_transform(CRS, "EPSG:4326", [600000 + 61 * 10 + 5], [4830000 - 41 * 10 - 5])
    value = read_pixel(path, outcome.zones, xs[0], ys[0])
    assert (value["row"], value["col"]) == (41, 61)
    assert value["above_threshold"] is True
    assert value["zone_id"] == outcome.zones[0]["id"]
    assert value["scl"]["label"] == "вода"
    assert value["reflectance"]["B08"] == pytest.approx(0.08, abs=1e-3)
    outside = read_pixel(path, outcome.zones, 0.0, 0.0)
    assert outside["inside"] is False
