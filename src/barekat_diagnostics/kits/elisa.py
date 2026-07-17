"""آداپتور کیت ELISA."""

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


class ElisaKitAdapter(KitAdapter):
  kit_type = KitType.ELISA
  default_cutoff = 1.0

  def extract_features(self, raw_data: dict[str, Any]) -> dict[str, float]:
    features = dict(raw_data.get("features") or {})
    od_450 = raw_data.get("od_450")
    od_620 = raw_data.get("od_620")
    od_ratio = raw_data.get("od_ratio")

    if od_450 is not None:
      features["od_450"] = float(od_450)
    if od_620 is not None:
      features["od_620"] = float(od_620)
    if od_ratio is not None:
      features["od_ratio"] = float(od_ratio)
    elif od_450 is not None and od_620 is not None and od_620 > 0:
      features["od_ratio"] = float(od_450) / float(od_620)

    for key in ("quality_score", "blank_od"):
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

    blank_od = features.get("blank_od")
    od_450 = features.get("od_450")
    if blank_od is not None and od_450 is not None and od_450 < blank_od * 1.1:
      flags.append(QCFlag(
        code="BELOW_BLANK",
        message=f"OD نمونه نزدیک blank: {od_450:.3f}",
        severity=QCSeverity.WARNING,
      ))

    od_ratio = features.get("od_ratio")
    if od_ratio is not None and od_ratio < 0:
      flags.append(QCFlag(
        code="INVALID_OD_RATIO",
        message="نسبت OD نامعتبر",
        severity=QCSeverity.CRITICAL,
      ))

    if raw_data.get("calibration_error"):
      flags.append(QCFlag(
        code="CALIBRATION_ERROR",
        message="خطای کالیبراسیون کیت",
        severity=QCSeverity.CRITICAL,
      ))

    has_critical = any(f.severity == QCSeverity.CRITICAL for f in flags)
    passed = quality is None or quality >= settings.qc_min_quality_score
    return QCResult(passed=passed, flags=flags, is_reliable=not has_critical)

  def build_clinical_metrics(
    self,
    features: dict[str, float],
    calibration: dict[str, Any] | None = None,
  ) -> ClinicalMetrics:
    od_ratio = features.get("od_ratio")
    cutoff = self.get_cutoff(calibration)
    ci = self.confidence_interval(od_ratio, 0.85) if od_ratio is not None else None
    return ClinicalMetrics(
      primary_value=od_ratio,
      cutoff=cutoff,
      confidence_interval=ci,
      unit="ratio",
      label="OD Ratio",
    )
