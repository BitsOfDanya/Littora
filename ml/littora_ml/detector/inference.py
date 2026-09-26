from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import torch

from littora_ml.common.io import read_json
from littora_ml.common.paths import MODELS
from littora_ml.detector.train import InputPipeline, build_model, device, predict


class TrainedDetector:
    def __init__(self, name: str) -> None:
        self.name = name
        self.folder = MODELS / "detector" / name
        self.kind = "network" if (self.folder / "model.pt").exists() else "trees"
        if self.kind == "network":
            self.config = json.loads((self.folder / "config.json").read_text())
            self.pipeline = InputPipeline.from_state(read_json(self.folder / "input.json"))
            self.device = device()
            channels = len(self.pipeline.mean)
            self.model = build_model(self.config, channels).to(self.device)
            state = torch.load(self.folder / "model.pt", map_location=self.device)
            self.model.load_state_dict(state)
            self.model.eval()
        else:
            self.model = joblib.load(self.folder / "model.joblib")

    def scorer(self, tta: bool, indices_on: bool = True, local_on: bool = True):
        if self.kind == "trees":
            from littora_ml.detector.baselines import tree_scorer

            return tree_scorer(self.model, indices_on, local_on)

        def score(images: np.ndarray) -> np.ndarray:
            valid = images[:, 1] != 0
            inputs = self.pipeline(images, valid)
            return predict(self.model, inputs, self.device, tta=tta)

        return score


class OnnxDetector:
    def __init__(self, path: Path) -> None:
        import onnxruntime as ort

        self.session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
        self.input = self.session.get_inputs()[0].name

    def scorer(self):
        def score(images: np.ndarray) -> np.ndarray:
            output = self.session.run(None, {self.input: images.astype(np.float32)})[0]
            return output.reshape(images.shape[0], *images.shape[2:])

        return score


def run_threshold(name: str) -> tuple[float, bool]:
    from littora_ml.common.paths import REPORTS

    report = read_json(REPORTS / "metrics" / "detector" / f"{name}.json")
    return float(report["threshold"]), bool(report.get("tta", {}).get("used", False))


def run_postprocessing(name: str) -> dict:
    from littora_ml.common.paths import REPORTS

    report = read_json(REPORTS / "metrics" / "detector" / f"{name}.json")
    chosen = (report.get("postprocessing") or {}).get("chosen")
    return chosen or {"scl": False, "min_pixels": 1, "threshold": float(report["threshold"])}


def model_folder(name: str) -> Path:
    return MODELS / "detector" / name
