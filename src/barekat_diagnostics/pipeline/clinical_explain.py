"""توضیح‌پذیری بالینی برای پزشک و بایولوژیست."""

from __future__ import annotations

from barekat_diagnostics.schemas import (
  ClinicalExplanation,
  ClinicalInsight,
  DiagnosisReport,
  SampleInput,
)


_FEATURE_CLINICAL = {
  "ct_value": ("Ct value", "Threshold cycle — lower suggests higher target load"),
  "Ct_Value": ("Ct value", "Threshold cycle — lower suggests higher target load"),
  "od_ratio": ("OD ratio", "Optical density ratio vs blank/cutoff"),
  "peak_intensity": ("Peak intensity", "Spectral peak intensity of analyte"),
  "signal_to_noise": ("Signal-to-noise", "Assay signal relative to background noise"),
  "amplification_efficiency": ("Amplification efficiency", "PCR amplification efficiency"),
  "quality_score": ("Quality score", "Overall curve/signal quality metric"),
  "Signal_to_Noise": ("Signal-to-noise", "Assay signal relative to background noise"),
  "Amplification_Efficiency": ("Amplification efficiency", "PCR amplification efficiency"),
  "Quality_Score": ("Quality score", "Overall curve/signal quality metric"),
}

_QC_CLINICAL = {
  "LOW_QUALITY": "Overall signal quality is below the laboratory acceptance threshold.",
  "LOW_SNR": "Signal-to-noise is low; distinguish true amplification from noise carefully.",
  "LOW_AMP_EFF": "Amplification efficiency is suboptimal; consider reagent or thermal issues.",
  "ABNORMAL_CT": "Ct is outside the expected analytical range.",
  "CALIBRATION_ERROR": "Calibration check failed; do not report until recalibrated.",
}


def build_clinical_explanation(
  report: DiagnosisReport,
  sample: SampleInput | None = None,
  calibration: dict | None = None,
) -> ClinicalExplanation:
  """ساخت روایت بالینی قابل‌فهم برای پزشک/بایولوژیست."""
  insights: list[ClinicalInsight] = []
  metrics = report.clinical_metrics
  kit = report.kit_type

  # نتیجه در برابر cutoff
  if metrics.primary_value is not None and metrics.cutoff is not None:
    if kit == "qpcr":
      delta = metrics.cutoff - metrics.primary_value
      if report.result == "positive":
        msg = (
          f"Ct={metrics.primary_value:.2f} is below cutoff {metrics.cutoff:.2f} "
          f"(Δ={delta:.2f} cycles), consistent with detectable target nucleic acid."
        )
      elif report.result == "negative":
        msg = (
          f"Ct={metrics.primary_value:.2f} is at/above cutoff {metrics.cutoff:.2f}, "
          "consistent with non-detection or below LoD."
        )
      else:
        msg = f"Ct={metrics.primary_value:.2f} near cutoff {metrics.cutoff:.2f}; interpret with QC."
      insights.append(
        ClinicalInsight(
          category="assay",
          title="Ct vs cutoff",
          detail=msg,
          severity="info" if report.qc_passed else "warning",
        )
      )
    else:
      direction = "above" if metrics.primary_value >= metrics.cutoff else "below"
      insights.append(
        ClinicalInsight(
          category="assay",
          title=f"{metrics.label} vs cutoff",
          detail=(
            f"{metrics.label}={metrics.primary_value:.3f} {metrics.unit} is {direction} "
            f"cutoff {metrics.cutoff:.3f}."
          ),
          severity="info",
        )
      )

  # QC narrative
  for flag in report.qc_flags:
    insights.append(
      ClinicalInsight(
        category="qc",
        title=flag.code,
        detail=_QC_CLINICAL.get(flag.code, flag.message),
        severity=flag.severity,
      )
    )

  # ML feature contributions → clinical language
  if report.explanation:
    for feat in report.explanation.top_features[:5]:
      label, meaning = _FEATURE_CLINICAL.get(
        feat.feature,
        (feat.feature, "Model feature contributing to the classification"),
      )
      direction = "supports positive call" if feat.direction == "positive" else "supports negative call"
      insights.append(
        ClinicalInsight(
          category="model",
          title=label,
          detail=f"{meaning}. Value={feat.value}; contribution={feat.contribution:.3f} ({direction}).",
          severity="info",
        )
      )

  # Recommendation narrative
  rec_text = {
    "report": "Result is suitable for clinical reporting after local review policy.",
    "retest": "Retest is recommended before final reporting.",
    "invalid": "Result is analytically invalid; do not report — investigate QC first.",
    "reassess": "Suspicious QC pattern — reassessment / reflex testing is advised.",
  }.get(report.recommendation, report.recommendation)

  insights.append(
    ClinicalInsight(
      category="recommendation",
      title="Action",
      detail=rec_text,
      severity="warning" if report.recommendation != "report" else "info",
    )
  )

  summary = _summary_sentence(report)
  return ClinicalExplanation(
    summary=summary,
    audience="physician_biologist",
    insights=insights,
    model_explanation=report.explanation,
    confidence_note=_confidence_note(report.confidence),
  )


def _summary_sentence(report: DiagnosisReport) -> str:
  kit = report.kit_type.upper()
  result = report.result
  conf = report.confidence * 100
  if result == "inconclusive":
    return (
      f"{kit} assay for sample {report.sample_id} is inconclusive "
      f"(confidence {conf:.0f}%). Review QC and consider reassessment."
    )
  return (
    f"{kit} assay for sample {report.sample_id} is {result} "
    f"with model confidence {conf:.0f}% (model {report.model_version})."
  )


def _confidence_note(confidence: float) -> str:
  if confidence >= 0.9:
    return "High model confidence."
  if confidence >= 0.75:
    return "Moderate model confidence — clinical correlation advised."
  if confidence > 0:
    return "Low model confidence — expert review recommended."
  return "No model confidence (QC blocked inference)."
