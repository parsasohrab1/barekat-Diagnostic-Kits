#!/usr/bin/env python3
"""بروزرسانی امن مدل روی دستگاه edge از manifest ناوگان."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import urllib.request

from barekat_diagnostics.core.config import get_settings
from barekat_diagnostics.ml.onnx_export import benchmark_onnx


def main() -> None:
  parser = argparse.ArgumentParser(description="Pull fleet model update for this device")
  parser.add_argument("--device-id", required=True)
  parser.add_argument("--api", default=None, help="API base e.g. http://localhost:8000/api/v1")
  parser.add_argument("--token", default=None)
  args = parser.parse_args()

  settings = get_settings()
  base = (args.api or settings.offline_sync_api_url).rstrip("/")
  headers = {"Content-Type": "application/json"}
  token = args.token or settings.edge_sync_token
  if token:
    headers["Authorization"] = f"Bearer {token}"

  req = urllib.request.Request(f"{base}/fleet/manifest/{args.device_id}", headers=headers)
  with urllib.request.urlopen(req, timeout=30) as resp:
    manifest = json.loads(resp.read().decode("utf-8"))

  src = Path(manifest["download_path"])
  if not src.exists():
    # try download endpoint
    dl = urllib.request.Request(
      f"{base}/fleet/download?path={src}",
      headers=headers,
    )
    with urllib.request.urlopen(dl, timeout=60) as resp:
      dest = Path(settings.onnx_model_path)
      dest.parent.mkdir(parents=True, exist_ok=True)
      dest.write_bytes(resp.read())
  else:
    dest = Path(settings.onnx_model_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(src.read_bytes())
    lock = src.parent / "model.lock.json"
    if lock.exists():
      (dest.parent / "model.lock.json").write_text(lock.read_text(encoding="utf-8"), encoding="utf-8")

  bench = None
  try:
    bench = benchmark_onnx(dest, n_iterations=30, settings=settings)
  except ImportError:
    bench = {"skipped": True}

  ack = {
    "device_id": args.device_id,
    "model_version": manifest["model_version"],
    "checksum_sha256": manifest["checksum_sha256"],
    "latency_p95_ms": (bench or {}).get("p95_ms"),
    "sla_ok": (bench or {}).get("sla_ok"),
  }
  ack_req = urllib.request.Request(
    f"{base}/fleet/ack",
    data=json.dumps(ack).encode("utf-8"),
    headers=headers,
    method="POST",
  )
  with urllib.request.urlopen(ack_req, timeout=30) as resp:
    print(resp.read().decode("utf-8"))


if __name__ == "__main__":
  main()
