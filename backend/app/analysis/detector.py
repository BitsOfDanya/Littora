from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

import numpy as np
from scipy.ndimage import binary_dilation, binary_erosion, binary_fill_holes
from scipy.ndimage import label as connected_holes
from shapely.geometry.base import BaseGeometry

from app.analysis.composites import (
    FDI_RANGE,
    NDVI_RANGE,
    Coverage,
    coverage_png,
    false_color_png,
    fdi,
    index_png,
    ndvi,
)
from app.analysis.models import DetectionOutcome, UnavailableDetector
from app.analysis.pixels import pack
from app.analysis.stability import load_rule as load_stability
from app.analysis.stability import zone_stability
from app.analysis.statuses import ResultStatus
from app.analysis.vessels import load_rule, object_features, vessel_flag
from app.analysis.zones import mask_zones
from app.earth.bands import GRID_M, BandStack, grid_size, read_band_stack
from app.earth.catalog import Scene
from app.earth.raster import (
    RasterError,
    RasterReadError,
    RenderedLayer,
    encode_png,
    layer_corners,
)

MANIFEST = "detector.json"
CALIBRATION = "calibration.json"
EQUATOR_M_PER_DEG = 111_320.0
MERIDIAN_M_PER_DEG = 110_574.0
SCL_EXCLUDED = (0, 1, 4, 5, 8, 9, 11)
SEA_CLASSES = (6, 10)
RAMP = np.array(
    [
        [255, 236, 179, 0],
        [255, 214, 102, 90],
        [255, 160, 60, 170],
        [235, 90, 50, 220],
        [200, 30, 60, 250],
    ],
    dtype=np.float32,
)


def oversize_side_km(max_pixels: int) -> int:
    return int(np.sqrt(max_pixels) * GRID_M / 1000)


def oversize_reason(max_pixels: int) -> str:
    side = oversize_side_km(max_pixels)
    return f"район больше {side}×{side} км для детектора — выберите «вид карты»"


def bbox_pixels(bbox: tuple[float, float, float, float] | list[float]) -> float:
    west, south, east, north = bbox
    width = (east - west) * EQUATOR_M_PER_DEG * np.cos(np.radians((south + north) / 2))
    height = (north - south) * MERIDIAN_M_PER_DEG
    return width * height / GRID_M**2


def sea_mask(scl: np.ndarray, grow: int, max_hole: int) -> np.ndarray:
    water = np.isin(scl, SEA_CLASSES)
    holes, count = connected_holes(binary_fill_holes(water) & ~water)
    if count:
        sizes = np.bincount(holes.ravel())
        small = np.flatnonzero(sizes <= max_hole)
        water |= np.isin(holes, small[small > 0])
    if grow > 0:
        return binary_dilation(water, iterations=grow)
    if grow < 0:
        return binary_erosion(water, iterations=-grow, border_value=1)
    return water


def apply_service_masks(
    probability: np.ndarray, image: np.ndarray, scl: np.ndarray, manifest: dict[str, Any]
) -> np.ndarray:
    probability[image[1] == 0] = 0
    if manifest["scl_filter"]:
        probability[np.isin(scl, SCL_EXCLUDED)] = 0
    rule = manifest.get("sea_mask")
    if rule:
        probability[~sea_mask(scl, rule["grow"], rule["max_hole"])] = 0
    return probability


def _starts(size: int, patch: int, stride: int) -> list[int]:
    if size <= patch:
        return [0]
    return sorted({*range(0, size - patch, stride), size - patch})


