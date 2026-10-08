"""Regression tests for the raw-curve -> Ct -> call chain (defects found during TRL-5 audit)."""

import numpy as np
import pandas as pd
import pytest

from barekat_diagnostics.data.curves import DEVICES, LOTS, generate_curve_dataset, simulate_curve
from barekat_diagnostics.ml.classifier import FeatureMismatchError, build_feature_row
from barekat_diagnostics.ml.curve_model import CURVE_FEATURES, build_curve_model, curves_to_features
from barekat_diagnostics.ml.registry import dataset_hash
from barekat_diagnostics.pipeline.feature_extraction import UNDETERMINED_CT, analyze_curve
from barekat_diagnostics.pipeline.runner import process_sample
from barekat_diagnostics.schemas import SampleInput


def _flat_noisy(seed=0, level=0.05, noise=0.01):
  return level + np.random.default_rng(seed).normal(0, noise, 40)


def test_no_template_curve_is_not_amplified():
  # Regression: per-curve min-max scaling used to turn noise into "Ct = 2.0" (a strong positive).
  for seed in range(20):
    f = analyze_curve(_flat_noisy(seed))
    assert f["amplified"] == 0.0
    assert f["ct_value"] == UNDETERMINED_CT


def test_ct_recovered_within_one_cycle():
  cycles = np.arange(1, 41)
  for true_ct in (15.0, 22.5, 30.0, 35.0):
    mid = true_ct + 1.4 * np.log(9)
    curve = 0.05 + 1.0 / (1 + np.exp(-(cycles - mid) / 1.4))
    curve += np.random.default_rng(1).normal(0, 0.005, 40)
    assert abs(analyze_curve(curve)["ct_value"] - true_ct) < 1.0


def test_ct_is_invariant_to_instrument_gain():
  cycles = np.arange(1, 41)
  base = 0.05 + 1.0 / (1 + np.exp(-(cycles - 25) / 1.4))
  small = analyze_curve(base)["ct_value"]
  large = analyze_curve(base * 40)["ct_value"]
  assert small == pytest.approx(large, abs=0.2)


def test_short_or_nan_curve_is_undetermined():
  assert analyze_curve([0.1] * 5)["amplified"] == 0.0
  assert analyze_curve([0.1] * 20 + [float("nan")] * 5)["amplified"] == 0.0


def test_feature_row_is_case_insensitive_and_strict():
  row = build_feature_row({"ct_value": 20.0, "Signal_To_Noise": 3.0}, ["Ct_Value", "signal_to_noise"])
  assert row.tolist() == [[20.0, 3.0]]
  # Regression: missing columns used to be silently filled with 0.0
  with pytest.raises(FeatureMismatchError) as exc:
    build_feature_row({"ct_value": 20.0}, ["Ct_Value", "Feature_1"], "v1")
  assert exc.value.missing == ["Feature_1"]


def test_dataset_hash_distinguishes_same_size_datasets():
  a = pd.DataFrame({"True_Status": [0, 1, 1], "x": [1.0, 2.0, 3.0]})
  b = pd.DataFrame({"True_Status": [0, 1, 1], "x": [1.0, 2.0, 9.0]})
  assert dataset_hash(a) != dataset_hash(b)
  assert dataset_hash(a) == dataset_hash(a.copy())


def test_simulator_is_deterministic_and_truth_is_not_a_ct_cutoff():
  a = generate_curve_dataset(60, seed=3)
  b = generate_curve_dataset(60, seed=3)
  assert a.drop(columns="Curve").equals(b.drop(columns="Curve"))
  assert all(x == y for x, y in zip(a.Curve, b.Curve))
  pos = a[a.True_Status == 1]
  assert (pos.Actual_Copies > 0).all() and (a[a.True_Status == 0].Actual_Copies == 0).all()


def test_end_to_end_curve_to_call_on_unseen_instrument():
  train = curves_to_features(generate_curve_dataset(500, seed=11))
  model = build_curve_model().fit(train[CURVE_FEATURES].to_numpy(), train.True_Status.to_numpy())

  def predict_fn(features):
    row = build_feature_row(features, CURVE_FEATURES, "t")
    pred = int(model.predict(row)[0])
    return ("positive" if pred else "negative"), float(model.predict_proba(row)[0][pred]), "t"

  rng = np.random.default_rng(5)
  device, lot = DEVICES["RotorGene-Q"], LOTS["LOT-B"]
  ntc, _, _ = simulate_curve(rng, device, lot, 0.0)
  high, _, _ = simulate_curve(rng, device, lot, 1e5)
  r_neg = process_sample(SampleInput(sample_id="N", curve_data=list(ntc)), predict_fn)
  r_pos = process_sample(SampleInput(sample_id="P", curve_data=list(high)), predict_fn)
  assert r_neg.result == "negative"
  assert r_pos.result == "positive"
