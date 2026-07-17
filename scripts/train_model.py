#!/usr/bin/env python3
"""آموزش مدل طبقه‌بندی تشخیصی."""

import argparse
import sys
from pathlib import Path

import pandas as pd

from barekat_diagnostics.ml.classifier import train_classifier


def main() -> None:
  if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
  parser = argparse.ArgumentParser(description="آموزش مدل تشخیصی")
  parser.add_argument("--data", default="data/raw/synthetic.csv")
  parser.add_argument("--version", default="v1")
  parser.add_argument("--no-promote", action="store_true")
  args = parser.parse_args()

  data_path = Path(args.data)
  if not data_path.exists():
    raise SystemExit(f"فایل داده یافت نشد: {data_path}")

  df = pd.read_csv(data_path)
  _, metrics = train_classifier(df, version=args.version, promote=not args.no_promote)

  print("آموزش مدل با موفقیت انجام شد:")
  print(f"  Version:     {metrics.model_version}")
  print(f"  Promoted:    {metrics.promoted}")
  print(f"  Accuracy:    {metrics.accuracy:.3f}")
  print(f"  Sensitivity: {metrics.sensitivity:.3f}")
  print(f"  Specificity: {metrics.specificity:.3f}")
  print(f"  PPV:         {metrics.ppv:.3f}")
  print(f"  NPV:         {metrics.npv:.3f}")
  print(f"  ROC-AUC:     {metrics.roc_auc:.3f}")
  print(f"  Model:       {metrics.model_path}")


if __name__ == "__main__":
  main()