def sliding(image: np.ndarray, run, patch: int, stride: int, batch: int = 8) -> np.ndarray:
    channels, height, width = image.shape
    full_h, full_w = max(height, patch), max(width, patch)
    canvas = np.zeros((channels, full_h, full_w), dtype=np.float32)
    canvas[:, :height, :width] = image
    total = np.zeros((full_h, full_w), dtype=np.float32)
    weight = np.zeros_like(total)
    ramp = np.minimum(np.arange(patch) + 1, np.arange(patch)[::-1] + 1).astype(np.float32)
    window = np.minimum(np.outer(ramp, ramp), 32.0)
    positions = [
        (r, c) for r in _starts(full_h, patch, stride) for c in _starts(full_w, patch, stride)
    ]
    for start in range(0, len(positions), batch):
        chunk = positions[start : start + batch]
        tiles = np.stack([canvas[:, r : r + patch, c : c + patch] for r, c in chunk])
        scores = run(tiles)
        for (r, c), score in zip(chunk, scores, strict=True):
            total[r : r + patch, c : c + patch] += score * window
            weight[r : r + patch, c : c + patch] += window
    return (total / np.maximum(weight, 1e-6))[:height, :width]


def probability_png(probability: np.ndarray, threshold: float) -> bytes:
    scaled = np.clip(probability / max(threshold, 1e-6), 0, 1.5) / 1.5 * (len(RAMP) - 1)
    lower = np.floor(scaled).astype(int)
    upper = np.minimum(lower + 1, len(RAMP) - 1)
    fraction = (scaled - lower)[..., None]
    rgba = RAMP[lower] * (1 - fraction) + RAMP[upper] * fraction
    rgba[probability < threshold * 0.25] = 0
    return encode_png(rgba.astype(np.uint8))


