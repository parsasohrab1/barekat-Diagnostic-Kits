"""Key feature extraction from diagnostic kit data."""

import numpy as np

from barekat_diagnostics.pipeline.preprocessing import remove_noise

_trapezoid = getattr(np, "trapezoid", None) or np.trapz  # numpy 2.x renamed trapz

# Ct value reported when no amplification is detected (conventional "undetermined").
UNDETERMINED_CT = 45.0

BASELINE_CYCLES = (2, 12)  # 0-based slice used to estimate baseline level and noise
THRESHOLD_NOISE_SD = 10.0  # threshold = baseline + 10 x baseline SD (instrument convention)
THRESHOLD_MIN_RISE_FRACTION = 0.10  # floor so noise-free curves do not cross at cycle ~1
AMPLIFICATION_MIN_SNR = 8.0  # rise above baseline must exceed this many noise SDs
NOISE_FLOOR_FRACTION = 0.005  # noise SD floor, relative to the curve's dynamic range


def _baseline_stats(arr: np.ndarray) -> tuple[float, float]:
  lo, hi = BASELINE_CYCLES
  window = arr[lo:min(hi, len(arr))]
  if window.size < 3:
    window = arr[: max(3, len(arr) // 4)]
  # detrend so slow baseline drift is not counted as noise
  x = np.arange(window.size)
  slope, intercept = np.polyfit(x, window, 1)
  residual = window - (slope * x + intercept)
  return float(window.mean()), float(residual.std(ddof=1)) if window.size > 2 else 0.0


def analyze_curve(curve: list[float] | np.ndarray) -> dict[str, float]:
  """
  Baseline-subtracted threshold analysis of a raw qPCR fluorescence curve.

  The curve is NOT rescaled per sample: a no-template curve must stay flat so that it
  is reported as "not amplified" instead of being stretched into a sigmoid.
  """
  arr = np.asarray(curve, dtype=float)
  if arr.size < 10 or not np.all(np.isfinite(arr)):
    return {
      "ct_value": UNDETERMINED_CT, "amplified": 0.0, "max_amplitude": 0.0,
      "baseline": float(np.nanmean(arr)) if arr.size else 0.0, "noise_sd": 0.0,
      "signal_to_noise": 0.0, "slope": 0.0, "auc": 0.0, "peak_cycle": 0.0,
      "rel_slope": 0.0, "rel_rise": 0.0, "rel_auc": 0.0,
    }

  smooth = remove_noise(arr, window=3)
  smooth[0], smooth[-1] = arr[0], arr[-1]  # 'same' convolution biases the edges
  baseline, noise_sd = _baseline_stats(arr)
  corrected = smooth - baseline

  rise = float(corrected.max())
  dynamic_range = float(np.ptp(arr)) or 1.0
  noise_sd = max(noise_sd, NOISE_FLOOR_FRACTION * dynamic_range)
  snr = rise / noise_sd
  amplified = snr >= AMPLIFICATION_MIN_SNR

  ct = UNDETERMINED_CT
  if amplified:
    threshold = max(THRESHOLD_NOISE_SD * noise_sd, THRESHOLD_MIN_RISE_FRACTION * rise)
    above = np.where(corrected >= threshold)[0]
    if above.size:
      i = int(above[0])
      if i == 0:
        ct = 1.0
      else:
        y0, y1 = corrected[i - 1], corrected[i]
        frac = (threshold - y0) / (y1 - y0) if y1 > y0 else 0.0
        ct = float(i + frac)  # cycle numbers are 1-based: index i-1 -> cycle i

  slope = float(np.max(np.diff(corrected))) if amplified else 0.0
  return {
    "ct_value": float(min(ct, UNDETERMINED_CT)),
    "amplified": 1.0 if amplified else 0.0,
    "max_amplitude": rise,
    "baseline": baseline,
    "noise_sd": noise_sd,
    "signal_to_noise": float(snr),
    "slope": slope,
    "auc": float(_trapezoid(np.clip(corrected, 0, None))),
    "peak_cycle": float(np.argmax(corrected) + 1),
    # scale-free shape descriptors: comparable across instruments with different gain
    "rel_slope": slope / rise if amplified and rise > 0 else 0.0,
    "rel_rise": rise / abs(baseline) if baseline else 0.0,
    "rel_auc": float(_trapezoid(np.clip(corrected, 0, None))) / (rise * arr.size) if rise > 0 else 0.0,
  }


def estimate_ct(curve: np.ndarray, threshold: float | None = None) -> float:
  """Estimate the Ct value from the growth curve (no amplification -> 45)."""
  return analyze_curve(curve)["ct_value"]


def extract_curve_features(curve: list[float] | np.ndarray) -> dict[str, float]:
  """Extract qPCR curve features."""
  return analyze_curve(curve)


def extract_sample_features(
  features: dict[str, float],
  ct_value: float | None = None,
  curve_data: list[float] | None = None,
) -> dict[str, float]:
  """Combine supplied and extracted features."""
  result = dict(features)
  if ct_value is not None:
    result["ct_value"] = ct_value
  if curve_data:
    result.update(extract_curve_features(curve_data))
  return result
