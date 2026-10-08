# TRL-5 validation report (simulated relevant environment)

Generated: 2026-10-07T20:47:26+00:00 | Python 3.10.1 | runtime 93.6 s

> **Data provenance:** SIMULATED (barekat_diagnostics.data.curves). No patient or instrument data.
> These results show the software chain behaves correctly under the simulator's stated assumptions. They are **not** clinical performance claims.

**Overall: PASS**

## Acceptance criteria

| ID | Observed | Criterion | Result |
|---|---|---|---|
| A1_ct_bias | 0.272 | |bias| <= 0.3 cycles | PASS |
| A1_ct_sd | 0.639 | SD <= 0.8 cycles | PASS |
| A2_clean_ntc | 0.00333 | <= 0.005 of template-free wells called amplified | PASS |
| A3_heldout_se_ci_lower | 0.9758 | Wilson 95% lower bound >= 0.9 | PASS |
| A3_heldout_sp_ci_lower | 0.9933 | Wilson 95% lower bound >= 0.95 | PASS |
| A4_lot_se_worst | 0.9869 | every held-out lot >= 0.9 | PASS |
| A4_lot_sp_worst | 0.9932 | every held-out lot >= 0.95 | PASS |
| A5_sens_ge3_copies | 0.9945 | >= 0.9 when >=3 molecules present (n=728) | PASS |
| A6_stress_se | 0.9048 | >= 0.9 at 2x noise/drift | PASS |
| A6_stress_sp | 1.0 | >= 0.95 at 2x noise/drift | PASS |
| A7_e2e_agreement | 1.0 | pipeline output == direct model output | PASS |
| A7_e2e_no_fallback | 0 | no sample served by rule-based fallback | PASS |
| A8_latency_p95_ms | 97.8 | p95 <= 100.0 ms | PASS |
| A9_reproducible | True | re-run gives identical features and predictions | PASS |

## Held-out instrument (RotorGene-Q, never seen in training)

| Classifier | Sensitivity [95% CI] | Specificity [95% CI] | FN | FP |
|---|---|---|---|---|
| Curve model (this work) | 0.9867 [0.9758, 0.9928] | 0.9988 [0.9933, 0.9998] | 10 | 1 |
| Previous production fallback (Ct < 30) | 0.5424 [0.5068, 0.5777] | 1.0 [0.9955, 1.0] | 345 | 0 |

## Detection by actual template copies (held-out instrument)

| Copies | n | Detection rate | 95% CI |
|---|---|---|---|
| 1-1 | 10 | 0.6 | [0.313, 0.832] |
| 2-2 | 16 | 0.875 | [0.64, 0.965] |
| 3-5 | 57 | 0.947 | [0.856, 0.982] |
| 6-10 | 75 | 0.987 | [0.928, 0.998] |
| 11-100 | 120 | 1.0 | [0.969, 1.0] |
| 101-inf | 476 | 1.0 | [0.992, 1.0] |

## Leave-one-lot-out

| Held-out lot | n | Se | Sp |
|---|---|---|---|
| LOT-A | 766 | 0.9969 | 0.9932 |
| LOT-B | 802 | 0.9945 | 0.9977 |
| LOT-C | 832 | 0.9869 | 1.0 |

## Other measurements

- Ct accuracy (>=100 copies, n=1147): bias 0.272, SD 0.639, max |err| 4.269 cycles
- Clean no-template wells called amplified: 0.00333 (n=1200)
- Stress (2x noise, 2x drift): Se 0.9048, Sp 1.0
- End-to-end: {'n': 250, 'agreement_with_direct_model': 1.0, 'rule_based_fallbacks': 0, 'model_version': 'curve-v1'}
- Latency (ms): {'p50': 82.77, 'p95': 97.8, 'max': 425.51, 'note': 'includes feature extraction, QC, model, report build; model unpickled once; this host, not a target device'}
- ONNX edge: {'n': 200, 'parity_with_sklearn': 1.0, 'model_latency_p95_ms': 0.208}
- Reproducibility: {'feature_hash': '5f927acb021f9ec4', 'identical_rerun': True}

Reproduce: `python scripts/trl5_validation.py`
