from __future__ import annotations

import hashlib
import json
import math
import urllib.parse
import urllib.request
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol

from shapely.geometry import LineString, Point, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform

from app.earth.catalog import build_ssl_context

OVERPASS_URLS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)
OSM_DIR = "osm"
USER_AGENT = "Littora/0.1 (+https://github.com/BitsOfDanya/Littora)"
TIMEOUT_S = 25
PAD_DEG = 0.01
STRUCTURE_M = 60.0
PORT_M = 2000.0
METERS_PER_DEGREE = 111_320.0
QUERY = """[out:json][timeout:25];
(
  way["man_made"~"^(pier|breakwater|groyne|jetty|quay|offshore_platform|bridge)$"]({box});
  way["bridge"="yes"]({box});
  way["landuse"="aquaculture"]({box});
  way["leisure"="marina"]({box});
  way["harbour"]({box});
  way["waterway"="dock"]({box});
  node["man_made"="offshore_platform"]({box});
  node["seamark:type"~"^(mooring|platform|buoy_lateral|buoy_cardinal)$"]({box});
);
out geom;"""
KIND_LABELS = {
    "pier": "причал",
    "breakwater": "мол или волнолом",
    "groyne": "буна",
    "jetty": "пирс",
    "quay": "набережная",
    "offshore_platform": "морская платформа",
    "bridge": "мост",
    "aquaculture": "садки или аквакультура",
    "marina": "марина",
    "harbour": "гавань",
    "dock": "док",
    "mooring": "швартовка",
    "platform": "платформа",
    "buoy_lateral": "буй",
    "buoy_cardinal": "буй",
}


class PortLike(Protocol):
    name: str
    position: tuple[float, float]


def _kind(tags: dict[str, str]) -> str:
    for key in ("man_made", "seamark:type", "landuse", "leisure", "waterway"):
        if tags.get(key) in KIND_LABELS:
            return tags[key]
    if tags.get("bridge") == "yes":
        return "bridge"
    if "harbour" in tags:
        return "harbour"
    return "pier"


def parse_overpass(payload: dict[str, Any]) -> list[tuple[str, BaseGeometry]]:
    items = []
    for element in payload.get("elements", []):
        kind = _kind(element.get("tags", {}))
        if element.get("type") == "node" and "lat" in element:
            items.append((kind, Point(element["lon"], element["lat"])))
        elif element.get("geometry"):
            points = [(point["lon"], point["lat"]) for point in element["geometry"]]
            geometry = LineString(points) if len(points) > 1 else Point(points[0])
            items.append((kind, geometry))
    return items


class OsmStructures:
    def __init__(self, cache_dir: Path, urls: Sequence[str] = OVERPASS_URLS) -> None:
        self.cache_dir = cache_dir
        self.urls = tuple(urls)

    def around(self, bounds: Sequence[float]) -> list[tuple[str, BaseGeometry]]:
        west, south, east, north = (round(value, 3) for value in bounds)
        box = f"{south - PAD_DEG},{west - PAD_DEG},{north + PAD_DEG},{east + PAD_DEG}"
        query = QUERY.format(box=box)
        key = hashlib.sha256(query.encode()).hexdigest()[:24]
        path = self.cache_dir / f"{key}.json"
        if path.exists():
            return parse_overpass(json.loads(path.read_text(encoding="utf-8")))
        payload = self._fetch(query)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(f".{key}.tmp")
        temporary.write_text(json.dumps(payload), encoding="utf-8")
        temporary.replace(path)
        return parse_overpass(payload)

    def _fetch(self, query: str) -> dict[str, Any]:
        error: OSError | None = None
        for url in self.urls:
            request = urllib.request.Request(
                url,
                data=urllib.parse.urlencode({"data": query}).encode(),
                headers={"User-Agent": USER_AGENT},
            )
            try:
                with urllib.request.urlopen(
                    request, timeout=TIMEOUT_S, context=build_ssl_context()
                ) as reply:
                    return json.load(reply)
            except OSError as failure:
                error = failure
        raise error or OSError("нет адресов Overpass")


def _local(center_lat: float):
    scale = math.cos(math.radians(center_lat))

    def project(x, y, z=None):
        return x * METERS_PER_DEGREE * scale, y * METERS_PER_DEGREE

    return project


def annotate(
    zones: list[dict[str, Any]],
    structures: list[tuple[str, BaseGeometry]],
    ports: Sequence[PortLike],
) -> None:
    if not zones or not (structures or ports):
        return
    centers = [shape(zone["geometry"]).centroid for zone in zones]
    project = _local(sum(center.y for center in centers) / len(centers))
    projected = [(kind, transform(project, geometry)) for kind, geometry in structures]
    for zone, point in zip(zones, centers, strict=True):
        flags = zone.setdefault("flags", [])
        footprint = transform(project, shape(zone["geometry"]))
        nearby = sorted(
            (footprint.distance(geometry), kind)
            for kind, geometry in projected
            if footprint.distance(geometry) <= STRUCTURE_M
        )
        if nearby:
            distance, kind = nearby[0]
            flags.append(
                {
                    "kind": "structure",
                    "label": "рядом сооружение",
                    "evidence": [f"{KIND_LABELS[kind]} в {distance:.0f} м по OpenStreetMap"],
                }
            )
        center = transform(project, point)
        close = sorted(
            (center.distance(transform(project, Point(port.position))), port.name) for port in ports
        )
        if close and close[0][0] <= PORT_M:
            flags.append(
                {
                    "kind": "port",
                    "label": "порт",
                    "evidence": [f"порт {close[0][1]} в {close[0][0] / 1000:.1f} км"],
                }
            )
