"""Preprocessing of raw sensor data."""

import numpy as np


def remove_noise(signal: np.ndarray, window: int = 3) -> np.ndarray:
  """Noise removal with a moving average filter."""
  if len(signal) < window:
    return signal.copy()
  kernel = np.ones(window) / window
  return np.convolve(signal, kernel, mode="same")


def normalize(signal: np.ndarray) -> np.ndarray:
  """Normalize the signal to the range [0, 1]."""
  min_val, max_val = signal.min(), signal.max()
  if max_val - min_val < 1e-9:
    return np.zeros_like(signal)
  return (signal - min_val) / (max_val - min_val)


def preprocess_curve(curve: list[float] | np.ndarray) -> np.ndarray:
  """Full preprocessing of the qPCR growth curve."""
  arr = np.asarray(curve, dtype=float)
  denoised = remove_noise(arr)
  return normalize(denoised)
