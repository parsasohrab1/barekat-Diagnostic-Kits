"""Tests for synthetic data generation."""

from barekat_diagnostics.data.synthetic import generate_diagnostic_kit_data


def test_generate_data_shape():
  df = generate_diagnostic_kit_data(n_samples=100, n_features=12)
  assert len(df) == 100
  assert "True_Status" in df.columns
  assert "Ct_Value" in df.columns
  assert "Quality_Score" in df.columns


def test_generate_data_distribution():
  df = generate_diagnostic_kit_data(n_samples=1000)
  positive_ratio = df["True_Status"].mean()
  assert 0.2 < positive_ratio < 0.4
