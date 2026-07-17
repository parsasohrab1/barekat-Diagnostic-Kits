#!/usr/bin/env python3
"""CLI for offline-first diagnosis."""

import argparse
import json
import sys

from barekat_diagnostics.edge.offline_service import OfflineDiagnosisService
from barekat_diagnostics.edge.sync import OfflineSyncService
from barekat_diagnostics.schemas import SampleInput


def main() -> None:
  if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

  parser = argparse.ArgumentParser(description="Offline diagnosis CLI")
  sub = parser.add_subparsers(dest="command", required=True)

  analyze_p = sub.add_parser("analyze", help="Analyze sample offline")
  analyze_p.add_argument("--sample-id", required=True)
  analyze_p.add_argument("--kit-type", default="qpcr")
  analyze_p.add_argument("--ct-value", type=float, default=None)

  sub.add_parser("pending", help="Show pending sync count")
  sync_p = sub.add_parser("sync", help="Sync to central server")
  sync_p.add_argument("--api", default=None)

  args = parser.parse_args()
  service = OfflineDiagnosisService()

  if args.command == "analyze":
    sample = SampleInput(
      sample_id=args.sample_id,
      kit_type=args.kit_type,
      ct_value=args.ct_value,
      quality_score=0.9,
    )
    report = service.analyze(sample)
    print(json.dumps(report.model_dump(mode="json"), indent=2, ensure_ascii=False))

  elif args.command == "pending":
    print(f"Pending samples: {service.store.pending_count()}")
    print(f"Pending sync: {service.pending_sync_count()}")

  elif args.command == "sync":
    result = OfflineSyncService().sync_all(api_base=args.api)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
  main()
