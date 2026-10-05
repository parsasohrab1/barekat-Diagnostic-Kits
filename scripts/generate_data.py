#!/usr/bin/env python3
"""Generate synthetic data for model training."""

import argparse
import sys
from pathlib import Path

from barekat_diagnostics.data.synthetic import generate_diagnostic_kit_data


def main() -> None:
  if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
  parser = argparse.ArgumentParser(description="Generate synthetic diagnostic kit data")
  parser.add_argument("--samples", type=int, default=800, help="Number of samples")
  parser.add_argument(
    "--output",
    type=str,
    default="data/raw/synthetic.csv",
    help="Output file path",
  )
  parser.add_argument(
    "--realistic",
    action="store_true",
    default=True,
    help="Simulate batch effect, drift and borderline (default)",
  )
  parser.add_argument(
    "--simple",
    action="store_true",
    help="Simple mode without batch/lot",
  )
  args = parser.parse_args()

  realistic = not args.simple
  df = generate_diagnostic_kit_data(n_samples=args.samples, realistic=realistic)
  output = Path(args.output)
  output.parent.mkdir(parents=True, exist_ok=True)
  df.to_csv(output, index=False)

  print(f"Number of samples: {len(df)}")
  print(f"Realistic mode: {realistic}")
  print(f"\nTrue status distribution:\n{df['True_Status'].value_counts()}")
  print(f"\nMean Ct Value: {df['Ct_Value'].mean():.2f}")
  if realistic:
    print(f"\nDevices: {df['Lab_Device'].value_counts().to_dict()}")
    print(f"Lots: {df['Kit_Lot'].value_counts().to_dict()}")
  print(f"\nSaved: {output}")


if __name__ == "__main__":
  main()
