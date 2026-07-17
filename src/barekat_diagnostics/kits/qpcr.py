"""آداپتور کیت qPCR."""

from typing import Any

from barekat_diagnostics.core.config import get_settings
from barekat_diagnostics.kits.base import (
  ClinicalMetrics,
  KitAdapter,
  KitType,
  QCFlag,
  QCResult,
  QCSeverity,
)
from barekat_diagnostics.pipeline.feature_extraction import extract_curve_features


class QpcrKitAdapter(KitAdapter):
  kit_type = KitType.QPCR
  default_cutoff = 30.0

  def extract_features(self, raw_data: dict[str, Any]) -> dict[str, float]:
    features = dict(raw_data.get("features") or {})
    ct_value = raw_data.get("ct_value")
    curve_data = raw_data.get("curve_data")

    if ct_value is not None:
      features["ct_value"] = float(ct_value)
    if curve_data:
      curve_features = extract_curve_features(curve_data)
      features.update(curve_features)
      if ct_value is not None:
        features["ct_value"] = float(ct_value)

    for key in ("signal_to_noise", "amplification_efficiency", "quality_score"):
      if raw_data.get(key) is not None:
        features[key] = float(raw_data[key])

    return features

  def run_qc(self, raw_data: dict[str, Any], features: dict[str, float]) -> QCResult:
    settings = get_settings()
    flags: list[QCFlag] = []

    quality = raw_data.get("quality_score")
    if quality is not None and quality < settings.qc_min_quality_score:
      flags.append(QCFlag(
        code="LOW_QUALITY",
        message=f"امتیاز کیفیت پایین: {quality:.2f}",
        severity=QCSeverity.CRITICAL,
      ))

    snr = raw_data.get("signal_to_noise")
    if snr is not None and snr < settings.qc_min_signal_to_noise:
      flags.append(QCFlag(
        code="LOW_SNR",
        message=f"نسبت سیگنال به نویز پایین: {snr:.2f}",
        severity=QCSeverity.WARNING,
      ))

    amp_eff = raw_data.get("amplification_efficiency")
    if amp_eff is not None and amp_eff < settings.qc_min_amplification_efficiency:
      flags.append(QCFlag(
        code="LOW_AMP_EFF",
        message=f"بازدهی تکثیر پایین: {amp_eff:.2f}",
        severity=QCSeverity.WARNING,
      ))

    if raw_data.get("calibration_error"):
      flags.append(QCFlag(
        code="CALIBRATION_ERROR",
        message="خطای کالیبراسیون شناسایی شد",
        severity=QCSeverity.CRITICAL,
      ))

    ct = features.get("ct_value")
    if ct is not None and (ct < 10 or ct > 45):
      flags.append(QCFlag(
        code="ABNORMAL_CT",
        message=f"مقدار Ct غیرعادی: {ct:.1f}",
        severity=QCSeverity.WARNING,
      ))

    has_critical = any(f.severity == QCSeverity.CRITICAL for f in flags)
    passed = quality is None or quality >= settings.qc_min_quality_score
    return QCResult(passed=passed, flags=flags, is_reliable=not has_critical and len(flags) == 0)

  def build_clinical_metrics(
    self,
    features: dict[str, float],
    calibration: dict[str, Any] | None = None,
  ) -> ClinicalMetrics:
    ct = features.get("ct_value")
    cutoff = self.get_cutoff(calibration)
    ci = self.confidence_interval(ct, 0.85) if ct is not None else None
    return ClinicalMetrics(
      primary_value=ct,
      cutoff=cutoff,
      confidence_interval=ci,
      unit="cycles",
      label="Ct Value",
    )
