"""Generate georeferenced debris scores and masks from a MARIDA-compatible patch."""
import argparse
import json
from pathlib import Path

import joblib

from models import predict_patch


def main():
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path, help="11-band ACOLITE Rayleigh reflectance in MARIDA band order")
    parser.add_argument("output_prefix", type=Path)
    parser.add_argument("--model-dir", type=Path, default=root / "data/processed/marida_baseline")
    args = parser.parse_args()
    metadata = json.loads((args.model_dir / "model_metadata.json").read_text())
    threshold = next(x["threshold"] for x in metadata["thresholds"] if x["model"] == "spectral_forest")
    model = joblib.load(args.model_dir / "spectral_forest.joblib")
    args.output_prefix.parent.mkdir(parents=True, exist_ok=True)
    predict_patch(model, threshold, args.image, args.output_prefix)
    print(f"Saved {args.output_prefix}_score.tif and {args.output_prefix}_mask.tif")
    print(metadata["prediction_status"])


if __name__ == "__main__":
    main()
