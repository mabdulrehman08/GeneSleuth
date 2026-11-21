# STATUS_A (Agent A: data + proof)

Updated: Sat 13:45 ET

## Done (on main)
- Shared contract, research briefs, WSL bcftools helper (genesleuth/data/bcf.py).
- Fakes: genesleuth/data/{fakes,api}.py (FAKE_MODE=1 builds a fake SCN1A splice case) and genesleuth/lookups/{fakes,api}.py (six lookups).
- assets/ first push: panel_regions.tsv, mane_features.tsv.gz (24 KB).
- Table builders: scripts/data_{panel,hpo,clinvar_table}.py.
- Bench: metrics (Wilson CIs), report/chart/failures, fixed_recipe baseline (tests included).

## In progress
- A1: background genome (NA12878 chunked regions), gnomAD rarity filter, suspects json, probes/A/REPORT.md.
- A2: real lookups, DATA_SOURCES.md, DESIGN_DATA.md, licence verification.
- A3: ClinVar candidates, splits, phenotypes, Hydrogen letters (scans), real build_case, scripts/data_setup.py.
- A4: bench/run.py, controls, BENCHMARK.md.

## Blocked
- none

## Not yet on main (due 2:15 PM)
- assets/: suspects, ClinVar panel table, HPO subset, candidates/splits/truth, letter PDFs, scripts/data_setup.py.
- docs/status_a/a1.md and probes/A/REPORT.md.

## HUMAN TO DO
- none yet (DEV report approval and TEST run go-ahead come later).
