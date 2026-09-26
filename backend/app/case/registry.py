from __future__ import annotations

import ast
import csv
import datetime as dt
import hashlib
import json
import platform
import statistics
from collections import Counter, defaultdict
from dataclasses import asdict
from decimal import ROUND_DOWN, ROUND_UP, Decimal
from importlib import metadata
from pathlib import Path
from typing import Any

import rasterio
import shapely
from shapely.geometry import mapping

from app.case.concentration import UNIT, CheckStatus
from app.case.config import CaseConfig, Target
from app.case.geometry import Footprint
from app.case.pairing import (
    PAIR_REASON_LABELS,
    EventResult,
    PairDecision,
    PairRow,
    SyncKind,
    pass_key,
)
from app.case.selection import Selection

OBSERVATIONS_FILE = "observations.csv"
PAIRS_FILE = "pairs.csv"
EVENTS_FILE = "events.geojson"
SUMMARY_FILE = "summary.json"

APP_ROOT = Path(__file__).resolve().parents[1]
APP_PACKAGE = "app"
CODE_ENTRYPOINT = "case/__main__.py"
RUNTIME_PACKAGES = ("numpy", "shapely", "rasterio")

HOURS_DIGITS = 2
KM_DIGITS = 2
AREA_DIGITS = 4
SHARE_DIGITS = 4
PERCENT_DIGITS = 2
DEGREE_DIGITS = 2
METER_DIGITS = 1
CONCENTRATION_DIGITS = 6
ITEMS_DIGITS = 3

NEVER_SMALLER = ROUND_UP
NEVER_LARGER = ROUND_DOWN
SHARE_ROUNDING = {
    "water": NEVER_LARGER,
    "cloud": NEVER_SMALLER,
    "shadow": NEVER_SMALLER,
    "nodata": NEVER_SMALLER,
    "bright_water": NEVER_SMALLER,
}

VERIFIABLE_CHECKS = (CheckStatus.MATCH, CheckStatus.ROUNDING, CheckStatus.MISMATCH)
OFFSET_MEASURES = {
    SyncKind.TIME_KNOWN: "abs_shift",
    SyncKind.DAYLIGHT_BOUNDED: "upper_bound",
    SyncKind.DAY_ONLY: "upper_bound",
}

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
    "source_id",
    "target_keys",
    "sample_ids",
    "scene_id",
    "collection",
    "platform",
    "tile",
    "relative_orbit",
    "pass_id",
    "tile_duplicate_of",
    "scene_datetime",
    "sun_elevation",
    "event_date",
    "event_time",
    "time_known",
    "shift_hours",
    "shift_days",
    "time_uncertainty_hours",
    "sync",
    "drift_km_max",
    "tile_cloud",
    "footprint_kind",
    "footprint_radius_m",
    "footprint_area_km2",
    "geometry_approximate",
    "coverage_fraction",
    "pixels",
    "water",
    "cloud",
    "shadow",
    "snow",
    "land",
    "nodata",
    "other",
    "bright_water",
    "decision",
    "reason_code",
    "reason",
    "detail",
]


def rounded(value: float | None, digits: int, rounding: str | None = None) -> float | None:
    if value is None:
        return None
    if rounding is None:
        return round(value, digits) + 0.0
    step = Decimal(1).scaleb(-digits)
    return float(Decimal(repr(value)).quantize(step, rounding=rounding)) + 0.0


def _number(value: float | None, digits: int, rounding: str | None = None) -> str:
    return "" if value is None else f"{rounded(value, digits, rounding):.{digits}f}"


def _share(shares: dict[str, float | int | None], name: str) -> str:
    return _number(shares.get(name), SHARE_DIGITS, SHARE_ROUNDING.get(name))


def _timestamp(moment: dt.datetime) -> str:
    return moment.isoformat().replace("+00:00", "Z")


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
        "published_items_km2": _number(check.published, CONCENTRATION_DIGITS),
        "items": _number(record.items, ITEMS_DIGITS),
        "area_km2": _number(record.area_km2, CONCENTRATION_DIGITS),
        "recomputed_items_km2": _number(check.recomputed, CONCENTRATION_DIGITS),
        "concentration_check": check.status.value,
        "target_key": selection.target_key or "",
        "decision": "accepted" if selection.accepted else "rejected",
        "reason_code": selection.reason.value,
        "reason": selection.label,
        "quality_flags": ";".join(record.flags),
    }


