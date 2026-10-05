"""Model drift and signal quality degradation monitoring."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

import numpy as np
from sqlalchemy.orm import Session

from barekat_diagnostics.core.config import get_settings
from barekat_diagnostics.ml.registry import ModelRegistry
from barekat_diagnostics.models.quality import DriftAlert, ModelBaseline
from barekat_diagnostics.models.sample import Diagnosis, Sample
from barekat_diagnostics.schemas import DriftAlertResponse, DriftCheckResponse
from barekat_diagnostics.services.audit_trail import AuditTrailService


class DriftMonitorService:
  def __init__(self, db: Session) -> None:
    self.db = db
    self.audit = AuditTrailService(db)
    self.settings = get_settings()

  def set_baseline_from_recent(
    self,
    model_version: str | None = None,
    *,
    lookback: int = 200,
  ) -> ModelBaseline:
    registry = ModelRegistry.load()
    version = model_version or registry.production_version

    diagnoses = (
      self.db.query(Diagnosis)
      .filter(Diagnosis.model_version == version)
      .order_by(Diagnosis.created_at.desc())
      .limit(lookback)
      .all()
    )
    samples = (
      self.db.query(Sample)
      .order_by(Sample.created_at.desc())
      .limit(lookback)
      .all()
    )

    feature_values: dict[str, list[float]] = {}
    for s in samples:
      if not s.features_json:
        continue
      try:
        feats = json.loads(s.features_json)
      except json.JSONDecodeError:
        continue
      for k, v in feats.items():
        if isinstance(v, (int, float)):
          feature_values.setdefault(k, []).append(float(v))

    feature_stats = {k: _stats(vals) for k, vals in feature_values.items() if vals}

    confidences = [d.confidence for d in diagnoses if d.confidence is not None]
    positives = sum(1 for d in diagnoses if d.result == "positive")
    quality = [s.quality_score for s in samples if s.quality_score is not None]
    snr = [s.signal_to_noise for s in samples if s.signal_to_noise is not None]

    existing = (
      self.db.query(ModelBaseline).filter(ModelBaseline.model_version == version).first()
    )
    if existing:
      row = existing
    else:
      row = ModelBaseline(model_version=version)
      self.db.add(row)

    row.feature_stats_json = json.dumps(feature_stats, ensure_ascii=False)
    row.positive_rate = (positives / len(diagnoses)) if diagnoses else None
    row.mean_confidence = float(np.mean(confidences)) if confidences else None
    row.mean_quality_score = float(np.mean(quality)) if quality else None
    row.mean_snr = float(np.mean(snr)) if snr else None
    row.sample_count = max(len(diagnoses), len(samples))
    self.db.commit()
    self.db.refresh(row)
    return row

  def check(
    self,
    *,
    lookback: int = 50,
    actor_id: str | None = None,
    actor_email: str | None = None,
    actor_role: str | None = None,
  ) -> DriftCheckResponse:
    registry = ModelRegistry.load()
    version = registry.production_version
    baseline = (
      self.db.query(ModelBaseline).filter(ModelBaseline.model_version == version).first()
    )
    if not baseline:
      baseline = self.set_baseline_from_recent(version)

    drift_threshold = self.settings.drift_psi_threshold
    quality_drop = self.settings.signal_quality_drop_threshold

    recent_samples = (
      self.db.query(Sample).order_by(Sample.created_at.desc()).limit(lookback).all()
    )
    recent_dx = (
      self.db.query(Diagnosis)
      .filter(Diagnosis.model_version == version)
      .order_by(Diagnosis.created_at.desc())
      .limit(lookback)
      .all()
    )

    alerts: list[DriftAlert] = []
    base_stats = json.loads(baseline.feature_stats_json or "{}")

    # feature drift via mean shift (proxy for PSI-lite)
    recent_feats: dict[str, list[float]] = {}
    for s in recent_samples:
      if not s.features_json:
        continue
      try:
        feats = json.loads(s.features_json)
      except json.JSONDecodeError:
        continue
      for k, v in feats.items():
        if isinstance(v, (int, float)):
          recent_feats.setdefault(k, []).append(float(v))

    max_shift = 0.0
    worst_feature = None
    for feat, vals in recent_feats.items():
      if feat not in base_stats or not vals:
        continue
      base_mean = float(base_stats[feat].get("mean", 0))
      base_std = float(base_stats[feat].get("std", 1)) or 1.0
      obs_mean = float(np.mean(vals))
      shift = abs(obs_mean - base_mean) / base_std
      if shift > max_shift:
        max_shift = shift
        worst_feature = feat

    if worst_feature and max_shift >= drift_threshold:
      alerts.append(
        self._create_alert(
          alert_type="model_drift",
          severity="critical" if max_shift >= drift_threshold * 1.5 else "warning",
          model_version=version,
          metric_name=f"feature_shift:{worst_feature}",
          baseline_value=float(base_stats[worst_feature]["mean"]),
          observed_value=float(np.mean(recent_feats[worst_feature])),
          threshold=drift_threshold,
          message=f"Feature shift {worst_feature}: z-shift={max_shift:.2f}",
          detail={"z_shift": max_shift, "feature": worst_feature},
        )
      )

    # prediction rate drift
    if baseline.positive_rate is not None and recent_dx:
      obs_pos = sum(1 for d in recent_dx if d.result == "positive") / len(recent_dx)
      rate_delta = abs(obs_pos - baseline.positive_rate)
      if rate_delta >= self.settings.drift_positive_rate_threshold:
        alerts.append(
          self._create_alert(
            alert_type="model_drift",
            severity="warning",
            model_version=version,
            metric_name="positive_rate",
            baseline_value=baseline.positive_rate,
            observed_value=obs_pos,
            threshold=self.settings.drift_positive_rate_threshold,
            message=f"Positive rate changed from {baseline.positive_rate:.2f} to {obs_pos:.2f}",
          )
        )

    # signal quality degradation
    recent_q = [s.quality_score for s in recent_samples if s.quality_score is not None]
    recent_snr = [s.signal_to_noise for s in recent_samples if s.signal_to_noise is not None]
    if baseline.mean_quality_score is not None and recent_q:
      obs_q = float(np.mean(recent_q))
      if obs_q < baseline.mean_quality_score - quality_drop:
        alerts.append(
          self._create_alert(
            alert_type="signal_quality",
            severity="warning",
            model_version=version,
            metric_name="quality_score",
            baseline_value=baseline.mean_quality_score,
            observed_value=obs_q,
            threshold=quality_drop,
            message=f"Signal quality drop: {obs_q:.3f} (baseline {baseline.mean_quality_score:.3f})",
          )
        )
    if baseline.mean_snr is not None and recent_snr:
      obs_snr = float(np.mean(recent_snr))
      if obs_snr < baseline.mean_snr - quality_drop * 2:
        alerts.append(
          self._create_alert(
            alert_type="signal_quality",
            severity="critical" if obs_snr < self.settings.qc_min_signal_to_noise else "warning",
            model_version=version,
            metric_name="signal_to_noise",
            baseline_value=baseline.mean_snr,
            observed_value=obs_snr,
            threshold=quality_drop * 2,
            message=f"SNR drop: {obs_snr:.3f} (baseline {baseline.mean_snr:.3f})",
          )
        )

    if alerts:
      self.audit.log(
        "drift.detected",
        actor_id=actor_id,
        actor_email=actor_email,
        actor_role=actor_role,
        resource_type="model",
        resource_id=version,
        model_version=version,
        detail={"alert_count": len(alerts), "types": [a.alert_type for a in alerts]},
      )

    return DriftCheckResponse(
      model_version=version,
      alerts_created=len(alerts),
      max_feature_shift=max_shift,
      alerts=[self.to_alert_response(a) for a in alerts],
      baseline_sample_count=baseline.sample_count,
      recent_sample_count=len(recent_samples),
    )

  def list_alerts(self, status: str | None = "open", limit: int = 50) -> list[DriftAlert]:
    q = self.db.query(DriftAlert).order_by(DriftAlert.created_at.desc())
    if status:
      q = q.filter(DriftAlert.status == status)
    return q.limit(limit).all()

  def acknowledge(
    self,
    alert_id: str,
    *,
    actor_id: str,
    actor_email: str,
  ) -> DriftAlert:
    row = self.db.query(DriftAlert).filter(DriftAlert.alert_id == alert_id).first()
    if not row:
      raise ValueError("Alert not found")
    row.status = "acknowledged"
    row.acknowledged_by = actor_id
    row.acknowledged_at = datetime.now(timezone.utc)
    self.db.commit()
    self.db.refresh(row)
    self.audit.log(
      "drift.acknowledged",
      actor_id=actor_id,
      actor_email=actor_email,
      resource_type="drift_alert",
      resource_id=alert_id,
    )
    return row

  def _create_alert(self, **kwargs: Any) -> DriftAlert:
    detail = kwargs.pop("detail", None)
    alert = DriftAlert(
      alert_id=f"DRIFT-{uuid.uuid4().hex[:10].upper()}",
      detail_json=json.dumps(detail, ensure_ascii=False) if detail else None,
      **kwargs,
    )
    self.db.add(alert)
    self.db.commit()
    self.db.refresh(alert)
    return alert

  def to_alert_response(self, row: DriftAlert) -> DriftAlertResponse:
    return DriftAlertResponse(
      alert_id=row.alert_id,
      alert_type=row.alert_type,
      severity=row.severity,
      model_version=row.model_version,
      metric_name=row.metric_name,
      baseline_value=row.baseline_value,
      observed_value=row.observed_value,
      threshold=row.threshold,
      message=row.message,
      status=row.status,
      created_at=row.created_at,
    )


def _stats(vals: list[float]) -> dict[str, float]:
  arr = np.asarray(vals, dtype=float)
  return {
    "mean": float(np.mean(arr)),
    "std": float(np.std(arr)) if len(arr) > 1 else 1.0,
    "p05": float(np.percentile(arr, 5)),
    "p95": float(np.percentile(arr, 95)),
    "n": float(len(arr)),
  }
