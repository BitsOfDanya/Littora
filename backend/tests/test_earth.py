import pytest

from app.earth.catalog import parse_scene


def feature(collection: str, baseline: str) -> dict:
    return {
        "id": "S2B_37TDK_20250904_0_L2A",
        "collection": collection,
        "geometry": {"type": "Polygon", "coordinates": [[[37, 44], [38, 44], [38, 45], [37, 44]]]},
        "properties": {
            "datetime": "2025-09-04T08:40:00Z",
            "platform": "sentinel-2b",
            "s2:processing_baseline": baseline,
        },
        "assets": {
            "nir": {
                "href": "https://example.org/B08.tif",
                "raster:bands": [{"scale": 0.0001, "offset": -0.1}],
            }
        },
    }


@pytest.mark.parametrize(
    ("collection", "baseline", "offset"),
    [
        ("sentinel-2-l2a", "05.11", 0.0),
        ("sentinel-2-l2a", "02.14", -0.1),
        ("sentinel-2-c1-l2a", "05.11", -0.1),
    ],
)
def test_harmonized_items_ignore_the_stated_offset(collection, baseline, offset) -> None:
    scene = parse_scene(feature(collection, baseline))
    assert scene.reflectance_scale == 0.0001
    assert scene.reflectance_offset == offset
