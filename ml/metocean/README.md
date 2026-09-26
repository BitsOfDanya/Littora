# Environmental covariates

Research pipeline: ERA5 wind + ERA5-Ocean waves + HYCOM currents; SMOC for DOORS 2024.
See protocol.md for fixed hypotheses, joins, imputation, groups and model comparisons.

From repository root:

```sh
ml/.venv/bin/python ml/metocean/acquire.py prepare
ml/.venv/bin/python ml/metocean/acquire.py download
ml/.venv/bin/python ml/metocean/acquire.py extract
ml/.venv/bin/python ml/metocean/train.py
ml/.venv/bin/python ml/metocean/report.py
ml/.venv/bin/python -m pytest -q ml/metocean/test_contracts.py
```

Download is cached by full request; rerun to retry failures. Four concurrent requests, bounded retries, no authentication. Metadata contains URLs, SHA256 and retrieval UTC. Original data and models are not overwritten. NetCDF CF scale/fill decoding is mandatory; HYCOM point CSV can omit packing metadata.

Outputs: `data/processed/metocean/features.csv` (508 patch/event joins), `macroplastic_marine_samples_metocean.csv` (935 source rows enriched by event ID), compressed sampled time series, six fixed classifier variants and frozen validation thresholds. All environmental missingness is retained in CSVs. Context-only date records have daily means, never fabricated instants. RF uses train-only median imputation plus missing indicators.

Read `reports/metocean/metocean_eda.html`, `conclusions.md`, and tables. `notebooks/07_metocean_eda.ipynb` displays cached EDA and scores without implicit downloads/retraining. Existing environment dependencies plus xarray/netCDF4/scipy/markdown/nbformat; exact runtime versions are recorded alongside output.

These are retrospective contextual variables at model grid resolution. Field concentration CV and pixel classification are distinct tasks. No new field record is automatically a pixel label. No production deployment or inference on unlabelled Black Sea holdout is performed.
