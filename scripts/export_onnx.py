#!/usr/bin/env python3
"""Export sklearn model to ONNX for edge deployment."""

import argparse
import sys
from pathlib import Path

from barekat_diagnostics.core.config import get_settings
from barekat_diagnostics.ml.onnx_export import benchmark_onnx, export_sklearn_to_onnx


def main() -> None:
  if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

  parser = argparse.ArgumentParser(description="Export model to ONNX")
  parser.add_argument("--model", default=None, help="Path to .pkl model")
  parser.add_argument("--output", default=None, help="Output .onnx path")
  parser.add_argument("--benchmark", action="store_true", default=True)
  args = parser.parse_args()

  settings = get_settings()
  model_path = Path(args.model or settings.model_path) / settings.classifier_model
  if not model_path.exists():
    raise SystemExit(f"Model not found: {model_path}")

  out = export_sklearn_to_onnx(model_path, args.output or settings.onnx_model_path, settings)
  print(f"Exported: {out}")
  print(f"Metadata: {out.with_suffix('.onnx.json')}")

  if args.benchmark:
    bench = benchmark_onnx(out)
    print(f"\nBenchmark ({bench['iterations']} iterations):")
    print(f"  Mean:  {bench['mean_ms']:.2f} ms")
    print(f"  P95:   {bench['p95_ms']:.2f} ms")
    print(f"  Max:   {bench['max_ms']:.2f} ms")
    print(f"  <100ms: {bench['under_100ms']}")


if __name__ == "__main__":
  main()
