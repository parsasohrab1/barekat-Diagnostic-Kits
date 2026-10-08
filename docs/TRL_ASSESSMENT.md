# TRL assessment — barekat-Diagnostic-Kits

Assessed 2026-10-08. Scale: NASA/EU TRL. Target: **TRL 5** — technology validated in a *relevant environment*.

## Verdict

| Scope | TRL | Basis |
|---|---|---|
| Software chain (raw qPCR curve → Ct → QC → call → report) | **5 on simulated data; not yet on real data** | `docs/evidence/trl5_report.md`: 14/14 pre-set criteria pass, incl. an unseen instrument and leave-one-lot-out |
| Whole product as a diagnostic claim | **4** | No real instrument runs or clinical specimens exist in the repo |

A formal TRL 5 claim for a diagnostic needs the open items below. The simulation shows the *software* is sound under stated assumptions; it says nothing about assay biology.

## Defects found and fixed during the audit

1. **No-template curves were read as strong positives.** `estimate_ct` min-max scaled each curve, so noise became Ct = 2.0. Replaced with baseline-subtracted threshold detection and an explicit "not amplified" result (`pipeline/feature_extraction.py`).
2. **Production never used the ML model.** The registry pointed at files that don't exist, so every sample silently fell back to `Ct < 30`. That rule detects 54 % of true positives on an unseen instrument and 0 % at ≤10 copies.
3. **Feature mismatch was silently zero-filled.** Models expect `Ct_Value`, `Feature_1…12`; the pipeline emits lowercase keys, and `features.get(c, 0.0)` hid it. Now case-insensitive and raises `FeatureMismatchError` (sklearn and ONNX paths); the service logs the fallback.
4. **Registry `dataset_hash` hashed only row count + positives.** Now a content hash.
5. **Pilot evaluation was in-sample.** `evaluate_pilot.py` now reports out-of-fold results and warns when labels are perfectly Ct-separable.

Regression tests: `tests/test_curve_validation.py`.

## Open items (cannot be closed in software)

| # | Item | Why it blocks a real TRL 5 |
|---|---|---|
| 1 | **Real data.** `data/pilot/pilot_qpcr.csv` is tagged `pilot_lab_anonymized` but is perfectly separable at Ct 30 (neg ≥ 30.2, pos ≤ 29.99) and nothing documents its origin. Treat it as synthetic unless its lab provenance can be shown. | Relevant-environment validation needs independent ground truth (e.g. reference-method results) |
| 2 | Real instrument exports (QuantStudio/CFX/LightCycler/Rotor-Gene RDML/CSV) run through `importers/` with a reference method comparison | Simulator ≠ optics, chemistry, inhibition in real matrices |
| 3 | Integrated stack run (Postgres + Redis + MinIO via `docker compose`) with the API under load | Tests use SQLite/mocks; Docker daemon was not running in this session |
| 4 | `ml/evaluation.py::evaluate_model` overall metrics (used by registry quality gates) are in-sample | Promotion gate can pass on resubstitution numbers |
| 5 | Committed `registry.json` lists `v3` with placeholder hashes (`abc`, `def`) and a missing file; test suite rewrites this tracked file | Misleading traceability record |
| 6 | Curve model is not in the real registry; run `train_curve_classifier` on validated data first | Harness used a sandbox registry |
| 7 | Edge latency on a real low-power device (harness p95 43 ms is this PC) | |
| 8 | Ruff reports 327 findings; CI lint job would fail | |

## Known limits of the evidence

- Truth is simulated template count; late weak amplification in artifact wells vs. 1–2 real molecules is a simulator assumption. Detection at 1 copy is 0.60 (n=10), 2 copies 0.875 (n=16) — reported, not gated.
- Two criteria pass narrowly: Ct bias 0.272 (limit 0.30), stress sensitivity 0.905 (limit 0.90).
- Criteria were written by the implementer, not an independent reviewer.

## Path to a defensible TRL 5

1. Provide provenance for the pilot file or replace it with ≥ 100 reference-confirmed specimens (≥ 30 positives incl. near-LoD) run on ≥ 2 instruments and ≥ 2 reagent lots.
2. Run `scripts/trl5_validation.py`-style criteria on that data (swap the simulator for the importer) — same acceptance table.
3. Close items 3–6; get criteria reviewed by someone independent.

Reproduce: `python scripts/trl5_validation.py` (≈1 min, writes `docs/evidence/`).
