from enum import StrEnum


class ReviewLabel(StrEnum):
    LIKELY_DEBRIS = "likely_debris"
    SHIP = "ship"
    STRUCTURE = "structure"
    WAKE = "wake"
    FOAM = "foam"
    SLICK = "slick"
    PLUME = "plume"
    LAND_EDGE = "land_edge"
    CLOUD_EDGE = "cloud_edge"
    WATER = "water"
    UNKNOWN = "unknown"


LABEL_TITLES: dict[ReviewLabel, str] = {
    ReviewLabel.LIKELY_DEBRIS: "вероятно мусор",
    ReviewLabel.SHIP: "судно",
    ReviewLabel.STRUCTURE: "сооружение",
    ReviewLabel.WAKE: "след судна",
    ReviewLabel.FOAM: "пена",
    ReviewLabel.SLICK: "плёнка, слик",
    ReviewLabel.PLUME: "шлейф, цветение",
    ReviewLabel.LAND_EDGE: "берег",
    ReviewLabel.CLOUD_EDGE: "край облака",
    ReviewLabel.WATER: "чистая вода",
    ReviewLabel.UNKNOWN: "не видно",
}

POSITIVE = ReviewLabel.LIKELY_DEBRIS
UNDECIDED = ReviewLabel.UNKNOWN


class ReviewSource(StrEnum):
    UI = "ui"
    AUDIT = "audit"


SOURCE_TITLES: dict[ReviewSource, str] = {
    ReviewSource.UI: "отметки в интерфейсе",
    ReviewSource.AUDIT: "аудит команды, CSV",
}
