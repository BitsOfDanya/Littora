from __future__ import annotations

import csv
import datetime as dt
import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any

from shapely.geometry import mapping

from app.case.concentration import UNIT
from app.case.config import CaseConfig
from app.case.pairing import PAIR_REASON_LABELS, EventResult, PairRow
from app.case.selection import Selection

OBSERVATIONS_FILE = "observations.csv"
PAIRS_FILE = "pairs.csv"
EVENTS_FILE = "events.geojson"
SUMMARY_FILE = "summary.json"

OBSERVATION_COLUMNS = [
    "sample_id",
    "event_id",
    "source_id",
    "record_type",
    "measurement_profile",
    "target_scope",
    "material",
    "size_class",
    "date_utc",
    "time_start_utc",
    "time_end_utc",
    "latitude",
    "longitude",
    "position_role",
    "published_items_km2",
    "items",
    "area_km2",
    "recomputed_items_km2",
    "concentration_check",
    "target_key",
    "decision",
    "reason_code",
    "reason",
    "quality_flags",
]
PAIR_COLUMNS = [
    "event_id",
    "target_keys",
    "sample_ids",
    "scene_id",
    "collection",
    "platform",
    "scene_datetime",
    "event_date",
    "event_time",
    "time_known",
    "shift_hours",
    "shift_days",
    "time_uncertainty_hours",
    "drift_km_max",
    "tile_cloud",
    "footprint_kind",
    "footprint_area_km2",
    "geometry_approximate",
    "water",
    "cloud",
    "shadow",
    "snow",
    "land",
    "nodata",
    "bright_water",
    "decision",
    "reason_code",
    "reason",
    "detail",
]


def _number(value: float | None, digits: int = 4) -> str:
    return "" if value is None else f"{round(value, digits):g}"


def round_coordinates(value: Any, digits: int = 5) -> Any:
    if isinstance(value, float):
        return round(value, digits)
    if isinstance(value, list | tuple):
        return [round_coordinates(item, digits) for item in value]
    if isinstance(value, dict):
        return {key: round_coordinates(item, digits) for key, item in value.items()}
    return value


def observation_row(selection: Selection) -> dict[str, str]:
    record, check = selection.record, selection.check
    return {
        "sample_id": record.sample_id,
        "event_id": record.event_id,
        "source_id": record.source_id,
        "record_type": record.record_type,
        "measurement_profile": record.profile,
        "target_scope": record.scope,
        "material": record.text("material"),
        "size_class": record.text("size_class"),
        "date_utc": record.text("date_utc"),
        "time_start_utc": record.text("time_start_utc"),
        "time_end_utc": record.text("time_end_utc"),
        "latitude": record.text("latitude"),
        "longitude": record.text("longitude"),
        "position_role": record.text("position_role"),
        "published_items_km2": _number(check.published, 6),
        "items": _number(record.items, 3),
        "area_km2": _number(record.area_km2, 6),
        "recomputed_items_km2": _number(check.recomputed, 6),
        "concentration_check": check.status.value,
        "target_key": selection.target_key or "",
        "decision": "accepted" if selection.accepted else "rejected",
        "reason_code": selection.reason.value,
        "reason": selection.label,
        "quality_flags": ";".join(record.flags),
    }


def pair_row(row: PairRow) -> dict[str, str]:
    event, scene, quality = row.event, row.scene, row.quality
    shares = quality.as_dict() if quality else {}
    return {
        "event_id": event.event_id,
        "target_keys": ";".join(event.target_keys),
        "sample_ids": ";".join(event.sample_ids),
        "scene_id": scene.id,
        "collection": scene.collection,
        "platform": scene.platform,
        "scene_datetime": scene.acquired_at.isoformat().replace("+00:00", "Z"),
        "event_date": event.record.text("date_utc"),
        "event_time": event.record.observed_at.isoformat() if event.record.observed_at else "",
        "time_known": "yes" if event.record.observed_at else "no",
        "shift_hours": _number(row.shift_hours, 2),
        "shift_days": str(row.shift_days),
        "time_uncertainty_hours": _number(row.uncertainty_hours, 1),
        "drift_km_max": _number(row.drift_km_max, 2),
        "tile_cloud": _number(scene.cloud_cover, 3),
        "footprint_kind": "",
        "footprint_area_km2": "",
        "geometry_approximate": "",
        "water": _number(shares.get("water")),
        "cloud": _number(shares.get("cloud")),
        "shadow": _number(shares.get("shadow")),
        "snow": _number(shares.get("snow")),
        "land": _number(shares.get("land")),
        "nodata": _number(shares.get("nodata")),
        "bright_water": _number(shares.get("bright_water")),
        "decision": row.decision.value,
        "reason_code": row.reason.value,
        "reason": PAIR_REASON_LABELS[row.reason],
        "detail": row.detail,
    }


