from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from app.core.config import get_settings
from app.review.audit import AUDIT_FILE, AUDIT_REVIEWER, LABELS, REQUIRED, audit_record


def import_audit(source: Path, target: Path, reviewer: str = AUDIT_REVIEWER) -> int:
    with source.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = [name for name in reader.fieldnames or [] if name != "reviewer"]
        rows = list(reader)
    missing = [name for name in REQUIRED if name not in columns]
    if missing:
        raise ValueError(f"в CSV нет колонок: {', '.join(missing)}")
    seen: set[tuple[str, str]] = set()
    for number, row in enumerate(rows, start=2):
        key = (row["scene_id"], row["zone_id"])
        if key in seen:
            raise ValueError(f"строка {number}: зона {row['zone_id']} повторяется")
        seen.add(key)
        if row["class"] not in LABELS:
            raise ValueError(f"строка {number}: неизвестный класс «{row['class']}»")
        if row["confidence"] not in {"1", "2", "3"}:
            raise ValueError(f"строка {number}: уверенность должна быть 1–3")
        if audit_record(row) is None:
            raise ValueError(f"строка {number}: координаты, пиксели или вероятность не читаются")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[*columns, "reviewer"], lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({**{name: row.get(name, "") for name in columns}, "reviewer": reviewer})
    return len(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.review.seed")
    parser.add_argument("source", type=Path)
    parser.add_argument("--out", type=Path, default=get_settings().data_dir / AUDIT_FILE)
    parser.add_argument("--reviewer", default=AUDIT_REVIEWER)
    args = parser.parse_args(argv)
    count = import_audit(args.source, args.out, args.reviewer)
    print(f"{count} зон → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
