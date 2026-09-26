from __future__ import annotations

import json
from typing import Any

import numpy as np
import onnxruntime as ort
import torch
from torch import nn

from littora_ml.common.io import read_json, write_json
from littora_ml.common.paths import MODELS, REPORTS
from littora_ml.detector.features import WAVELENGTH
from littora_ml.detector.inference import TrainedDetector
from littora_ml.detector.marida import BANDS
from littora_ml.detector.postprocess import SEA_CLASSES, SEA_GROW, SEA_MAX_HOLE

SERVICE = MODELS / "detector" / "service"


class ServingModel(nn.Module):
    def __init__(self, network: nn.Module, mean, std, indices: bool, bands: list[str]) -> None:
        super().__init__()
        self.network = network
        self.indices = indices
        self.selected = [BANDS.index(name) for name in bands]
        self.register_buffer("mean", torch.tensor(mean, dtype=torch.float32).view(1, -1, 1, 1))
        self.register_buffer("std", torch.tensor(std, dtype=torch.float32).view(1, -1, 1, 1))

    @staticmethod
    def _ratio(a: torch.Tensor, b: torch.Tensor) -> torch.Tensor:
        return (a - b) / (a + b + 1e-6)

    def derived(self, x: torch.Tensor) -> torch.Tensor:
        band = {name: x[:, index : index + 1] for index, name in enumerate(BANDS)}
        span = (WAVELENGTH["B08"] - WAVELENGTH["B04"]) / (WAVELENGTH["B11"] - WAVELENGTH["B04"])
        nir, red = band["B08"], band["B04"]
        fdi = nir - (band["B06"] + (band["B11"] - band["B06"]) * span * 10)
        fai = nir - (red + (band["B11"] - red) * span)
        return torch.cat(
            [
                self._ratio(nir, red),
                fdi,
                fai,
                self._ratio(band["B03"], nir),
                self._ratio(nir, band["B11"]),
                nir / (nir + red + 1e-6),
                band["B07"] - band["B05"],
                band["B11"] / (band["B12"] + 1e-6),
            ],
            dim=1,
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        valid = (x[:, 1:2] != 0).float()
        selected = x[:, self.selected]
        stack = torch.cat([selected, self.derived(x)], dim=1) if self.indices else selected
        z = torch.clamp((stack - self.mean) / self.std, -20, 20) * valid
        logits, _ = self.network(z)
        return torch.sigmoid(logits[:, 0])


def export_detector(run: str, max_pixels: int) -> dict[str, Any]:
    detector = TrainedDetector(run)
    if detector.kind != "network":
        raise ValueError("экспорт в ONNX поддержан только для сетей")
    network = detector.model.to("cpu").eval()
    pipeline = detector.pipeline
    serving = ServingModel(
        network, pipeline.mean, pipeline.std, pipeline.indices, pipeline.bands
    ).eval()
    SERVICE.mkdir(parents=True, exist_ok=True)
    sample = torch.zeros(1, len(BANDS), 256, 256)
    path = SERVICE / "detector.onnx"
    torch.onnx.export(
        serving,
        sample,
        path,
        input_names=["reflectance"],
        output_names=["probability"],
        dynamic_axes={"reflectance": {0: "batch"}, "probability": {0: "batch"}},
        opset_version=17,
        dynamo=False,
    )
    rng = np.random.default_rng(0)
    probe = rng.uniform(0.0, 0.08, size=(2, len(BANDS), 256, 256)).astype(np.float32)
    session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    onnx_out = session.run(None, {"reflectance": probe})[0]
    with torch.no_grad():
        torch_out = serving(torch.from_numpy(probe)).numpy()
    report = read_json(REPORTS / "metrics" / "detector" / f"{run}.json")
    post = report.get("postprocessing") or {}
    chosen = post.get("chosen") or {"scl": False, "min_pixels": 1, "threshold": report["threshold"]}
    manifest = {
        "name": run,
        "file": path.name,
        "bands": list(BANDS),
        "patch": 256,
        "stride": 192,
        "threshold": chosen["threshold"],
        "scl_filter": bool(chosen.get("scl")),
        "sea_mask": {
            "classes": list(SEA_CLASSES),
            "grow": SEA_GROW,
            "max_hole": SEA_MAX_HOLE,
            "rule": (
                "море — вода и перистые облака по SCL; дыры до 100 пикселей (1 га) внутри воды "
                "считаются морем, острова, косы и мосты — нет; маска сжата на 2 пикселя от "
                "берега; вне моря вероятность обнуляется; на train и val сохраняется 97,7 % "
                "и 99,4 % пикселей мусора"
            ),
        },
        "min_pixels": int(chosen.get("min_pixels", 1)),
        "max_pixels": max_pixels,
        "test_metrics": {
            key: report["test"][key] for key in ("precision", "recall", "f1", "iou", "pr_auc")
        },
        "test_ci95": report.get("test_ci95_scene_bootstrap"),
        "postprocessed_test_metrics": {
            key: (post.get("test") or {}).get(key) for key in ("precision", "recall", "f1", "iou")
        },
        "data": report["config"].get("data"),
        "split": report["config"].get("split"),
        "validation": (
            f"MARIDA ({report['config'].get('data')}, разбиение {report['config'].get('split')}); "
            "порог, TTA и постобработка выбраны на валидации; precision — по размеченным пикселям"
        ),
        "onnx_max_abs_difference": float(np.abs(onnx_out - torch_out).max()),
        "config": json.loads((detector.folder / "config.json").read_text()),
    }
    calibration_path = SERVICE / "calibration.json"
    if calibration_path.exists():
        calibration = json.loads(calibration_path.read_text())
        if calibration.get("name") == run:
            manifest["service_metrics"] = {
                **calibration["service_metrics"],
                "mode": (
                    "как работает сервис: без TTA, порог манифеста, маска моря, зоны от "
                    f"{manifest['min_pixels']} пикс.; порог выбран на val, test посчитан один раз"
                ),
            }
            manifest["calibration"] = {
                "method": calibration["method"],
                "temperature": calibration.get("temperature"),
                "threshold": calibration["threshold"],
                "note": ("показываемая вероятность откалибрована на val; решения детектора те же"),
            }
    write_json(SERVICE / "detector.json", manifest)
    return manifest
