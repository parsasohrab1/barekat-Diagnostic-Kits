"""Diagnostic sample processing pipeline."""

import json
from typing import Callable

from barekat_diagnostics.kits.registry import get_kit_adapter
from barekat_diagnostics.pipeline.report import build_diagnosis_report, sample_to_raw_data
from barekat_diagnostics.schemas import DiagnosisReport, ModelExplanation, SampleInput


def process_sample(
  sample: SampleInput,
  model_predict_fn: Callable[..., tuple],
  calibration: dict | None = None,
  explain_fn: Callable[[dict[str, float]], ModelExplanation] | None = None,
) -> DiagnosisReport:
  """Full processing: QC → feature extraction → prediction → structured report."""
  adapter = get_kit_adapter(sample.kit_type)
  raw_data = sample_to_raw_data(sample)
  features = adapter.extract_features(raw_data)
  qc = adapter.run_qc(raw_data, features)

  if not qc.is_reliable:
    return build_diagnosis_report(
      sample=sample,
      result="inconclusive",
      confidence=0.0,
      qc=qc,
      calibration=calibration,
    )

  prediction = model_predict_fn(features)
  if len(prediction) == 3:
    result, confidence, model_version = prediction
  else:
    result, confidence = prediction
    model_version = "v1"

  explanation = explain_fn(features) if explain_fn else None

  return build_diagnosis_report(
    sample=sample,
    result=result,
    confidence=confidence,
    qc=qc,
    calibration=calibration,
    model_version=model_version,
    explanation=explanation,
  )


def report_to_json(report: DiagnosisReport) -> str:
  return json.dumps(report.model_dump(mode="json"), ensure_ascii=False)
