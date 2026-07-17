"""Tests for model explainability."""

from barekat_diagnostics.ml.explainability import explain_prediction
from barekat_diagnostics.ml.features import build_model, prepare_features
from barekat_diagnostics.data.synthetic import generate_diagnostic_kit_data


def test_explain_prediction_returns_top_features():
  df = generate_diagnostic_kit_data(n_samples=200, realistic=False)
  X, y, cols = prepare_features(df)
  model = build_model()
  model.fit(X, y)

  features = {col: float(df[col].iloc[0]) for col in cols}
  explanation = explain_prediction(model, cols, features)

  assert explanation.predicted_class in ("positive", "negative")
  assert len(explanation.top_features) > 0
  assert explanation.top_features[0].feature in cols
