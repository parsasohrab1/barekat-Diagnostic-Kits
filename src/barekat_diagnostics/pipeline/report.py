"""Build a structured diagnosis report."""

from datetime import datetime, timezone
from typing import Any, Literal

from barekat_diagnostics.kits.base import QCFlag, QCResult, QCSeverity
from barekat_diagnostics.kits.registry import get_kit_adapter
from barekat_diagnostics.schemas import (
  ClinicalMetricsSchema,
  DiagnosisReport,
  ModelExplanation,
  QCFlagSchema,
  SampleInput,
)


def determine_recommendation(
  result: str,
  qc: QCResult,
  confidence: float,
) -> Literal["report", "retest", "invalid", "reassess"]:
  if any(f.severity == QCSeverity.CRITICAL for f in qc.flags):
    return "invalid"
  if result == "inconclusive":
    return "retest"
  warning_count = sum(1 for f in qc.flags if f.severity == QCSeverity.WARNING)
  # Suspicious multi-flag pattern → clinical reassessment suggestion
  if warning_count >= 2 and confidence < 0.85:
    return "reassess"
  if warning_count >= 1 and confidence < 0.75:
    return "retest"
  return "report"


def _flags_to_schema(flags: list[QCFlag]) -> list[QCFlagSchema]:
  return [
    QCFlagSchema(code=f.code, message=f.message, severity=f.severity.value)
    for f in flags
  ]


def sample_to_raw_data(sample: SampleInput) -> dict[str, Any]:
  return sample.model_dump(exclude_none=True)


def build_diagnosis_report(
  sample: SampleInput,
  result: str,
  confidence: float,
  qc: QCResult,
  calibration: dict[str, Any] | None = None,
  report_id: int | None = None,
  model_version: str = "v1",
  explanation: ModelExplanation | None = None,
) -> DiagnosisReport:
  adapter = get_kit_adapter(sample.kit_type)
  raw_data = sample_to_raw_data(sample)
  features = adapter.extract_features(raw_data)
  metrics = adapter.build_clinical_metrics(features, calibration)
  recommendation = determine_recommendation(result, qc, confidence)

  return DiagnosisReport(
    report_id=report_id,
    sample_id=sample.sample_id,
    kit_type=sample.kit_type,
    result=result,  # type: ignore[arg-type]
    confidence=confidence,
    qc_passed=qc.passed,
    qc_flags=_flags_to_schema(qc.flags),
    recommendation=recommendation,
    clinical_metrics=ClinicalMetricsSchema(
      primary_value=metrics.primary_value,
      cutoff=metrics.cutoff,
      confidence_interval=metrics.confidence_interval,
      unit=metrics.unit,
      label=metrics.label,
    ),
    model_version=model_version,
    explanation=explanation,
    created_at=datetime.now(timezone.utc),
  )
