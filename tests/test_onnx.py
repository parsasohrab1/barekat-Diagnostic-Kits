"""Tests for ONNX export (integration skipped on Windows — skl2onnx import crash)."""

import platform

import pytest

SKIP_ONNX_INTEGRATION = platform.system() == "Windows"


def test_export_raises_without_edge_deps(monkeypatch):
  """export_sklearn_to_onnx surfaces missing edge extras."""
  import builtins

  real_import = builtins.__import__

  def mock_import(name, *args, **kwargs):
    if name == "skl2onnx" or name.startswith("skl2onnx."):
      raise ImportError("no skl2onnx")
    return real_import(name, *args, **kwargs)

  monkeypatch.setattr(builtins, "__import__", mock_import)

  from barekat_diagnostics.ml.onnx_export import export_sklearn_to_onnx

  with pytest.raises(ImportError, match="edge extras"):
    export_sklearn_to_onnx("dummy.pkl")


@pytest.mark.skipif(SKIP_ONNX_INTEGRATION, reason="skl2onnx unstable on Windows")
def test_export_and_predict(tmp_path):
  pytest.importorskip("skl2onnx")
  pytest.importorskip("onnxruntime")

  import joblib
  import numpy as np
  from sklearn.ensemble import RandomForestClassifier

  from barekat_diagnostics.ml.onnx_export import EdgeOnnxPredictor, export_sklearn_to_onnx

  model = RandomForestClassifier(n_estimators=10, random_state=42)
  X = np.random.rand(100, 4)
  y = (X[:, 0] > 0.5).astype(int)
  model.fit(X, y)

  pkl_path = tmp_path / "model.pkl"
  cols = ["f1", "f2", "f3", "f4"]
  joblib.dump({"model": model, "feature_columns": cols, "version": "test"}, pkl_path)

  onnx_path = export_sklearn_to_onnx(pkl_path, tmp_path / "model.onnx")
  assert onnx_path.exists()

  predictor = EdgeOnnxPredictor(onnx_path)
  result, confidence, version, latency = predictor.predict({c: 0.6 for c in cols})
  assert result in ("positive", "negative")
  assert 0.0 <= confidence <= 1.0
  assert latency < 500


@pytest.mark.skipif(SKIP_ONNX_INTEGRATION, reason="skl2onnx unstable on Windows")
def test_benchmark(tmp_path):
  pytest.importorskip("skl2onnx")
  pytest.importorskip("onnxruntime")

  import joblib
  import numpy as np
  from sklearn.ensemble import RandomForestClassifier

  from barekat_diagnostics.ml.onnx_export import benchmark_onnx, export_sklearn_to_onnx

  model = RandomForestClassifier(n_estimators=5, random_state=1)
  X = np.random.rand(50, 3)
  y = (X[:, 0] > 0.5).astype(int)
  model.fit(X, y)
  pkl = tmp_path / "m.pkl"
  joblib.dump({"model": model, "feature_columns": ["a", "b", "c"], "version": "v1"}, pkl)
  onnx = export_sklearn_to_onnx(pkl, tmp_path / "m.onnx")
  bench = benchmark_onnx(onnx, n_iterations=20)
  assert bench["mean_ms"] < 100
  assert "p95_ms" in bench
