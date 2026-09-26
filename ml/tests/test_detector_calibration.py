import numpy as np
from scipy.special import expit

from littora_ml.detector.calibration import (
    Isotonic,
    Temperature,
    decision_metrics,
    expected_calibration_error,
    from_params,
    log_loss,
    out_of_fold,
    reliability_bins,
)
from littora_ml.detector.metrics import best_threshold


def synthetic(scale: float, size: int = 200_000, seed: int = 0):
    rng = np.random.default_rng(seed)
    logits = rng.normal(-3.0, 3.0, size)
    truth = rng.random(size) < expit(logits / scale)
    return expit(logits), truth


def test_ece_uses_fifteen_equal_bins() -> None:
    probability = np.array([0.1, 0.1, 0.9, 0.9, 1.0])
    truth = np.array([False, False, True, False, True])
    assert np.isclose(expected_calibration_error(probability, truth), (0.2 + 0.8) / 5)
    bins = reliability_bins(probability, truth)
    assert len(bins) == 15
    assert [row["pixels"] for row in bins if row["pixels"]] == [2, 2, 1]
    assert bins[14]["frequency"] == 1.0 and bins[0]["mean_probability"] is None
    calibrated = np.random.default_rng(1).random(100_000)
    outcomes = np.random.default_rng(2).random(100_000) < calibrated
    assert expected_calibration_error(calibrated, outcomes) < 0.01


def test_temperature_recovers_known_scale_and_lowers_log_loss() -> None:
    probability, truth = synthetic(scale=2.0)
    model = Temperature().fit(probability, truth)
    assert abs(model.temperature - 2.0) < 0.1
    assert log_loss(model(probability), truth) < log_loss(probability, truth)
    assert expected_calibration_error(model(probability), truth) < expected_calibration_error(
        probability, truth
    )


def test_calibrators_are_monotone_bounded_and_serializable() -> None:
    probability, truth = synthetic(scale=1.5, size=20_000)
    grid = np.linspace(0.0, 1.0, 501)
    for model in (Temperature().fit(probability, truth), Isotonic().fit(probability, truth)):
        values = model(grid)
        assert np.all(np.diff(values) >= 0)
        assert values.min() >= 0 and values.max() <= 1
        assert np.allclose(from_params(model.params())(grid), values)


def test_monotone_calibration_keeps_the_threshold_decision() -> None:
    probability, truth = synthetic(scale=1.7, size=50_000, seed=3)
    model = Temperature(1.7)
    raw_threshold, raw_f1 = best_threshold(probability, truth)
    calibrated_threshold, calibrated_f1 = best_threshold(model(probability), truth)
    assert np.isclose(calibrated_threshold, model(np.array([raw_threshold]))[0])
    assert np.isclose(raw_f1, calibrated_f1)
    raw = probability >= raw_threshold
    calibrated = model(probability) >= calibrated_threshold
    assert np.array_equal(raw, calibrated)


def test_out_of_fold_never_sees_the_held_out_group() -> None:
    probability = np.array([0.2, 0.2, 0.8, 0.8])
    truth = np.array([False, False, True, True])
    groups = np.array(["a", "a", "b", "b"])
    predicted = out_of_fold("isotonic", probability, truth, groups)
    assert np.allclose(predicted, [1.0, 1.0, 0.0, 0.0])


def test_decision_metrics_count_only_labeled_pixels() -> None:
    labels = np.array([[[1, 1, 7, 0]]])
    mask = np.array([[[True, False, True, True]]])
    result = decision_metrics(mask, labels)
    assert (result["tp"], result["fp"], result["fn"]) == (1, 1, 1)
    assert np.isclose(result["f1"], 0.5)
