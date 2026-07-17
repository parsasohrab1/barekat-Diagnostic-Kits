"""پیش‌پردازش داده‌های خام حسگر."""

import numpy as np


def remove_noise(signal: np.ndarray, window: int = 3) -> np.ndarray:
  """حذف نویز با فیلتر میانگین متحرک."""
  if len(signal) < window:
    return signal.copy()
  kernel = np.ones(window) / window
  return np.convolve(signal, kernel, mode="same")


def normalize(signal: np.ndarray) -> np.ndarray:
  """نرمال‌سازی سیگنال به بازه [0, 1]."""
  min_val, max_val = signal.min(), signal.max()
  if max_val - min_val < 1e-9:
    return np.zeros_like(signal)
  return (signal - min_val) / (max_val - min_val)


def preprocess_curve(curve: list[float] | np.ndarray) -> np.ndarray:
  """پیش‌پردازش کامل منحنی رشد qPCR."""
  arr = np.asarray(curve, dtype=float)
  denoised = remove_noise(arr)
  return normalize(denoised)
