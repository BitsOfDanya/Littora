from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.case.config import CaseConfig, load_case_config
from app.case.records import CaseRecord, load_records
from app.case.selection import Selection, select_records


class CaseDataMissingError(FileNotFoundError):
    pass


@dataclass(frozen=True)
class CaseData:
    config: CaseConfig
    csv_path: Path
    records: list[CaseRecord]
    selections: list[Selection]


def load_case_data(config_path: Path, data_dir: Path) -> CaseData:
    config = load_case_config(config_path)
    csv_path = data_dir / config.csv
    if not csv_path.exists():
        raise CaseDataMissingError(f"нет файла кейса {csv_path}")
    records = load_records(csv_path)
    return CaseData(config, csv_path, records, select_records(records, config))
