#!/usr/bin/env python3
"""
TRL-5 validation harness: raw qPCR curve -> Ct -> classification, in a simulated relevant
environment, against acceptance criteria that are fixed in this file BEFORE results are read.

Design rules that make the result meaningful:
  * truth = simulated template molecules, never a Ct cutoff (no label leakage);
  * model is fitted ONLY on instruments in TRAIN_DEVICES; the held-out instrument is unseen;
  * lot-wise leave-one-out checks reagent-lot transfer;
  * end-to-end check runs the real pipeline + real DiagnosticPredictor + real registry.

Outputs docs/evidence/trl5_report.json and docs/evidence/trl5_report.md
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = ROOT / "docs" / "evidence"

# ---------------------------------------------------------------- acceptance criteria
CRITERIA = {
  "A1_ct_bias_max": 0.30,  # |mean(Ct_est - Ct_true)| cycles, >=100 copies
  "A1_ct_sd_max": 0.80,  # SD of Ct error, cycles
  "A2_clean_ntc_amplified_max": 0.005,  # clean template-free wells called amplified
  "A3_heldout_se_ci_lower_min": 0.90,  # held-out instrument, Wilson 95% lower bound
  "A3_heldout_sp_ci_lower_min": 0.95,
  "A4_lot_se_min": 0.90,  # leave-one-lot-out, every lot (point estimate)
  "A4_lot_sp_min": 0.95,
  "A5_sens_ge3_copies_min": 0.90,  # sensitivity where >=3 template molecules are present
  "A6_stress_se_min": 0.90,  # 2x read noise on held-out instrument
  "A6_stress_sp_min": 0.95,
  "A7_e2e_agreement_min": 1.0,  # pipeline result == direct model result
  "A7_e2e_fallback_max": 0,  # samples that fell back to the rule-based path
  "A8_latency_p95_ms_max": 100.0,  # curve -> report, single-thread CPU
  "A9_reproducible": True,  # identical outputs on re-run
}
SEED_TRAIN, SEED_HELDOUT, SEED_LOT, SEED_STRESS = 101, 202, 303, 404


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float, float]:
  if n == 0:
    return 0.0, 0.0, 0.0
  p = k / n
  d = 1 + z * z / n
  c = p + z * z / (2 * n)
  m = z * np.sqrt((p * (1 - p) + z * z / (4 * n)) / n)
  return float(p), float(max(0.0, (c - m) / d)), float(min(1.0, (c + m) / d))


def se_sp(y: np.ndarray, pred: np.ndarray) -> dict:
  tp = int(((y == 1) & (pred == 1)).sum())
  fn = int(((y == 1) & (pred == 0)).sum())
  tn = int(((y == 0) & (pred == 0)).sum())
  fp = int(((y == 0) & (pred == 1)).sum())
  se, se_lo, se_hi = wilson(tp, tp + fn)
  sp, sp_lo, sp_hi = wilson(tn, tn + fp)
  return {
    "n": int(len(y)), "tp": tp, "fn": fn, "tn": tn, "fp": fp,
    "sensitivity": round(se, 4), "se_ci": [round(se_lo, 4), round(se_hi, 4)],
    "specificity": round(sp, 4), "sp_ci": [round(sp_lo, 4), round(sp_hi, 4)],
  }


def check(name: str, observed, ok: bool, criterion: str) -> dict:
  return {"id": name, "observed": observed, "criterion": criterion, "pass": bool(ok)}


def predict_labels(model, feats: pd.DataFrame, cols: list[str]) -> np.ndarray:
  return model.predict(feats[cols].to_numpy())


def main() -> int:
  ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
  ap.add_argument("--train-n", type=int, default=2400)
  ap.add_argument("--test-n", type=int, default=1600)
  ap.add_argument("--e2e-n", type=int, default=250)
  ap.add_argument("--out-dir", default=str(EVIDENCE_DIR))
  args = ap.parse_args()

  sandbox = tempfile.mkdtemp(prefix="trl5_models_")
  os.environ["MODEL_PATH"] = sandbox  # never touch the repository's own registry
  os.environ["AUTH_ENABLED"] = "false"

  from barekat_diagnostics.core.config import get_settings

  get_settings.cache_clear()

  from barekat_diagnostics.data.curves import (
    DEVICES, HELDOUT_DEVICE, LOTS, TRAIN_DEVICES, DeviceProfile, generate_curve_dataset,
  )
  from barekat_diagnostics.ml.classifier import DiagnosticPredictor
  from barekat_diagnostics.ml.curve_model import (
    CURVE_FEATURES, build_curve_model, curves_to_features, train_curve_classifier,
  )
  from barekat_diagnostics.ml.registry import ModelRegistry
  from barekat_diagnostics.pipeline.feature_extraction import analyze_curve
  from barekat_diagnostics.pipeline.runner import process_sample
  from barekat_diagnostics.schemas import SampleInput

  t_start = time.time()
  results: list[dict] = []
  detail: dict = {}

  # ------------------------------------------------------------ data (all simulated)
  train_raw = generate_curve_dataset(args.train_n, seed=SEED_TRAIN, devices=TRAIN_DEVICES)
  held_raw = generate_curve_dataset(args.test_n, seed=SEED_HELDOUT, devices=(HELDOUT_DEVICE,))
  train = curves_to_features(train_raw)
  held = curves_to_features(held_raw)
  detail["datasets"] = {
    "train": {"n": len(train), "devices": list(TRAIN_DEVICES), "seed": SEED_TRAIN,
              "prevalence": round(float(train.True_Status.mean()), 3)},
    "heldout": {"n": len(held), "device": HELDOUT_DEVICE, "seed": SEED_HELDOUT,
                "prevalence": round(float(held.True_Status.mean()), 3)},
  }

  # ------------------------------------------------------------ A1 Ct accuracy
  pos_hi = pd.concat([train, held])
  pos_hi = pos_hi[(pos_hi.Actual_Copies >= 100) & (pos_hi.amplified == 1)]
  err = pos_hi.ct_value - pos_hi.True_Ct
  bias, sd = float(err.mean()), float(err.std())
  detail["ct_accuracy"] = {"n": int(len(err)), "bias": round(bias, 3), "sd": round(sd, 3),
                           "max_abs_error": round(float(err.abs().max()), 3)}
  results.append(check("A1_ct_bias", round(bias, 3), abs(bias) <= CRITERIA["A1_ct_bias_max"],
                       f"|bias| <= {CRITERIA['A1_ct_bias_max']} cycles"))
  results.append(check("A1_ct_sd", round(sd, 3), sd <= CRITERIA["A1_ct_sd_max"],
                       f"SD <= {CRITERIA['A1_ct_sd_max']} cycles"))

  # ------------------------------------------------------------ A2 clean NTC integrity
  rng = np.random.default_rng(SEED_STRESS)
  ntc_raw = generate_curve_dataset(1200, seed=SEED_STRESS, devices=tuple(DEVICES),
                                   prevalence=0.0, artifact_rate=0.0)
  ntc = curves_to_features(ntc_raw)
  ntc_rate = float(ntc.amplified.mean())
  detail["clean_ntc"] = {"n": len(ntc), "amplified_rate": round(ntc_rate, 5),
                         "min_ct_reported": float(ntc.ct_value.min())}
  results.append(check("A2_clean_ntc", round(ntc_rate, 5),
                       ntc_rate <= CRITERIA["A2_clean_ntc_amplified_max"],
                       f"<= {CRITERIA['A2_clean_ntc_amplified_max']:.3f} of template-free wells called amplified"))

  # ------------------------------------------------------------ fit candidate model
  model = build_curve_model().fit(train[CURVE_FEATURES].to_numpy(), train.True_Status.to_numpy())

  # ------------------------------------------------------------ A3 held-out instrument
  pred_held = predict_labels(model, held, CURVE_FEATURES)
  m = se_sp(held.True_Status.values, pred_held)
  detail["heldout_instrument"] = m
  results.append(check("A3_heldout_se_ci_lower", m["se_ci"][0],
                       m["se_ci"][0] >= CRITERIA["A3_heldout_se_ci_lower_min"],
                       f"Wilson 95% lower bound >= {CRITERIA['A3_heldout_se_ci_lower_min']}"))
  results.append(check("A3_heldout_sp_ci_lower", m["sp_ci"][0],
                       m["sp_ci"][0] >= CRITERIA["A3_heldout_sp_ci_lower_min"],
                       f"Wilson 95% lower bound >= {CRITERIA['A3_heldout_sp_ci_lower_min']}"))

  # comparison: the pre-existing production fallback (Ct < 30), same held-out data
  legacy = (held.ct_value < 30).astype(int).values
  detail["baseline_legacy_ct30_rule"] = se_sp(held.True_Status.values, legacy)

  # ------------------------------------------------------------ A4 leave-one-lot-out
  lot_raw = generate_curve_dataset(args.train_n, seed=SEED_LOT, devices=tuple(DEVICES))
  lot_df = curves_to_features(lot_raw)
  lot_rows = {}
  for lot in LOTS:
    tr, te = lot_df[lot_df.Kit_Lot != lot], lot_df[lot_df.Kit_Lot == lot]
    mdl = build_curve_model().fit(tr[CURVE_FEATURES].to_numpy(), tr.True_Status.to_numpy())
    lot_rows[lot] = se_sp(te.True_Status.values, predict_labels(mdl, te, CURVE_FEATURES))
  detail["leave_one_lot_out"] = lot_rows
  worst_se = min(v["sensitivity"] for v in lot_rows.values())
  worst_sp = min(v["specificity"] for v in lot_rows.values())
  results.append(check("A4_lot_se_worst", worst_se, worst_se >= CRITERIA["A4_lot_se_min"],
                       f"every held-out lot >= {CRITERIA['A4_lot_se_min']}"))
  results.append(check("A4_lot_sp_worst", worst_sp, worst_sp >= CRITERIA["A4_lot_sp_min"],
                       f"every held-out lot >= {CRITERIA['A4_lot_sp_min']}"))

  # ------------------------------------------------------------ A5 analytical sensitivity
  pos = held[held.True_Status == 1].copy()
  pos["hit"] = pred_held[pos.index]
  bins = [(1, 1), (2, 2), (3, 5), (6, 10), (11, 100), (101, 10**9)]
  by_copies = {}
  for lo, hi in bins:
    sel = pos[(pos.Actual_Copies >= lo) & (pos.Actual_Copies <= hi)]
    if len(sel):
      p, a, b = wilson(int(sel.hit.sum()), len(sel))
      by_copies[f"{lo}-{hi if hi < 10**9 else 'inf'}"] = {
        "n": int(len(sel)), "detection_rate": round(p, 3), "ci": [round(a, 3), round(b, 3)]}
  detail["detection_by_actual_copies"] = by_copies
  ge3 = pos[pos.Actual_Copies >= 3]
  ge3_rate = float(ge3.hit.mean())
  results.append(check("A5_sens_ge3_copies", round(ge3_rate, 4),
                       ge3_rate >= CRITERIA["A5_sens_ge3_copies_min"],
                       f">= {CRITERIA['A5_sens_ge3_copies_min']} when >=3 molecules present (n={len(ge3)})"))
  detail["note_1_2_copies"] = ("1-2 molecule detection is reported but not gated: with so little "
                               "template the curve is often indistinguishable from late artifacts.")

  # ------------------------------------------------------------ A6 stress: 2x read noise
  noisy = dict(DEVICES)
  base = DEVICES[HELDOUT_DEVICE]
  noisy[HELDOUT_DEVICE] = DeviceProfile(base.name, base.gain, base.offset, base.noise_sd * 2.0,
                                        base.ct_shift, base.drift * 2.0)
  import barekat_diagnostics.data.curves as curves_mod

  original = dict(curves_mod.DEVICES)
  try:
    curves_mod.DEVICES.update(noisy)
    stress_raw = generate_curve_dataset(args.test_n, seed=SEED_STRESS + 1, devices=(HELDOUT_DEVICE,))
  finally:
    curves_mod.DEVICES.clear()
    curves_mod.DEVICES.update(original)
  stress = curves_to_features(stress_raw)
  sm = se_sp(stress.True_Status.values, predict_labels(model, stress, CURVE_FEATURES))
  detail["stress_2x_noise_2x_drift"] = sm
  results.append(check("A6_stress_se", sm["sensitivity"], sm["sensitivity"] >= CRITERIA["A6_stress_se_min"],
                       f">= {CRITERIA['A6_stress_se_min']} at 2x noise/drift"))
  results.append(check("A6_stress_sp", sm["specificity"], sm["specificity"] >= CRITERIA["A6_stress_sp_min"],
                       f">= {CRITERIA['A6_stress_sp_min']} at 2x noise/drift"))

  # ------------------------------------------------------------ A7 end-to-end through real stack
  metrics_for_registry = {"sensitivity": m["sensitivity"], "specificity": m["specificity"],
                          "roc_auc": 0.0, "evidence": "scripts/trl5_validation.py (simulated)"}
  train_curve_classifier(train, version="curve-v1", metrics=metrics_for_registry)
  reg = ModelRegistry.load()
  reg.promote("curve-v1", force=True)
  predictor = DiagnosticPredictor()
  assert predictor.registry.production_version == "curve-v1"

  def predict_fn(features):
    return predictor.predict(features)  # no fallback: any failure must surface

  e2e = held_raw.iloc[: args.e2e_n]
  agree = fallback = 0
  latencies = []
  direct = predict_labels(model, held.iloc[: args.e2e_n], CURVE_FEATURES)
  for i, row in enumerate(e2e.itertuples()):
    sample = SampleInput(sample_id=row.Sample_ID, kit_type="qpcr", curve_data=list(row.Curve))
    t0 = time.perf_counter()
    report = process_sample(sample, predict_fn)
    latencies.append((time.perf_counter() - t0) * 1000)
    if report.model_version == "rule-based":
      fallback += 1
    got = 1 if report.result == "positive" else 0 if report.result == "negative" else -1
    agree += int(got == int(direct[i]))
  agreement = agree / len(e2e)
  detail["end_to_end"] = {"n": len(e2e), "agreement_with_direct_model": round(agreement, 4),
                          "rule_based_fallbacks": fallback, "model_version": "curve-v1"}
  results.append(check("A7_e2e_agreement", round(agreement, 4), agreement >= CRITERIA["A7_e2e_agreement_min"],
                       "pipeline output == direct model output"))
  results.append(check("A7_e2e_no_fallback", fallback, fallback <= CRITERIA["A7_e2e_fallback_max"],
                       "no sample served by rule-based fallback"))

  # ------------------------------------------------------------ A8 latency
  p50, p95 = float(np.percentile(latencies, 50)), float(np.percentile(latencies, 95))
  detail["latency_ms"] = {"p50": round(p50, 2), "p95": round(p95, 2), "max": round(max(latencies), 2),
                          "note": "includes feature extraction, QC, model, report build; "
                                  "model unpickled once; this host, not a target device"}
  results.append(check("A8_latency_p95_ms", round(p95, 2), p95 <= CRITERIA["A8_latency_p95_ms_max"],
                       f"p95 <= {CRITERIA['A8_latency_p95_ms_max']} ms"))

  # ------------------------------------------------------------ edge: ONNX parity (informational)
  # Run in a subprocess: a native crash in the onnx stack must not abort the validation run.
  n_onnx = min(200, len(held))
  feats_json = Path(sandbox) / "onnx_features.json"
  feats_json.write_text(json.dumps({
    "rows": [{c: float(held.iloc[i][c]) for c in CURVE_FEATURES} for i in range(n_onnx)],
    "expected": [int(x) for x in pred_held[:n_onnx]],
  }), encoding="utf-8")
  child = (
    "import json,sys,numpy as np;from pathlib import Path;"
    "from barekat_diagnostics.ml.onnx_export import EdgeOnnxPredictor,export_sklearn_to_onnx;"
    "sb=Path(sys.argv[1]);d=json.loads((sb/'onnx_features.json').read_text());"
    "o=export_sklearn_to_onnx(sb/'diagnostic_classifier_curve-v1.pkl');p=EdgeOnnxPredictor(o);"
    "r=[p.predict(f) for f in d['rows']];"
    "same=sum((1 if x[0]=='positive' else 0)==e for x,e in zip(r,d['expected']));"
    "print(json.dumps({'n':len(r),'parity_with_sklearn':round(same/len(r),4),"
    "'model_latency_p95_ms':round(float(np.percentile([x[3] for x in r],95)),3)}))"
  )
  try:
    proc = subprocess.run([sys.executable, "-c", child, sandbox], capture_output=True, text=True,
                          timeout=180, env=dict(os.environ))
    if proc.returncode == 0:
      detail["onnx_edge"] = json.loads(proc.stdout.strip().splitlines()[-1])
    else:
      detail["onnx_edge"] = {"skipped": f"onnx subprocess exited {proc.returncode} "
                                        "(native crash importing skl2onnx/onnxruntime in this "
                                        "environment); edge parity NOT verified"}
  except Exception as exc:
    detail["onnx_edge"] = {"skipped": f"{type(exc).__name__}: {exc}"}

  # ------------------------------------------------------------ A9 reproducibility
  again = curves_to_features(generate_curve_dataset(args.train_n, seed=SEED_TRAIN, devices=TRAIN_DEVICES))
  h1 = hashlib.sha256(pd.util.hash_pandas_object(train[CURVE_FEATURES], index=False).values.tobytes()).hexdigest()
  h2 = hashlib.sha256(pd.util.hash_pandas_object(again[CURVE_FEATURES], index=False).values.tobytes()).hexdigest()
  pred2 = predict_labels(build_curve_model().fit(again[CURVE_FEATURES].to_numpy(), again.True_Status.to_numpy()), held, CURVE_FEATURES)
  reproducible = (h1 == h2) and bool((pred2 == pred_held).all())
  detail["reproducibility"] = {"feature_hash": h1[:16], "identical_rerun": reproducible}
  results.append(check("A9_reproducible", reproducible, reproducible is CRITERIA["A9_reproducible"],
                       "re-run gives identical features and predictions"))

  # ------------------------------------------------------------ verdict + report
  passed = all(r["pass"] for r in results)
  report = {
    "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "environment": {"python": platform.python_version(), "platform": platform.platform(),
                    "numpy": np.__version__, "pandas": pd.__version__,
                    "runtime_seconds": round(time.time() - t_start, 1)},
    "data_provenance": "SIMULATED (barekat_diagnostics.data.curves). No patient or instrument data.",
    "criteria": CRITERIA,
    "results": results,
    "overall_pass": passed,
    "detail": detail,
  }
  out = Path(args.out_dir)
  out.mkdir(parents=True, exist_ok=True)
  (out / "trl5_report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
  (out / "trl5_report.md").write_text(render_markdown(report), encoding="utf-8")

  for r in results:
    print(f"[{'PASS' if r['pass'] else 'FAIL'}] {r['id']:28s} observed={r['observed']}  ({r['criterion']})")
  print(f"\nOVERALL (simulated relevant environment): {'PASS' if passed else 'FAIL'}")
  print(f"Wrote {out / 'trl5_report.md'}")
  return 0 if passed else 1


def render_markdown(r: dict) -> str:
  d = r["detail"]
  L = [
    "# TRL-5 validation report (simulated relevant environment)",
    "",
    f"Generated: {r['generated_at']} | Python {r['environment']['python']} | "
    f"runtime {r['environment']['runtime_seconds']} s",
    "",
    f"> **Data provenance:** {r['data_provenance']}",
    "> These results show the software chain behaves correctly under the simulator's stated "
    "assumptions. They are **not** clinical performance claims.",
    "",
    f"**Overall: {'PASS' if r['overall_pass'] else 'FAIL'}**",
    "",
    "## Acceptance criteria",
    "",
    "| ID | Observed | Criterion | Result |",
    "|---|---|---|---|",
  ]
  for x in r["results"]:
    L.append(f"| {x['id']} | {x['observed']} | {x['criterion']} | {'PASS' if x['pass'] else 'FAIL'} |")
  h = d["heldout_instrument"]
  b = d["baseline_legacy_ct30_rule"]
  L += [
    "",
    f"## Held-out instrument ({d['datasets']['heldout']['device']}, never seen in training)",
    "",
    "| Classifier | Sensitivity [95% CI] | Specificity [95% CI] | FN | FP |",
    "|---|---|---|---|---|",
    f"| Curve model (this work) | {h['sensitivity']} {h['se_ci']} | {h['specificity']} {h['sp_ci']} | {h['fn']} | {h['fp']} |",
    f"| Previous production fallback (Ct < 30) | {b['sensitivity']} {b['se_ci']} | {b['specificity']} {b['sp_ci']} | {b['fn']} | {b['fp']} |",
    "",
    "## Detection by actual template copies (held-out instrument)",
    "",
    "| Copies | n | Detection rate | 95% CI |",
    "|---|---|---|---|",
  ]
  for k, v in d["detection_by_actual_copies"].items():
    L.append(f"| {k} | {v['n']} | {v['detection_rate']} | {v['ci']} |")
  L += ["", "## Leave-one-lot-out", "", "| Held-out lot | n | Se | Sp |", "|---|---|---|---|"]
  for k, v in d["leave_one_lot_out"].items():
    L.append(f"| {k} | {v['n']} | {v['sensitivity']} | {v['specificity']} |")
  L += [
    "",
    "## Other measurements",
    "",
    f"- Ct accuracy (>=100 copies, n={d['ct_accuracy']['n']}): bias {d['ct_accuracy']['bias']}, "
    f"SD {d['ct_accuracy']['sd']}, max |err| {d['ct_accuracy']['max_abs_error']} cycles",
    f"- Clean no-template wells called amplified: {d['clean_ntc']['amplified_rate']} (n={d['clean_ntc']['n']})",
    f"- Stress (2x noise, 2x drift): Se {d['stress_2x_noise_2x_drift']['sensitivity']}, "
    f"Sp {d['stress_2x_noise_2x_drift']['specificity']}",
    f"- End-to-end: {d['end_to_end']}",
    f"- Latency (ms): {d['latency_ms']}",
    f"- ONNX edge: {d['onnx_edge']}",
    f"- Reproducibility: {d['reproducibility']}",
    "",
    "Reproduce: `python scripts/trl5_validation.py`",
    "",
  ]
  return "\n".join(L)


if __name__ == "__main__":
  sys.exit(main())