def pair_row(row: PairRow, footprint: Footprint | None, duplicate_of: str = "") -> dict[str, str]:
    event, scene, quality = row.event, row.scene, row.quality
    shares = quality.as_dict() if quality else {}
    observed = event.record.observed_at
    return {
        "event_id": event.event_id,
        "source_id": event.source_id,
        "target_keys": ";".join(event.target_keys),
        "sample_ids": ";".join(event.sample_ids),
        "scene_id": scene.id,
        "collection": scene.collection,
        "platform": scene.platform,
        "tile": scene.tile,
        "relative_orbit": "" if scene.relative_orbit is None else str(scene.relative_orbit),
        "pass_id": pass_key(scene),
        "tile_duplicate_of": duplicate_of,
        "scene_datetime": _timestamp(scene.acquired_at),
        "sun_elevation": _number(scene.sun_elevation, DEGREE_DIGITS),
        "event_date": event.record.text("date_utc"),
        "event_time": _timestamp(observed) if observed else "",
        "time_known": "yes" if observed else "no",
        "shift_hours": _number(row.shift_hours, HOURS_DIGITS, NEVER_SMALLER),
        "shift_days": str(row.shift_days),
        "time_uncertainty_hours": _number(row.uncertainty_hours, HOURS_DIGITS, NEVER_SMALLER),
        "sync": row.sync.value,
        "drift_km_max": _number(row.drift_km_max, KM_DIGITS, NEVER_SMALLER),
        "tile_cloud": _number(scene.cloud_cover, PERCENT_DIGITS, NEVER_SMALLER),
        "footprint_kind": footprint.kind.value if footprint else "",
        "footprint_radius_m": _number(footprint.radius_m, METER_DIGITS) if footprint else "",
        "footprint_area_km2": _number(footprint.analysis_area_km2, AREA_DIGITS)
        if footprint
        else "",
        "geometry_approximate": ("yes" if footprint.approximate else "no") if footprint else "",
        "coverage_fraction": _number(row.coverage_fraction, SHARE_DIGITS, NEVER_LARGER),
        "pixels": "" if quality is None else str(quality.pixels),
        "water": _share(shares, "water"),
        "cloud": _share(shares, "cloud"),
        "shadow": _share(shares, "shadow"),
        "snow": _share(shares, "snow"),
        "land": _share(shares, "land"),
        "nodata": _share(shares, "nodata"),
        "other": _share(shares, "other"),
        "bright_water": _share(shares, "bright_water"),
        "decision": row.decision.value,
        "reason_code": row.reason.value,
        "reason": PAIR_REASON_LABELS[row.reason],
        "detail": row.detail,
    }


def distinct_pairs(result: EventResult) -> list[PairRow]:
    duplicates = result.tile_duplicates
    return [pair for pair in result.pairs if pair.scene.id not in duplicates]


def event_feature(result: EventResult) -> dict[str, Any]:
    event, footprint, best = result.event, result.footprint, result.best
    geometry = round_coordinates(mapping(footprint.analysis)) if footprint else None
    distinct = distinct_pairs(result)
    observed = event.record.observed_at
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
            "time": _timestamp(observed) if observed else None,
            "footprint_kind": footprint.kind.value if footprint else None,
            "footprint_label": footprint.label if footprint else None,
            "footprint_radius_m": rounded(footprint.radius_m, METER_DIGITS) if footprint else None,
            "footprint_area_km2": rounded(footprint.analysis_area_km2, AREA_DIGITS)
            if footprint
            else None,
            "geometry_approximate": footprint.approximate if footprint else None,
            "candidates": len(result.pairs),
            "candidate_passes": len(distinct),
            "accepted": sum(1 for pair in result.pairs if pair.decision is PairDecision.ACCEPTED),
            "accepted_passes": sum(
                1 for pair in distinct if pair.decision is PairDecision.ACCEPTED
            ),
            "best_scene_id": best.scene.id if best else None,
            "best_platform": best.scene.platform if best else None,
            "best_sync": best.sync.value if best else None,
            "best_shift_hours": rounded(best.shift_hours, HOURS_DIGITS, NEVER_SMALLER)
            if best
            else None,
            "best_shift_days": best.shift_days if best else None,
            "best_time_uncertainty_hours": rounded(
                best.uncertainty_hours, HOURS_DIGITS, NEVER_SMALLER
            )
            if best
            else None,
            "best_coverage_fraction": rounded(best.coverage_fraction, SHARE_DIGITS, NEVER_LARGER)
            if best
            else None,
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


def _target_summary(target: Target, accepted: list[Selection]) -> dict[str, Any]:
    chosen = [s for s in accepted if s.target_key == target.key]
    checks = Counter(s.check.status.value for s in chosen)
    verifiable = sum(1 for s in chosen if s.check.status in VERIFIABLE_CHECKS)
    return {
        "key": target.key,
        "primary": target.primary,
        "title": target.title,
        "records": len(chosen),
        "events": len({s.record.event_id for s in chosen}),
        "profiles": list(target.profiles),
        "concentration_checks": dict(sorted(checks.items())),
        "verifiable_records": verifiable,
        "verifiable_share": rounded(verifiable / len(chosen), SHARE_DIGITS) if chosen else None,
    }


