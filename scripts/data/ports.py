from __future__ import annotations

import argparse
import csv
import io
import json
import re
from pathlib import Path

from fetch import DATA_DIR, EXTERNAL_DIR, get_entry, load_catalog, open_url

SOURCE_KEY = "world-port-index"
SOURCE_FILE = EXTERNAL_DIR / SOURCE_KEY / "UpdatedPub150.csv"
OUTPUT = DATA_DIR / "aoi" / "ports.geojson"
SHARED_SEAS = ("Black Sea", "Sea of Azov")
HOME_COUNTRY = "Russia"
EXCLUDED_NAME = re.compile(r"\bterminal\b", re.IGNORECASE)
DIGITS = 4

SEA_NAMES = {
    "Black Sea": "Чёрное море",
    "Sea of Azov": "Азовское море",
    "Baltic Sea": "Балтийское море",
    "Gulf of Finland": "Финский залив",
    "Barents Sea": "Баренцево море",
    "White Sea": "Белое море",
    "Kara Sea": "Карское море",
    "Laptev Sea": "море Лаптевых",
    "East Siberian Sea": "Восточно-Сибирское море",
    "Bering Sea": "Берингово море",
    "Anadyrskiy Zaliv": "Анадырский залив",
    "Sea of Okhotsk": "Охотское море",
    "Tatar Strait": "Татарский пролив",
    "Sea of Japan": "Японское море",
    "North Pacific Ocean": "Тихий океан",
}

RUSSIAN_NAMES = {
    28300: "Выборг",
    28310: "Высоцк",
    28360: "Приморск",
    28370: "Санкт-Петербург",
    28390: "Ломоносов",
    28400: "Кронштадт",
    28410: "Усть-Луга",
    28680: "Балтийск",
    28690: "Калининград",
    43500: "Бургас",
    43510: "Варна",
    43550: "Мангалия",
    43558: "Басараби",
    43560: "Констанца",
    43562: "Меджидия",
    43565: "Канал Дунай — Чёрное море",
    43566: "Чернаводэ",
    43568: "Мидия",
    43570: "Сулина",
    43572: "Тулча",
    43590: "Брэила",
    43600: "Галац",
    43625: "Измаил",
    43645: "Черноморск",
    43650: "Одесса",
    43655: "Южный",
    43670: "Николаев",
    43673: "Октябрьск",
    43677: "Днепро-Бугский порт",
    43680: "Херсон",
    43700: "Белгород-Днестровский",
    43710: "Скадовск",
    43720: "Хорлы",
    43745: "Черноморское",
    43747: "Усть-Дунайск",
    43750: "Евпатория",
    43760: "Севастополь",
    43780: "Балаклава",
    43790: "Ялта",
    43810: "Алушта",
    43835: "Судак",
    43850: "Феодосия",
    43900: "Керчь",
    43925: "Рени",
    43940: "Геническ",
    43950: "Кирилловка",
    44000: "Бердянск",
    44010: "Мариуполь",
    44060: "Таганрог",
    44070: "Ростов-на-Дону",
    44080: "Азов",
    44090: "Ейск",
    44140: "Темрюк",
    44180: "Анапа",
    44200: "Новороссийск",
    44210: "Геленджик",
    44230: "Туапсе",
    44240: "Сочи",
    44270: "Адлер",
    44320: "Сухум",
    44350: "Батуми",
    44370: "Хопа",
    44380: "Ризе",
    44390: "Трабзон",
    44410: "Гиресун",
    44420: "Орду",
    44450: "Самсун",
    44460: "Синоп",
    44480: "Инеболу",
    44490: "Зонгулдак",
    44500: "Эрегли",
    60540: "Посьет",
    60582: "Зарубино",
    60610: "Владивосток",
    60670: "Суходол",
    60720: "Бухта Гайдамак",
    60725: "Восточный",
    60730: "Находка",
    60795: "Советская Гавань",
    60800: "Ванино",
    60810: "Де-Кастри",
    60820: "Николаевск-на-Амуре",
    60880: "Поронайск",
    60920: "Корсаков",
    60930: "Невельск",
    60940: "Холмск",
    60980: "Углегорск",
    60981: "Шахтёрск",
    60990: "Лесогорск",
    61020: "Мыс Рогатый (Октябрьский)",
    61040: "Александровск-Сахалинский",
    61045: "Лазарев",
    61060: "Москальво",
    61090: "Шикотан",
    60860: "Оха",
    62535: "Славянка",
    62540: "Охотск",
    62550: "Магадан, бухта Нагаева",
    62600: "Петропавловск-Камчатский",
    62630: "Никольское",
    62635: "Беринговский",
    62640: "Провидения",
    62670: "Тикси",
    62680: "Певек",
    62695: "Диксон",
    62720: "Дудинка",
    62730: "Игарка",
    62775: "Мезень",
    62800: "Архангельск",
    62810: "Северодвинск",
    62840: "Рабочеостровск",
    62890: "Кандалакша",
    62894: "Витино",
    62900: "Большая Пирья Губа",
    62910: "Островной (Гремиха)",
    62950: "Мурманск",
    62970: "Мыс Абрам",
}


