#!/usr/bin/env python3
"""تولید داده سنتتیک برای آموزش مدل."""

import argparse
import sys
from pathlib import Path

from barekat_diagnostics.data.synthetic import generate_diagnostic_kit_data


def main() -> None:
  if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
  parser = argparse.ArgumentParser(description="تولید داده سنتتیک کیت تشخیصی")
  parser.add_argument("--samples", type=int, default=800, help="تعداد نمونه‌ها")
  parser.add_argument(
    "--output",
    type=str,
    default="data/raw/synthetic.csv",
    help="مسیر فایل خروجی",
  )
  parser.add_argument(
    "--realistic",
    action="store_true",
    default=True,
    help="شبیه‌سازی batch effect، drift و borderline (پیش‌فرض)",
  )
  parser.add_argument(
    "--simple",
    action="store_true",
    help="حالت ساده بدون batch/lot",
  )
  args = parser.parse_args()

  realistic = not args.simple
  df = generate_diagnostic_kit_data(n_samples=args.samples, realistic=realistic)
  output = Path(args.output)
  output.parent.mkdir(parents=True, exist_ok=True)
  df.to_csv(output, index=False)

  print(f"تعداد نمونه‌ها: {len(df)}")
  print(f"حالت realistic: {realistic}")
  print(f"\nتوزیع وضعیت واقعی:\n{df['True_Status'].value_counts()}")
  print(f"\nمیانگین Ct Value: {df['Ct_Value'].mean():.2f}")
  if realistic:
    print(f"\nدستگاه‌ها: {df['Lab_Device'].value_counts().to_dict()}")
    print(f"Lotها: {df['Kit_Lot'].value_counts().to_dict()}")
  print(f"\nذخیره شد: {output}")


if __name__ == "__main__":
  main()
