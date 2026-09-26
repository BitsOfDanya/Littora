import numpy as np
import pandas as pd
import pytest

from littora_ml.concentration.external import (
    DOORS,
    EMBLAS,
    SOURCE_COLUMN,
    Design,
    Fold,
    Spec,
    check_design,
    guard,
    make_specs,
    run_design,
    v1_designs,
    v4_design,
)
from littora_ml.concentration.external_sources import (
    BURGAS_DOUBLE_FLAG,
    BURGAS_SOURCE,
    burgas_rows,
    campaign_areas,
    campaign_labels,
    case_columns,
    emblas_rows,
    model_rows,
    write_case_csv,
)
from littora_ml.concentration.guard import LeakageError
from littora_ml.concentration.models import Candidate

HEADER = "\t".join(
    [
        "Cruise",
        "Station",
        "Type",
        "yyyy-mm-ddThh:mm:ss",
        "Longitude [degrees_east]",
        "Latitude [degrees_north]",
        "LOCAL_CDI_ID",
        "QV:SEADATANET",
        "Total_Items [items.km^2]",
        "QV:SEADATANET",
        "Bags [items.km^2]]",
    ]
)
ODV = [
    "//SDN_parameter_mapping\n",
    "//<subject>SDN:LOCAL:Total_Items</subject>\n",
    HEADER + "\n",
    "Bridge_2021\tML1\tB\t2021-09-13T09:00:00\t27.71491\t42.419265\tX\t1\t222\t1\t74\n",
    "Bridge_2021\tML5\tB\t2022-02-10T09:10:00\t27.672895\t42.43202\tX\t1\t74\t1\t0\n",
    "Bridge_2021\tML2\tB\t2023-06-27T09:20:00\t27.746895\t42.390695\tX\t1\t37\t1\t0\n",
]
CONFIG = {
    "seed": 3,
    "inner_splits": 2,
    "jobs": 1,
    "site_radius_km": 0.5,
    "baselines": ["median", "site_climatology", "idw_k5"],
    "models": ["ridge_log"],
    "feature_sets": {"spatial_weather": ["spatial", "weather"]},
    "forward_split": "2023-01-01",
    "transfer": {"feature_sets": ["spatial_weather"]},
}


def test_burgas_rows_follow_case_schema_with_flags() -> None:
    frame = burgas_rows(ODV)
    assert list(frame.columns) == case_columns()
    first, winter, double = (frame.iloc[i] for i in range(3))
    assert first["source_id"] == BURGAS_SOURCE
    assert first["measurement_profile"] == "S4_visual_GT2_5"
    assert first["target_scope"] == "all_litter"
    assert (first["date_utc"], first["time_start_utc"]) == ("2021-09-13", "06:00:00")
    assert winter["time_start_utc"] == "07:10:00"
    assert first["items_count"] == "3" and first["density_numerator_items"] == "3"
    assert first["sampled_area_km2"] == "0.0135"
    assert first["transect_width_m"] == "6" and first["transect_length_km"] == "2.25"
    for flag in ("time_assumed_local_eet_eest", "position_role_unknown"):
        assert flag in first["quality_flags"]
    assert first["position_role"] == "published_transect_point_role_unknown"
    assert double["items_count"] == "1" and double["density_numerator_items"] == "1"
    assert double["sampled_area_km2"] == "0.027"
    assert double["transect_length_km"] == "" and double["transect_width_m"] == ""
    assert BURGAS_DOUBLE_FLAG in double["quality_flags"]
    assert "items_not_integer" not in double["quality_flags"]
    assert double["concentration_items_km2"] == "37"


def test_burgas_campaign_area_falls_back_to_empty_items() -> None:
    densities = pd.Series([74.0, 148.0, 37.0, 0.0, 50.0, 20.0])
    campaigns = pd.Series(["a", "a", "b", "b", "c", "c"])
    assert campaign_areas(densities, campaigns) == {"a": 0.0135, "b": 0.027, "c": None}