def read_rows(path: Path | None) -> list[dict[str, str]]:
    if path is not None and path.exists():
        text = path.read_text(encoding="utf-8-sig")
    else:
        url = get_entry(load_catalog(), SOURCE_KEY)["files"][0]["url"]
        with open_url(url) as response:
            text = response.read().decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text)))


def water_bodies(row: dict[str, str]) -> list[str]:
    return [part.strip() for part in row["World Water Body"].split(";") if part.strip()]


def selected(row: dict[str, str]) -> bool:
    if EXCLUDED_NAME.search(row["Main Port Name"]):
        return False
    bodies = water_bodies(row)
    return any(sea in bodies for sea in SHARED_SEAS) or row["Country Code"].strip() == HOME_COUNTRY


def text(value: str) -> str | None:
    value = value.strip()
    return value or None


def feature(row: dict[str, str]) -> dict:
    number = int(float(row["World Port Index Number"]))
    bodies = water_bodies(row)
    sea = next((SEA_NAMES[body] for body in bodies if body in SEA_NAMES), None)
    lon = round(float(row["Longitude"]), DIGITS)
    lat = round(float(row["Latitude"]), DIGITS)
    english = row["Main Port Name"].strip()
    return {
        "type": "Feature",
        "id": f"wpi-{number}",
        "properties": {
            "id": f"wpi-{number}",
            "name": RUSSIAN_NAMES.get(number, english),
            "name_en": english,
            "country": row["Country Code"].strip(),
            "sea": sea,
            "harbor_size": text(row["Harbor Size"]),
            "harbor_type": text(row["Harbor Type"]),
            "unlocode": text(row["UN/LOCODE"].replace(" ", "")),
            "wpi": number,
        },
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
    }


def build(rows: list[dict[str, str]]) -> dict:
    features = sorted(
        (feature(row) for row in rows if selected(row)),
        key=lambda item: item["properties"]["wpi"],
    )
    return {
        "type": "FeatureCollection",
        "name": "littora-ports",
        "source": "World Port Index, NGA Pub 150 (UpdatedPub150.csv)",
        "features": features,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Порты Чёрного и Азовского морей и морей России из World Port Index"
    )
    parser.add_argument("--source", type=Path, default=SOURCE_FILE)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    collection = build(read_rows(args.source))
    args.output.write_text(
        json.dumps(collection, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    missing = [
        item["properties"]["name_en"]
        for item in collection["features"]
        if item["properties"]["name"] == item["properties"]["name_en"]
    ]
    print(f"{len(collection['features'])} портов → {args.output}")
    if missing:
        print("без русского названия: " + ", ".join(missing))


if __name__ == "__main__":
    main()
