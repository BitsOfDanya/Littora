from __future__ import annotations

import datetime as dt
import json
import re
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from shapely.geometry import mapping, shape
from shapely.geometry.base import BaseGeometry

USER_AGENT = "littora-api/0.1"
SYSTEM_CA_BUNDLES = (Path("/etc/ssl/cert.pem"), Path("/etc/ssl/certs/ca-certificates.crt"))
PLATFORMS = {
    "sentinel-2a": "S2A",
    "sentinel-2b": "S2B",
    "sentinel-2c": "S2C",
    "landsat-8": "L8",
    "landsat-9": "L9",
}
ORBIT_PATTERN = re.compile(r"_R(\d{3})_")


class CatalogError(RuntimeError):
    pass


def build_ssl_context() -> ssl.SSLContext:
    defaults = ssl.get_default_verify_paths()
    if defaults.cafile or defaults.capath:
        return ssl.create_default_context()
    for bundle in SYSTEM_CA_BUNDLES:
        if bundle.exists():
            return ssl.create_default_context(cafile=str(bundle))
    return ssl.create_default_context()


@dataclass(frozen=True)
class Scene:
    id: str
    collection: str
    platform: str
    acquired_at: dt.datetime
    cloud_cover: float | None
    tile: str
    relative_orbit: int | None
    sun_elevation: float | None
    water_percentage: float | None
    nodata_percentage: float | None
    geometry: BaseGeometry
    assets: dict[str, str] = field(default_factory=dict)
    reflectance_scale: float = 0.0001
    reflectance_offset: float = 0.0
    requester_pays: bool = False

    @property
    def is_sentinel2(self) -> bool:
        return self.platform.startswith("S2")

    @property
    def footprint_bbox(self) -> tuple[float, float, float, float]:
        return self.geometry.bounds


def _platform(properties: dict) -> str:
    raw = str(properties.get("platform", "")).lower()
    return PLATFORMS.get(raw, raw.upper() or "?")


def _relative_orbit(properties: dict) -> int | None:
    for key in ("sat:relative_orbit", "landsat:wrs_path"):
        if properties.get(key) is not None:
            try:
                return int(properties[key])
            except (TypeError, ValueError):
                pass
    match = ORBIT_PATTERN.search(str(properties.get("s2:product_uri", "")))
    return int(match.group(1)) if match else None


def _tile(properties: dict) -> str:
    code = str(properties.get("grid:code", ""))
    if code:
        return code.split("-", 1)[-1]
    path, row = properties.get("landsat:wrs_path"), properties.get("landsat:wrs_row")
    return f"{path}{row}" if path and row else ""


def _asset_hrefs(assets: dict) -> tuple[dict[str, str], bool]:
    hrefs = {}
    requester_pays = False
    for key, asset in assets.items():
        href = str(asset.get("href", ""))
        if href.startswith("s3://"):
            requester_pays = True
            continue
        if href.startswith("http"):
            hrefs[key] = href
    return hrefs, requester_pays


def parse_scene(feature: dict) -> Scene:
    properties = feature.get("properties", {})
    assets, requester_pays = _asset_hrefs(feature.get("assets", {}))
    band = (feature.get("assets", {}).get("nir", {}).get("raster:bands") or [{}])[0]
    return Scene(
        id=feature["id"],
        collection=feature.get("collection", ""),
        platform=_platform(properties),
        acquired_at=dt.datetime.fromisoformat(properties["datetime"].replace("Z", "+00:00")),
        cloud_cover=properties.get("eo:cloud_cover"),
        tile=_tile(properties),
        relative_orbit=_relative_orbit(properties),
        sun_elevation=properties.get("view:sun_elevation"),
        water_percentage=properties.get("s2:water_percentage"),
        nodata_percentage=properties.get("s2:nodata_pixel_percentage"),
        geometry=shape(feature["geometry"]),
        assets=assets,
        reflectance_scale=float(band.get("scale", 0.0001)),
        reflectance_offset=float(band.get("offset", 0.0)),
        requester_pays=requester_pays,
    )


class SceneCatalog(Protocol):
    def search(
        self,
        collection: str,
        geometry: BaseGeometry,
        start: dt.datetime,
        end: dt.datetime,
        limit: int = 100,
    ) -> list[Scene]: ...

    def get(self, collection: str, scene_id: str) -> Scene: ...


class StacCatalog:
    def __init__(self, url: str, timeout: float = 30.0) -> None:
        self.url = url.rstrip("/")
        self.timeout = timeout
        self.context = build_ssl_context()

    def _request(self, path: str, body: dict | None = None) -> dict:
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(
            f"{self.url}{path}",
            data=data,
            method="POST" if data else "GET",
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/geo+json",
                **({"Content-Type": "application/json"} if data else {}),
            },
        )
        try:
            with urllib.request.urlopen(
                request, timeout=self.timeout, context=self.context
            ) as reply:
                return json.load(reply)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as error:
            raise CatalogError(f"каталог снимков недоступен: {error}") from error

    def search(
        self,
        collection: str,
        geometry: BaseGeometry,
        start: dt.datetime,
        end: dt.datetime,
        limit: int = 100,
    ) -> list[Scene]:
        body = {
            "collections": [collection],
            "intersects": mapping(geometry),
            "datetime": f"{start:%Y-%m-%dT%H:%M:%SZ}/{end:%Y-%m-%dT%H:%M:%SZ}",
            "limit": limit,
        }
        features = self._request("/search", body).get("features", [])
        return sorted((parse_scene(item) for item in features), key=lambda s: (s.acquired_at, s.id))

    def get(self, collection: str, scene_id: str) -> Scene:
        return parse_scene(self._request(f"/collections/{collection}/items/{scene_id}"))
