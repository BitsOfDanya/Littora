"""Scientific boundary checks for the acquired validation data."""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import rasterio

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
from imagery import acquire, reflectance
from review import evaluation_ready


def test_nodata_is_not_negative_reflectance():
    raw = np.array([0, 500, 2000, 6000], dtype="uint16")
    values = reflectance(
        raw,
        np.array([True, True, True, False]),
        {"scale": 0.0001, "offset": -0.1, "nodata": 0},
    )
    assert np.isnan(values[[0, 3]]).all()
    np.testing.assert_allclose(values[1:3], [-0.05, 0.1], atol=1e-7)
    with pytest.raises(ValueError):
        reflectance(raw, np.ones(4, dtype=bool), {"scale": 0.0001})


def test_independent_review_gate():
    complete = {
        "reviewer_ids": ["person_a", "person_b"],
        "adjudicator_id": "person_c",
        "adjudication_status": "complete",
        "evidence_audit_passed": True,
        "prediction_blind_review": True,
        "reference_pixels": 10,
    }
    assert evaluation_ready(complete)
    assert not evaluation_ready({})
    for key, value in [
        ("reviewer_ids", ["a", "a"]),
        ("reference_pixels", 0),
        ("evidence_audit_passed", False),
        ("prediction_blind_review", False),
        ("adjudication_status", "pending"),
    ]:
        assert not evaluation_ready({**complete, key: value})


def test_no_station_times_transferred_to_litter():
    doors = pd.read_csv(
        ROOT / "reports/validation_bridge/tables/doors_transects_pending_geometry.csv"
    )
    assert len(doors) == 33
    assert doors.start_time_utc.isna().all() and doors.area_km2.isna().all()
    assert not doors.precise_pairing_ready.any()
    assert (
        doors.coordinate_status == "source_lat_lon_swapped_in_existing_case"
    ).sum() == 1
    assert doors.loc[~doors.source_coordinate_usable, "transect_id"].tolist() == ["T33"]
    neighbours = pd.read_csv(
        ROOT
        / "reports/validation_bridge/tables/doors_optical_neighbours_NOT_JOINED.csv"
    )
    assert not neighbours.join_approved.any()


def test_optical_spectra_and_pair_quality():
    d = pd.read_csv(ROOT / "reports/validation_bridge/tables/doors_trios_rrs.csv")
    assert set(d.filter(regex=r"^Rrs_\d+$")) == {f"Rrs_{w}" for w in range(400, 851)}
    assert len(d) == 27 and not d.litter_label_available.any()
    assert pd.to_datetime(d.datetime_utc, utc=True).notna().all()
    c = pd.read_csv(
        ROOT / "reports/validation_bridge/tables/doors_optical_satellite_candidates.csv"
    )
    accepted = c[c.accepted]
    assert accepted.time_difference_hours.le(3).all()
    assert accepted.water_fraction.eq(1).all() and accepted.nodata_fraction.eq(0).all()


def test_holdout_unknown_and_never_in_training():
    d = pd.read_csv(
        ROOT / "reports/validation_bridge/tables/blacksea_holdout_registry.csv"
    )
    assert len(d) == 12 and d.chip_id.is_unique
    assert not d.training_allowed.any()
    for row in d[d.review_status == "pending_two_reviewers"].itertuples():
        assert row.date.startswith("2025-")
        assert not row.model_predictions_computed
        folder = ROOT / row.folder
        with rasterio.open(folder / "l2a.tif") as ds:
            assert ds.count == 11 and np.isfinite(ds.read()).all()
            transform, crs = ds.transform, ds.crs
        with rasterio.open(folder / "labels.tif") as ds:
            assert ds.transform == transform and ds.crs == crs
            assert not ds.read().any()  # initial release only; 0 means unknown
        assert json.loads((folder / "stac.json").read_text())["id"] == row.stac_id


def test_pairs_have_identical_grids_and_acquisition_keys():
    d = pd.read_csv(ROOT / "reports/validation_bridge/tables/radiometry_pairs.csv")
    for row in d[d.match_status == "paired"].itertuples():
        folder = ROOT / row.paired_folder
        stac = json.loads((folder / "stac.json").read_text())
        assert stac["properties"]["grid:code"] == "MGRS-" + row.tile
        assert stac["properties"]["datetime"][:10] == row.date
        with (
            rasterio.open(folder / "rhorc.tif") as r,
            rasterio.open(folder / "l2a.tif") as l,
        ):
            assert r.transform == l.transform and r.crs == l.crs
            assert r.shape == l.shape and r.count == l.count == 11


def test_cannot_change_scene_under_existing_review(tmp_path):
    (tmp_path / "stac.json").write_text(json.dumps({"id": "old_scene"}))
    (tmp_path / "review.json").write_text(json.dumps({"status": "complete"}))
    with pytest.raises(ValueError, match="existing annotations"):
        acquire({"id": "different_scene"}, {}, tmp_path)
    assert json.loads((tmp_path / "stac.json").read_text())["id"] == "old_scene"
