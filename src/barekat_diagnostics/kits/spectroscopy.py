"""Spectroscopy kit adapter."""

from typing import Any

import numpy as np

from barekat_diagnostics.core.config import get_settings
from barekat_diagnostics.kits.base import (
  ClinicalMetrics,
  KitAdapter,
  KitType,
  QCFlag,
  QCResult,
  QCSeverity,
)


class SpectroscopyKitAdapter(KitAdapter):
  kit_type = KitType.SPECTROSCOPY
  default_cutoff = 0.5

  def extract_features(self, raw_data: dict[str, Any]) -> dict[str, float]:
    features = dict(raw_data.get("features") or {})

    peak = raw_data.get("peak_intensity")
    if peak is not None:
      features["peak_intensity"] = float(peak)

    bands = raw_data.get("wavelength_bands") or {}
    for band, intensity in bands.items():
      features[f"band_{band}"] = float(intensity)

    if bands and "peak_intensity" not in features:
      features["peak_intensity"] = float(max(bands.values()))

    spectrum = raw_data.get("spectrum")
    if spectrum:
      arr = np.asarray(spectrum, dtype=float)
      features["spectrum_mean"] = float(arr.mean())
      features["spectrum_max"] = float(arr.max())
      if "peak_intensity" not in features:
        features["peak_intensity"] = float(arr.max())

    for key in ("quality_score", "signal_to_noise"):
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
        message=f"Low quality score: {quality:.2f}",
        severity=QCSeverity.CRITICAL,
      ))

    snr = raw_data.get("signal_to_noise") or features.get("signal_to_noise")
    if snr is not None and snr < settings.qc_min_signal_to_noise:
      flags.append(QCFlag(
        code="LOW_SNR",
        message=f"Low signal-to-noise ratio: {snr:.2f}",
        severity=QCSeverity.WARNING,
      ))

    peak = features.get("peak_intensity")
    if peak is not None and peak <= 0:
      flags.append(QCFlag(
        code="NO_PEAK",
        message="No detectable peak found",
        severity=QCSeverity.CRITICAL,
      ))

    bands = raw_data.get("wavelength_bands") or {}
    if bands and len(bands) < 2:
      flags.append(QCFlag(
        code="INSUFFICIENT_BANDS",
        message="Insufficient number of spectral bands",
        severity=QCSeverity.WARNING,
      ))

    has_critical = any(f.severity == QCSeverity.CRITICAL for f in flags)
    passed = quality is None or quality >= settings.qc_min_quality_score
    return QCResult(passed=passed, flags=flags, is_reliable=not has_critical)

  def build_clinical_metrics(
    self,
    features: dict[str, float],
    calibration: dict[str, Any] | None = None,
  ) -> ClinicalMetrics:
    peak = features.get("peak_intensity")
    cutoff = self.get_cutoff(calibration)
    ci = self.confidence_interval(peak, 0.85) if peak is not None else None
    return ClinicalMetrics(
      primary_value=peak,
      cutoff=cutoff,
      confidence_interval=ci,
      unit="a.u.",
      label="Peak Intensity",
    )
