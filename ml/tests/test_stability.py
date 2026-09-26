import numpy as np

from littora_ml.detector.stability import VIEWS, stratified_auc, view_scores, zone_group


def test_every_view_is_turned_back_to_the_original_orientation() -> None:
    images = np.random.default_rng(0).random((2, 3, 16, 16)).astype(np.float32)
    scores = view_scores(lambda batch: batch[:, 0] * 2, images)
    assert scores.shape == (len(VIEWS), 2, 16, 16)
    for view in scores:
        np.testing.assert_allclose(view, images[:, 0] * 2)


def test_orientation_sensitive_model_disagrees_between_views() -> None:
    images = np.ones((1, 1, 8, 8), dtype=np.float32)
    left = np.zeros((8, 8), dtype=np.float32)
    left[:, :4] = 1
    scores = view_scores(lambda batch: batch[:, 0] * left, images)
    votes = (scores[:, 0, 2, 1] >= 0.5).sum()
    assert 0 < votes < len(VIEWS)


def test_stratified_auc_ignores_pairs_across_strata() -> None:
    truth = np.array([True, False, True, False])
    score = np.array([0.9, 0.1, 0.2, 0.8])
    strata = np.array([0, 0, 1, 1])
    assert stratified_auc(truth, score, strata) == 0.5
    assert stratified_auc(truth, score, np.zeros(4, dtype=int)) == 0.75
    assert stratified_auc(truth[:2], score[:2], strata[:2]) == 1.0


def test_zone_groups_follow_the_labels_inside_and_around() -> None:
    labels = np.zeros((5, 5), dtype=np.uint8)
    mask = np.zeros((5, 5), dtype=bool)
    mask[2, 2] = True
    assert zone_group(labels, mask) == "unlabeled"
    labels[2, 3] = 5
    assert zone_group(labels, mask) == "ship"
    labels[2, 2] = 7
    assert zone_group(labels, mask) == "ship"
    labels[2, 3] = 0
    assert zone_group(labels, mask) == "other_labeled"
    labels[2, 2] = 1
    assert zone_group(labels, mask) == "debris"
