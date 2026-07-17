"""Tests for QC module."""

from barekat_diagnostics.pipeline.qc import run_qc
from barekat_diagnostics.schemas import SampleInput


def test_qc_passes_good_sample():
  sample = SampleInput(
    sample_id="S0001",
    ct_value=22.0,
    quality_score=0.9,
    signal_to_noise=3.0,
    amplification_efficiency=0.95,
  )
  result = run_qc(sample)
  assert result.passed is True
  assert result.is_reliable is True
  assert len(result.warnings) == 0


def test_qc_warns_low_quality():
  sample = SampleInput(
    sample_id="S0002",
    ct_value=22.0,
    quality_score=0.3,
    signal_to_noise=1.0,
    calibration_error=True,
  )
  result = run_qc(sample)
  assert result.is_reliable is False
  assert len(result.warnings) >= 2
