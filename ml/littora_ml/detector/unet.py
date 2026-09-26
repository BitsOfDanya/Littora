from __future__ import annotations

import torch
from torch import nn
from torch.nn import functional as F


class ResidualBlock(nn.Module):
    def __init__(self, in_channels: int, out_channels: int, dropout: float = 0.0) -> None:
        super().__init__()
        self.body = nn.Sequential(
            nn.Conv2d(in_channels, out_channels, 3, padding=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
            nn.Dropout2d(dropout) if dropout else nn.Identity(),
            nn.Conv2d(out_channels, out_channels, 3, padding=1, bias=False),
            nn.BatchNorm2d(out_channels),
        )
        self.skip = (
            nn.Identity()
            if in_channels == out_channels
            else nn.Sequential(
                nn.Conv2d(in_channels, out_channels, 1, bias=False), nn.BatchNorm2d(out_channels)
            )
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return F.relu(self.body(x) + self.skip(x))


class AttentionGate(nn.Module):
    def __init__(self, gate_channels: int, skip_channels: int, inner_channels: int) -> None:
        super().__init__()
        self.gate = nn.Sequential(
            nn.Conv2d(gate_channels, inner_channels, 1, bias=False), nn.BatchNorm2d(inner_channels)
        )
        self.skip = nn.Sequential(
            nn.Conv2d(skip_channels, inner_channels, 1, bias=False), nn.BatchNorm2d(inner_channels)
        )
        self.psi = nn.Sequential(nn.Conv2d(inner_channels, 1, 1), nn.BatchNorm2d(1), nn.Sigmoid())

    def forward(self, gate: torch.Tensor, skip: torch.Tensor) -> torch.Tensor:
        alpha = self.psi(F.relu(self.gate(gate) + self.skip(skip)))
        return skip * alpha


class UpBlock(nn.Module):
    def __init__(self, in_channels: int, skip_channels: int, out_channels: int, dropout: float):
        super().__init__()
        self.up = nn.ConvTranspose2d(in_channels, out_channels, 2, stride=2)
        self.attention = AttentionGate(out_channels, skip_channels, max(skip_channels // 2, 8))
        self.block = ResidualBlock(out_channels + skip_channels, out_channels, dropout)

    def forward(self, x: torch.Tensor, skip: torch.Tensor) -> torch.Tensor:
        x = self.up(x)
        return self.block(torch.cat([x, self.attention(x, skip)], dim=1))


class ResidualAttentionUNet(nn.Module):
    def __init__(
        self,
        in_channels: int,
        classes: int = 1,
        aux_classes: int = 0,
        width: int = 32,
        depth: int = 4,
        dropout: float = 0.1,
    ) -> None:
        super().__init__()
        channels = [width * 2**level for level in range(depth + 1)]
        self.stem = ResidualBlock(in_channels, channels[0])
        self.down = nn.ModuleList(
            ResidualBlock(channels[level], channels[level + 1], dropout if level >= 2 else 0.0)
            for level in range(depth)
        )
        self.up = nn.ModuleList(
            UpBlock(
                channels[level + 1],
                channels[level],
                channels[level],
                dropout if level >= 2 else 0.0,
            )
            for level in reversed(range(depth))
        )
        self.head = nn.Conv2d(channels[0], classes, 1)
        self.aux_head = nn.Conv2d(channels[0], aux_classes, 1) if aux_classes else None

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor | None]:
        skips = [self.stem(x)]
        for block in self.down:
            skips.append(block(F.max_pool2d(skips[-1], 2)))
        y = skips.pop()
        for block in self.up:
            y = block(y, skips.pop())
        aux = self.aux_head(y) if self.aux_head is not None else None
        return self.head(y), aux