def selection_summary(config: CaseConfig, selections: list[Selection]) -> dict[str, Any]:
    accepted = [s for s in selections if s.accepted]
    rules = config.selection
    return {
        "unit": UNIT,
        "primary_target": config.primary_target.key,
        "selection_rules": {
            "record_type": rules.record_type,
            "category_scopes": list(rules.category_scopes),
            "exclude_flags": list(rules.exclude_flags),
            "reject_on_mismatch": rules.reject_on_mismatch,
        },
        "targets": [_target_summary(target, accepted) for target in config.targets],
        "records": len(selections),
        "selection": dict(sorted(Counter(s.reason.value for s in selections).items())),
        "concentration_checks": dict(
            sorted(
                Counter(
                    s.check.status.value
                    for s in selections
                    if s.record.record_type == rules.record_type
                ).items()
            )
        ),
    }


def write_selection(out_dir: Path, config: CaseConfig, selections: list[Selection]) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = [observation_row(s) for s in sorted(selections, key=lambda s: s.record.sample_id)]
    _write_csv(out_dir / OBSERVATIONS_FILE, OBSERVATION_COLUMNS, rows)
    return selection_summary(config, selections)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _imported_modules(path: Path) -> set[str]:
    modules = set()
    for node in ast.walk(ast.parse(path.read_bytes(), filename=str(path))):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.add(node.module)
            modules.update(f"{node.module}.{alias.name}" for alias in node.names)
    return modules


def _module_file(root: Path, parts: list[str]) -> Path | None:
    if parts[0] != APP_PACKAGE:
        return None
    base = root.joinpath(*parts[1:])
    candidates = [base / "__init__.py"]
    if len(parts) > 1:
        candidates.insert(0, base.with_suffix(".py"))
    return next((path for path in candidates if path.is_file()), None)


def code_files(root: Path = APP_ROOT, entrypoint: str = CODE_ENTRYPOINT) -> list[Path]:
    pending = [root / entrypoint]
    seen: set[Path] = set()
    while pending:
        path = pending.pop()
        if path in seen:
            continue
        seen.add(path)
        for module in _imported_modules(path):
            parts = module.split(".")
            for size in range(1, len(parts) + 1):
                found = _module_file(root, parts[:size])
                if found is not None and found not in seen:
                    pending.append(found)
    return sorted(seen)


def code_fingerprint(root: Path = APP_ROOT, entrypoint: str = CODE_ENTRYPOINT) -> dict[str, Any]:
    digest = hashlib.sha256()
    names = []
    for path in code_files(root, entrypoint):
        name = path.relative_to(root).as_posix()
        content = path.read_bytes()
        digest.update(f"{name}\0{len(content)}\0".encode())
        digest.update(content)
        names.append(name)
    return {"sha256": digest.hexdigest(), "files": names}


def runtime_versions() -> dict[str, str]:
    return {
        "python": platform.python_version(),
        **{name: metadata.version(name) for name in RUNTIME_PACKAGES},
        "geos": shapely.geos_version_string,
        "gdal": rasterio.__gdal_version__,
    }


def _stats(
    values: list[float], digits: int, rounding: str | None = None
) -> dict[str, float | int] | None:
    if not values:
        return None
    ordered = sorted(values)
    quartiles = (
        statistics.quantiles(ordered, n=4, method="inclusive")
        if len(ordered) > 1
        else [ordered[0]] * 3
    )
    return {
        "n": len(ordered),
        "min": rounded(ordered[0], digits, rounding),
        "q1": rounded(quartiles[0], digits, rounding),
        "median": rounded(statistics.median(ordered), digits, rounding),
        "q3": rounded(quartiles[2], digits, rounding),
        "max": rounded(ordered[-1], digits, rounding),
    }


def _offset_hours(row: PairRow) -> float:
    return abs(row.shift_hours) if row.shift_hours is not None else row.uncertainty_hours


def _offset_bins(values: list[float]) -> dict[str, int]:
    edges = [(3, "0-3 h"), (6, "3-6 h"), (12, "6-12 h"), (24, "12-24 h"), (72, "1-3 d")]
    counts = Counter()
    for hours in values:
        label = next((name for edge, name in edges if hours <= edge), "> 3 d")
        counts[label] += 1
    return {name: counts.get(name, 0) for _, name in edges} | {"> 3 d": counts.get("> 3 d", 0)}


