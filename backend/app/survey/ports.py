from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.survey.geo import distance_km

PORTS_SOURCE = "World Port Index, NGA Pub 150"


@dataclass(frozen=True)
class Port:
    id: str
    name: str
    name_en: str
    country: str | None
    sea: str | None
    harbor_size: str | None
    harbor_type: str | None
    position: tuple[float, float]

    def summary(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "name_en": self.name_en,
            "country": self.country,
            "sea": self.sea,
            "harbor_size": self.harbor_size,
            "harbor_type": self.harbor_type,
            "position": list(self.position),
            "source": PORTS_SOURCE,
        }


def load_ports(path: Path) -> list[Port]:
    if not path.exists():
        return []
    ports = []
    for feature in json.loads(path.read_text(encoding="utf-8")).get("features", []):
        properties = feature.get("properties") or {}
        geometry = feature.get("geometry") or {}
        if geometry.get("type") != "Point" or not properties.get("id"):
            continue
        lon, lat = geometry["coordinates"][:2]
        name = str(properties.get("name") or properties.get("name_en") or properties["id"])
        ports.append(
            Port(
                id=str(properties["id"]),
                name=name,
                name_en=str(properties.get("name_en") or name),
                country=properties.get("country"),
                sea=properties.get("sea"),
                harbor_size=properties.get("harbor_size"),
                harbor_type=properties.get("harbor_type"),
                position=(float(lon), float(lat)),
            )
        )
    return ports


def nearest_port(ports: list[Port], point: tuple[float, float] | list[float]):
    best: tuple[float, Port] | None = None
    for port in ports:
        distance = distance_km(port.position, point)
        if best is None or distance < best[0]:
            best = (distance, port)
    return best
