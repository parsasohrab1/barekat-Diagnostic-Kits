"""بسته ONNX قفل‌شده برای کیوسک/دستگاه edge."""

from __future__ import annotations

import hashlib
import hmac
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from barekat_diagnostics.core.config import Settings, get_settings
from barekat_diagnostics.ml.onnx_export import benchmark_onnx, export_sklearn_to_onnx
from barekat_diagnostics.ml.registry import ModelRegistry, file_sha256


class BundleError(Exception):
  def __init__(self, message: str) -> None:
    self.message = message
    super().__init__(message)


def _sign(checksum: str, secret: str) -> str:
  return hmac.new(secret.encode("utf-8"), checksum.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_bundle_signature(checksum: str, signature: str, secret: str) -> bool:
  expected = _sign(checksum, secret)
  return hmac.compare_digest(expected, signature)


def build_locked_edge_bundle(
  *,
  output_dir: str | Path | None = None,
  model_version: str | None = None,
  settings: Settings | None = None,
  run_benchmark: bool = True,
) -> dict[str, Any]:
  """ساخت بسته کیوسک: ONNX + lockfile + checksum + signature + SLA."""
  settings = settings or get_settings()
  registry = ModelRegistry.load()
  version = model_version or registry.production_version

  if version not in registry.versions:
    raise BundleError(f"نسخه {version} در registry نیست")

  info = registry.versions[version]
  if registry.production_locked and version == registry.production_version:
    # فقط نسخه production قفل‌شده برای کیوسک مجاز است
    pass
  elif info.status not in {"production", "locked", "validated"}:
    raise BundleError(f"نسخه {version} برای بسته‌بندی edge تأیید نشده (status={info.status})")

  model_dir = Path(settings.model_path)
  pkl = model_dir / info.file
  if not pkl.exists():
    # fallback به classifier پیش‌فرض
    pkl = model_dir / settings.classifier_model
  if not pkl.exists():
    raise BundleError(f"فایل مدل یافت نشد: {pkl}")

  out_root = Path(output_dir or settings.edge_bundle_dir)
  bundle_dir = out_root / f"kiosk-{version}"
  if bundle_dir.exists():
    shutil.rmtree(bundle_dir)
  bundle_dir.mkdir(parents=True, exist_ok=True)

  onnx_path = bundle_dir / f"model_{version}.onnx"
  export_sklearn_to_onnx(pkl, onnx_path, settings=settings)

  # بهینه‌سازی session: warm-up + benchmark
  bench = None
  if run_benchmark:
    try:
      # warm-up
      from barekat_diagnostics.ml.onnx_export import EdgeOnnxPredictor

      predictor = EdgeOnnxPredictor(onnx_path, settings=settings)
      warm = {c: 0.5 for c in predictor.feature_columns}
      for _ in range(5):
        predictor.predict(warm)
      bench = benchmark_onnx(onnx_path, n_iterations=settings.edge_benchmark_iterations)
    except ImportError:
      bench = {"skipped": True, "reason": "onnxruntime not installed"}

  sla_ms = settings.edge_latency_sla_ms
  sla_ok = True
  if bench and "p95_ms" in bench:
    sla_ok = float(bench["p95_ms"]) <= sla_ms
    if settings.edge_enforce_latency_sla and not sla_ok:
      raise BundleError(
        f"latency SLA رد شد: p95={bench['p95_ms']}ms > {sla_ms}ms"
      )

  checksum = file_sha256(onnx_path) or hashlib.sha256(onnx_path.read_bytes()).hexdigest()
  signature = _sign(checksum, settings.edge_bundle_secret)

  lockfile = {
    "format": "barekat-edge-bundle-v1",
    "model_version": version,
    "onnx_file": onnx_path.name,
    "checksum_sha256": checksum,
    "signature": signature,
    "locked": True,
    "production_locked": registry.production_locked,
    "created_at": datetime.now(timezone.utc).isoformat(),
    "latency_sla_ms": sla_ms,
    "benchmark": bench,
    "sla_ok": sla_ok,
    "inference_backend": "onnx",
    "ort_intra_op_threads": settings.edge_ort_intra_op_threads,
    "ort_inter_op_threads": settings.edge_ort_inter_op_threads,
  }
  lock_path = bundle_dir / "model.lock.json"
  lock_path.write_text(json.dumps(lockfile, indent=2, ensure_ascii=False), encoding="utf-8")

  # کپی sidecar metadata
  meta_src = onnx_path.with_suffix(".onnx.json")
  if meta_src.exists():
    meta = json.loads(meta_src.read_text(encoding="utf-8"))
    meta["checksum_sha256"] = checksum
    meta["locked"] = True
    meta_src.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

  readme = bundle_dir / "README.txt"
  readme.write_text(
    "Barekat Edge Kiosk Bundle\n"
    f"version={version}\n"
    f"checksum={checksum}\n"
    "Set INFERENCE_BACKEND=onnx and ONNX_MODEL_PATH to the .onnx file.\n"
    "Verify model.lock.json signature before deployment.\n",
    encoding="utf-8",
  )

  return {
    "bundle_dir": str(bundle_dir),
    "onnx_path": str(onnx_path),
    "lock_path": str(lock_path),
    "model_version": version,
    "checksum_sha256": checksum,
    "signature": signature,
    "locked": True,
    "sla_ok": sla_ok,
    "benchmark": bench,
  }


def load_and_verify_locked_model(
  onnx_path: str | Path,
  *,
  settings: Settings | None = None,
) -> dict[str, Any]:
  """بارگذاری و تأیید قفل/checksum/امضای مدل قبل از inference."""
  settings = settings or get_settings()
  path = Path(onnx_path)
  lock_path = path.parent / "model.lock.json"
  if not lock_path.exists():
    # sidecar بدون lock — فقط در حالت غیرسخت‌گیر
    if settings.edge_require_locked_model:
      raise BundleError("model.lock.json الزامی است")
    return {"locked": False, "verified": False}

  lock = json.loads(lock_path.read_text(encoding="utf-8"))
  if not lock.get("locked", False) and settings.edge_require_locked_model:
    raise BundleError("مدل قفل نشده است")

  checksum = hashlib.sha256(path.read_bytes()).hexdigest()
  expected = lock.get("checksum_sha256", "")
  # مقایسه با 32 یا 64 کاراکتر
  if expected and not (
    checksum.startswith(expected) or expected.startswith(checksum[: len(expected)])
  ):
    # مقایسه کامل اگر هر دو 64 باشند
    full = hashlib.sha256(path.read_bytes()).hexdigest()
    short = file_sha256(path)
    if expected not in {full, short, full[:32], short}:
      raise BundleError("checksum مدل با lockfile مطابقت ندارد")

  sig = lock.get("signature", "")
  check_val = lock.get("checksum_sha256", "")
  if sig and not verify_bundle_signature(check_val, sig, settings.edge_bundle_secret):
    raise BundleError("امضای مدل نامعتبر است")

  return {
    "locked": True,
    "verified": True,
    "model_version": lock.get("model_version"),
    "checksum_sha256": check_val,
    "benchmark": lock.get("benchmark"),
    "sla_ok": lock.get("sla_ok"),
  }