def _time_offsets(rows: list[PairRow]) -> dict[str, Any]:
    offsets = {}
    for sync in SyncKind:
        subset = [row for row in rows if row.sync is sync]
        values = [_offset_hours(row) for row in subset]
        accepted = [_offset_hours(row) for row in subset if row.decision is PairDecision.ACCEPTED]
        offsets[sync.value] = {
            "measure": OFFSET_MEASURES[sync],
            "all_pairs": _stats(values, HOURS_DIGITS, NEVER_SMALLER),
            "accepted_pairs": _stats(accepted, HOURS_DIGITS, NEVER_SMALLER),
            "bins_all_pairs": _offset_bins(values),
        }
    return offsets


def _quality(rows: list[PairRow]) -> dict[str, Any]:
    evaluated = [row.quality for row in rows if row.quality is not None]
    names = ("water", "cloud", "shadow", "nodata", "land", "other", "bright_water")
    return {
        "evaluated_pairs": len(evaluated),
        "pixels": _stats([float(q.pixels) for q in evaluated], 0),
        **{
            name: _stats(
                [value for q in evaluated if (value := getattr(q, name)) is not None],
                SHARE_DIGITS,
                SHARE_ROUNDING.get(name),
            )
            for name in names
        },
    }


def _grouped(results: list[EventResult], key) -> dict[str, dict[str, int]]:
    groups: dict[str, Counter] = defaultdict(Counter)
    for result in results:
        for group in key(result):
            groups[group][result.reason.value] += 1
    return {group: dict(sorted(counts.items())) for group, counts in sorted(groups.items())}


def _accepted_entry(result: EventResult) -> dict[str, Any]:
    best, footprint = result.best, result.footprint
    return {
        "event_id": result.event.event_id,
        "source_id": result.event.source_id,
        "sample_ids": list(result.event.sample_ids),
        "target_keys": list(result.event.target_keys),
        "scene_id": best.scene.id,
        "collection": best.scene.collection,
        "platform": best.scene.platform,
        "tile": best.scene.tile,
        "pass_id": pass_key(best.scene),
        "scene_datetime": _timestamp(best.scene.acquired_at),
        "shift_days": best.shift_days,
        "shift_hours": rounded(best.shift_hours, HOURS_DIGITS, NEVER_SMALLER),
        "time_uncertainty_hours": rounded(best.uncertainty_hours, HOURS_DIGITS, NEVER_SMALLER),
        "sync": best.sync.value,
        "footprint_kind": footprint.kind.value if footprint else None,
        "footprint_radius_m": rounded(footprint.radius_m, METER_DIGITS) if footprint else None,
        "coverage_fraction": rounded(best.coverage_fraction, SHARE_DIGITS, NEVER_LARGER),
        "water": rounded(best.quality.water, SHARE_DIGITS, NEVER_LARGER) if best.quality else None,
    }


def _counts(values) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))


def write_pairing(
    out_dir: Path,
    config: CaseConfig,
    selections: list[Selection],
    results: list[EventResult],
    provenance: dict[str, Any] | None = None,
) -> dict:
    summary = write_selection(out_dir, config, selections)
    ordered = sorted(results, key=lambda r: r.event.event_id)
    pair_rows = []
    distinct: list[PairRow] = []
    for result in ordered:
        duplicates = result.tile_duplicates
        for pair in result.pairs:
            duplicate_of = duplicates.get(pair.scene.id, "")
            pair_rows.append(pair_row(pair, result.footprint, duplicate_of))
            if not duplicate_of:
                distinct.append(pair)
    _write_csv(out_dir / PAIRS_FILE, PAIR_COLUMNS, pair_rows)
    features = [event_feature(r) for r in ordered]
    _write_json(out_dir / EVENTS_FILE, {"type": "FeatureCollection", "features": features})
    accepted_results = [r for r in ordered if r.decision is PairDecision.ACCEPTED]
    summary.update(
        {
            "provenance": provenance or {},
            "catalog": config.pairing.catalog,
            "pairing_rules": {
                key: (value.isoformat() if isinstance(value, dt.date) else value)
                for key, value in asdict(config.pairing).items()
            },
            "events": _counts(r.decision.value for r in results),
            "event_reasons": _counts(r.reason.value for r in results),
            "event_reasons_by_source": _grouped(results, lambda r: [r.event.source_id]),
            "event_reasons_by_target": _grouped(results, lambda r: list(r.event.target_keys)),
            "scene_candidates": len(pair_rows),
            "tile_duplicates": len(pair_rows) - len(distinct),
            "scene_passes": len(distinct),
            "pairs": _counts(pair.decision.value for pair in distinct),
            "pair_reasons": _counts(pair.reason.value for pair in distinct),
            "pair_collections": _counts(pair.scene.collection for pair in distinct),
            "time_offset_hours": _time_offsets(distinct),
            "sync_accepted_events": _counts(r.best.sync.value for r in accepted_results),
            "quality": _quality(distinct),
            "accepted_pairs": [_accepted_entry(r) for r in accepted_results],
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
