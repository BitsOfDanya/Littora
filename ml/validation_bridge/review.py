"""Prepare independent review forms; unknown pixels never become water labels."""

import json
import shutil
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports/validation_bridge"


def evaluation_ready(record):
    reviewers = record.get("reviewer_ids", [])
    return bool(
        len(reviewers) >= 2
        and len(set(reviewers)) == len(reviewers)
        and all(str(x).strip() for x in reviewers)
        and record.get("adjudicator_id")
        and record.get("adjudication_status") == "complete"
        and record.get("evidence_audit_passed") is True
        and record.get("prediction_blind_review") is True
        and record.get("reference_pixels", 0) > 0
    )


def main():
    registry = pd.read_csv(OUT / "tables/blacksea_holdout_registry.csv")
    forms = []
    for row in registry.itertuples():
        if row.review_status != "pending_two_reviewers":
            continue
        folder = ROOT / row.folder
        for reviewer in ["reviewer_a", "reviewer_b"]:
            dest = folder / reviewer
            dest.mkdir(exist_ok=True)
            for filename in ["labels.tif", "annotations.geojson"]:
                if not (dest / filename).exists():
                    shutil.copy2(folder / filename, dest / filename)
            path = dest / "review.json"
            if not path.exists():
                path.write_text(
                    json.dumps(
                        {
                            "chip_id": row.chip_id,
                            "reviewer_id": "",
                            "status": "pending",
                            "prediction_blind_review": True,
                            "classes": {
                                0: "ignore",
                                1: "debris",
                                4: "natural_organics",
                                5: "ship",
                                7: "water",
                                9: "foam",
                                12: "waves_wakes",
                            },
                            "evidence": [],
                            "notes": "",
                        },
                        indent=2,
                    )
                )
            forms.append(
                {
                    "chip_id": row.chip_id,
                    "reviewer_slot": reviewer,
                    "review_form": str(path.relative_to(ROOT)),
                    "status": "pending",
                    "reviewer_id": "",
                    "reviewed_at_utc": "",
                    "training_allowed": False,
                }
            )
    # This is an assignment template, not the authoritative status of edited review.json files.
    pd.DataFrame(forms).to_csv(
        OUT / "tables/reviewer_assignment_template.csv", index=False
    )


if __name__ == "__main__":
    main()
