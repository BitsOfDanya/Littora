import numpy as np
import pandas as pd
import torch

from littora_ml.detector.export import ServingModel
from littora_ml.detector.features import spectral_indices
from littora_ml.detector.marida import BANDS, parse_scene
from littora_ml.detector.metrics import best_threshold, evaluate
from littora_ml.detector.splits import check_scene_disjoint, region_holdout
from littora_ml.satellite.sliding import sliding_scores


def pixel(**values: float) -> np.ndarray:
    image = np.full((len(BANDS), 1, 1), 0.02, dtype=np.float32)
    for name, value in values.items():
        image[BANDS.index(name)] = value
    return image


def test_fdi_follows_biermann_definition() -> None:
    image = pixel(B04=0.03, B06=0.04, B08=0.09, B11=0.02)
    span = (832.8 - 664.6) / (1613.7 - 664.6)
    expected = 0.09 - (0.04 + (0.02 - 0.04) * span * 10)
    assert np.isclose(spectral_indices(image)[1, 0, 0], expected)
    assert np.isclose(spectral_indices(image)[0, 0, 0], (0.09 - 0.03) / (0.09 + 0.03), atol=1e-4)


def test_serving_graph_matches_numpy_indices() -> None:
    rng = np.random.default_rng(1)
    image = rng.uniform(0.001, 0.1, (len(BANDS), 8, 8)).astype(np.float32)
    serving = ServingModel(torch.nn.Identity(), np.zeros(19), np.ones(19), True, list(BANDS))
    derived = serving.derived(torch.from_numpy(image[None])).numpy()[0]
    assert np.allclose(derived, spectral_indices(image), atol=1e-5)


def test_metrics_ignore_unlabeled_pixels() -> None:
    labels = np.array([[1, 1, 7, 0], [7, 9, 0, 0]])
    scores = np.array([[0.9, 0.2, 0.1, 0.99], [0.8, 0.1, 0.99, 0.99]])
    result = evaluate(scores, labels, threshold=0.5)
    assert (result["tp"], result["fp"], result["fn"]) == (1, 1, 1)
    assert result["pixels"] == 5
    assert result["false_positives_by_class"]["marine_water"]["false_positive_rate"] == 0.5
    threshold, f1 = best_threshold(np.array([0.9, 0.2, 0.1]), np.array([True, True, False]))
    assert threshold == 0.2 and np.isclose(f1, 1.0)


def test_scene_names_and_region_holdout_are_consistent() -> None:
    day, tile = parse_scene("1-12-19_48MYU")
    assert (day.isoformat(), tile) == ("2019-12-01", "48MYU")
    table = pd.DataFrame(
        {
            "scene": ["a", "a", "b", "c"],
            "tile": ["16PCC", "16PCC", "48MYU", "18QYF"],
            "official_split": ["train", "train", "test", "val"],
        }
    )
    split = region_holdout(table, ("indonesia",))
    assert split.tolist() == ["train", "train", "test", "val"]
    assert check_scene_disjoint(table, split)["scenes_in_several_splits"] == 0


def test_sliding_scores_cover_every_pixel() -> None:
    image = np.random.default_rng(2).random((2, 300, 500)).astype(np.float32)
    result = sliding_scores(image, lambda tiles: tiles[:, 1])
    assert np.allclose(result, image[1], atol=1e-5)
