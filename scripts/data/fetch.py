from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import http.client
import json
import re
import shutil
import ssl
import subprocess
import sys
import tarfile
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

REPOSITORY_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = REPOSITORY_DIR / "data"
CATALOG_PATH = DATA_DIR / "sources.toml"
EXTERNAL_DIR = DATA_DIR / "external"
MANIFEST_DIR = DATA_DIR / "manifests"
USER_AGENT = "littora-data/0.2"
CHUNK_SIZE = 1024 * 1024
CONFIRM_ABOVE_BYTES = 2_000_000_000
DOWNLOAD_ATTEMPTS = 5
S3_NAMESPACE = "{http://s3.amazonaws.com/doc/2006-03-01/}"
SYSTEM_CA_BUNDLES = (Path("/etc/ssl/cert.pem"), Path("/etc/ssl/certs/ca-certificates.crt"))
MD5_PATTERN = re.compile(r"^[0-9a-f]{32}$")
ARCHIVE_SUFFIXES = (".zip", ".tar", ".tar.gz", ".tgz", ".rar", ".7z")

KIND_LABELS = {
    "labelled": "разметка",
    "spectra": "спектры",
    "observations": "наблюдения",
    "model": "модель",
    "imagery": "снимки",
    "ocean": "океан",
    "atmosphere": "ветер",
    "geo": "геоданные",
}
REGION_LABELS = {"russia": "Россия", "global": "весь мир", "international": "зарубеж"}
ACCESS_LABELS = {
    "open": "открыт",
    "account": "аккаунт",
    "request": "по запросу",
    "embargo": "эмбарго",
    "unavailable": "недоступен",
}
USE_LABELS = {
    "pretrain": "предобучение",
    "baseline": "базовая модель",
    "train": "обучение",
    "validation": "валидация",
    "calibration": "калибровка",
    "inference": "инференс",
    "demo": "демо",
    "drift": "дрейф",
    "aoi": "районы и маски",
}


@dataclass(frozen=True)
class RemoteFile:
    name: str
    url: str
    size: int | None
    md5: str | None


def load_catalog() -> dict[str, dict]:
    with CATALOG_PATH.open("rb") as handle:
        return tomllib.load(handle)


def build_ssl_context() -> ssl.SSLContext:
    defaults = ssl.get_default_verify_paths()
    if defaults.cafile or defaults.capath:
        return ssl.create_default_context()
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        pass
    for bundle in SYSTEM_CA_BUNDLES:
        if bundle.exists():
            return ssl.create_default_context(cafile=str(bundle))
    return ssl.create_default_context()


SSL_CONTEXT = build_ssl_context()


def open_url(
    url: str, headers: dict[str, str] | None = None, method: str = "GET", data: bytes | None = None
):
    request = urllib.request.Request(
        url, data=data, method=method, headers={"User-Agent": USER_AGENT, **(headers or {})}
    )
    return urllib.request.urlopen(request, timeout=60, context=SSL_CONTEXT)


def fetch_json(url: str) -> dict | list:
    with open_url(url, {"Accept": "application/json"}) as response:
        return json.load(response)


def as_md5(value: str | None) -> str | None:
    value = (value or "").strip('"').lower().removeprefix("md5:")
    return value if MD5_PATTERN.match(value) else None


def list_zenodo_files(record_id: int) -> list[RemoteFile]:
    record = fetch_json(f"https://zenodo.org/api/records/{record_id}")
    return [
        RemoteFile(
            name=entry["key"],
            url=entry["links"]["self"],
            size=entry.get("size"),
            md5=as_md5(entry.get("checksum")),
        )
        for entry in record["files"]
    ]


def list_figshare_files(api: str, article_id: int) -> list[RemoteFile]:
    article = fetch_json(f"{api}/articles/{article_id}")
    return [
        RemoteFile(
            name=entry["name"],
            url=entry["download_url"],
            size=entry.get("size"),
            md5=as_md5(entry.get("computed_md5") or entry.get("supplied_md5")),
        )
        for entry in article["files"]
    ]


def iter_s3_objects(endpoint: str, bucket: str, prefix: str) -> Iterator[ET.Element]:
    token: str | None = None
    while True:
        query = {"list-type": "2", "prefix": prefix, "max-keys": "1000"}
        if token:
            query["continuation-token"] = token
        with open_url(f"{endpoint}/{bucket}?{urllib.parse.urlencode(query)}") as response:
            root = ET.parse(response).getroot()
        yield from root.iter(f"{S3_NAMESPACE}Contents")
        token = root.findtext(f"{S3_NAMESPACE}NextContinuationToken")
        if not token:
            return