def test_burgas_rows_pass_case_selection(tmp_path) -> None:
    path = write_case_csv(burgas_rows(ODV), tmp_path / "burgas.csv")
    table, report = model_rows(path)
    assert report["selection"] == {"accepted": 3}
    assert report["concentration_check"] == {"match": 3}
    assert set(table["target_key"]) == {"litter-visual"}
    assert table["observed_at"].iloc[0].startswith("2021-09-13T06:00")


def test_campaigns_join_consecutive_days_and_split_on_gaps() -> None:
    dates = pd.Series(
        ["2021-09-14", "2021-09-13", "2021-11-04", "2021-11-05", "2022-02-11", "2023-04-29"]
    )
    labels = campaign_labels(dates).tolist()
    assert labels == ["2021-09", "2021-09", "2021-11", "2021-11", "2022-02", "2023-04"]


def test_emblas_rows_convert_local_window_and_flag_date_range() -> None:
    derived = pd.DataFrame(
        {
            "survey": ["EMBLAS-II JOSS RF 2016, RV Impuls", "EMBLAS-II NPMS RF-III 2016, RV A"],
            "transect": ["st116-st117 (report label)", "1G-2G"],
            "date": ["2016-05-29", "2016-05-09/10"],
            "window_local": ["08:43-12:10", np.nan],
            "lat_start": [43.2, 44.56],
            "lon_start": [36.8, 38.05],
            "lat_end": [43.4, 44.54],
            "lon_end": [37.0, 38.03],
            "lat_mid": [43.3, 44.55],
            "lon_mid": [36.9, 38.04],
            "length_km": [20.7, 1.6],
            "width_km": [0.05, 0.02],
            "area_km2": [1.04, 0.032],
            "items": [46, 11],
            "density_items_km2": [44.4, 351.6],
        }
    )
    frame = emblas_rows(derived)
    joss, npms = frame.iloc[0], frame.iloc[1]
    assert (joss["time_start_utc"], joss["time_end_utc"]) == ("05:43:00", "09:10:00")
    assert "station_mapping_inferred" in joss["quality_flags"]
    assert "wide_strip" in joss["quality_flags"]
    assert npms["date_utc"] == "2016-05-09" and npms["time_start_utc"] == ""
    assert "date_range_first_day_used" in npms["quality_flags"]
    assert "reconstructed from report tables" in npms["provenance"]


