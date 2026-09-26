"""Regression checks for newly introduced eligibility, joins and evaluation boundaries."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from field_data import ROOT, normalize_emblas
from mados import exact_spectrum_matches


def test_missing_emblas_coordinates_never_become_train_labels():
    frame = normalize_emblas(
        ROOT / "data/external/emblas-floating-litter/gonzalez-fernandez2022-mmc2.xlsx"
    )
    assert len(frame) == 302 and not frame.t3_eligible.any()
    assert frame[["latitude", "longitude"]].isna().all().all()
    assert frame.is_observed_zero.sum() == 40 and frame.items_count.sum() == 7655
    assert frame.start_time_reported.dt.tz is None
    assert np.isclose(frame.area_km2.sum(), 93.92213002)


def test_duplicate_screen_matches_full_vector_not_one_bright_band():
    reference = np.arange(33, dtype=np.float32).reshape(3, 11) / 100
    query = reference.copy()
    query[1, -1] += 0.001
    assert exact_spectrum_matches(query, reference).tolist() == [True, False, True]
    assert not exact_spectrum_matches(np.zeros((1, 11)), np.zeros((1, 11))).any()


def test_plp_outside_crop_and_reeds_excluded_from_plastic_target():
    table = pd.read_csv(ROOT / "reports/expansion/tables/plp2019_pixel_cover.csv")
    pred = pd.read_csv(
        ROOT / "reports/expansion/tables/plp2019_date_holdout_predictions.csv"
    )
    assert len(table) == 65 and table.spatial_match_valid.sum() == 63
    assert np.allclose(table.plastic_cover_pct, table.CP_Bags + table.CP_Bottles)
    included = table.set_index(["date", "pixel_name"]).spatial_match_valid
    assert all(included.loc[(r.date, r.pixel_name)] for r in pred.itertuples())
    assert (
        not table.loc[table.spatial_match_valid]
        .duplicated(["date", "nc_row", "nc_col"])
        .any()
    )
    for _, g in pred.groupby("model"):
        assert len(g) == 63 and not g.duplicated(["date", "pixel_name"]).any()


def test_weather_is_prior_day_and_folds_preserved():
    weather = pd.read_csv(ROOT / "reports/expansion/tables/era5_event_context.csv")
    case = pd.read_csv(ROOT / "data/case/macroplastic_marine_samples.csv")
    joined = weather.merge(
        case[["event_id", "date_utc"]].drop_duplicates(),
        on="event_id",
        validate="one_to_one",
    )
    assert len(joined) == 74
    assert (
        (
            pd.to_datetime(joined.date_utc) - pd.to_datetime(joined.context_day_utc)
        ).dt.days
        == 1
    ).all()
    pred = pd.read_csv(ROOT / "reports/expansion/tables/weather_oof_predictions.csv")
    original = pd.read_csv(ROOT / "reports/eda/tables/cv_memberships.csv")
    expected = original[original.role == "test"].set_index("event_id")["fold"]
    assert pred.event_id.map(expected).eq(pred.fold).all()
    for _, g in pred.groupby("model"):
        assert g.event_id.is_unique and len(g) == 74


def test_mados_scene_split_and_cross_source_screen():
    data = pd.read_csv(ROOT / "reports/expansion/tables/mados_inventory.csv")
    assert len(data) == 2803
    assert data.groupby("scene_id").split.nunique().max() == 1
    assert data.groupby("image_sha256").split.nunique().max() == 1
    assert data.groupby("group").split.nunique().max() == 1
    assert not data.loc[
        data.marida_exact_spectral_matches > 0, "cross_source_screen_pass"
    ].any()
    thresholds = pd.read_csv(ROOT / "reports/expansion/tables/detector_thresholds.csv")
    assert (
        thresholds.loc[thresholds.model != "marida_frozen", "selection"]
        .str.startswith("MADOS validation")
        .all()
    )
    predictions = np.load(ROOT / "data/processed/expansion/mados_test_predictions.npz")
    patches = data.iloc[predictions["patch_index"]]
    assert patches.split.eq("test").all() and patches.cross_source_screen_pass.all()
    assert (predictions["y"] > 0).all() and (predictions["confidence"] > 0).all()