def list_s3_files(endpoint: str, bucket: str, prefix: str) -> list[RemoteFile]:
    files = []
    for item in iter_s3_objects(endpoint, bucket, prefix):
        key = item.findtext(f"{S3_NAMESPACE}Key", "")
        if key.endswith("/"):
            continue
        files.append(
            RemoteFile(
                name=key.removeprefix(prefix),
                url=f"{endpoint}/{bucket}/{urllib.parse.quote(key)}",
                size=int(item.findtext(f"{S3_NAMESPACE}Size", "0")),
                md5=as_md5(item.findtext(f"{S3_NAMESPACE}ETag")),
            )
        )
    return files


def list_insitu_index(source: dict) -> list[RemoteFile]:
    west, south, east, north = source["bbox"]
    since = source.get("since", "")
    with open_url(source["index"]) as response:
        lines = response.read().decode("utf-8").splitlines()
    files = []
    for line in lines:
        if line.startswith("#") or not line.strip():
            continue
        fields = [field.strip() for field in line.split(",")]
        lat_min, lat_max, lon_min, lon_max = map(float, fields[2:6])
        inside = west <= lon_min and lon_max <= east and south <= lat_min and lat_max <= north
        if not inside or fields[7] < since:
            continue
        relative = "/".join(fields[1].strip("/").split("/")[source.get("strip", 0) :])
        files.append(
            RemoteFile(name=Path(relative).name, url=source["base"] + relative, size=None, md5=None)
        )
    return files


def probe_url(url: str, name: str | None = None) -> RemoteFile:
    try:
        with open_url(url, method="HEAD") as response:
            length = response.headers.get("Content-Length")
    except urllib.error.HTTPError:
        length = None
    fallback = Path(urllib.parse.urlparse(url).path).name
    return RemoteFile(
        name=name or fallback, url=url, size=int(length) if length else None, md5=None
    )


def list_remote_files(entry: dict) -> list[RemoteFile]:
    if "zenodo" in entry:
        return list_zenodo_files(entry["zenodo"])
    if "figshare" in entry:
        source = entry["figshare"]
        return list_figshare_files(source["api"], source["article"])
    if "s3_listing" in entry:
        listing = entry["s3_listing"]
        return list_s3_files(listing["endpoint"], listing["bucket"], listing["prefix"])
    if "insitu_index" in entry:
        return list_insitu_index(entry["insitu_index"])
    if "files" in entry:
        return [probe_url(item["url"], item.get("name")) for item in entry["files"]]
    return []


def is_downloadable(entry: dict) -> bool:
    fields = ("zenodo", "figshare", "s3_listing", "insitu_index", "files")
    return any(field in entry for field in fields)


def format_size(size: int | None) -> str:
    if size is None:
        return "?"
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1000 or unit == "TB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1000
    return f"{size} B"


