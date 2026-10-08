"""
Raw qPCR fluorescence-curve simulator for end-to-end (curve -> Ct -> call) validation.

Ground truth is the *number of template molecules actually present* (Poisson-sampled at low
copy number), never a Ct cutoff. This keeps the label independent of the analysis under test.

This is a SIMULATION. Results measured on it show the software behaves correctly under the
stated assumptions; they are not a substitute for real instrument runs / clinical specimens.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

N_CYCLES = 40


@dataclass(frozen=True)
class DeviceProfile:
  name: str
  gain: float  # fluorescence scale
  offset: float  # baseline level
  noise_sd: float  # read noise (fraction of gain)
  ct_shift: float  # systematic cycle offset (optics / thermal block)
  drift: float  # baseline drift per cycle (fraction of gain)


@dataclass(frozen=True)
class LotProfile:
  name: str
  efficiency: float  # mean per-cycle amplification efficiency
  ct1_shift: float  # shift of Ct at 1 copy (reagent activity)


DEVICES = {
  "QuantStudio-5": DeviceProfile("QuantStudio-5", 1.00, 0.05, 0.010, 0.0, 0.0005),
  "LightCycler480": DeviceProfile("LightCycler480", 1.60, 0.10, 0.014, 0.7, -0.0008),
  "CFX96": DeviceProfile("CFX96", 0.80, 0.03, 0.012, -0.5, 0.0010),
  # Never used for model fitting: held out to test cross-instrument transfer.
  "RotorGene-Q": DeviceProfile("RotorGene-Q", 1.30, 0.07, 0.020, 1.2, 0.0015),
}
TRAIN_DEVICES = ("QuantStudio-5", "LightCycler480", "CFX96")
HELDOUT_DEVICE = "RotorGene-Q"

LOTS = {
  "LOT-A": LotProfile("LOT-A", 0.97, 0.0),
  "LOT-B": LotProfile("LOT-B", 0.92, 0.5),
  "LOT-C": LotProfile("LOT-C", 0.88, 1.0),
}

CT_AT_ONE_COPY = 37.0  # nominal Ct for a single template molecule at E = 1.0


def _logistic_curve(cycles: np.ndarray, ct: float, amplitude: float, width: float) -> np.ndarray:
  """Sigmoid whose noiseless 10 % rise point sits at cycle `ct`."""
  mid = ct + width * np.log(9.0)  # logistic = 0.1 at (mid - width*ln 9)
  return amplitude / (1.0 + np.exp(-(cycles - mid) / width))


def simulate_curve(
  rng: np.random.Generator,
  device: DeviceProfile,
  lot: LotProfile,
  expected_copies: float,
  *,
  inhibited: bool = False,
  artifact: bool = False,
) -> tuple[np.ndarray, int, float | None]:
  """Return (curve, actual_copies, true_ct)."""
  cycles = np.arange(1, N_CYCLES + 1, dtype=float)
  actual = int(rng.poisson(expected_copies)) if expected_copies > 0 else 0

  eff = float(np.clip(rng.normal(lot.efficiency, 0.02), 0.6, 1.0))
  if inhibited:
    eff = float(np.clip(eff - rng.uniform(0.10, 0.25), 0.55, 1.0))

  signal = np.zeros(N_CYCLES)
  true_ct: float | None = None
  if actual > 0:
    true_ct = (
      CT_AT_ONE_COPY + lot.ct1_shift + device.ct_shift
      - np.log(actual) / np.log(1.0 + eff)
      + rng.normal(0, 0.15)
    )
    if inhibited:
      true_ct += rng.uniform(1.0, 3.0)
    true_ct = float(np.clip(true_ct, 8.0, 44.0))
    amp = device.gain * rng.uniform(0.85, 1.15) * (0.6 if inhibited else 1.0)
    signal = _logistic_curve(cycles, true_ct, amp, width=rng.uniform(1.1, 1.8))
  elif artifact:
    # primer-dimer / non-specific late rise in a template-free well: weak and shallow
    art_ct = rng.uniform(33.0, 39.0)
    signal = _logistic_curve(
      cycles, art_ct, device.gain * rng.uniform(0.08, 0.30), width=rng.uniform(2.2, 3.5)
    )

  baseline = device.offset * device.gain + device.drift * device.gain * cycles
  noise = rng.normal(0, device.noise_sd * device.gain, N_CYCLES)
  curve = baseline + signal + noise
  return curve, actual, true_ct


def generate_curve_dataset(
  n_samples: int = 600,
  *,
  seed: int = 7,
  devices: tuple[str, ...] = TRAIN_DEVICES,
  prevalence: float = 0.45,
  low_copy_fraction: float = 0.25,
  inhibition_rate: float = 0.05,
  artifact_rate: float = 0.06,
) -> pd.DataFrame:
  """
  Positives get an expected copy number drawn log-uniformly; `low_copy_fraction` of them are
  placed at 1-10 copies (the limit-of-detection region where Poisson dropout matters).
  """
  rng = np.random.default_rng(seed)
  rows = []
  for i in range(n_samples):
    device = DEVICES[str(rng.choice(devices))]
    lot = LOTS[str(rng.choice(list(LOTS)))]
    is_pos_intent = rng.random() < prevalence
    if not is_pos_intent:
      expected = 0.0
    elif rng.random() < low_copy_fraction:
      expected = float(rng.uniform(1.0, 10.0))
    else:
      expected = float(10 ** rng.uniform(1.0, 6.5))
    curve, actual, true_ct = simulate_curve(
      rng, device, lot, expected,
      inhibited=bool(is_pos_intent and rng.random() < inhibition_rate),
      artifact=bool(not is_pos_intent and rng.random() < artifact_rate),
    )
    rows.append({
      "Sample_ID": f"SIM-{seed}-{i:05d}",
      "Lab_Device": device.name,
      "Kit_Lot": lot.name,
      "Expected_Copies": expected,
      "Actual_Copies": actual,
      "True_Status": int(actual > 0),
      "True_Ct": true_ct,
      "Curve": curve.tolist(),
    })
  return pd.DataFrame(rows)