def synthetic_features(seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    campaigns = [("2021-09", ["2021-09-13", "2021-09-14"]), ("2021-11", ["2021-11-04"])]
    campaigns += [("2022-02", ["2022-02-10", "2022-02-11"]), ("2023-04", ["2023-04-29"])]
    campaigns += [("2023-06", ["2023-06-27"])]
    for campaign, days in campaigns:
        for day in days:
            for transect, x in (("ML1", 0.0), ("ML2", 4.0), ("ML3", 8.0)):
                rows.append(
                    {
                        "source": "burgas",
                        "campaign": campaign,
                        "transect": transect,
                        "group": f"burgas:{campaign}",
                        "date": day,
                        "x_km": x,
                        "y_km": 0.0,
                    }
                )
    for day, x in (("2024-06-02", 300.0), ("2024-06-03", 500.0), ("2024-06-05", 700.0)):
        rows.append(
            {
                "source": DOORS,
                "campaign": f"doors:{day}",
                "transect": f"T{x:.0f}",
                "group": f"doors:{day}",
                "date": day,
                "x_km": x,
                "y_km": 10.0,
            }
        )
    frame = pd.DataFrame(rows)
    frame["sample_id"] = [f"S{i:03d}" for i in range(len(frame))]
    frame["concentration"] = rng.gamma(1.0, 200.0, len(frame)).round()
    for column in ("wind_now", "wind_24h", "wind_72h", "wind_max_72h", "wave_now", "wave_24h"):
        frame[column] = rng.uniform(0.5, 8.0, len(frame))
    frame[SOURCE_COLUMN] = (frame["source"] != "burgas").astype(float)
    return frame


def test_leave_campaign_out_never_shares_a_campaign() -> None:
    features = synthetic_features()
    only, with_doors = v1_designs(features, CONFIG)
    for design in (only, with_doors):
        check_design(design)
        campaigns = design.frame["campaign"].to_numpy()
        sources = design.frame["source"].to_numpy()
        assert len(design.folds) == 5
        for fold in design.folds:
            assert len(set(campaigns[fold.test])) == 1
            assert not set(campaigns[fold.train]) & set(campaigns[fold.test])
            assert set(sources[fold.test]) == {"burgas"}
    doors = np.flatnonzero(with_doors.frame["source"].to_numpy() == DOORS)
    for fold in with_doors.folds:
        assert set(doors) <= set(fold.train)
    assert any(SOURCE_COLUMN in spec.columns for spec in with_doors.specs)
    assert not any(SOURCE_COLUMN in spec.columns for spec in only.specs)


def test_nested_run_keeps_inner_folds_grouped_and_reports_each_row_once() -> None:
    features = synthetic_features(1)
    design = v1_designs(features, CONFIG)[1]
    outcome = run_design(design, CONFIG)
    burgas = np.flatnonzero(design.frame["source"].to_numpy() == "burgas")
    assert np.array_equal(outcome.rows, burgas)
    assert np.isfinite(outcome.nested[burgas]).all()
    assert np.isnan(outcome.nested[design.frame["source"].to_numpy() == DOORS]).all()
    assert {row["selected"] for row in outcome.selections} <= {s.label for s in design.specs}


def test_site_climatology_uses_training_campaigns_of_the_same_transect() -> None:
    features = synthetic_features(2)
    design = v1_designs(features, CONFIG)[0]
    outcome = run_design(design, CONFIG)
    frame = design.frame
    for fold in design.folds:
        train = frame.iloc[fold.train]
        for row in fold.test:
            same = train[train["transect"] == frame.loc[row, "transect"]]
            expected = same["concentration"].mean()
            assert np.isclose(outcome.predictions["site_climatology"][row], expected)
    model = Candidate("site", "site_mean", {"radius_km": 0.5})
    model.fit(pd.DataFrame({"x_km": [0.0, 0.0, 5.0], "y_km": [0.0, 0.0, 0.0]}), np.array([1, 3, 9]))
    far = pd.DataFrame({"x_km": [0.1, 50.0], "y_km": [0.0, 0.0]})
    assert np.allclose(model.predict(far), [2.0, 3.0])


def test_leave_transect_out_holds_out_whole_transects_without_climatology() -> None:
    design = v4_design(synthetic_features(), CONFIG)
    transects = design.frame["transect"].to_numpy()
    for fold in design.folds:
        assert len(set(transects[fold.test])) == 1
        assert not set(transects[fold.train]) & set(transects[fold.test])
    assert "site_climatology" not in {spec.label for spec in design.specs}


def test_design_guard_rejects_emblas_training_and_shared_groups() -> None:
    frame = synthetic_features()
    frame.loc[0, "source"] = EMBLAS
    specs = make_specs(CONFIG, frame, ["spatial_weather"])
    rows = np.arange(len(frame))
    design = Design(
        "bad",
        "bad",
        frame,
        specs,
        [Fold("f", rows[:-3], rows[-3:])],
        frame["group"].to_numpy(),
        np.ones(len(frame), dtype=bool),
        frame["group"].to_numpy(),
    )
    with pytest.raises(LeakageError):
        check_design(design)
    frame.loc[0, "source"] = "burgas"
    shared = Design(
        "shared",
        "shared",
        frame,
        specs,
        [Fold("f", rows[:10], rows[5:15])],
        frame["group"].to_numpy(),
        np.ones(len(frame), dtype=bool),
        frame["group"].to_numpy(),
    )
    with pytest.raises(LeakageError):
        check_design(shared)


def test_feature_guard_allows_the_source_indicator_only() -> None:
    frame = synthetic_features()
    specs = make_specs(CONFIG, frame, ["spatial_weather"], pooled=True)
    report = guard(specs)
    assert SOURCE_COLUMN in report["design_columns"]
    assert SOURCE_COLUMN not in report["checked"]
    leaky = [*specs, Spec("leak", specs[-1].candidate, ["x_km", "items_count"])]
    with pytest.raises(LeakageError):
        guard(leaky)