def md5_of(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_complete(path: Path, remote: RemoteFile) -> bool:
    if not path.exists():
        return False
    if remote.size is not None and path.stat().st_size != remote.size:
        return False
    return remote.md5 is None or md5_of(path) == remote.md5


def report_progress(name: str, done: int, total: int | None, started_at: float) -> None:
    elapsed = max(time.monotonic() - started_at, 1e-6)
    speed = format_size(int(done / elapsed))
    share = f" {done / total:6.1%}" if total else ""
    sys.stderr.write(f"\r  {name}: {format_size(done)} / {format_size(total)}{share}  {speed}/s ")
    sys.stderr.flush()


def stream_into(remote: RemoteFile, partial: Path, started_at: float) -> None:
    offset = partial.stat().st_size if partial.exists() else 0
    headers = {"Range": f"bytes={offset}-"} if offset else {}
    last_report = 0.0
    with open_url(remote.url, headers) as response:
        if offset and response.status != 206:
            offset = 0
        with partial.open("ab" if offset else "wb") as handle:
            done = offset
            while chunk := response.read(CHUNK_SIZE):
                handle.write(chunk)
                done += len(chunk)
                if time.monotonic() - last_report > 0.5:
                    report_progress(remote.name, done, remote.size, started_at)
                    last_report = time.monotonic()
    report_progress(remote.name, done, remote.size, started_at)
    sys.stderr.write("\n")


def curl_into(remote: RemoteFile, partial: Path) -> None:
    if not shutil.which("curl"):
        raise RuntimeError(f"{remote.name}: сервер отказал (403), а curl не найден")
    command = ["curl", "-fsSL", "--retry", "3", "-A", USER_AGENT, "-o", str(partial), remote.url]
    subprocess.run(command, check=True)


def download_file(remote: RemoteFile, destination: Path) -> None:
    target = destination / remote.name
    if is_complete(target, remote):
        print(f"  {remote.name}: уже скачан")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")
    started_at = time.monotonic()
    for attempt in range(1, DOWNLOAD_ATTEMPTS + 1):
        try:
            stream_into(remote, partial, started_at)
        except urllib.error.HTTPError as error:
            if error.code != 403:
                raise RuntimeError(f"{remote.name}: сервер ответил {error.code}") from error
            curl_into(remote, partial)
            break
        except (urllib.error.URLError, http.client.HTTPException, OSError) as error:
            sys.stderr.write(
                f"\n  {remote.name}: обрыв ({error}), попытка {attempt} из {DOWNLOAD_ATTEMPTS}\n"
            )
            time.sleep(min(60, 5 * attempt))
            continue
        if remote.size is None or partial.stat().st_size >= remote.size:
            break
    if not partial.exists():
        raise RuntimeError(f"{remote.name}: файл не получен, запустите снова")
    received = partial.stat().st_size
    if remote.size is not None and received != remote.size:
        raise RuntimeError(
            f"{remote.name}: получено {format_size(received)} из {format_size(remote.size)}; "
            "запустите снова — загрузка продолжится"
        )
    if remote.md5 and md5_of(partial) != remote.md5:
        partial.unlink()
        raise RuntimeError(f"{remote.name}: контрольная сумма не совпала, файл удалён, повторите")
    partial.replace(target)


def select_files(files: list[RemoteFile], wanted: list[str] | None) -> list[RemoteFile]:
    if not wanted:
        return files
    by_name = {remote.name: remote for remote in files}
    missing = [name for name in wanted if name not in by_name]
    if missing:
        raise SystemExit(f"нет таких файлов: {', '.join(missing)}; список — команда show")
    return [by_name[name] for name in wanted]


def confirm_large_download(total: int, assume_yes: bool) -> None:
    if total <= CONFIRM_ABOVE_BYTES or assume_yes:
        return
    answer = input(f"Будет скачано {format_size(total)}. Продолжить? [y/N] ").strip().lower()
    if answer != "y":
        raise SystemExit("отменено")


def get_entry(catalog: dict[str, dict], key: str) -> dict:
    if key not in catalog:
        raise SystemExit(f"нет источника «{key}»; список — команда list")
    return catalog[key]


def source_link(entry: dict) -> str | None:
    if "doi" in entry:
        return f"https://doi.org/{entry['doi']}"
    return entry.get("homepage")


def manifest_path(key: str) -> Path:
    return MANIFEST_DIR / f"{key}.json"


def read_manifest(key: str) -> dict | None:
    path = manifest_path(key)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def write_manifest(key: str, manifest: dict) -> None:
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    text = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    manifest_path(key).write_text(text, encoding="utf-8")


def record_download(key: str, entry: dict, files: list[RemoteFile]) -> None:
    destination = EXTERNAL_DIR / key
    previous = read_manifest(key) or {}
    recorded = {item["name"]: item for item in previous.get("files", [])}
    for remote in files:
        path = destination / remote.name
        if path.exists():
            recorded[remote.name] = {
                "name": remote.name,
                "bytes": path.stat().st_size,
                "md5": remote.md5 or md5_of(path),
            }
    manifest = {
        "key": key,
        "title": entry["title"],
        "license": entry["license"],
        "source": source_link(entry),
        "retrieved": dt.date.today().isoformat(),
        "bytes": sum(item["bytes"] for item in recorded.values()),
        "files": sorted(recorded.values(), key=lambda item: item["name"]),
    }
    if "unpacked" in previous:
        manifest["unpacked"] = previous["unpacked"]
    write_manifest(key, manifest)


def local_state(key: str) -> str:
    manifest = read_manifest(key)
    if not manifest:
        return "—"
    folder = EXTERNAL_DIR / key
    present = [item for item in manifest["files"] if (folder / item["name"]).exists()]
    if len(present) == len(manifest["files"]):
        return "есть"
    return "нет файлов" if not present else "частично"


def labels(values: list[str], mapping: dict[str, str]) -> str:
    return ", ".join(mapping.get(value, value) for value in values)


def command_list(catalog: dict[str, dict], args: argparse.Namespace) -> None:
    rows = [
        (key, entry)
        for key, entry in catalog.items()
        if (not args.kind or entry["kind"] == args.kind)
        and (not args.region or entry["region"] == args.region)
    ]
    width = max(len(key) for key, _ in rows) if rows else 0
    columns = (
        f"{'ключ':<{width}}",
        f"{'тип':<10}",
        f"{'регион':<8}",
        f"{'доступ':<10}",
        f"{'лицензия':<16}",
        f"{'объём':>10}",
        f"{'локально':<9}",
        "назначение",
    )
    print("  ".join(columns))
    for key, entry in rows:
        print(
            f"{key:<{width}}  {KIND_LABELS.get(entry['kind'], entry['kind']):<10}  "
            f"{REGION_LABELS.get(entry['region'], entry['region']):<8}  "
            f"{ACCESS_LABELS.get(entry['access'], entry['access']):<10}  "
            f"{entry['license']:<16}  {entry.get('size', '?'):>10}  {local_state(key):<9}  "
            f"{labels(entry.get('use', []), USE_LABELS)}"
        )


def command_show(catalog: dict[str, dict], args: argparse.Namespace) -> None:
    entry = get_entry(catalog, args.source)
    print(entry["title"])
    print(f"  {entry['about']}")
    fields = (
        ("тип", KIND_LABELS.get(entry["kind"], entry["kind"])),
        ("регион", REGION_LABELS.get(entry["region"], entry["region"])),
        ("назначение", labels(entry.get("use", []), USE_LABELS)),
        ("лицензия", entry["license"]),
        ("коммерция", {True: "можно", False: "нельзя"}.get(entry.get("commercial"), "не указано")),
        ("доступ", ACCESS_LABELS.get(entry["access"], entry["access"])),
        ("объём", entry.get("size")),
        ("источник", source_link(entry)),
        ("статья", entry.get("paper")),
        ("локально", local_state(args.source)),
    )
    for label, value in fields:
        if value:
            print(f"  {label:>10}: {value}")
    if not is_downloadable(entry):
        return
    files = list_remote_files(entry)
    print(f"\n{len(files)} файл(ов), всего {format_size(sum(f.size or 0 for f in files))}:")
    for remote in files[: args.limit]:
        print(f"  {format_size(remote.size):>10}  {remote.name}")
    if len(files) > args.limit:
        print(f"  … ещё {len(files) - args.limit} (--limit)")


def command_download(catalog: dict[str, dict], args: argparse.Namespace) -> None:
    entry = get_entry(catalog, args.source)
    if not is_downloadable(entry):
        access = ACCESS_LABELS.get(entry["access"], entry["access"])
        hint = source_link(entry) or "описание в data/sources.toml"
        raise SystemExit(f"{args.source}: скрипт не скачивает этот источник ({access}); см. {hint}")
    files = select_files(list_remote_files(entry), args.file)
    destination = EXTERNAL_DIR / args.source
    total = sum(remote.size or 0 for remote in files)
    print(
        f"{args.source}: {len(files)} файл(ов), {format_size(total)} → data/external/{args.source}"
    )
    print(f"лицензия: {entry['license']}")
    if args.dry_run:
        for remote in files:
            print(f"  {format_size(remote.size):>10}  {remote.name}")
        return
    confirm_large_download(total, args.yes)
    try:
        for remote in files:
            download_file(remote, destination)
    finally:
        record_download(args.source, entry, files)
    print(f"готово; манифест: data/manifests/{args.source}.json")


def command_verify(catalog: dict[str, dict], args: argparse.Namespace) -> None:
    get_entry(catalog, args.source)
    manifest = read_manifest(args.source)
    if not manifest:
        raise SystemExit(f"{args.source}: манифеста нет, источник не скачан")
    folder = EXTERNAL_DIR / args.source
    problems = 0
    for item in manifest["files"]:
        path = folder / item["name"]
        if not path.exists():
            state = "нет файла"
        elif path.stat().st_size != item["bytes"]:
            state = "другой размер"
        elif md5_of(path) != item["md5"]:
            state = "другая сумма md5"
        else:
            state = "ok"
        problems += state != "ok"
        print(f"  {state:<16}  {item['name']}")
    if problems:
        raise SystemExit(f"{args.source}: проблем — {problems}")
    print(f"{args.source}: все файлы совпадают с манифестом")


def is_archive(path: Path) -> bool:
    return path.name.lower().endswith(ARCHIVE_SUFFIXES)


def is_junk(name: str) -> bool:
    parts = Path(name).parts
    return any(part == "__MACOSX" or part.startswith("._") or part == ".DS_Store" for part in parts)


def unpack_zip(archive: Path, destination: Path) -> None:
    with zipfile.ZipFile(archive) as bundle:
        members = [member for member in bundle.namelist() if not is_junk(member)]
        bundle.extractall(destination, members)


def unpack_tar(archive: Path, destination: Path) -> None:
    with tarfile.open(archive) as bundle:
        members = [member for member in bundle.getmembers() if not is_junk(member.name)]
        bundle.extractall(destination, members, filter="data")


def unpack_external(archive: Path, destination: Path) -> None:
    for tool, arguments in (
        ("bsdtar", ["-xf", str(archive), "-C", str(destination)]),
        (
            "unar",
            ["-quiet", "-force-overwrite", "-no-directory", "-o", str(destination), str(archive)],
        ),
        ("7z", ["x", "-y", f"-o{destination}", str(archive)]),
    ):
        if shutil.which(tool):
            subprocess.run([tool, *arguments], check=True)
            return
    raise SystemExit(f"{archive.name}: нужен bsdtar, unar или 7z")


def unpack_archive(archive: Path, destination: Path) -> None:
    name = archive.name.lower()
    if name.endswith(".zip"):
        unpack_zip(archive, destination)
    elif name.endswith((".tar", ".tar.gz", ".tgz")):
        unpack_tar(archive, destination)
    else:
        unpack_external(archive, destination)


def folder_summary(folder: Path, skip: set[Path]) -> tuple[int, int]:
    files = [path for path in folder.rglob("*") if path.is_file() and path not in skip]
    return len(files), sum(path.stat().st_size for path in files)


def command_unpack(catalog: dict[str, dict], args: argparse.Namespace) -> None:
    get_entry(catalog, args.source)
    folder = EXTERNAL_DIR / args.source
    archives = sorted(path for path in folder.glob("*") if path.is_file() and is_archive(path))
    if args.file:
        archives = [path for path in archives if path.name in args.file]
    if not archives:
        raise SystemExit(f"{args.source}: архивов нет в data/external/{args.source}")
    for archive in archives:
        print(f"  распаковка {archive.name} …")
        unpack_archive(archive, folder)
    count, size = folder_summary(folder, set(archives))
    manifest = read_manifest(args.source)
    if manifest:
        manifest["unpacked"] = {"files": count, "bytes": size}
        write_manifest(args.source, manifest)
    print(f"{args.source}: распаковано, {count} файл(ов), {format_size(size)}")


def command_status(catalog: dict[str, dict], _: argparse.Namespace) -> None:
    total = 0
    for key in catalog:
        manifest = read_manifest(key)
        folder = EXTERNAL_DIR / key
        if not manifest and not folder.exists():
            continue
        on_disk = (
            sum(path.stat().st_size for path in folder.rglob("*") if path.is_file())
            if folder.exists()
            else 0
        )
        total += on_disk
        print(f"  {key:<28} {local_state(key):<10} {format_size(on_disk):>10} на диске")
    print(f"всего в data/external: {format_size(total)}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Внешние открытые данные Littora: каталог data/sources.toml."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    listing = commands.add_parser("list", help="каталог источников")
    listing.add_argument("--kind", choices=sorted(KIND_LABELS))
    listing.add_argument("--region", choices=sorted(REGION_LABELS))
    listing.set_defaults(handler=command_list)

    show = commands.add_parser("show", help="описание источника и список файлов")
    show.add_argument("source")
    show.add_argument("--limit", type=int, default=40)
    show.set_defaults(handler=command_show)

    download = commands.add_parser("download", help="скачать в data/external/<ключ> с докачкой")
    download.add_argument("source")
    download.add_argument("--file", action="append", help="только этот файл (можно несколько)")
    download.add_argument("--dry-run", action="store_true", help="только показать план")
    download.add_argument("--yes", action="store_true", help="не спрашивать про большой объём")
    download.set_defaults(handler=command_download)

    verify = commands.add_parser("verify", help="сверить файлы с манифестом")
    verify.add_argument("source")
    verify.set_defaults(handler=command_verify)

    unpack = commands.add_parser("unpack", help="распаковать архивы источника рядом с ними")
    unpack.add_argument("source")
    unpack.add_argument("--file", action="append", help="только этот архив")
    unpack.set_defaults(handler=command_unpack)

    commands.add_parser("status", help="что уже скачано").set_defaults(handler=command_status)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.handler(load_catalog(), args)


if __name__ == "__main__":
    main()
