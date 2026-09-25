from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import warnings
from collections import Counter
from pathlib import Path

from fetch import DATA_DIR, MANIFEST_DIR, format_size, md5_of

RASTER_SUFFIXES = {".tif", ".tiff", ".jp2", ".nc", ".vrt", ".img", ".hdf", ".h5"}
COMPOUND_SUFFIXES = (".tar.gz", ".shp.xml", ".aux.xml")
LIST_LIMIT = 20_000
RASTER_SAMPLES = 8


def suffix_of(path: Path) -> str:
    name = path.name.lower()
    for compound in COMPOUND_SUFFIXES:
        if name.endswith(compound):
            return compound
    return path.suffix.lower() or "без расширения"


def collect(folder: Path) -> list[Path]:
    return sorted(
        path
        for path in folder.rglob("*")
        if path.is_file()
        and not any(part.startswith(".") for part in path.relative_to(folder).parts)
    )


def describe_raster(path: Path, root: Path) -> dict:
    import rasterio

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", rasterio.errors.NotGeoreferencedWarning)
        dataset = rasterio.open(path)
    with dataset:
        return {
            "file": path.relative_to(root).as_posix(),
            "width": dataset.width,
            "height": dataset.height,
            "bands": dataset.count,
            "dtype": dataset.dtypes[0] if dataset.count else None,
            "crs": dataset.crs.to_string() if dataset.crs else None,
            "resolution": [round(value, 6) for value in dataset.res],
            "band_names": [name for name in dataset.descriptions if name],
            "variables": [name.rsplit(":", 1)[-1] for name in dataset.subdatasets],
        }


def sample_rasters(files: list[Path], root: Path) -> list[dict]:
    if importlib.util.find_spec("rasterio") is None:
        return []
    samples = []
    for path in [path for path in files if suffix_of(path) in RASTER_SUFFIXES][:RASTER_SAMPLES]:
        try:
            samples.append(describe_raster(path, root))
        except Exception as error:
            samples.append({"file": path.relative_to(root).as_posix(), "error": str(error)})
    return samples


def summarise(files: list[Path], root: Path, with_md5: bool) -> dict:
    by_suffix: Counter[str] = Counter()
    bytes_by_suffix: Counter[str] = Counter()
    by_folder: Counter[str] = Counter()
    for path in files:
        size = path.stat().st_size
        suffix = suffix_of(path)
        by_suffix[suffix] += 1
        bytes_by_suffix[suffix] += size
        parts = path.relative_to(root).parts
        by_folder[parts[0] if len(parts) > 1 else "."] += 1
    summary = {
        "files": len(files),
        "bytes": sum(bytes_by_suffix.values()),
        "by_suffix": {
            suffix: {"files": count, "bytes": bytes_by_suffix[suffix]}
            for suffix, count in by_suffix.most_common()
        },
        "by_folder": dict(by_folder.most_common()),
        "rasters": sample_rasters(files, root),
    }
    if len(files) <= LIST_LIMIT:
        summary["listing"] = [
            {
                "file": path.relative_to(root).as_posix(),
                "bytes": path.stat().st_size,
                **({"md5": md5_of(path)} if with_md5 else {}),
            }
            for path in files
        ]
    return summary


def print_summary(name: str, summary: dict) -> None:
    print(f"{name}: {summary['files']} файл(ов), {format_size(summary['bytes'])}")
    print("  по типам:")
    for suffix, stats in list(summary["by_suffix"].items())[:15]:
        print(f"    {suffix:<16} {stats['files']:>7}  {format_size(stats['bytes']):>10}")
    print("  по папкам верхнего уровня:")
    for folder, count in list(summary["by_folder"].items())[:15]:
        print(f"    {folder:<32} {count:>7}")
    for raster in summary["rasters"]:
        if "error" in raster:
            print(f"  растр {raster['file']}: не читается ({raster['error']})")
            continue
        if raster["variables"]:
            names = ", ".join(raster["variables"][:12])
            more = len(raster["variables"]) - 12
            tail = f" … ещё {more}" if more > 0 else ""
            count = len(raster["variables"])
            print(f"  массив {raster['file']}: переменных {count}: {names}{tail}")
            continue
        size = f"{raster['width']}×{raster['height']}"
        print(
            f"  растр {raster['file']}: {size}, каналов {raster['bands']}, "
            f"{raster['dtype']}, {raster['crs']}, шаг {raster['resolution']}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Опись папки внутри data/: что лежит, сколько, какие растры."
    )
    parser.add_argument(
        "target", nargs="?", default="case", help="папка относительно data/, по умолчанию case"
    )
    parser.add_argument("--md5", action="store_true", help="посчитать md5 каждого файла")
    parser.add_argument("--no-write", action="store_true", help="не записывать манифест")
    args = parser.parse_args()

    root = (DATA_DIR / args.target).resolve()
    if not root.is_dir() or DATA_DIR.resolve() not in root.parents:
        raise SystemExit(f"нет папки data/{args.target}")
    files = collect(root)
    if not files:
        raise SystemExit(
            f"data/{args.target} пуста: положите туда данные как есть и запустите снова"
        )
    summary = summarise(files, root, args.md5)
    name = args.target.strip("/").replace("/", "-")
    print_summary(f"data/{args.target}", summary)
    if args.no_write:
        return
    manifest = {
        "target": f"data/{args.target}",
        "inventoried": dt.date.today().isoformat(),
        **summary,
    }
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    path = MANIFEST_DIR / f"{name}.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"манифест: data/manifests/{path.name}")


if __name__ == "__main__":
    main()
