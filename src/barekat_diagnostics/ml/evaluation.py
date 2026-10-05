"""Model evaluation with IVD metrics."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import (
  accuracy_score,
  confusion_matrix,
  roc_auc_score,
  roc_curve,
)
from sklearn.model_selection import GroupKFold

from barekat_diagnostics.ml.features import build_model, get_feature_columns
from barekat_diagnostics.schemas import (
  ConfusionMatrixSchema,
  CrossValidationFold,
  IVDEvaluationResult,
  MetricWithCI,
  PerLotEvaluation,
)

def _wilson_ci(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
  if total == 0:
    return 0.0, 0.0
  p = successes / total
  denom = 1 + z**2 / total
  centre = p + z**2 / (2 * total)
  margin = z * np.sqrt((p * (1 - p) + z**2 / (4 * total)) / total)
  lower = max(0.0, (centre - margin) / denom)
  upper = min(1.0, (centre + margin) / denom)
  return float(lower), float(min(1.0, upper))


def _metric_with_ci(successes: int, total: int) -> MetricWithCI:
  value = successes / total if total > 0 else 0.0
  lo, hi = _wilson_ci(successes, total)
  value = min(value, hi)
  return MetricWithCI(value=value, ci_lower=lo, ci_upper=hi)


def _compute_ivd_metrics(y_true: np.ndarray, y_pred: np.ndarray, y_proba: np.ndarray | None) -> dict:
  cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
  tn, fp, fn, tp = int(cm[0, 0]), int(cm[0, 1]), int(cm[1, 0]), int(cm[1, 1])

  sensitivity = _metric_with_ci(tp, tp + fn)
  specificity = _metric_with_ci(tn, tn + fp)
  ppv = (
    _metric_with_ci(tp, tp + fp)
    if (tp + fp) > 0
    else MetricWithCI(value=0.0, ci_lower=0.0, ci_upper=0.0)
  )
  npv = (
    _metric_with_ci(tn, tn + fn)
    if (tn + fn) > 0
    else MetricWithCI(value=0.0, ci_lower=0.0, ci_upper=0.0)
  )

  roc_auc = 0.0
  fpr, tpr, thresholds = [], [], []
  if y_proba is not None and len(np.unique(y_true)) > 1:
    roc_auc = float(roc_auc_score(y_true, y_proba))
    fpr, tpr, thresholds = roc_curve(y_true, y_proba)

  return {
    "accuracy": float(accuracy_score(y_true, y_pred)),
    "sensitivity": sensitivity,
    "specificity": specificity,
    "ppv": ppv,
    "npv": npv,
    "roc_auc": roc_auc,
    "confusion_matrix": ConfusionMatrixSchema(tn=tn, fp=fp, fn=fn, tp=tp),
    "roc_curve": {
      "fpr": [float(x) for x in fpr[:50]],
      "tpr": [float(x) for x in tpr[:50]],
      "thresholds": [float(x) for x in thresholds[:50]],
    },
  }


def _prepare_xy(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, list[str]]:
  feature_cols = get_feature_columns(df)
  extra_cols = ["Ct_Value", "Signal_to_Noise", "Amplification_Efficiency", "Quality_Score"]
  all_features = feature_cols + [c for c in extra_cols if c in df.columns]
  X = df[all_features].values
  y = df["True_Status"].values
  return X, y, all_features


def evaluate_model(
  df: pd.DataFrame,
  model=None,
  *,
  group_col: str = "Lab_Device",
  lot_col: str = "Kit_Lot",
) -> IVDEvaluationResult:
  """Full IVD evaluation with cross-validation and confusion matrix per lot."""
  X, y, features = _prepare_xy(df)
  if model is None:
    model = build_model()
    model.fit(X, y)

  y_pred = model.predict(X)
  y_proba = model.predict_proba(X)[:, 1] if hasattr(model, "predict_proba") else None
  overall = _compute_ivd_metrics(y, y_pred, y_proba)

  cv_folds: list[CrossValidationFold] = []
  groups = None
  gkf = None
  if group_col in df.columns and df[group_col].nunique() > 1:
    groups = df[group_col].values
    gkf = GroupKFold(n_splits=min(5, df[group_col].nunique()))

  if groups is not None and gkf is not None:
    fold_idx = 0
    for train_idx, test_idx in gkf.split(X, y, groups):
      fold_idx += 1
      fold_model = build_model()
      fold_model.fit(X[train_idx], y[train_idx])
      fold_pred = fold_model.predict(X[test_idx])
      fold_proba = fold_model.predict_proba(X[test_idx])[:, 1]
      fold_metrics = _compute_ivd_metrics(y[test_idx], fold_pred, fold_proba)
      batch_name = str(df.iloc[test_idx[0]][group_col])
      cv_folds.append(CrossValidationFold(
        fold=fold_idx,
        group=batch_name,
        accuracy=fold_metrics["accuracy"],
        sensitivity=fold_metrics["sensitivity"].value,
        specificity=fold_metrics["specificity"].value,
        roc_auc=fold_metrics["roc_auc"],
      ))

  per_lot: list[PerLotEvaluation] = []
  if lot_col in df.columns:
    for lot, lot_df in df.groupby(lot_col):
      lot_X, lot_y, _ = _prepare_xy(lot_df)
      lot_pred = model.predict(lot_X)
      lot_proba = model.predict_proba(lot_X)[:, 1] if hasattr(model, "predict_proba") else None
      lot_metrics = _compute_ivd_metrics(lot_y, lot_pred, lot_proba)
      per_lot.append(PerLotEvaluation(
        kit_lot=str(lot),
        sample_count=len(lot_df),
        confusion_matrix=lot_metrics["confusion_matrix"],
        sensitivity=lot_metrics["sensitivity"].value,
        specificity=lot_metrics["specificity"].value,
      ))

  return IVDEvaluationResult(
    accuracy=overall["accuracy"],
    sensitivity=overall["sensitivity"],
    specificity=overall["specificity"],
    ppv=overall["ppv"],
    npv=overall["npv"],
    roc_auc=overall["roc_auc"],
    confusion_matrix=overall["confusion_matrix"],
    roc_curve=overall["roc_curve"],
    cross_validation=cv_folds,
    per_lot=per_lot,
    feature_columns=features,
  )
