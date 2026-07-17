"""Tests for model registry and A/B testing."""

from pathlib import Path

from barekat_diagnostics.ml.registry import ModelRegistry, dataset_hash
from barekat_diagnostics.data.synthetic import generate_diagnostic_kit_data


def test_ab_test_routing(tmp_path: Path):
  registry = ModelRegistry(production_version="v1")
  registry.versions["v1"] = type(registry.versions)  # noqa — set properly below
  from barekat_diagnostics.ml.registry import ModelVersionInfo

  registry.versions["v1"] = ModelVersionInfo(
    version="v1", file="v1.pkl", algorithm="rf", features=[], metrics={"sensitivity": 0.9},
    dataset_hash="abc", created_at="2026-01-01T00:00:00+00:00", status="production",
  )
  registry.versions["v2"] = ModelVersionInfo(
    version="v2", file="v2.pkl", algorithm="rf", features=[], metrics={"sensitivity": 0.91},
    dataset_hash="def", created_at="2026-01-02T00:00:00+00:00", status="staging",
  )
  registry.ab_test.enabled = True
  registry.ab_test.challenger_version = "v2"
  registry.ab_test.traffic_pct = 1.0

  assert registry.route_version("any-sample") == "v2"

  registry.ab_test.traffic_pct = 0.0
  assert registry.route_version("any-sample") == "v1"


def test_quality_gate_blocks_degraded_model(tmp_path: Path):
  from barekat_diagnostics.core.config import Settings

  registry = ModelRegistry(production_version="v1")
  from barekat_diagnostics.ml.registry import ModelVersionInfo

  registry.versions["v1"] = ModelVersionInfo(
    version="v1", file="v1.pkl", algorithm="rf", features=[],
    metrics={"sensitivity": 0.95, "specificity": 0.95, "roc_auc": 0.98},
    dataset_hash="abc", created_at="2026-01-01T00:00:00+00:00", status="production",
  )
  path = tmp_path / "registry.json"
  settings = Settings(model_path=str(tmp_path), ml_rollback_threshold=0.05)

  promoted, msg = registry.register_version(
    version="v2",
    file="v2.pkl",
    algorithm="rf",
    features=["Ct_Value"],
    metrics={"sensitivity": 0.70, "specificity": 0.70, "roc_auc": 0.75},
    dataset_hash="xyz",
    promote=True,
    settings=settings,
  )
  registry.save(path)
  assert promoted is False
  assert "blocked" in msg
  assert registry.production_version == "v1"


def test_dataset_hash_stable():
  df = generate_diagnostic_kit_data(n_samples=50, realistic=False)
  assert dataset_hash(df) == dataset_hash(df)
  assert len(dataset_hash(df)) == 16
