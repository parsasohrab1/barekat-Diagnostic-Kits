"""Export sklearn models to ONNX for edge inference."""

from __future__ import annotations

import json
import time
from pathlib import Path

import joblib
import numpy as np

from barekat_diagnostics.core.config import Settings, get_settings


def export_sklearn_to_onnx(
  model_path: str | Path,
  output_path: str | Path | None = None,
  settings: Settings | None = None,
) -> Path:
  """Convert a saved sklearn artifact to ONNX."""
  try:
    from skl2onnx import convert_sklearn
    from skl2onnx.common.data_types import FloatTensorType
  except ImportError as exc:
    raise ImportError("Install edge extras: pip install -e '.[edge]'") from exc

  settings = settings or get_settings()
  artifact = joblib.load(model_path)
  model = artifact["model"]
  feature_columns = artifact["feature_columns"]
  n_features = len(feature_columns)

  initial_type = [("input", FloatTensorType([None, n_features]))]
  onnx_model = convert_sklearn(model, initial_types=initial_type)

  out = Path(output_path) if output_path else Path(model_path).with_suffix(".onnx")
  out.parent.mkdir(parents=True, exist_ok=True)
  with open(out, "wb") as f:
    f.write(onnx_model.SerializeToString())

  meta_path = out.with_suffix(".onnx.json")
  meta_path.write_text(
    json.dumps({"feature_columns": feature_columns, "version": artifact.get("version", "v1")}, indent=2),
    encoding="utf-8",
  )
  return out


class EdgeOnnxPredictor:
  """ONNX Runtime predictor for low-power CPU (<100ms target)."""

  def __init__(self, onnx_path: str | Path, settings: Settings | None = None):
    try:
      import onnxruntime as ort
    except ImportError as exc:
      raise ImportError("Install edge extras: pip install -e '.[edge]'") from exc

    self.settings = settings or get_settings()
    self.onnx_path = Path(onnx_path)
    so = ort.SessionOptions()
    so.intra_op_num_threads = max(1, int(self.settings.edge_ort_intra_op_threads))
    so.inter_op_num_threads = max(1, int(self.settings.edge_ort_inter_op_threads))
    so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    self.session = ort.InferenceSession(
      str(self.onnx_path),
      sess_options=so,
      providers=["CPUExecutionProvider"],
    )
    meta_path = self.onnx_path.with_suffix(".onnx.json")
    if meta_path.exists():
      meta = json.loads(meta_path.read_text(encoding="utf-8"))
      self.feature_columns: list[str] = meta["feature_columns"]
      self.version: str = meta.get("version", "onnx-v1")
    else:
      self.feature_columns = []
      self.version = "onnx-v1"

  def predict(self, features: dict[str, float]) -> tuple[str, float, str, float]:
    """Returns (result, confidence, version, latency_ms)."""
    X = np.array([[features.get(c, 0.0) for c in self.feature_columns]], dtype=np.float32)
    input_name = self.session.get_inputs()[0].name

    t0 = time.perf_counter()
    outputs = self.session.run(None, {input_name: X})
    latency_ms = (time.perf_counter() - t0) * 1000

    if len(outputs) >= 2:
      pred = int(outputs[0][0])
      proba = outputs[1][0]
      if len(proba) == 1:
        confidence = float(proba[0]) if pred == 1 else 1.0 - float(proba[0])
      else:
        confidence = float(proba[pred])
    else:
      pred = int(outputs[0][0])
      confidence = 0.85

    result = "positive" if pred == 1 else "negative"
    return result, confidence, self.version, latency_ms


def benchmark_onnx(onnx_path: str | Path, n_iterations: int = 100, settings: Settings | None = None) -> dict:
  """Benchmark ONNX inference latency against clinical SLA."""
  settings = settings or get_settings()
  predictor = EdgeOnnxPredictor(onnx_path, settings=settings)
  features = {col: 0.5 for col in predictor.feature_columns}
  # warm-up
  for _ in range(max(1, settings.edge_warmup_iterations)):
    predictor.predict(features)
  latencies: list[float] = []
  for _ in range(n_iterations):
    _, _, _, ms = predictor.predict(features)
    latencies.append(ms)
  sla = settings.edge_latency_sla_ms
  p95 = float(np.percentile(latencies, 95))
  return {
    "iterations": n_iterations,
    "mean_ms": round(float(np.mean(latencies)), 3),
    "p95_ms": round(p95, 3),
    "max_ms": round(float(np.max(latencies)), 3),
    "sla_ms": sla,
    "under_100ms": all(ms < 100 for ms in latencies),
    "sla_ok": p95 <= sla,
  }
