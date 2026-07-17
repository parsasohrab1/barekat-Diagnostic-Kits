"""Tests for realistic synthetic data."""

from barekat_diagnostics.data.synthetic import generate_diagnostic_kit_data


def test_realistic_data_has_lab_and_lot():
  df = generate_diagnostic_kit_data(n_samples=200, realistic=True)
  assert "Lab_Device" in df.columns
  assert "Kit_Lot" in df.columns
  assert "Day_Index" in df.columns
  assert df["Lab_Device"].nunique() >= 2
  assert df["Kit_Lot"].nunique() >= 2


def test_borderline_samples_near_cutoff():
  df = generate_diagnostic_kit_data(n_samples=500, realistic=True, borderline_fraction=0.1)
  near_cutoff = df[(df["Ct_Value"] >= 28) & (df["Ct_Value"] <= 32)]
  assert len(near_cutoff) >= 20


def test_simple_mode_still_works():
  df = generate_diagnostic_kit_data(n_samples=50, realistic=False)
  assert len(df) == 50
  assert "True_Status" in df.columns
