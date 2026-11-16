# Rimegepant ODT Oral/Hypersensitivity FAERS Pipeline

A four-layer, fully reproducible Python pipeline for post-marketing safety analysis of **rimegepant orally disintegrating tablets (Nurtec ODT / Vydura)**, focusing on the **oral / oropharyngeal / hypersensitivity** event spectrum.

**Layers:** FAERS disproportionality signal detection → machine-learning reporting-feature profiling → bridged network toxicology → AutoDock Vina molecular docking, plus a pre/post label-revision (notoriety-bias) natural experiment.

Companion manuscript: *Oral and hypersensitivity-spectrum adverse events of rimegepant ODT: a multi-layer pharmacovigilance analysis of FAERS 2020–2026* (under preparation; DOI will be added at submission).

> 中文说明见 [README_zh.md](README_zh.md)

---

## Why this cut?

Four independent FAERS studies repeatedly detected label-absent oral/oropharyngeal signals for rimegepant (swollen tongue, oral paraesthesia, pharyngeal swelling, tongue discomfort, excipient reaction), and FDA listed anaphylactic reaction for Nurtec ODT in the April–June 2025 quarterly review, revising the label in August 2025. Yet all published studies **stop at disproportionality lists**: none models reporting risk features, none attempts mechanistic interpretation, and none extends past 2025Q1. This pipeline fills all three gaps and adds a pre/post label-revision comparison to test notoriety bias.

## Repository layout

```
rimegepant_hypersensitivity/
├── config/
│   └── pt_sets.py              MedDRA PT case definitions (5 subsets + 3 severity tiers)
├── src/
│   ├── faers_io.py             FAERS ASCII reader ($-delimited, header compat, FDA dedup)
│   ├── stream_cache.py         Five-pass streaming aggregation engine + disk cache
│   ├── run_module1.py          Module 1: disproportionality (ROR/PRR/BCPNN/MGPS + BH-FDR)
│   ├── run_module1_stream.py   Module 1, streaming version (full-window, 25 quarters)
│   ├── extract_subset.py       Primary-suspect case subset extraction
│   ├── ml_risk.py              Module 2: ML risk profiling (LR/RF/XGB/LGBM, SHAP, TRIPOD+AI)
│   ├── network_tox.py          Module 3: bridged network toxicology (ChEMBL→STRING→Enrichr)
│   ├── dock_prep.py            Module 4: ligand/receptor prep + Vina configs
│   ├── label_change.py         Pre/post label-revision comparison (2025Q3 cut-off)
│   ├── stats_disproportionality.py  Four algorithms + BH-FDR
│   ├── download_faers.py       Direct-link FAERS ASCII downloader (resume, retry)
│   └── make_demo_data.py       Synthetic-data self-test
├── docs/
│   ├── R_crosscheck.R          R cross-validation of IC025/EBGM (PhViD/openEBGM)
│   └── docking_guide.md        Docking reproduction guide
├── results_full/               Full-window results (Tables 1–6, 7, 8, 11, 12; forest plot)
├── results_ml_real/            Module 2 outputs (model comparison, SHAP, figures)
├── results_label_change/       Pre/post label-revision outputs (Table 12, trend figure)
├── results/network_tox/        Module 3 outputs (targets, bridges, enrichment, PPI)
├── tools/                      (download AutoDock Vina here — see below)
└── data/                       FAERS ASCII extracts (git-ignored; re-download)
```

## Quick start

```bash
python -m pip install -r requirements.txt

# 1) Self-test on synthetic data (~3 min, no downloads)
python src/make_demo_data.py
python src/run_module1.py --demo
python src/ml_risk.py --demo

# 2) Real data: download FAERS/AEMS ASCII quarters 2020Q2–2026Q2
python src/download_faers.py --from 2020Q2 --to 2026Q2 --out data/raw

# 3) Run the four layers
python src/run_module1_stream.py --raw data/raw --quarters 2020Q2 ... 2026Q2
python src/ml_risk.py --raw data/raw --quarters 2020Q2 ... 2026Q2
python src/network_tox.py
python src/dock_prep.py && vina < config from src/dock_prep.py output
python src/label_change.py --cutoff 2025Q3
```

