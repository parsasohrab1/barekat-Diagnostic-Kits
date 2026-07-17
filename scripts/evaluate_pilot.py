#!/usr/bin/env python3
"""ارزیابی Se/Sp با فاصله اطمینان روی دادهٔ پایلوت."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from barekat_diagnostics.core.config import get_settings
from barekat_diagnostics.ml.evaluation import evaluate_model
from barekat_diagnostics.ml.features import build_model, prepare_features


def main() -> None:
  parser = argparse.ArgumentParser(description="Pilot IVD evaluation with Wilson CI")
  parser.add_argument(
    "--data",
    default=None,
    help="Path to pilot CSV (default: settings.pilot_data_path)",
  )
  parser.add_argument("--out", default=None, help="Optional JSON output path")
  args = parser.parse_args()

  path = Path(args.data or get_settings().pilot_data_path)
  if not path.exists():
    raise SystemExit(f"Pilot file not found: {path}")

  df = pd.read_csv(path)
  X, y, _ = prepare_features(df)
  model = build_model()
  model.fit(X, y)
  result = evaluate_model(df, model=model)

  print(f"Samples: {len(df)}")
  print(f"Accuracy: {result.accuracy:.4f}")
  print(
    f"Sensitivity: {result.sensitivity.value:.4f} "
    f"[{result.sensitivity.ci_lower:.4f}, {result.sensitivity.ci_upper:.4f}]"
  )
  print(
    f"Specificity: {result.specificity.value:.4f} "
    f"[{result.specificity.ci_lower:.4f}, {result.specificity.ci_upper:.4f}]"
  )
  print(f"ROC-AUC: {result.roc_auc:.4f}")
  print(f"Confusion: TN={result.confusion_matrix.tn} FP={result.confusion_matrix.fp} "
        f"FN={result.confusion_matrix.fn} TP={result.confusion_matrix.tp}")

  if args.out:
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    print(f"Wrote {out}")


if __name__ == "__main__":
  main()
