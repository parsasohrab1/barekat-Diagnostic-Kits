"""Tests for kit adapters."""

from barekat_diagnostics.kits import get_kit_adapter
from barekat_diagnostics.kits.base import KitType


def test_qpcr_extract_features():
  adapter = get_kit_adapter(KitType.QPCR)
  features = adapter.extract_features({
    "ct_value": 22.0,
    "curve_data": [0.1] * 10 + [0.5, 0.8, 1.0, 1.2],
    "signal_to_noise": 3.0,
  })
  assert features["ct_value"] == 22.0
  assert "max_amplitude" in features


def test_elisa_extract_features():
  adapter = get_kit_adapter(KitType.ELISA)
  features = adapter.extract_features({"od_450": 2.0, "od_620": 1.0})
  assert features["od_ratio"] == 2.0


def test_spectroscopy_extract_features():
  adapter = get_kit_adapter(KitType.SPECTROSCOPY)
  features = adapter.extract_features({
    "wavelength_bands": {"450": 0.8, "620": 0.3},
    "peak_intensity": 0.8,
  })
  assert features["peak_intensity"] == 0.8
  assert features["band_450"] == 0.8


def test_elisa_qc_critical_on_low_quality():
  adapter = get_kit_adapter(KitType.ELISA)
  qc = adapter.run_qc({"quality_score": 0.2}, {"od_ratio": 1.5})
  assert qc.passed is False
  assert any(f.severity.value == "critical" for f in qc.flags)