**External tool:** AutoDock Vina 1.2.5 standalone executable ([download](https://github.com/ccsb-scripps/AutoDock-Vina/releases)); place at `tools/vina.exe`.

## Method notes

- **Deduplication:** FDA-recommended rule — group by `caseid`, keep latest `fda_dt` (ties broken by `primaryid`); analysis unit = deduplicated case (N = 9,094,154 across 25 quarters).
- **Streaming:** 25 quarters exceed memory; `run_module1_stream.py` uses a five-pass scan with disk caching, cross-checked against in-memory results on 3 quarters (zero difference).
- **Positivity (pre-specified):** ROR025 > 1; PRR ≥ 2 & χ² ≥ 4; IC025 > 0; EB05 > 2; all with a ≥ 3; BH-FDR; "robust" = ≥2 algorithms.
- **Leakage control (ML):** serious outcomes and event counts excluded from features (temporally posterior / co-defined with the label).
- **Bridged network toxicology:** rimegepant is highly selective (ChEMBL anchors CALCRL/RAMP1/CALCA intersect event gene sets in only 2–3 genes), so instead of classic intersection we run BFS (≤4 hops) from anchors on the anchor ∪ event-module STRING network (score ≥ 700); bridge genes ranked by traversal counts; enrichment via Enrichr (GO-BP/KEGG, BH).
- **Docking criteria (pre-registered):** CALCRL ΔG ≤ −8 kcal/mol validates the system; off-target Δ ≥ 2 kcal/mol = no receptor-level off-target evidence; Δ < 2 phrased as "no evidence supporting" (grey zone).

## Data availability

FAERS/AEMS public ASCII quarterly extracts are freely downloadable from the FDA ([direct-link pattern](https://fis.fda.gov/content/Exports/faers_ascii_YYYYQn.zip)); no data files are redistributed here. All derived counts, tables, and figures are included under `results*/`.

## Pre-release verification

Before tagging a release or submitting a revision, run the claim auditor. It checks every quantitative statement in `docs/manuscript_en.md` against its source file and fails on any mismatch, unsupported figure, or selectively quoted value (for example citing a docking RMSD lower bound without its upper bound):

```bash
python tools/verify_claims.py --strict --write-report
```

A non-zero exit code blocks the release. The report is written to `docs/claim_audit.md`.

Literature values cannot be traced to a result file, so they are locked a second way: each cited benchmark must sit in the same sentence as its reference number and the reference entry must be complete, with reference numbering checked for continuity. Changing a quoted literature number without updating its citation therefore fails the gate as well.

What is checked: docking scores and their derived Δ values, RMSD quotation completeness, signal counts and per-PT ROR, model AUCs, pre/post family ratios, cohort and reference sizes, the TTO filtering chain, every standardised mean difference (Table 1 both reference columns plus the INDI-subset sensitivity, with each SMD recomputed from the paired percentages), and every percentage — Table 1/4/5 are recomputed from their own numerators and denominators, each percentage in the prose must either trace to a table, be recomputed from counts at runtime, or be registered in `EXTERNAL_PCT` with its source (literature values and nominal 95% CI levels only), and each `a% vs b%` pair must correspond to one row or one column of a table. A new number that has no source therefore fails the gate instead of slipping through.

### Age units

`DEMO.age` is a bare number; its unit lives in `DEMO.age_cod`. Reading the numeric field without the unit code turns `age = 5, age_cod = DEC` (50 years) into a 5-year-old. All age handling therefore goes through `src/ageutil.py`, which converts decades, months, weeks, days and hours to years and caps the result at 120. Table 1, Table 5 and both reference populations share it, and `verify_claims.py` cross-checks that the two tables report the same number of under-18 cases; a second, independent age derivation anywhere in the codebase fails that check.

The age bands are half-open (`<18`, `[18,45)`, `[45,65)`, `>=65`) because converted ages are fractional: with integer-closed bins a 44.5-year-old fell into no band at all and the four bands silently stopped summing to the number of reports with age recorded. The same arithmetic self-check — bands must sum to the recorded total — runs on every release.


## Citation / DOI

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.24134724.svg)](https://doi.org/10.5281/zenodo.24134724)

## License

MIT — see [LICENSE](LICENSE).
