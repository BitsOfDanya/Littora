from __future__ import annotations

import json
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from littora_ml.common.io import write_json
from littora_ml.detector.marida import PATCH_SIZE, list_patches, patch_table, read_patch

IMAGES = "images.npy"
LABELS = "labels.npy"
CONFIDENCE = "confidence.npy"
VALID = "valid.npy"
TABLE = "patches.parquet"


@dataclass
class PatchSet:
    root: Path
    table: pd.DataFrame
    images: np.ndarray
    labels: np.ndarray
    confidence: np.ndarray
    valid: np.ndarray

    @property
    def names(self) -> list[str]:
        return self.table["name"].tolist()


def build_marida_cache(marida_root: Path, out_dir: Path, workers: int = 8) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    patches = list_patches(marida_root)
    table = patch_table(marida_root)
    count = len(patches)
    images = np.lib.format.open_memmap(
        out_dir / IMAGES, mode="w+", dtype=np.float16, shape=(count, 11, PATCH_SIZE, PATCH_SIZE)
    )
    labels = np.zeros((count, PATCH_SIZE, PATCH_SIZE), dtype=np.uint8)
    confidence = np.zeros_like(labels)
    valid = np.zeros_like(labels, dtype=bool)

    def load(index: int) -> None:
        image, label, conf = read_patch(patches[index])
        finite = np.isfinite(image).all(axis=0)
        images[index] = np.nan_to_num(image, nan=0.0).astype(np.float16)
        labels[index] = label
        confidence[index] = conf
        valid[index] = finite & (image != 0).any(axis=0)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(load, range(count)))
    images.flush()
    np.save(out_dir / LABELS, labels)
    np.save(out_dir / CONFIDENCE, confidence)
    np.save(out_dir / VALID, valid)
    table.to_parquet(out_dir / TABLE, index=False)
    write_json(out_dir / "source.json", {"variant": "marida", "root": str(marida_root.name)})
    return out_dir


def load_patch_set(root: Path, mmap: bool = True) -> PatchSet:
    mode = "r" if mmap else None
    table = pd.read_parquet(root / TABLE)
    return PatchSet(
        root=root,
        table=table,
        images=np.load(root / IMAGES, mmap_mode=mode),
        labels=np.load(root / LABELS),
        confidence=np.load(root / CONFIDENCE),
        valid=np.load(root / VALID),
    )


def describe(root: Path) -> dict:
    source = root / "source.json"
    return json.loads(source.read_text()) if source.exists() else {}


def _train_only(table: pd.DataFrame) -> pd.DataFrame:
    return table.assign(
        official_split=table["official_split"].where(table["official_split"] == "train", "none")
    )


def build_mixed_cache(
    marida: Path, l2a: Path, out_dir: Path, extra: Sequence[tuple[Path, str]] = ()
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    first = load_patch_set(marida)
    parts: list[tuple[PatchSet, np.ndarray, pd.DataFrame]] = [
        (first, np.arange(len(first.table)), _train_only(first.table).assign(source="marida"))
    ]
    second = load_patch_set(l2a)
    keep = np.flatnonzero(second.table["l2a_found"].to_numpy())
    parts.append((second, keep, second.table.iloc[keep].assign(source="l2a")))
    for path, name in extra:
        patches = load_patch_set(path)
        found = patches.table.get("l2a_found")
        everything = np.arange(len(patches.table))
        chosen = np.flatnonzero(found.to_numpy()) if found is not None else everything
        parts.append((patches, chosen, _train_only(patches.table.iloc[chosen]).assign(source=name)))
    count = sum(len(chosen) for _, chosen, _ in parts)
    images = np.lib.format.open_memmap(
        out_dir / IMAGES, mode="w+", dtype=np.float16, shape=(count, *first.images.shape[1:])
    )
    offset = 0
    for patches, chosen, _ in parts:
        for start in range(0, len(chosen), 64):
            block = chosen[start : start + 64]
            images[offset + start : offset + start + len(block)] = patches.images[block]
        offset += len(chosen)
    images.flush()
    np.save(out_dir / LABELS, np.concatenate([p.labels[c] for p, c, _ in parts]))
    np.save(out_dir / CONFIDENCE, np.concatenate([p.confidence[c] for p, c, _ in parts]))
    np.save(out_dir / VALID, np.concatenate([p.valid[c] for p, c, _ in parts]))
    table = pd.concat([frame for _, _, frame in parts], ignore_index=True)
    table["index"] = np.arange(len(table))
    table.to_parquet(out_dir / TABLE, index=False)
    sources = {name: len(frame) for name, frame in table.groupby("source")}
    write_json(out_dir / "source.json", {"variant": "mixed", "patches": count, "sources": sources})
    return out_dir
