import csv
import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter

from app.api.dependencies import SettingsDep

router = APIRouter(tags=["labels"])

NEGATIVES_FILE = Path("validation") / "black_sea_negatives.geojson"
AUDIT_FILE = Path("validation") / "black_sea_zone_audit.csv"
CLASS_TITLES = {
    "aquaculture": "садки",
    "water": "вода",
    "cloud": "облако",
    "ship": "судно",
    "slick": "пятно",
    "turbid_front": "фронт мутности",
    "river_plume": "речной шлейф",
    "likely_debris": "мусор",
    "plume": "шлейф или цветение",
    "land_edge": "берег",
    "cloud_edge": "край облака",
    "structure": "сооружение",
    "wake": "кильватер",
    "foam": "пена",
    "unknown": "не понять",
}


def negatives(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    features = json.loads(path.read_text(encoding="utf-8")).get("features", [])
    return [
        {
            "type": "Feature",
            "geometry": feature["geometry"],
            "properties": {
                "source": "negatives",
                "class": feature["properties"].get("class"),
                "title": CLASS_TITLES.get(feature["properties"].get("class"), "фон"),
                "scene_id": feature["properties"].get("scene_id"),
            },
        }
        for feature in features
        if feature.get("geometry")
    ]


def audit(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [float(row["lon"]), float(row["lat"])]},
            "properties": {
                "source": "audit",
                "class": row["class"],
                "title": CLASS_TITLES.get(row["class"], row["class"]),
                "scene_id": row["scene_id"],
                "date": row["date"],
                "zone_id": row["zone_id"],
                "confidence": int(row["confidence"] or 0),
            },
        }
        for row in rows
        if row.get("lon") and row.get("lat")
    ]


@router.get("/labels")
def read_labels(settings: SettingsDep) -> dict[str, Any]:
    data = settings.data_dir
    features = negatives(data / NEGATIVES_FILE) + audit(data / AUDIT_FILE)
    return {"type": "FeatureCollection", "features": features}