def event_feature(result: EventResult) -> dict[str, Any]:
    event, footprint, best = result.event, result.footprint, result.best
    geometry = round_coordinates(mapping(footprint.analysis)) if footprint else None
    return {
        "type": "Feature",
        "id": event.event_id,
        "geometry": geometry,
        "properties": {
            "event_id": event.event_id,
            "source_id": event.source_id,
            "target_keys": list(event.target_keys),
            "sample_ids": list(event.sample_ids),
            "date": event.record.text("date_utc"),
            "time": event.record.observed_at.isoformat() if event.record.observed_at else None,
            "footprint_kind": footprint.kind.value if footprint else None,
            "footprint_label": footprint.label if footprint else None,
            "footprint_area_km2": round(footprint.analysis_area_km2, 4) if footprint else None,
            "geometry_approximate": footprint.approximate if footprint else None,
            "candidates": len(result.pairs),
            "accepted": sum(1 for pair in result.pairs if pair.decision.value == "accepted"),
            "best_scene_id": best.scene.id if best else None,
            "best_platform": best.scene.platform if best else None,
            "best_shift_hours": round(best.shift_hours, 2)
            if best and best.shift_hours is not None
            else None,
            "best_shift_days": best.shift_days if best else None,
            "decision": result.decision.value,
            "reason_code": result.reason.value,
            "reason": PAIR_REASON_LABELS[result.reason],
            "detail": result.detail,
        },
    }


def _write_csv(path: Path, columns: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def selection_summary(config: CaseConfig, selections: list[Selection]) -> dict[str, Any]:
    accepted = [s for s in selections if s.accepted]
    return {
        "unit": UNIT,
        "primary_target": config.primary_target.key,
        "targets": [
            {
                "key": target.key,
                "primary": target.primary,
                "title": target.title,
                "records": sum(1 for s in accepted if s.target_key == target.key),
                "events": len({s.record.event_id for s in accepted if s.target_key == target.key}),
                "profiles": list(target.profiles),
            }
            for target in config.targets
        ],
        "records": len(selections),
        "selection": dict(sorted(Counter(s.reason.value for s in selections).items())),
        "concentration_checks": dict(
            sorted(
                Counter(
                    s.check.status.value
                    for s in selections
                    if s.record.record_type == config.selection.record_type
                ).items()
            )
        ),
    }


def write_selection(out_dir: Path, config: CaseConfig, selections: list[Selection]) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = [observation_row(s) for s in sorted(selections, key=lambda s: s.record.sample_id)]
    _write_csv(out_dir / OBSERVATIONS_FILE, OBSERVATION_COLUMNS, rows)
    return selection_summary(config, selections)


def write_pairing(
    out_dir: Path,
    config: CaseConfig,
    selections: list[Selection],
    results: list[EventResult],
) -> dict:
    summary = write_selection(out_dir, config, selections)
    pair_rows = []
    for result in sorted(results, key=lambda r: r.event.event_id):
        footprint = result.footprint
        for pair in result.pairs:
            row = pair_row(pair)
            if footprint:
                row["footprint_kind"] = footprint.kind.value
                row["footprint_area_km2"] = _number(footprint.analysis_area_km2, 4)
                row["geometry_approximate"] = "yes" if footprint.approximate else "no"
            pair_rows.append(row)
    _write_csv(out_dir / PAIRS_FILE, PAIR_COLUMNS, pair_rows)
    features = [event_feature(r) for r in sorted(results, key=lambda r: r.event.event_id)]
    _write_json(out_dir / EVENTS_FILE, {"type": "FeatureCollection", "features": features})
    accepted = [
        {
            "event_id": r.event.event_id,
            "scene_id": r.best.scene.id,
            "platform": r.best.scene.platform,
            "shift_days": r.best.shift_days,
            "shift_hours": r.best.shift_hours,
            "water": r.best.quality.water if r.best.quality else None,
        }
        for r in results
        if r.best and r.best.decision.value == "accepted"
    ]
    summary.update(
        {
            "generated": dt.date.today().isoformat(),
            "catalog": config.pairing.catalog,
            "pairing_rules": {
                key: (value.isoformat() if isinstance(value, dt.date) else value)
                for key, value in asdict(config.pairing).items()
            },
            "events": dict(sorted(Counter(r.decision.value for r in results).items())),
            "event_reasons": dict(sorted(Counter(r.reason.value for r in results).items())),
            "pairs": dict(sorted(Counter(row["decision"] for row in pair_rows).items())),
            "pair_reasons": dict(sorted(Counter(row["reason_code"] for row in pair_rows).items())),
            "accepted_pairs": sorted(accepted, key=lambda item: item["event_id"]),
        }
    )
    _write_json(out_dir / SUMMARY_FILE, summary)
    return summary


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
