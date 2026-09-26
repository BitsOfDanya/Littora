import numpy as np
import pandas as pd
import pytest

from littora_ml.concentration.models import Candidate
from littora_ml.concentration.run import _service_options, calendar_day, season_window
from littora_ml.concentration.validation import (
    date_block_split,
    folds,
    paired_difference,
    repeated_nested_cv,
)


def survey(days: int = 8, per_day: int = 3) -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(0)
    rows = days * per_day
    dates = [f"2024-06-{day + 1:02d}" for day in range(days) for _ in range(per_day)]
    x = np.repeat(np.arange(days) * 20.0, per_day) + rng.normal(0, 2, rows)
    y = rng.normal(0, 5, rows)
    target = np.exp(3 + x / 60) + rng.gamma(2, 2, rows)
    table = pd.DataFrame({"x_km": x, "y_km": y, "date": dates})
    return table, target, np.array(dates)


def test_random_group_folds_are_seeded_and_keep_days_together() -> None:
    groups = np.repeat([f"d{i}" for i in range(12)], 2)
    first = folds(groups, 5, [42, 0])
    again = folds(groups, 5, [42, 0])
    other = folds(groups, 5, [42, 1])
    assert all(np.array_equal(a[1], b[1]) for a, b in zip(first, again, strict=True))
    assert not all(np.array_equal(a[1], b[1]) for a, b in zip(first, other, strict=True))
    for train, test in first:
        assert not set(groups[train]) & set(groups[test])
    assert sorted(np.concatenate([test for _, test in first])) == list(range(len(groups)))


def test_repeated_nested_cv_predicts_every_event_once_per_repetition() -> None:
    table, target, groups = survey()
    options = [
        ("median", Candidate("median", "median"), ["x_km", "y_km"]),
        ("idw_k5", Candidate("idw_k5", "idw", {"k": 5, "power": 2}), ["x_km", "y_km"]),
    ]
    config = {"seed": 7, "repetitions": 3, "outer_splits": 4, "inner_splits": 3, "coverage": 0.8}
    cv = repeated_nested_cv(options, table, target, groups, {**config, "jobs": 1})
    assert cv.assignments.shape == (3, len(target))
    assert (cv.assignments >= 0).all()
    assert len(cv.selections) == 3 and all(len(rows) == 4 for rows in cv.selections)
    for repetition, rows in enumerate(cv.selections):
        for fold in rows:
            mask = cv.assignments[repetition] == fold["fold"]
            chosen = cv.oof[fold["selected"]][repetition, mask]
            assert np.array_equal(cv.nested[repetition, mask], chosen)
    again = repeated_nested_cv(options, table, target, groups, {**config, "jobs": 2})
    assert np.array_equal(cv.nested, again.nested)
    assert cv.coverage().shape == (3,)


def test_paired_difference_is_zero_for_identical_models_and_negative_for_better() -> None:
    _, target, groups = survey()
    baseline = np.tile(np.full(len(target), np.median(target)), (3, 1))
    same = paired_difference(target, baseline, baseline, groups, 500, 1)
    assert same["mae"]["mean"] == 0 and same["mae"]["ci"] == [0.0, 0.0]
    assert same["mae"]["confidence"] == 0.95
    better = np.tile(target * 1.02, (3, 1))
    result = paired_difference(target, better, baseline, groups, 500, 1)
    assert result["mae"]["ci"][1] < 0
    assert result["rmse"]["ci"][1] < 0
    wide = paired_difference(target, better, baseline, groups, 500, 1, confidence=0.975)
    assert wide["mae"]["ci"][0] <= result["mae"]["ci"][0]
    assert wide["mae"]["ci"][1] >= result["mae"]["ci"][1]
    assert -1 < result["mae"]["relative"] < 0


def test_date_block_holdout_takes_the_first_days_for_training() -> None:
    dates = pd.Series([f"2024-06-{day:02d}" for day in (1, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10)])
    train, test = date_block_split(dates, 0.7)
    assert dates.iloc[train].max() < dates.iloc[test].min()
    assert dates.iloc[train].nunique() == 7


def test_season_window_adds_margin_and_wraps() -> None:
    june = season_window(pd.Series(["2024-06-02", "2024-06-18"]), 30)
    assert (june["doy_start"], june["doy_end"]) == (123, 199)
    assert june["span"] == ["02.06", "18.06"]
    winter = season_window(pd.Series(["2023-12-20", "2024-01-10"]), 10)
    assert winter["doy_start"] > winter["doy_end"]
    assert winter["doy_start"] == 344 and winter["doy_end"] == 20
    assert winter["span"] == ["20.12", "10.01"]
    year = season_window(pd.Series(["2024-01-10", "2024-05-01", "2024-09-01"]), 70)
    assert (year["doy_start"], year["doy_end"]) == (1, 365)


def test_leap_year_days_share_one_numbering_around_new_year() -> None:
    days = calendar_day(pd.Series(["2024-02-29", "2024-03-01", "2023-03-01", "2024-12-31"]))
    assert list(days) == [59, 60, 60, 365]
    december = season_window(pd.Series(["2024-12-30", "2024-12-31"]), 10)
    assert (december["doy_start"], december["doy_end"]) == (354, 10)
    assert december["span"] == ["30.12", "31.12"]
    crossing = season_window(pd.Series(["2024-12-31", "2025-01-01"]), 5)
    assert (crossing["doy_start"], crossing["doy_end"]) == (360, 6)
    assert crossing["span"] == ["31.12", "01.01"]


def test_service_options_accept_only_coordinates() -> None:
    table, _, _ = survey()
    table = table.assign(doy_sin=np.linspace(0, 1, len(table)), doy_cos=1.0)
    config = {
        "seed": 1,
        "feature_sets": {"spatial": ["spatial"], "spatial_season": ["spatial", "season"]},
        "service": {"options": ["median", "idw_k5", "tweedie_glm|spatial"]},
    }
    labels = [label for label, _, _ in _service_options(config, table)]
    assert labels == ["median", "idw_k5", "tweedie_glm|spatial"]
    config["service"]["options"] = ["median", "tweedie_glm|spatial_season"]
    with pytest.raises(ValueError, match="только координаты"):
        _service_options(config, table)
