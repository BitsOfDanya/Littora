from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch import nn

from littora_ml.common.io import write_json
from littora_ml.common.paths import MODELS
from littora_ml.detector.dataset import PatchSet
from littora_ml.detector.evaluation import choose_threshold, usable_labels
from littora_ml.detector.features import spectral_indices
from littora_ml.detector.losses import auxiliary_loss, binary_loss
from littora_ml.detector.marida import BANDS
from littora_ml.detector.metrics import best_threshold
from littora_ml.detector.unet import ResidualAttentionUNet

AUX_CLASSES = 15


def device() -> torch.device:
    if torch.backends.mps.is_available():
        return torch.device("mps")
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def build_model(config: dict[str, Any], in_channels: int) -> nn.Module:
    model_config = config["model"]
    aux = AUX_CLASSES if config["loss"].get("aux_weight", 0) > 0 else 0
    kind = model_config["kind"]
    if kind == "raunet":
        return ResidualAttentionUNet(
            in_channels,
            1,
            aux,
            width=model_config.get("width", 32),
            depth=model_config.get("depth", 4),
            dropout=model_config.get("dropout", 0.1),
        )
    import segmentation_models_pytorch as smp

    architectures = {
        "unetplusplus": smp.UnetPlusPlus,
        "deeplabv3plus": smp.DeepLabV3Plus,
        "segformer": smp.Segformer,
        "unet": smp.Unet,
    }
    network = architectures[kind](
        encoder_name=model_config["encoder"],
        encoder_weights=model_config.get("encoder_weights"),
        in_channels=in_channels,
        classes=1 + aux,
    )
    return SplitHeads(network, aux)


class SplitHeads(nn.Module):
    def __init__(self, network: nn.Module, aux: int) -> None:
        super().__init__()
        self.network = network
        self.aux = aux

    def forward(self, x: torch.Tensor):
        out = self.network(x)
        return out[:, :1], (out[:, 1:] if self.aux else None)


class InputPipeline:
    def __init__(
        self, indices: bool, mean: np.ndarray, std: np.ndarray, bands: list[str] | None = None
    ) -> None:
        self.indices = indices
        self.bands = list(bands) if bands else list(BANDS)
        self.mean = mean.astype(np.float32)
        self.std = std.astype(np.float32)

    @staticmethod
    def raw(images: np.ndarray, indices: bool, bands: list[str]) -> np.ndarray:
        images = images.astype(np.float32)
        selected = images[:, [BANDS.index(name) for name in bands]]
        if not indices:
            return selected
        derived = np.stack([spectral_indices(image) for image in images])
        return np.concatenate([selected, derived], axis=1)

    @classmethod
    def fit(
        cls, images: np.ndarray, valid: np.ndarray, indices: bool, bands: list[str] | None = None
    ) -> InputPipeline:
        chosen = list(bands) if bands else list(BANDS)
        stack = cls.raw(images, indices, chosen)
        mask = valid[:, None].repeat(stack.shape[1], axis=1)
        values = np.where(mask, stack, np.nan)
        mean = np.nanmean(values, axis=(0, 2, 3))
        std = np.nanstd(values, axis=(0, 2, 3)) + 1e-6
        return cls(indices, mean, std, chosen)

    def __call__(self, images: np.ndarray, valid: np.ndarray | None = None) -> np.ndarray:
        stack = self.raw(images, self.indices, self.bands)
        stack = (stack - self.mean[None, :, None, None]) / self.std[None, :, None, None]
        stack = np.clip(stack, -20, 20)
        if valid is not None:
            stack = np.where(valid[:, None], stack, 0.0)
        return stack.astype(np.float32)

    def state(self) -> dict[str, Any]:
        return {
            "indices": self.indices,
            "bands": self.bands,
            "mean": self.mean.tolist(),
            "std": self.std.tolist(),
        }

    @classmethod
    def from_state(cls, state: dict[str, Any]) -> InputPipeline:
        return cls(
            state["indices"], np.array(state["mean"]), np.array(state["std"]), state.get("bands")
        )


