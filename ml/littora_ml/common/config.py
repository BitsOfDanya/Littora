from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from littora_ml.common.io import file_sha256
from littora_ml.common.paths import resolve


def load_config(path: str | Path) -> dict[str, Any]:
    resolved = resolve(path)
    with resolved.open("rb") as handle:
        config = tomllib.load(handle)
    config["_path"] = str(resolved.relative_to(resolve(".")))
    config["_sha256"] = file_sha256(resolved)
    return config
