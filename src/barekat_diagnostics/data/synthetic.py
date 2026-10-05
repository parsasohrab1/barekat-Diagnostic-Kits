"""Generate realistic synthetic data for diagnostic kits."""

import numpy as np
import pandas as pd

LAB_DEVICES = ["Lab-A", "Lab-B", "Lab-C"]
KIT_LOTS = ["LOT-2026-A", "LOT-2026-B", "LOT-2026-C"]

DEVICE_BATCH_EFFECT = {
  "Lab-A": {"ct_shift": 0.0, "noise_scale": 1.0},
  "Lab-B": {"ct_shift": 1.5, "noise_scale": 1.2},
  "Lab-C": {"ct_shift": -0.8, "noise_scale": 0.9},
}

LOT_CALIBRATION_DRIFT = {
  "LOT-2026-A": 0.0,
  "LOT-2026-B": 0.3,
  "LOT-2026-C": -0.2,
}


def generate_diagnostic_kit_data(
  n_samples: int = 1000,
  n_features: int = 12,
  *,
  realistic: bool = True,
  borderline_fraction: float = 0.08,
  seed: int = 42,
) -> pd.DataFrame:
  """
  Generate synthetic data with batch effect, calibration drift and borderline samples.

  realistic=True: simulate differences between devices, lots and samples close to the cutoff
  """
  rng = np.random.default_rng(seed)

  true_status = rng.choice([0, 1], n_samples, p=[0.70, 0.30])
  lab_devices = rng.choice(LAB_DEVICES, n_samples)
  kit_lots = rng.choice(KIT_LOTS, n_samples)
  day_index = rng.integers(0, 90, n_samples)

  feature_data: dict[str, np.ndarray] = {}
  for i in range(n_features):
    base_signal = rng.normal(0.5, 0.15, n_samples)
    base_signal = np.clip(base_signal, 0, 1.5)
    positive_boost = rng.normal(0.3, 0.1, n_samples) * true_status
    feature_data[f"Feature_{i + 1}"] = base_signal + positive_boost
    if i > 5:
      noise = rng.normal(0, 0.05, n_samples) * rng.choice([0, 1], n_samples, p=[0.70, 0.30])
      feature_data[f"Feature_{i + 1}"] += noise

  ct_values = np.zeros(n_samples)
  for i in range(n_samples):
    if true_status[i] == 1:
      ct_values[i] = rng.normal(18, 3)
    else:
      ct_values[i] = rng.normal(35, 5)
  ct_values = np.clip(ct_values, 12, 45)

  if realistic:
    for i in range(n_samples):
      device = lab_devices[i]
      lot = kit_lots[i]
      effect = DEVICE_BATCH_EFFECT[device]
      drift = LOT_CALIBRATION_DRIFT[lot] + day_index[i] * 0.005
      ct_values[i] += effect["ct_shift"] + drift
      scale = effect["noise_scale"]
      for j in range(n_features):
        feature_data[f"Feature_{j + 1}"][i] += rng.normal(0, 0.03 * scale)

    n_borderline = int(n_samples * borderline_fraction)
    borderline_idx = rng.choice(n_samples, size=n_borderline, replace=False)
    for i in borderline_idx:
      ct_values[i] = rng.uniform(28.0, 32.0)
      true_status[i] = rng.choice([0, 1], p=[0.55, 0.45])

  calibration_error = rng.choice([0, 1], n_samples, p=[0.90, 0.10])
  for i in range(n_samples):
    if calibration_error[i] == 1:
      for j in range(n_features):
        feature_data[f"Feature_{j + 1}"][i] *= rng.uniform(0.8, 1.2)

  ct_values = np.clip(ct_values, 12, 45)

  df = pd.DataFrame({
    "Sample_ID": [f"S{str(i).zfill(4)}" for i in range(n_samples)],
    "True_Status": true_status,
    "Ct_Value": np.round(ct_values, 2),
    "Calibration_Error": calibration_error,
    "Lab_Device": lab_devices,
    "Kit_Lot": kit_lots,
    "Day_Index": day_index,
  })

  for feat_name, feat_values in feature_data.items():
    df[feat_name] = np.round(feat_values, 4)

  df["Signal_to_Noise"] = np.round(rng.uniform(1.5, 4.0, n_samples), 3)
  df["Amplification_Efficiency"] = np.round(rng.uniform(0.85, 1.05, n_samples), 3)
  df["Quality_Score"] = np.round(rng.uniform(0.6, 0.99, n_samples), 3)

  unreliable_idx = rng.choice(n_samples, size=int(n_samples * 0.05), replace=False)
  df.loc[unreliable_idx, "Quality_Score"] = np.round(
    rng.uniform(0.2, 0.5, len(unreliable_idx)), 3
  )

  return df