def _augment(x: torch.Tensor, *targets: torch.Tensor, generator: torch.Generator):
    k = int(torch.randint(0, 4, (1,), generator=generator))
    flip = bool(torch.randint(0, 2, (1,), generator=generator))
    out = []
    for tensor in (x, *targets):
        dims = (-2, -1)
        tensor = torch.rot90(tensor, k, dims)
        if flip:
            tensor = torch.flip(tensor, (-1,))
        out.append(tensor)
    return out


def predict(
    model: nn.Module, inputs: np.ndarray, run_device: torch.device, tta: bool, batch: int = 8
) -> np.ndarray:
    model.eval()
    out = np.zeros((inputs.shape[0], inputs.shape[2], inputs.shape[3]), dtype=np.float32)
    with torch.no_grad():
        for start in range(0, len(inputs), batch):
            x = torch.from_numpy(inputs[start : start + batch]).to(run_device).float()
            views = [(0, False)]
            if tta:
                views = [(k, flip) for k in range(4) for flip in (False, True)]
            total = torch.zeros(x.shape[0], x.shape[2], x.shape[3], device=run_device)
            for k, flip in views:
                view = torch.rot90(x, k, (-2, -1))
                if flip:
                    view = torch.flip(view, (-1,))
                logits, _ = model(view)
                probability = torch.sigmoid(logits[:, 0])
                if flip:
                    probability = torch.flip(probability, (-1,))
                total += torch.rot90(probability, -k, (-2, -1))
            out[start : start + len(x)] = (total / len(views)).float().cpu().numpy()
    return out


def _aux_weights(labels: np.ndarray) -> torch.Tensor:
    counts = np.bincount(labels[labels > 0].astype(np.int64) - 1, minlength=AUX_CLASSES) + 1
    weights = 1 / np.sqrt(counts)
    return torch.tensor(weights / weights.mean(), dtype=torch.float32)


