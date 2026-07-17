"""استخراج ویژگی‌های کلیدی از داده‌های کیت تشخیصی."""

import numpy as np

from barekat_diagnostics.pipeline.preprocessing import preprocess_curve


def estimate_ct(curve: np.ndarray, threshold: float = 0.5) -> float:
  """تخمین Ct value از منحنی رشد."""
  processed = preprocess_curve(curve)
  crossings = np.where(processed >= threshold)[0]
  if len(crossings) == 0:
    return 45.0
  return float(crossings[0] + 1)


def extract_curve_features(curve: list[float] | np.ndarray) -> dict[str, float]:
  """استخراج ویژگی‌های منحنی qPCR."""
  arr = np.asarray(curve, dtype=float)
  processed = preprocess_curve(arr)

  return {
    "ct_value": estimate_ct(arr),
    "max_amplitude": float(processed.max()),
    "baseline": float(processed[:5].mean()),
    "slope": float(np.polyfit(np.arange(len(processed)), processed, 1)[0]),
    "auc": float(np.trapezoid(processed)),
    "peak_cycle": float(np.argmax(processed) + 1),
  }


def extract_sample_features(
  features: dict[str, float],
  ct_value: float | None = None,
  curve_data: list[float] | None = None,
) -> dict[str, float]:
  """ترکیب ویژگی‌های ورودی و استخراج‌شده."""
  result = dict(features)
  if ct_value is not None:
    result["ct_value"] = ct_value
  if curve_data:
    result.update(extract_curve_features(curve_data))
  return result
