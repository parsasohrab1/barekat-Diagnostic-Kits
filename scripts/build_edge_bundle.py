#!/usr/bin/env python3
"""ساخت بسته کیوسک با مدل ONNX قفل‌شده."""

from __future__ import annotations

import argparse
import json

from barekat_diagnostics.edge.bundle import BundleError, build_locked_edge_bundle


def main() -> None:
  parser = argparse.ArgumentParser(description="Build locked edge kiosk ONNX bundle")
  parser.add_argument("--version", default=None, help="Model version (default: production)")
  parser.add_argument("--out", default=None, help="Output directory")
  parser.add_argument("--enforce-sla", action="store_true", help="Fail if p95 > SLA")
  args = parser.parse_args()

  from barekat_diagnostics.core.config import get_settings

  settings = get_settings()
  if args.enforce_sla:
    settings.edge_enforce_latency_sla = True
  if args.out:
    settings.edge_bundle_dir = args.out

  try:
    result = build_locked_edge_bundle(model_version=args.version, settings=settings)
  except BundleError as exc:
    raise SystemExit(exc.message) from exc

  print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
  main()