def train_detector(
    patches: PatchSet, split, config: dict[str, Any], name: str
) -> tuple[dict[str, Any], np.ndarray, np.ndarray, Path]:
    seed = config.get("seed", 42)
    torch.manual_seed(seed)
    generator = torch.Generator().manual_seed(seed)
    run_device = device()
    train_config = config["train"]
    loss_config = config["loss"]
    max_confidence_code = config.get("labels", {}).get("max_confidence_code", 3)
    values = split.to_numpy()
    train_index = np.flatnonzero(values == "train")
    val_index = np.flatnonzero(values == "val")
    test_index = np.flatnonzero(values == "test")
    train_images = np.asarray(patches.images[train_index], dtype=np.float32)
    train_valid = patches.valid[train_index]
    pipeline = InputPipeline.fit(
        train_images,
        train_valid,
        config["input"].get("indices", True),
        config["input"].get("bands"),
    )
    x_train = torch.from_numpy(pipeline(train_images, train_valid).astype(np.float16))
    del train_images
    train_labels = usable_labels(patches, train_index, max_confidence_code)
    y_train = torch.from_numpy(train_labels.astype(np.int64))
    x_val = pipeline(
        np.asarray(patches.images[val_index], dtype=np.float32), patches.valid[val_index]
    ).astype(np.float16)
    val_labels = usable_labels(patches, val_index, max_confidence_code)
    model = build_model(config, x_train.shape[1]).to(run_device)
    optimizer = torch.optim.AdamW(
        model.parameters(), lr=train_config["lr"], weight_decay=train_config["weight_decay"]
    )
    epochs = train_config["epochs"]
    steps = math.ceil(len(train_index) / train_config["batch"])
    scheduler = torch.optim.lr_scheduler.OneCycleLR(
        optimizer, max_lr=train_config["lr"], total_steps=epochs * steps, pct_start=0.1
    )
    has_debris = (train_labels == 1).any(axis=(1, 2)).astype(np.float64)
    hard = np.isin(train_labels, train_config.get("hard_negative_classes", [])).any(axis=(1, 2))
    weights = torch.tensor(
        1
        + train_config.get("positive_oversample", 0.0) * has_debris
        + train_config.get("hard_negative_oversample", 0.0) * hard.astype(np.float64)
    )
    class_weights = torch.ones(AUX_CLASSES + 1)
    for code, value in loss_config.get("negative_weights", {}).items():
        class_weights[int(code)] = float(value)
    class_weights = class_weights.to(run_device)
    use_pixel_weights = bool(loss_config.get("negative_weights"))
    aux_weight = loss_config.get("aux_weight", 0.0)
    aux_class_weights = _aux_weights(train_labels).to(run_device) if aux_weight else None
    best = {"f1": -1.0, "epoch": -1}
    history = []
    folder = MODELS / "detector" / name
    folder.mkdir(parents=True, exist_ok=True)
    started = time.time()
    patience = train_config.get("patience", epochs)
    for epoch in range(epochs):
        model.train()
        epoch_loss = 0.0
        for _ in range(steps):
            batch = torch.multinomial(weights, train_config["batch"], True, generator=generator)
            x = x_train[batch].to(run_device).float()
            labels = y_train[batch].to(run_device)
            x, labels = _augment(x, labels, generator=generator)
            mask = labels > 0
            target = (labels == 1).float()
            logits, aux_logits = model(x)
            loss = binary_loss(
                loss_config["kind"],
                logits[:, 0],
                target,
                mask,
                loss_config.get("pos_weight", 1.0),
                class_weights[labels] if use_pixel_weights else None,
            )
            if aux_weight and aux_logits is not None:
                aux_target = torch.where(mask, labels - 1, torch.full_like(labels, -1))
                loss = loss + aux_weight * auxiliary_loss(aux_logits, aux_target, aux_class_weights)
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()
            scheduler.step()
            epoch_loss += float(loss.detach())
        val_scores = predict(model, x_val, run_device, tta=False)
        labeled = val_labels > 0
        threshold, f1 = best_threshold(val_scores[labeled], val_labels[labeled] == 1)
        history.append(
            {"epoch": epoch, "loss": round(epoch_loss / steps, 5), "val_f1": round(f1, 4)}
        )
        print(
            f"{name} эпоха {epoch}: loss {epoch_loss / steps:.4f} val F1 {f1:.4f} "
            f"({time.time() - started:.0f} с)",
            flush=True,
        )
        if f1 > best["f1"]:
            best = {"f1": f1, "epoch": epoch, "threshold": threshold}
            torch.save(model.state_dict(), folder / "model.pt")
        if epoch - best["epoch"] >= patience:
            break
    model.load_state_dict(torch.load(folder / "model.pt", map_location=run_device))
    x_test = pipeline(
        np.asarray(patches.images[test_index], dtype=np.float32), patches.valid[test_index]
    ).astype(np.float16)
    plain_val = predict(model, x_val, run_device, tta=False)
    tta_val = predict(model, x_val, run_device, tta=True)
    _, plain_f1 = choose_threshold(plain_val, val_labels)
    _, tta_f1 = choose_threshold(tta_val, val_labels)
    use_tta = bool(train_config.get("tta", True) and tta_f1 > plain_f1)
    val_scores = tta_val if use_tta else plain_val
    test_scores = predict(model, x_test, run_device, tta=use_tta)
    write_json(folder / "input.json", pipeline.state())
    (folder / "config.json").write_text(
        json.dumps({k: v for k, v in config.items() if not k.startswith("_")}, indent=1)
    )
    extra = {
        "device": str(run_device),
        "parameters": sum(p.numel() for p in model.parameters()),
        "best_epoch": best["epoch"],
        "epochs_run": len(history),
        "train_seconds": round(time.time() - started, 1),
        "tta": {"used": use_tta, "val_f1_plain": plain_f1, "val_f1_tta": tta_f1},
        "history": history,
    }
    return extra, val_scores, test_scores, folder
