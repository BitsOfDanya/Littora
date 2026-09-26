import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from acquire import distance, summarize
from train import feature_columns, make_imputer


def test_no_future_or_date_only_fake_instant():
    ix = pd.date_range("2020-01-01", periods=97, freq="h", tz="UTC")
    frame = pd.DataFrame({"wind_speed_ms": np.ones(97)}, index=ix)
    frame.loc[frame.index > pd.Timestamp("2020-01-04T12:30Z")] = 999
    r = summarize(frame, "2020-01-04T12:30Z", "2020-01-04", 1)
    assert (
        r["wind_speed_ms_instant"]
        == r["wind_speed_ms_mean24h"]
        == r["wind_speed_ms_mean72h"]
        == 1
    )
    assert r["time_offset_h"] == 0.5
    d = summarize(frame, "", "2020-01-04", 1)
    assert not any("instant" in c for c in d)
    assert "wind_speed_ms_daily_mean" in d


def test_missing_coverage_not_zero():
    ix = pd.date_range("2020-01-01", periods=96, freq="h", tz="UTC")
    f = pd.DataFrame({"wave_height_m": np.nan}, index=ix)
    f.iloc[-3:] = 0
    r = summarize(f, "2020-01-04T23:30Z", "2020-01-04", 1)
    assert r["wave_height_m_instant"] == 0
    assert np.isnan(r["wave_height_m_mean24h"])
    assert r["wave_height_m_coverage24h"] == 3 / 24


def test_imputation_uses_train_only():
    tr = pd.DataFrame({"wind": [1.0, 3.0, np.nan], "missing": [np.nan] * 3})
    te = pd.DataFrame({"wind": [999.0, np.nan], "missing": [50.0, 60.0]})
    _, out, used, _ = make_imputer(tr, pd.concat([tr, te]), ["wind", "missing"])
    assert used == ["wind"]
    assert out[-1, 0] == 2 and out[-1, 1] == 1


def test_dateline_distance_and_predictor_whitelist():
    assert distance(0, 179.99, 0, -179.99) < 3
    f = pd.DataFrame(
        columns=[
            "wind_speed_ms_instant",
            "items_count",
            "wind_speed_ms_coverage24h",
            "concentration_items_km2",
            "latitude",
            "current_u_ms_mean72h",
        ]
    )
    assert feature_columns(f) == ["wind_speed_ms_instant", "current_u_ms_mean72h"]


def test_downloaded_hycom_scale_and_zero_depth():
    from acquire import ROOT, parse_series

    manifest_path = ROOT / "reports/metocean/tables/download_manifest.csv"
    if not manifest_path.exists():
        return
    m = pd.read_csv(manifest_path)
    m = m[(m.status == "ok") & m.path.str.endswith(".nc")]
    if m.empty:
        return
    points = pd.read_csv(ROOT / "data/processed/metocean/points.csv").set_index(
        "join_id"
    )
    row = m.iloc[0]
    f, meta, _ = parse_series(ROOT / row.path, points.loc[row.join_id], "current")
    assert np.nanmax(np.abs(f[["current_u_ms", "current_v_ms"]])) < 10
    assert meta["native_step_h"] == 3


def test_saved_joins_keep_missing_time_and_case_rows():
    from acquire import DATA, ROOT

    f = pd.read_csv(DATA / "features.csv")
    unknown = f[f.time_precision == "date_only"]
    instant = [c for c in f if c.endswith("_instant")]
    assert unknown[instant].isna().all().all()
    source = pd.read_csv(ROOT / "data/case/macroplastic_marine_samples.csv")
    merged = pd.read_csv(DATA / "macroplastic_marine_samples_metocean.csv")
    pd.testing.assert_frame_equal(source, merged[source.columns])
    assert f.join_id.is_unique


def test_frozen_classifier_input_and_group_partition():
    import json

    from acquire import DATA, sha

    frozen = json.loads((DATA / "frozen_before_test.json").read_text())
    assert frozen["input_sha256"] == sha(DATA / "features.csv")
    f = pd.read_csv(DATA / "features.csv")
    p = f[f.kind == "patch"]
    assert p.groupby("group").split.nunique().max() == 1
    for spec in frozen["variants"].values():
        assert not set(spec["features"]) & {
            "latitude",
            "longitude",
            "items_count",
            "date",
            "selection_index",
        }
    protected = json.loads((DATA / "protected_hashes.json").read_text())
    assert all(sha(Path(path)) == digest for path, digest in protected.items())
