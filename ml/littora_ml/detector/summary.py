from __future__ import annotations

import json

import pandas as pd

from littora_ml.common.io import write_json
from littora_ml.common.paths import REPORTS

KEYS = ("precision", "recall", "f1", "iou", "pr_auc")


def detector_summary() -> pd.DataFrame:
    rows = []
    for path in sorted((REPORTS / "metrics" / "detector").glob("*.json")):
        if path.name.startswith(("summary", "calibration__", "regions_service__")):
            continue
        report = json.loads(path.read_text(encoding="utf-8"))
        post = (report.get("postprocessing") or {}).get("chosen") or {}
        row = {
            "run": report["name"],
            "data": report["config"].get("data"),
            "split": report["config"].get("split"),
            "threshold": round(report["threshold"], 4),
            "threshold_source": report.get("threshold_source"),
            "tta": (report.get("tta") or {}).get("used"),
            "postprocessing": f"scl={post.get('scl')} min={post.get('min_pixels')}" if post else "",
        }
        for split in ("val", "test"):
            for key in KEYS:
                value = report[split].get(key)
                row[f"{split}_{key}"] = round(value, 4) if value is not None else None
            row[f"{split}_positives"] = report[split]["positives"]
        rows.append(row)
    frame = pd.DataFrame(rows).sort_values(["data", "val_f1"], ascending=[True, False])
    frame.to_csv(REPORTS / "metrics" / "detector" / "summary.csv", index=False)
    write_json(REPORTS / "metrics" / "detector" / "summary.json", frame.to_dict(orient="records"))
    return frame
