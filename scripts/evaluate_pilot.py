#!/usr/bin/env python3
"""Evaluate Se/Sp with Wilson CI on pilot data (out-of-fold, not resubstitution)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold, StratifiedKFold, cross_val_predict

from barekat_diagnostics.core.config import get_settings
from barekat_diagnostics.ml.evaluation import _metric_with_ci
from barekat_diagnostics.ml.features import build_model, prepare_features


def main() -> None:
  parser = argparse.ArgumentParser(description="Pilot IVD evaluation with Wilson CI (out-of-fold)")
  parser.add_argument("--data", default=None, help="Path to pilot CSV (default: settings.pilot_data_path)")
  parser.add_argument("--out", default=None, help="Optional JSON output path")
  args = parser.parse_args()

  path = Path(args.data or get_settings().pilot_data_path)
  if not path.exists():
    raise SystemExit(f"Pilot file not found: {path}")

  df = pd.read_csv(path)
  X, y, _ = prepare_features(df)

  # Every prediction comes from a model that never saw that sample (or its instrument).
  if "Lab_Device" in df.columns and df["Lab_Device"].nunique() > 1:
    cv = GroupKFold(n_splits=min(5, df["Lab_Device"].nunique()))
    pred = cross_val_predict(build_model(), X, y, cv=cv, groups=df["Lab_Device"].values)
    scheme = "leave-instrument-out GroupKFold"
  else:
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    pred = cross_val_predict(build_model(), X, y, cv=cv)
    scheme = "stratified 5-fold"

  tp = int(((y == 1) & (pred == 1)).sum())
  fn = int(((y == 1) & (pred == 0)).sum())
  tn = int(((y == 0) & (pred == 0)).sum())
  fp = int(((y == 0) & (pred == 1)).sum())
  se, sp = _metric_with_ci(tp, tp + fn), _metric_with_ci(tn, tn + fp)

  print(f"Samples: {len(df)}  scheme: {scheme}")
  print(f"Sensitivity: {se.value:.4f} [{se.ci_lower:.4f}, {se.ci_upper:.4f}]")
  print(f"Specificity: {sp.value:.4f} [{sp.ci_lower:.4f}, {sp.ci_upper:.4f}]")
  print(f"Confusion: TN={tn} FP={fp} FN={fn} TP={tp}")

  ct = df.get("Ct_Value")
  if ct is not None and ((df.loc[df.True_Status == 1, "Ct_Value"].max() < df.loc[df.True_Status == 0, "Ct_Value"].min())):
    print(
      "WARNING: labels are perfectly separable by a Ct cutoff, i.e. they appear derived from "
      "Ct. This file cannot serve as independent ground truth; use scripts/trl5_validation.py "
      "for simulated validation and real lab runs for TRL 5 evidence."
    )

  if args.out:
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
      json.dumps({"scheme": scheme, "n": len(df), "sensitivity": se.model_dump(),
                  "specificity": sp.model_dump(),
                  "confusion": {"tn": tn, "fp": fp, "fn": fn, "tp": tp}}, indent=2),
      encoding="utf-8",
    )
    print(f"Wrote {out}")


if __name__ == "__main__":
  main()
