import pytest

from littora_ml.concentration.guard import LeakageError, blocked_columns, check_features


def test_answer_fields_are_blocked() -> None:
    blocked = blocked_columns()
    for column in (
        "concentration_items_km2",
        "items_count",
        "density_numerator_items",
        "source_object_filtered_items",
        "reported_concentration_items_km2",
        "parent_concentration_items_km2",
        "wind_speed_kn",
        "sampled_area_km2",
        "concentration",
        "event_id",
    ):
        assert column in blocked


def test_model_features_pass_and_leaks_fail() -> None:
    assert check_features(["x_km", "y_km", "wind_now"])["checked"] == ["wind_now", "x_km", "y_km"]
    with pytest.raises(LeakageError):
        check_features(["x_km", "items_count"])
    with pytest.raises(LeakageError):
        check_features(["sea_state_beaufort"])
    with pytest.raises(LeakageError):
        check_features(["x_km", "concentration"])


def test_feature_provenance_documents_the_observation_time() -> None:
    report = check_features(["x_km", "wind_now", "doy_sin"])
    assert report["provenance"]["x_km"]["case_columns"] == ["latitude", "longitude"]
    assert report["provenance"]["doy_sin"]["case_columns"] == ["date_utc"]
    assert "time_start_utc" in report["provenance"]["wind_now"]["case_columns"]
    assert "observed_at" in report["allowed_time_source"]
