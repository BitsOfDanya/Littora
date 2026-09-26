from __future__ import annotations

import torch
from torch.nn import functional as F


def _masked(logits: torch.Tensor, target: torch.Tensor, mask: torch.Tensor):
    return logits[mask], target[mask]


def dice_loss(probability: torch.Tensor, target: torch.Tensor, smooth: float = 1.0) -> torch.Tensor:
    intersection = (probability * target).sum()
    return 1 - (2 * intersection + smooth) / (probability.sum() + target.sum() + smooth)


def tversky_loss(
    probability: torch.Tensor, target: torch.Tensor, alpha: float, beta: float, smooth: float = 1.0
) -> torch.Tensor:
    tp = (probability * target).sum()
    fp = (probability * (1 - target)).sum()
    fn = ((1 - probability) * target).sum()
    return 1 - (tp + smooth) / (tp + alpha * fp + beta * fn + smooth)


def focal_loss(
    logits: torch.Tensor, target: torch.Tensor, gamma: float, alpha: float
) -> torch.Tensor:
    bce = F.binary_cross_entropy_with_logits(logits, target, reduction="none")
    probability = torch.sigmoid(logits)
    pt = probability * target + (1 - probability) * (1 - target)
    weight = alpha * target + (1 - alpha) * (1 - target)
    return (weight * (1 - pt) ** gamma * bce).mean()


def binary_loss(
    kind: str,
    logits: torch.Tensor,
    target: torch.Tensor,
    mask: torch.Tensor,
    pos_weight: float = 1.0,
    pixel_weights: torch.Tensor | None = None,
) -> torch.Tensor:
    weights = pixel_weights[mask] if pixel_weights is not None else None
    logits, target = _masked(logits, target, mask)
    if logits.numel() == 0:
        return logits.sum()
    probability = torch.sigmoid(logits)
    if kind == "bce_dice":
        weight = torch.tensor(pos_weight, device=logits.device)
        bce = F.binary_cross_entropy_with_logits(
            logits, target, weight=weights, pos_weight=weight, reduction="sum"
        ) / (weights.sum() if weights is not None else logits.numel())
        return bce + dice_loss(probability, target)
    if kind == "focal_dice":
        return focal_loss(logits, target, gamma=2.0, alpha=0.75) + dice_loss(probability, target)
    if kind == "tversky":
        return tversky_loss(probability, target, alpha=0.3, beta=0.7)
    if kind == "focal_tversky":
        return tversky_loss(probability, target, alpha=0.3, beta=0.7) ** 0.75
    raise ValueError(f"unknown loss {kind}")


def auxiliary_loss(
    logits: torch.Tensor, classes: torch.Tensor, weights: torch.Tensor | None
) -> torch.Tensor:
    return F.cross_entropy(logits, classes, weight=weights, ignore_index=-1)
