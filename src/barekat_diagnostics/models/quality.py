"""مدل‌های فاز ۲: اعتبارسنجی بالینی، change control، drift."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from barekat_diagnostics.core.database import Base


class ClinicalValidationProtocol(Base):
  """پروتکل اعتبارسنجی بالینی مرتبط با سری ساخت / batch / lot."""

  __tablename__ = "clinical_validation_protocols"

  id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
  protocol_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
  model_version: Mapped[str] = mapped_column(String(64), index=True)
  build_series: Mapped[str] = mapped_column(String(64), index=True)
  batch_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
  lot_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
  data_path: Mapped[str] = mapped_column(String(512))
  status: Mapped[str] = mapped_column(String(24), default="draft")
  # acceptance criteria
  min_sensitivity: Mapped[float] = mapped_column(Float, default=0.90)
  min_specificity: Mapped[float] = mapped_column(Float, default=0.90)
  min_roc_auc: Mapped[float] = mapped_column(Float, default=0.85)
  min_samples: Mapped[int] = mapped_column(Integer, default=30)
  # results
  sample_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
  sensitivity: Mapped[float | None] = mapped_column(Float, nullable=True)
  specificity: Mapped[float | None] = mapped_column(Float, nullable=True)
  roc_auc: Mapped[float | None] = mapped_column(Float, nullable=True)
  passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
  result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
  failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
  created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
  signed_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
  signed_by_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
  signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
  created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ChangeRequest(Base):
  """کنترل تغییر نرم‌افزار پزشکی برای مدل / پایپ‌لاین / تنظیمات."""

  __tablename__ = "change_requests"

  id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
  change_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
  change_type: Mapped[str] = mapped_column(String(32))  # model|pipeline|config|cutoff
  title: Mapped[str] = mapped_column(String(256))
  description: Mapped[str | None] = mapped_column(Text, nullable=True)
  risk_level: Mapped[str] = mapped_column(String(16), default="medium")  # low|medium|high|critical
  mitigation: Mapped[str | None] = mapped_column(Text, nullable=True)
  target_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
  previous_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
  protocol_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
  status: Mapped[str] = mapped_column(String(24), default="draft")
  # draft|pending|approved|rejected|applied|cancelled
  detail_json: Mapped[str | None] = mapped_column(Text, nullable=True)
  requested_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
  requested_by_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
  approved_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
  approved_by_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
  approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
  applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
  created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DriftAlert(Base):
  """هشدار drift مدل یا افت کیفیت سیگنال."""

  __tablename__ = "drift_alerts"

  id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
  alert_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
  alert_type: Mapped[str] = mapped_column(String(32))  # model_drift|signal_quality
  severity: Mapped[str] = mapped_column(String(16), default="warning")  # info|warning|critical
  model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
  metric_name: Mapped[str] = mapped_column(String(64))
  baseline_value: Mapped[float | None] = mapped_column(Float, nullable=True)
  observed_value: Mapped[float | None] = mapped_column(Float, nullable=True)
  threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
  message: Mapped[str] = mapped_column(Text)
  status: Mapped[str] = mapped_column(String(16), default="open")  # open|acknowledged|resolved
  detail_json: Mapped[str | None] = mapped_column(Text, nullable=True)
  created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
  acknowledged_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
  acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ModelBaseline(Base):
  """توزیع پایه ویژگی‌ها برای مانیتورینگ drift."""

  __tablename__ = "model_baselines"

  id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
  model_version: Mapped[str] = mapped_column(String(64), unique=True, index=True)
  feature_stats_json: Mapped[str] = mapped_column(Text)  # {feature: {mean, std, p05, p95}}
  positive_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
  mean_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
  mean_quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
  mean_snr: Mapped[float | None] = mapped_column(Float, nullable=True)
  sample_count: Mapped[int] = mapped_column(Integer, default=0)
  created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
