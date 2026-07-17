"""Tests for structured diagnosis reports."""

from barekat_diagnostics.pipeline.report import build_diagnosis_report, determine_recommendation
from barekat_diagnostics.kits.base import QCFlag, QCResult, QCSeverity
from barekat_diagnostics.schemas import SampleInput


def test_recommendation_invalid_on_critical():
  qc = QCResult(
    passed=False,
    flags=[QCFlag("CAL", "error", QCSeverity.CRITICAL)],
    is_reliable=False,
  )
  assert determine_recommendation("positive", qc, 0.9) == "invalid"


def test_structured_report_has_clinical_metrics():
  sample = SampleInput(sample_id="S0001", kit_type="qpcr", ct_value=22.0, quality_score=0.9)
  qc = QCResult(passed=True, flags=[], is_reliable=True)
  report = build_diagnosis_report(sample, "positive", 0.92, qc)
  assert report.clinical_metrics.primary_value == 22.0
  assert report.clinical_metrics.cutoff == 30.0
  assert report.recommendation == "report"


def test_pdf_generation():
  from barekat_diagnostics.reports.pdf import generate_report_pdf

  sample = SampleInput(sample_id="S0001", kit_type="elisa", od_ratio=1.5, quality_score=0.9)
  qc = QCResult(passed=True, flags=[], is_reliable=True)
  report = build_diagnosis_report(sample, "positive", 0.88, qc)
  pdf = generate_report_pdf(report)
  assert pdf[:4] == b"%PDF"
