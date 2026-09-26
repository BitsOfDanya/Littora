from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

SUFFIX = ".jsonl"


class ReviewStore:
    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self._lock = threading.Lock()

    def _path(self, analysis_id: str) -> Path:
        return self.folder / f"{analysis_id}{SUFFIX}"

    def append(self, record: dict[str, Any]) -> None:
        line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
        with self._lock:
            self.folder.mkdir(parents=True, exist_ok=True)
            with self._path(record["analysis_id"]).open("a", encoding="utf-8") as handle:
                handle.write(line)

    @staticmethod
    def _read(path: Path) -> list[dict[str, Any]]:
        records = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict) and record.get("zone_id") and record.get("label"):
                records.append(record)
        return records

    def read(self, analysis_id: str) -> list[dict[str, Any]]:
        path = self._path(analysis_id)
        with self._lock:
            return self._read(path) if path.exists() else []

    def read_all(self) -> list[dict[str, Any]]:
        if not self.folder.exists():
            return []
        with self._lock:
            return [
                record
                for path in sorted(self.folder.glob(f"*{SUFFIX}"))
                for record in self._read(path)
            ]
