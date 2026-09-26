from dataclasses import dataclass

from shapely.geometry import box, mapping

from app.analysis.structures import annotate, parse_overpass

PAYLOAD = {
    "elements": [
        {
            "type": "way",
            "tags": {"man_made": "pier"},
            "geometry": [{"lat": 44.7000, "lon": 37.8000}, {"lat": 44.7000, "lon": 37.8010}],
        },
        {"type": "node", "tags": {"man_made": "offshore_platform"}, "lat": 44.9, "lon": 37.9},
    ]
}


@dataclass(frozen=True)
class Port:
    name: str
    position: tuple[float, float]


def zone(lon: float, lat: float) -> dict:
    return {"geometry": mapping(box(lon, lat, lon + 0.0002, lat + 0.0002))}


def test_overpass_elements_become_typed_geometries() -> None:
    items = parse_overpass(PAYLOAD)
    assert [kind for kind, _ in items] == ["pier", "offshore_platform"]
    assert items[0][1].geom_type == "LineString"


def test_zone_next_to_a_pier_and_a_port_is_flagged() -> None:
    near, far = zone(37.8004, 44.7001), zone(37.95, 44.60)
    annotate([near, far], parse_overpass(PAYLOAD), [Port("Новороссийск", (37.80, 44.71))])
    assert [flag["kind"] for flag in near["flags"]] == ["structure", "port"]
    assert "причал" in near["flags"][0]["evidence"][0]
    assert far["flags"] == []


def test_nothing_to_compare_leaves_zones_untouched() -> None:
    lonely = zone(37.8, 44.7)
    annotate([lonely], [], [])
    assert "flags" not in lonely
