"""Tests for IVD evaluation pipeline."""

from barekat_diagnostics.data.synthetic import generate_diagnostic_kit_data
from barekat_diagnostics.ml.evaluation import evaluate_model
from barekat_diagnostics.ml.features import build_model, prepare_features


def test_ivd_metrics_with_ci():
  df = generate_diagnostic_kit_data(n_samples=400, realistic=True)
  X, y, _ = prepare_features(df)
  model = build_model()
  model.fit(X, y)
  result = evaluate_model(df, model=model)

  assert 0.0 <= result.sensitivity.value <= 1.0
  assert result.sensitivity.ci_lower <= result.sensitivity.value <= result.sensitivity.ci_upper
  assert 0.0 <= result.roc_auc <= 1.0
  assert result.confusion_matrix.tp + result.confusion_matrix.tn >= 0


def test_cross_validation_by_lab():
  df = generate_diagnostic_kit_data(n_samples=600, realistic=True)
  X, y, _ = prepare_features(df)
  model = build_model()
  model.fit(X, y)
  result = evaluate_model(df, model=model)
  assert len(result.cross_validation) >= 1


def test_per_lot_confusion_matrix():
  df = generate_diagnostic_kit_data(n_samples=600, realistic=True)
  X, y, _ = prepare_features(df)
  model = build_model()
  model.fit(X, y)
  result = evaluate_model(df, model=model)
  assert len(result.per_lot) == df["Kit_Lot"].nunique()
  for lot_eval in result.per_lot:
    cm = lot_eval.confusion_matrix
    assert cm.tp + cm.tn + cm.fp + cm.fn == lot_eval.sample_count


def test_headline_metrics_are_out_of_fold_not_resubstitution():
  df = generate_diagnostic_kit_data(n_samples=400, realistic=True)
  result = evaluate_model(df)
  assert result.evaluation_basis.startswith("out_of_fold")
  assert result.confusion_matrix.tp + result.confusion_matrix.fn + result.confusion_matrix.tn + result.confusion_matrix.fp == len(df)

  in_sample = evaluate_model(df, out_of_fold=False)
  assert in_sample.evaluation_basis == "resubstitution"
