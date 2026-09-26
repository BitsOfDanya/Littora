from __future__ import annotations

import argparse
from pathlib import Path

from app import __version__
from app.case.data import load_case_data
from app.case.pairing import PairingEngine, build_event_inputs
from app.case.registry import (
    OBSERVATIONS_FILE,
    code_fingerprint,
    file_sha256,
    runtime_versions,
    write_pairing,
    write_selection,
)
from app.core.config import get_settings
from app.earth.catalog import StacCatalog
from app.earth.raster import quality_shares


def _print_counts(title: str, counts: dict) -> None:
    print(title)
    for key, value in counts.items():
        print(f"  {key:<24} {value}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m app.case",
        description="Подготовка данных кейса: отбор наблюдений и подбор спутниковых пар.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    select = commands.add_parser("select", help="отбор наблюдений по целевым величинам")
    pair = commands.add_parser("pair", help="отбор и подбор пар со снимками, нужен интернет")
    pair.add_argument("--workers", type=int, default=8)
    for command in (select, pair):
        command.add_argument("--out", type=Path, help="куда писать реестр")
    args = parser.parse_args(argv)

    settings = get_settings()
    data = load_case_data(settings.case_config, settings.data_dir)
    out = args.out or settings.registry_dir
    if args.command == "select":
        summary = write_selection(out, data.config, data.selections)
        _print_counts("отбор записей:", summary["selection"])
        _print_counts("проверка N/A:", summary["concentration_checks"])
        print(f"реестр: {out / OBSERVATIONS_FILE}")
        return

    rules = data.config.pairing
    provenance = {
        "dataset": data.csv_path.name,
        "dataset_sha256": file_sha256(data.csv_path),
        "dataset_rows": len(data.records),
        "config": settings.case_config.name,
        "config_sha256": file_sha256(settings.case_config),
        "catalog": rules.catalog,
        "collections": [rules.sentinel2, rules.sentinel2_fallback, rules.landsat],
        "code_version": __version__,
        "code_fingerprint": code_fingerprint(),
        "runtime": runtime_versions(),
    }
    engine = PairingEngine(
        rules,
        StacCatalog(rules.catalog),
        lambda scene, footprint: quality_shares(
            scene, footprint.analysis, rules.bright_water_reflectance
        ),
    )
    events = build_event_inputs(data.selections, data.config.selection.record_type)
    results = engine.pair_events(events, args.workers)
    summary = write_pairing(out, data.config, data.selections, results, provenance)
    _print_counts("отбор записей:", summary["selection"])
    _print_counts("события:", summary["events"])
    _print_counts("причины по событиям:", summary["event_reasons"])
    _print_counts("пары (без дублей тайлов):", summary["pair_reasons"])
    print(
        f"пар-кандидатов: {summary['scene_candidates']}, "
        f"дублей тайлов: {summary['tile_duplicates']}, "
        f"событий с принятой парой: {len(summary['accepted_pairs'])}; реестр: {out}"
    )
