from __future__ import annotations

import pandas as pd

REGIONS = {
    "16PCC": "honduras",
    "16PDC": "honduras",
    "16PEC": "honduras",
    "16QED": "honduras",
    "18QYF": "hispaniola",
    "18QYG": "hispaniola",
    "18QWF": "hispaniola",
    "19QDA": "hispaniola",
    "48PZC": "south_china_sea",
    "51PTS": "south_china_sea",
    "51RVQ": "east_asia",
    "52SDD": "east_asia",
    "48MXU": "indonesia",
    "48MYU": "indonesia",
    "50LLR": "indonesia",
    "36JUN": "south_africa",
    "30VWH": "scotland",
}


def with_regions(table: pd.DataFrame) -> pd.DataFrame:
    return table.assign(region=table["tile"].map(REGIONS).fillna("other"))


def official(table: pd.DataFrame) -> pd.Series:
    return table["official_split"]


def region_holdout(table: pd.DataFrame, test_regions: tuple[str, ...]) -> pd.Series:
    regions = with_regions(table)["region"]
    split = official(table).where(~regions.isin(test_regions), "test")
    return split.where(~((split == "test") & ~regions.isin(test_regions)), "val")


def check_scene_disjoint(table: pd.DataFrame, split: pd.Series) -> dict:
    per_scene = split.groupby(table["scene"]).nunique()
    per_tile = split.groupby(table["tile"]).agg(lambda values: sorted(set(values)))
    shared_tiles = {tile: splits for tile, splits in per_tile.items() if len(splits) > 1}
    return {
        "scenes_in_several_splits": int((per_scene > 1).sum()),
        "tiles_in_several_splits": shared_tiles,
    }
