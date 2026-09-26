import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run import DATA, OUT, ROOT, T, predictors, sha


def test_original_records_are_preserved():
    source = pd.read_csv(ROOT / "data/case/macroplastic_marine_samples.csv")
    merged = pd.read_csv(DATA / "macroplastic_marine_samples_with_burgas.csv")
    pd.testing.assert_frame_equal(
        source, merged.iloc[: len(source)][source.columns], check_dtype=False
    )
    assert len(merged) == 1019 and merged.event_id.nunique() == 402


def test_repeated_station_ids_are_not_deduplicated():
    e = pd.read_csv(DATA / "events.csv")
    assert e.source_event_id.nunique() == 8 and e.event_id.nunique() == 84
    assert (e.concentration_items_km2 == 0).sum() == 26
    assert e.confirmed_datetime_utc.isna().all() and e.date_utc.isna().all()
    assert e.date_reported.notna().all()
    assert np.isfinite(predictors(e)).all()


def test_campaigns_and_transfer_folds_stay_disjoint():
    membership = pd.read_csv(T / "temporal_memberships.csv")
    assert membership.groupby("campaign").split.nunique().max() == 1
    assert (membership.split == "test").sum() == 28
    assert set(membership.loc[membership.split == "test", "event_id"]).isdisjoint(
        membership.loc[membership.split == "train", "event_id"]
    )
    p = pd.read_csv(T / "doors_transfer_predictions.csv")
    assert p.groupby(["event_id", "variant"]).size().eq(1).all()
    assert p.groupby("variant").event_id.nunique().eq(33).all()
    assert pd.read_csv(T / "transfer_fold_integrity.csv").test_group_overlap.eq(0).all()


def test_no_fabricated_counts_and_frozen_inputs():
    e = pd.read_csv(DATA / "events.csv")
    assert "items_count" not in e
    assert e.target_scope.eq("all_litter").all()
    frozen = json.loads((DATA / "frozen_experiment.json").read_text())
    assert frozen["events_sha256"] == sha(DATA / "events.csv")
    assert frozen["predictors"] == ["latitude", "longitude", "season_sin", "season_cos"]
    protected = json.loads((OUT / "protected_hashes.json").read_text())
    assert all(sha(Path(p)) == h for p, h in protected.items())
