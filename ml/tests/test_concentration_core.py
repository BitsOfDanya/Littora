import numpy as np
import pandas as pd

from littora_ml.concentration.models import Candidate
from littora_ml.concentration.validation import (
    conformal_quantile,
    conformal_rank,
    folds,
    interval,
    metrics,
)


def frame(values) -> pd.DataFrame:
    return pd.DataFrame(values, columns=["x_km", "y_km"])


def test_group_folds_never_split_a_survey_day() -> None:
    groups = np.array(["d1", "d1", "d2", "d3", "d3", "d4", "d5", "d5"])
    for train, test in folds(groups, 3):
        assert not set(groups[train]) & set(groups[test])


def test_idw_interpolates_in_log_space_and_nearest_copies() -> None:
    train = frame([[0, 0], [10, 0]])
    target = np.array([10.0, 1000.0])
    idw = Candidate("idw", "idw", {"k": 2, "power": 2}).fit(train, target)
    middle = idw.predict(frame([[5, 0]]))[0]
    assert np.isclose(middle, np.expm1((np.log1p(10) + np.log1p(1000)) / 2))
    nearest = Candidate("nn", "nearest").fit(train, target)
    assert nearest.predict(frame([[9, 0]]))[0] == 1000.0


def test_conformal_interval_contains_the_training_residual_level() -> None:
    truth = np.array([10.0, 20.0, 40.0, 80.0, 160.0])
    prediction = np.array([12.0, 18.0, 50.0, 60.0, 150.0])
    q = conformal_quantile(truth, prediction, 0.8)
    lower, upper = interval(prediction, q)
    assert ((truth >= lower) & (truth <= upper)).mean() >= 0.8
    assert metrics(truth, prediction)["mae"] == np.mean(np.abs(truth - prediction))


def test_conformal_quantile_takes_the_split_conformal_order_statistic() -> None:
    residual = np.random.default_rng(3).permutation(np.arange(1, 51) / 10)
    truth = np.expm1(residual)
    prediction = np.zeros(50)
    assert conformal_rank(50, 0.8) == 41
    assert np.isclose(conformal_quantile(truth, prediction, 0.8), 4.1)
    assert conformal_rank(99, 0.55) == 55
    assert conformal_rank(5, 0.95) == 5
    assert np.isclose(conformal_quantile(truth[:5], prediction[:5], 0.95), residual[:5].max())
