#!/usr/bin/env python3
"""ارزیابی IVD مدل تشخیصی."""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from barekat_diagnostics.ml.evaluation import evaluate_model
from barekat_diagnostics.ml.features import build_model, prepare_features


def main() -> None:
  if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

  parser = argparse.ArgumentParser(description="ارزیابی IVD مدل")
  parser.add_argument("--data", default="data/raw/synthetic.csv")
  parser.add_argument("--output", default=None, help="مسیر JSON خروجی")
  args = parser.parse_args()

  data_path = Path(args.data)
  if not data_path.exists():
    raise SystemExit(f"فایل داده یافت نشد: {data_path}")

  df = pd.read_csv(data_path)
  X, y, _ = prepare_features(df)
  model = build_model()
  model.fit(X, y)
  result = evaluate_model(df, model=model)

  print("ارزیابی IVD:")
  print(f"  Accuracy:    {result.accuracy:.3f}")
  print(f"  Sensitivity: {result.sensitivity.value:.3f} [{result.sensitivity.ci_lower:.3f}, {result.sensitivity.ci_upper:.3f}]")
  print(f"  Specificity: {result.specificity.value:.3f} [{result.specificity.ci_lower:.3f}, {result.specificity.ci_upper:.3f}]")
  print(f"  PPV:         {result.ppv.value:.3f}")
  print(f"  NPV:         {result.npv.value:.3f}")
  print(f"  ROC-AUC:     {result.roc_auc:.3f}")
  print(f"  CV folds:    {len(result.cross_validation)}")
  print(f"  Per-lot:     {len(result.per_lot)}")

  if args.output:
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result.model_dump(), indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nذخیره شد: {out}")


if __name__ == "__main__":
  main()
