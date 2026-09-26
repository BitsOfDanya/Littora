from __future__ import annotations

import csv
import datetime as dt
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import h5py
import numpy as np

EPOCH_1950_S = -631_152_000
GOOD_QC = 1
DROGUE_ON = 1
DROGUE_OFF = 3
NAUTILOS_KINDS = {
    "flacone": "bottle",
    "flacone 3L": "bottle_3l",
    "tavoletta": "board",
    "tavoletta forata": "board_perforated",
    "ciambella": "ring",
}


@dataclass(frozen=True)
class Track:
    drifter: str
    source: str
    kind: str
    seconds: np.ndarray
    lon: np.ndarray
    lat: np.ndarray
    drogue: np.ndarray
    anchor: np.ndarray

    @property
    def size(self) -> int:
        return int(self.seconds.size)


def unix_seconds(moment: str | dt.datetime) -> int:
    if isinstance(moment, str):
        moment = dt.datetime.fromisoformat(moment.replace("Z", "+00:00"))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=dt.UTC)
    return int(moment.timestamp())


def make_track(
    drifter: str,
    source: str,
    kind: str,
    seconds: np.ndarray,
    lon: np.ndarray,
    lat: np.ndarray,
    drogue: np.ndarray | None = None,
    anchor: np.ndarray | None = None,
) -> Track:
    seconds = np.asarray(seconds, dtype=np.int64)
    count = seconds.size
    drogue = np.zeros(count, dtype=np.int8) if drogue is None else np.asarray(drogue, np.int8)
    anchor = np.ones(count, dtype=bool) if anchor is None else np.asarray(anchor, dtype=bool)
    lon, lat = np.asarray(lon, dtype=float), np.asarray(lat, dtype=float)
    keep = np.isfinite(lon) & np.isfinite(lat)
    order = np.argsort(seconds[keep], kind="stable")
    seconds = seconds[keep][order]
    unique = np.concatenate([[True], np.diff(seconds) > 0]) if seconds.size else np.array([], bool)

    def pick(values: np.ndarray) -> np.ndarray:
        return values[keep][order][unique]

    return Track(
        drifter, source, kind, seconds[unique], pick(lon), pick(lat), pick(drogue), pick(anchor)
    )


def _text(value: object) -> str:
    if isinstance(value, bytes | np.bytes_):
        return value.decode("utf-8", "replace").strip()
    return str(value).strip()


def _first_column(values: np.ndarray) -> np.ndarray:
    return values[:, 0] if values.ndim == 2 else values


def read_copernicus(path: Path) -> dict[str, object]:
    with h5py.File(path, "r") as handle:
        days = handle["TIME"][:]
        drogue = (
            _first_column(handle["DROGUE_TEST"][:]).astype(np.int8)
            if "DROGUE_TEST" in handle
            else np.zeros(days.size, dtype=np.int8)
        )
        return {
            "seconds": np.round(days * 86_400.0).astype(np.int64) + EPOCH_1950_S,
            "lon": handle["LONGITUDE"][:].astype(float),
            "lat": handle["LATITUDE"][:].astype(float),
            "qc": handle["POSITION_QC"][:],
            "drogue": drogue,
            "platform": _text(handle.attrs.get("platform_code", path.stem)),
            "institution": _text(handle.attrs.get("institution", "")),
        }


def load_blacksea(folder: Path, platform: str, kind: str) -> list[Track]:
    parts = [read_copernicus(path) for path in sorted(folder.glob(f"GL_TS_DB_{platform}_*.nc"))]
    if not parts:
        return []
    good = [part["qc"] == GOOD_QC for part in parts]
    return [
        make_track(
            platform,
            "blacksea",
            kind,
            np.concatenate([part["seconds"][mask] for part, mask in zip(parts, good, strict=True)]),
            np.concatenate([part["lon"][mask] for part, mask in zip(parts, good, strict=True)]),
            np.concatenate([part["lat"][mask] for part, mask in zip(parts, good, strict=True)]),
        )
    ]


def in_mediterranean(lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    atlantic = lon < -5.6
    marmara_black = (lon > 26.6) & (lat > 40.2)
    return ~atlantic & ~marmara_black


def load_mediterranean(folder: Path, since: str, kind: str) -> list[Track]:
    start = unix_seconds(since)
    tracks = []
    for path in sorted(folder.glob("GL_TS_DC_*.nc")):
        part = read_copernicus(path)
        mask = (
            (part["qc"] == GOOD_QC)
            & (part["seconds"] >= start)
            & in_mediterranean(part["lon"], part["lat"])
        )
        if mask.sum() < 2:
            continue
        tracks.append(
            make_track(
                str(part["platform"]),
                "med",
                kind,
                part["seconds"][mask],
                part["lon"][mask],
                part["lat"][mask],
                part["drogue"][mask],
            )
        )
    return tracks


def swot_kind(path: Path) -> str:
    return path.stem.split("_")[1].upper()


def load_swot(folder: Path, kinds: list[str], anchor_gap_s: float, max_gap_s: float) -> list[Track]:
    wanted = {kind.upper() for kind in kinds}
    tracks = []
    for path in sorted(folder.rglob("*.nc")):
        if path.name.startswith("._") or swot_kind(path) not in wanted:
            continue
        with h5py.File(path, "r") as handle:
            days = handle["TIME"][:]
            gaps = handle["GAPS"][:].astype(float)
            lon = handle["LONGITUDE"][:].astype(float)
            lat = handle["LATITUDE"][:].astype(float)
        keep = np.isfinite(gaps) & (gaps <= max_gap_s / 2)
        tracks.append(
            make_track(
                path.stem,
                "swot",
                swot_kind(path),
                np.round(days[keep] * 86_400.0).astype(np.int64) + EPOCH_1950_S,
                lon[keep],
                lat[keep],
                anchor=gaps[keep] <= anchor_gap_s,
            )
        )
    return [track for track in tracks if track.size >= 2]


def load_nautilos(path: Path, since: str) -> list[Track]:
    start = unix_seconds(since)
    rows: dict[tuple[str, str, str], list[tuple[int, float, float]]] = defaultdict(list)
    with path.open(encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if not row["mission"] or row["time"] == "UTC":
                continue
            moment = unix_seconds(row["time"])
            if moment < start:
                continue
            key = (row["mission"], row["ID"], row["drifter_type"])
            rows[key].append((moment, float(row["longitude"]), float(row["latitude"])))
    tracks = []
    for (mission, identifier, kind), fixes in sorted(rows.items()):
        values = np.array(fixes)
        tracks.append(
            make_track(
                f"{mission}:{identifier}",
                "nautilos",
                NAUTILOS_KINDS.get(kind, kind.replace(" ", "_")),
                values[:, 0].astype(np.int64),
                values[:, 1],
                values[:, 2],
            )
        )
    return [track for track in tracks if track.size >= 2]
