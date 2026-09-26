"""Recompute metrics from saved predictions and verify masks/split without retraining."""
from pathlib import Path
import hashlib
import json

import nbformat
import numpy as np
import pandas as pd
import rasterio
from sklearn.metrics import average_precision_score


def main():
    root = Path(__file__).resolve().parents[2]
    out = root / "reports/marida"
    model_dir = root / "data/processed/marida_baseline"
    membership = pd.read_csv(out / "tables/split_membership.csv")
    assert membership.patch_index.to_list() == list(range(len(membership)))
    assert membership.patch_id.is_unique
    assert membership.groupby("group").split.nunique().max() == 1
    assert membership.groupby("scene_id").split.nunique().max() == 1
    assert membership.loc[membership.original_split == "test", "split"].eq("test").all()
    audit = pd.read_csv(out / "tables/split_integrity.csv")
    assert audit.loc[audit.version == "strict", "all_dependency_edges"].eq(0).all()
    predictions = np.load(model_dir / "heldout_predictions.npz")
    roles = membership.split.to_numpy()[predictions["patch_index"]]
    assert set(roles) == {"val", "test"}
    y = predictions["y"] == 1
    metrics = pd.read_csv(out / "tables/detector_metrics.csv")
    thresholds = json.loads((model_dir / "model_metadata.json").read_text())["thresholds"]
    for row in metrics.itertuples():
        keep = roles == row.split
        if row.confidence == "high_only":
            keep &= predictions["confidence"] == 1
        pred = predictions[row.model + "_prediction"][keep].astype(bool)
        score = predictions[row.model + "_score"][keep]
        truth = y[keep]
        threshold = next(t["threshold"] for t in thresholds if t["model"] == row.model)
        assert np.array_equal(pred, score >= threshold)
        tp = int((truth & pred).sum()); fp = int((~truth & pred).sum())
        fn = int((truth & ~pred).sum()); tn = int((~truth & ~pred).sum())
        assert (tp, fp, fn, tn) == (row.tp, row.fp, row.fn, row.tn)
        assert len(truth) == row.pixels and truth.sum() == row.positive_pixels
        actual = [tp / (tp + fp), tp / (tp + fn), 2 * tp / (2 * tp + fp + fn), tp / (tp + fp + fn),
                  average_precision_score(truth, score)]
        assert np.allclose(actual, [row.precision, row.recall, row.f1, row.iou, row.average_precision], atol=1e-12)
    examples = pd.read_csv(out / "tables/reviewed_examples.csv")
    for row in examples.itertuples():
        patch = membership.loc[membership.patch_id == row.patch_id].iloc[0]
        keep = predictions["patch_index"] == patch.patch_index
        with rasterio.open(root / row.mask_path) as mask, rasterio.open(root / "data/external/marida" / patch.image_path) as image:
            assert mask.crs == image.crs and mask.transform == image.transform and mask.shape == image.shape
            assert mask.count == 1 and mask.nodata == 255
            data = mask.read(1)
            assert np.isin(data, [0, 1, 255]).all()
            actual = data[predictions["row"][keep], predictions["col"][keep]]
            assert np.array_equal(actual, predictions["spectral_forest_prediction"][keep])
    for name in ["input_hashes", "artifact_hashes"]:
        for row in pd.read_csv(out / "tables" / f"{name}.csv").itertuples():
            with (root / row.path).open("rb") as stream:
                assert hashlib.file_digest(stream, "sha256").hexdigest() == row.sha256, row.path
    notebook = nbformat.read(root / "notebooks/02_marida_eda.ipynb", as_version=4)
    nbformat.validate(notebook)
    code = [c for c in notebook.cells if c.cell_type == "code"]
    assert [c.execution_count for c in code] == list(range(1, len(code) + 1))
    assert not [o for c in code for o in c.outputs if o.output_type == "error"]
    print(f"Verified {len(metrics)} metric rows from saved predictions, {len(examples)} georeferenced masks, split integrity, hashes and notebook.")


if __name__ == "__main__":
    main()
