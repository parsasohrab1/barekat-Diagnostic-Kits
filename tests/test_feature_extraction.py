"""Tests for feature extraction."""

import numpy as np

from barekat_diagnostics.pipeline.feature_extraction import estimate_ct, extract_curve_features


def test_estimate_ct_positive_curve():
  curve = list(1 / (1 + np.exp(-0.5 * (np.arange(40) - 20))))
  ct = estimate_ct(np.array(curve))
  assert 15 < ct < 25


def test_extract_curve_features():
  curve = [0.1] * 10 + list(np.linspace(0.1, 1.0, 30))
  features = extract_curve_features(curve)
  assert "ct_value" in features
  assert "max_amplitude" in features
  assert features["max_amplitude"] > 0
