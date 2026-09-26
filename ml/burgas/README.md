# Burgas field integration

Run from repository root with the existing scientific environment:

```sh
ml/.venv/bin/python ml/burgas/run.py
ml/.venv/bin/python -m pytest -q ml/burgas/test_burgas.py
```

Input: user-provided `data/external/burgas-floating-litter/burgas_107709.txt`, verified against SEANOE DOI 10.17882/98351. Source metadata, original download, paper and STAC responses are cached alongside it. Requires the previous DOORS CV memberships and metocean baseline predictions to verify the control. Read protocol.md before interpreting models.

Outputs: `data/processed/burgas/events.csv`, `categories.csv`, additive `macroplastic_marine_samples_with_burgas.csv`, trained temporal model and frozen experiment configuration. No changes to the original case CSV or pixel detector. `date_reported` preserves the source calendar date; UTC fields remain missing pending confirmation. Density targets remain reported all-litter values, with a separate measurement profile and quality/rights flags.

Report: `reports/burgas/burgas_analysis.html`; reproducible tables and source audit in the same directory. `notebooks/08_burgas_integration.ipynb` displays cached outputs. Rebuild only report with `run.py report`. Dependencies: previous metocean requirements plus shapely (already present in ml/.venv).

Neither source scope equivalence nor unambiguous external reuse rights is established by a successful model run. Current work is local exploratory analysis; contact the actual providers IBER-BAS (Bobchev/Berov), not IO-BAS, for the outstanding source questions documented in the report. No email sent.
