"""تست تولید داده سنتتیک."""

from barekat_diagnostics.data.synthetic import generate_diagnostic_kit_data


def test_generate_synthetic_data():
  df = generate_diagnostic_kit_data(n_samples=100)
  assert len(df) == 100
  assert "True_Status" in df.columns
  assert "Ct_Value" in df.columns
  assert set(df["True_Status"].unique()).issubset({0, 1})
