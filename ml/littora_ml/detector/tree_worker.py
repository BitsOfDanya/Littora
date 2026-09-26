from __future__ import annotations

import numpy as np


def score_tree_member(root: str, run: str, indices: np.ndarray) -> np.ndarray:
    from littora_ml.detector.baselines import score_tree_run

    return score_tree_run(root, run, indices)
