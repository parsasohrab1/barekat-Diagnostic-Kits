"""Training and evaluation of diagnostic classification models."""

from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

from barekat_diagnostics.core.config import Settings, get_settings
from barekat_diagnostics.ml.evaluation import evaluate_model
from barekat_diagnostics.ml.explainability import explain_prediction
from barekat_diagnostics.ml.features import build_model, prepare_features
from barekat_diagnostics.ml.registry import ModelRegistry, RegistryError, dataset_hash
from barekat_diagnostics.schemas import ModelExplanation, TrainingMetrics


def train_classifier(
  df: pd.DataFrame,
  settings: Settings | None = None,
  *,
  version: str = "v1",
  promote: bool = False,
) -> tuple[object, TrainingMetrics]:
  """Train the model, IVD evaluation and registry recording (no promote by default)."""
  settings = settings or get_settings()
  X, y, all_features = prepare_features(df)

  X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
  )

  model = build_model(settings)
  model.fit(X_train, y_train)

  ivd = evaluate_model(df.copy(), model=model)

  model_dir = Path(settings.model_path)
  model_dir.mkdir(parents=True, exist_ok=True)
  model_filename = f"diagnostic_classifier_{version}.pkl"
  model_path = model_dir / model_filename

  artifact = {
    "model": model,
    "feature_columns": all_features,
    "version": version,
  }
  joblib.dump(artifact, model_path)

  registry = ModelRegistry.load()
  metrics_dict = {
    "accuracy": ivd.accuracy,
    "sensitivity": ivd.sensitivity.model_dump(),
    "specificity": ivd.specificity.model_dump(),
    "ppv": ivd.ppv.model_dump(),
    "npv": ivd.npv.model_dump(),
    "roc_auc": ivd.roc_auc,
    "confusion_matrix": ivd.confusion_matrix.model_dump(),
  }
  try:
    promoted, _msg = registry.register_version(
      version=version,
      file=model_filename,
      algorithm=settings.classifier_type,
      features=all_features,
      metrics=metrics_dict,
      dataset_hash=dataset_hash(df),
      promote=promote,
      settings=settings,
    )
  except RegistryError as exc:
    raise RuntimeError(exc.message) from exc

  if promote and not promoted:
    registry.rollback_if_degraded(version, settings)

  metrics = TrainingMetrics(
    accuracy=ivd.accuracy,
    sensitivity=ivd.sensitivity.value,
    specificity=ivd.specificity.value,
    f1_score=0.0,
    model_path=str(model_path),
    roc_auc=ivd.roc_auc,
    ppv=ivd.ppv.value,
    npv=ivd.npv.value,
    model_version=version,
    promoted=promoted,
  )

  if promote:
    try:
      from barekat_diagnostics.ml.onnx_export import export_sklearn_to_onnx

      export_sklearn_to_onnx(model_path, settings.onnx_model_path, settings)
    except ImportError:
      pass

  return model, metrics


class FeatureMismatchError(ValueError):
  """Raised when the pipeline cannot supply the columns a model was trained on."""

  def __init__(self, missing: list[str], version: str) -> None:
    self.missing = missing
    self.version = version
    super().__init__(f"model {version} requires features not produced by the pipeline: {missing}")


def build_feature_row(
  features: dict[str, float], columns: list[str], version: str = "?"
) -> np.ndarray:
  """Map pipeline features onto model columns (case-insensitive); never zero-fill silently."""
  lowered = {k.lower(): v for k, v in features.items()}
  missing = [c for c in columns if c.lower() not in lowered]
  if missing:
    raise FeatureMismatchError(missing, version)
  return np.array([[float(lowered[c.lower()]) for c in columns]])


class DiagnosticPredictor:
  """Prediction with registry and A/B test support."""

  def __init__(self, settings: Settings | None = None):
    self.settings = settings or get_settings()
    self.registry = ModelRegistry.load()
    if self.settings.ml_ab_test_enabled:
      self.registry.ab_test.enabled = True
      self.registry.ab_test.challenger_version = self.settings.ml_ab_test_challenger
      self.registry.ab_test.traffic_pct = self.settings.ml_ab_test_traffic_pct
    self._artifacts: dict[str, dict] = {}

  def _resolve_version(self, sample_id: str | None) -> str:
    return self.registry.route_version(sample_id)

  def _load(self, version: str | None = None) -> dict:
    version = version or self.registry.production_version
    if version not in self._artifacts:
      model_file = self.registry.model_file(version, self.settings)
      model_path = Path(self.settings.model_path) / model_file
      if not model_path.exists():
        raise FileNotFoundError(f"Model not found: {model_path}")
      self._artifacts[version] = joblib.load(model_path)
    return self._artifacts[version]

  def predict(self, features: dict[str, float], sample_id: str | None = None) -> tuple[str, float, str]:
    version = self._resolve_version(sample_id)
    artifact = self._load(version)
    model = artifact["model"]
    columns = artifact["feature_columns"]

    X = build_feature_row(features, columns, version)
    proba = model.predict_proba(X)[0]
    pred = int(model.predict(X)[0])

    result = "positive" if pred == 1 else "negative"
    confidence = float(proba[pred])
    return result, confidence, version

  def explain(self, features: dict[str, float], sample_id: str | None = None) -> ModelExplanation:
    version = self._resolve_version(sample_id)
    artifact = self._load(version)
    return explain_prediction(
      artifact["model"],
      artifact["feature_columns"],
      features,
      model_version=version,
    )

  def predict_rule_based(self, features: dict[str, float]) -> tuple[str, float, str]:
    if "od_ratio" in features:
      ratio = features["od_ratio"]
      cutoff = 1.0
      if ratio >= cutoff:
        return "positive", min(0.95, ratio / (cutoff + 0.5)), "rule-based"
      return "negative", min(0.95, 1.0 - ratio / cutoff), "rule-based"

    if "peak_intensity" in features:
      peak = features["peak_intensity"]
      cutoff = 0.5
      if peak >= cutoff:
        return "positive", min(0.95, peak / (cutoff + 0.5)), "rule-based"
      return "negative", min(0.95, 1.0 - peak / cutoff), "rule-based"

    ct = features.get("ct_value", 35.0)
    if ct < 30:
      return "positive", min(0.95, 1.0 - ct / 40), "rule-based"
    return "negative", min(0.95, ct / 45), "rule-based"
