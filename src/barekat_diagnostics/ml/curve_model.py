"""Classifier trained on features the pipeline can derive from a raw qPCR curve."""

from __future__ import annotations

from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier

from barekat_diagnostics.core.config import Settings, get_settings
from barekat_diagnostics.ml.registry import ModelRegistry, dataset_hash
from barekat_diagnostics.pipeline.feature_extraction import analyze_curve

# Scale-free by construction: no raw fluorescence units, so the model is not tied to one
# instrument's gain. Every one of these is emitted by analyze_curve().
CURVE_FEATURES = [
  "ct_value", "amplified", "signal_to_noise", "rel_slope", "rel_rise", "rel_auc",
]


def curves_to_features(df: pd.DataFrame, curve_col: str = "Curve") -> pd.DataFrame:
  feats = pd.DataFrame([analyze_curve(c) for c in df[curve_col]])
  base = df.drop(columns=[curve_col]).reset_index(drop=True)
  return pd.concat([base, feats], axis=1)


def build_curve_model() -> RandomForestClassifier:
  return RandomForestClassifier(n_estimators=300, min_samples_leaf=3, random_state=0)


def train_curve_classifier(
  feature_df: pd.DataFrame,
  *,
  version: str,
  metrics: dict,
  settings: Settings | None = None,
) -> Path:
  """Fit on a feature frame and register as *staging* (promotion stays a gated, separate step)."""
  settings = settings or get_settings()
  model = build_curve_model().fit(
    feature_df[CURVE_FEATURES].to_numpy(), feature_df["True_Status"].to_numpy()
  )
  model_dir = Path(settings.model_path)
  model_dir.mkdir(parents=True, exist_ok=True)
  filename = f"diagnostic_classifier_{version}.pkl"
  joblib.dump(
    {"model": model, "feature_columns": list(CURVE_FEATURES), "version": version},
    model_dir / filename,
  )
  registry = ModelRegistry.load()
  registry.register_version(
    version=version,
    file=filename,
    algorithm="random_forest",
    features=list(CURVE_FEATURES),
    metrics=metrics,
    dataset_hash=dataset_hash(feature_df.drop(columns=["Curve"], errors="ignore")),
    promote=False,
    settings=settings,
  )
  return model_dir / filename
