"""استخراج ویژگی‌ها و ساخت مدل."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.svm import SVC

from barekat_diagnostics.core.config import Settings, get_settings

FEATURE_COLUMNS = [f"Feature_{i}" for i in range(1, 13)]


def get_feature_columns(df: pd.DataFrame) -> list[str]:
  return [c for c in FEATURE_COLUMNS if c in df.columns]


def build_model(settings: Settings | None = None):
  settings = settings or get_settings()
  if settings.classifier_type == "svm":
    return SVC(kernel="rbf", probability=True, random_state=42)
  return RandomForestClassifier(n_estimators=100, random_state=42)


def prepare_features(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, list[str]]:
  feature_cols = get_feature_columns(df)
  extra_cols = ["Ct_Value", "Signal_to_Noise", "Amplification_Efficiency", "Quality_Score"]
  all_features = feature_cols + [c for c in extra_cols if c in df.columns]
  return df[all_features].values, df["True_Status"].values, all_features