class OnnxDetector:
    def __init__(self, folder: Path, manifest: dict[str, Any]) -> None:
        import onnxruntime as ort

        options = ort.SessionOptions()
        options.intra_op_num_threads = 4
        self.session = ort.InferenceSession(
            str(folder / manifest["file"]), options, providers=["CPUExecutionProvider"]
        )
        self.manifest = manifest
        self.calibration = _read_json(folder / CALIBRATION)
        self.vessels = load_rule(folder)
        self.stability = load_stability(folder)
        self.fingerprint = hashlib.sha256(
            json.dumps(
                [manifest, self.calibration, self.vessels, self.stability],
                sort_keys=True,
                ensure_ascii=False,
            ).encode()
        ).hexdigest()[:16]
        self.name = manifest["name"]

    @classmethod
    def load(cls, folder: Path):
        path = folder / MANIFEST
        if not path.exists():
            return UnavailableDetector()
        try:
            return cls(folder, json.loads(path.read_text(encoding="utf-8")))
        except (ImportError, OSError, ValueError):
            return UnavailableDetector()

    @property
    def max_pixels(self) -> int:
        return int(self.manifest["max_pixels"])

    def _run(self, tiles: np.ndarray) -> np.ndarray:
        return self.session.run(None, {"reflectance": tiles.astype(np.float32)})[0]

    def calibrate(self, probability: np.ndarray) -> np.ndarray:
        if not self.calibration or self.calibration.get("method") != "temperature":
            return probability
        clipped = np.clip(probability, 1e-7, 1 - 1e-7)
        logits = np.log(clipped / (1 - clipped)) / float(self.calibration["temperature"])
        calibrated = 1 / (1 + np.exp(-logits))
        return np.where(probability > 0, calibrated, 0.0).astype(np.float32)

    def _describer(self, stack: BandStack):
        rule = self.vessels
        if rule is None:
            return None

        def describe(labels: np.ndarray, index: int, bounds: tuple[slice, slice]) -> dict:
            features = object_features(
                stack.image, stack.scl, labels, index, bounds, int(rule["window"])
            )
            flag = vessel_flag(features, rule)
            return {"features": features, "flags": [flag] if flag else []}

        return describe

    def _measurer(self, stack: BandStack, coverage: Coverage, timings: dict[str, float]):
        rule = self.stability

        def measure(labels: np.ndarray, keep: list[int], bounds: list) -> dict[int, dict]:
            started = time.perf_counter()
            out: dict[int, dict] = {}
            if rule is not None:
                out = zone_stability(
                    stack.image,
                    labels,
                    keep,
                    bounds,
                    self._run,
                    int(self.manifest["patch"]),
                    float(self.manifest["threshold"]),
                    rule,
                )
            timings["stability_s"] = round(time.perf_counter() - started, 2)
            for index in keep:
                box = bounds[index - 1]
                if box is None:
                    continue
                inside = np.zeros(labels.shape, dtype=bool)
                inside[box] = labels[box] == index
                estimate = coverage.zone(inside)
                if estimate is not None:
                    out.setdefault(index, {})["coverage"] = estimate
            return out

        return measure

    def detect(self, scene: Scene, area: BaseGeometry) -> DetectionOutcome:
        manifest = self.manifest
        height, width = grid_size(scene, area)
        if height * width > self.max_pixels:
            return DetectionOutcome(
                status=ResultStatus.INSUFFICIENT_DATA,
                reason=oversize_reason(self.max_pixels),
                model=self.name,
            )
        timings: dict[str, float] = {}
        started = time.perf_counter()
        try:
            stack = read_band_stack(scene, area)
        except RasterError as error:
            return DetectionOutcome(
                ResultStatus.INSUFFICIENT_DATA,
                str(error),
                self.name,
                retryable=isinstance(error, RasterReadError),
            )
        timings["read_s"] = round(time.perf_counter() - started, 2)
        started = time.perf_counter()
        raw = sliding(stack.image, self._run, manifest["patch"], manifest["stride"])
        tiles = len(
            _starts(max(stack.shape[0], manifest["patch"]), manifest["patch"], manifest["stride"])
        ) * len(
            _starts(max(stack.shape[1], manifest["patch"]), manifest["patch"], manifest["stride"])
        )
        timings["inference_s"] = round(time.perf_counter() - started, 2)
        probability = apply_service_masks(raw, stack.image, stack.scl, manifest)
        raw_threshold = manifest["threshold"]
        shown = self.calibrate(probability)
        threshold = float(self.calibrate(np.array([raw_threshold]))[0])
        valid = stack.image[1] != 0
        sea = np.isin(stack.scl, SEA_CLASSES) & valid
        coverage = Coverage(stack.image, sea)
        started = time.perf_counter()
        detected = probability >= raw_threshold
        zones = mask_zones(
            detected,
            shown,
            stack.transform,
            stack.crs,
            manifest["min_pixels"],
            stack.scl,
            self._describer(stack),
            self._measurer(stack, coverage, timings),
        )
        timings["zones_s"] = round(time.perf_counter() - started - timings.get("stability_s", 0), 2)
        height, width = stack.shape
        corners = layer_corners(stack.transform, stack.crs, height, width)
        started = time.perf_counter()
        layer = RenderedLayer(probability_png(shown, threshold), corners, width, height)
        extra_layers = {
            "false_color": RenderedLayer(
                false_color_png(stack.image, valid), corners, width, height
            ),
            "fdi": RenderedLayer(
                index_png(fdi(stack.image), valid, *FDI_RANGE), corners, width, height
            ),
            "ndvi": RenderedLayer(
                index_png(ndvi(stack.image), valid, *NDVI_RANGE), corners, width, height
            ),
            "coverage": RenderedLayer(
                coverage_png(coverage.central, detected), corners, width, height
            ),
        }
        packed = pack(
            stack.image, stack.scl, shown, coverage.central, stack.transform, stack.crs, threshold
        )
        timings["layers_s"] = round(time.perf_counter() - started, 2)
        timings["pixels"] = int(height * width)
        timings["tiles"] = int(tiles)
        pixels = int(sum(zone["pixels"] for zone in zones))
        status = ResultStatus.DETECTED if zones else ResultStatus.NOT_DETECTED
        reason = (
            f"зон: {len(zones)}, пикселей выше порога {threshold:.2f}: {pixels}"
            if zones
            else f"пикселей выше порога {threshold:.2f} нет"
        )
        return DetectionOutcome(
            status=status,
            reason=reason,
            model=self.name,
            zones=zones,
            layer=layer,
            threshold=threshold,
            extra_layers=extra_layers,
            timings=timings,
            pixels=packed,
        )


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
