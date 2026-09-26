from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry

SOURCE_KINDS = ("port", "river_mouth")


@dataclass(frozen=True)
class Place:
    id: str
    name: str
    kind: str
    geometry: BaseGeometry
    anchor: tuple[float, float]


def load_places(path: Path) -> list[Place]:
    if not path.exists():
        return []
    places = []
    for feature in json.loads(path.read_text(encoding="utf-8")).get("features", []):
        properties = feature.get("properties") or {}
        if not properties.get("id") or not properties.get("name") or not feature.get("geometry"):
            continue
        geometry = shape(feature["geometry"])
        anchor = geometry.representative_point()
        places.append(
            Place(
                id=str(properties["id"]),
                name=str(properties["name"]),
                kind=str(properties.get("kind", "")),
                geometry=geometry,
                anchor=(round(anchor.x, 5), round(anchor.y, 5)),
            )
        )
    return places
