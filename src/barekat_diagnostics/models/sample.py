"""Database models."""

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from barekat_diagnostics.core.database import Base


class KitCalibration(Base):
  __tablename__ = "kit_calibrations"

  id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
  lot_number: Mapped[str] = mapped_column(String(64), unique=True, index=True)
  kit_type: Mapped[str] = mapped_column(String(32), default="qpcr")
  expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
  cutoff_value: Mapped[float | None] = mapped_column(Float, nullable=True)
  standard_curve_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
  standard_curve_json: Mapped[str | None] = mapped_column(Text, nullable=True)
  # Batch-oriented controls (expected values)
  pos_control_ct_max: Mapped[float | None] = mapped_column(Float, nullable=True)
  neg_control_ct_min: Mapped[float | None] = mapped_column(Float, nullable=True)
  require_controls: Mapped[bool] = mapped_column(Boolean, default=True)
  created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AssayBatch(Base):
  """Laboratory batch with mandatory positive/negative control."""

  __tablename__ = "assay_batches"

  id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
  batch_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
  lot_number: Mapped[str] = mapped_column(String(64), index=True)
  kit_type: Mapped[str] = mapped_column(String(32), default="qpcr")
  label: Mapped[str | None] = mapped_column(String(128), nullable=True)
  status: Mapped[str] = mapped_column(String(24), default="open")
  pos_control_ct_max: Mapped[float] = mapped_column(Float, default=32.0)
  neg_control_ct_min: Mapped[float] = mapped_column(Float, default=38.0)
  positive_control_sample_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
  negative_control_sample_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
  positive_control_ct: Mapped[float | None] = mapped_column(Float, nullable=True)
  negative_control_ct: Mapped[float | None] = mapped_column(Float, nullable=True)
  positive_control_passed: Mapped[bool] = mapped_column(Boolean, default=False)
  negative_control_passed: Mapped[bool] = mapped_column(Boolean, default=False)
  controls_validated: Mapped[bool] = mapped_column(Boolean, default=False)
  validation_message: Mapped[str | None] = mapped_column(Text, nullable=True)
  created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
  validated_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
  created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
  validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Sample(Base):
  __tablename__ = "samples"

  id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
  sample_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
  patient_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
  kit_type: Mapped[str] = mapped_column(String(32), default="qpcr")
  status: Mapped[str] = mapped_column(String(16), default="pending")
  calibration_lot: Mapped[str | None] = mapped_column(String(64), nullable=True)
  batch_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
  sample_role: Mapped[str] = mapped_column(String(32), default="patient")
  tenant_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
  center_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
  device_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
  ct_value: Mapped[float | None] = mapped_column(Float, nullable=True)
  od_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
  peak_intensity: Mapped[float | None] = mapped_column(Float, nullable=True)
  quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
  signal_to_noise: Mapped[float | None] = mapped_column(Float, nullable=True)
  amplification_efficiency: Mapped[float | None] = mapped_column(Float, nullable=True)
  calibration_error: Mapped[bool] = mapped_column(Boolean, default=False)
  is_reliable: Mapped[bool] = mapped_column(Boolean, default=True)
  raw_data_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
  curve_object_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
  features_json: Mapped[str | None] = mapped_column(Text, nullable=True)
  created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Diagnosis(Base):
  __tablename__ = "diagnoses"

  id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
  sample_id: Mapped[str] = mapped_column(String(32), index=True)
  kit_type: Mapped[str] = mapped_column(String(32), default="qpcr")
  result: Mapped[str] = mapped_column(String(16))
  confidence: Mapped[float] = mapped_column(Float)
  recommendation: Mapped[str] = mapped_column(String(16), default="report")
  model_version: Mapped[str] = mapped_column(String(64), default="v1")
  qc_passed: Mapped[bool] = mapped_column(Boolean, default=True)
  qc_warnings: Mapped[str | None] = mapped_column(Text, nullable=True)
  report_json: Mapped[str | None] = mapped_column(Text, nullable=True)
  pdf_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
  features_json: Mapped[str | None] = mapped_column(Text, nullable=True)
  approval_status: Mapped[str] = mapped_column(String(16), default="pending")
  approved_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
  approved_by_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
  approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
  approval_note: Mapped[str | None] = mapped_column(Text, nullable=True)
  client_report_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True, index=True)
  tenant_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
  center_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
  device_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
  created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BatchJob(Base):
  __tablename__ = "batch_jobs"

  id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
  job_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
  status: Mapped[str] = mapped_column(String(16), default="pending")
  total_samples: Mapped[int] = mapped_column(Integer, default=0)
  completed_samples: Mapped[int] = mapped_column(Integer, default=0)
  results_json: Mapped[str | None] = mapped_column(Text, nullable=True)
  created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
  completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DiagnosisJob(Base):
  __tablename__ = "diagnosis_jobs"

  id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
  job_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
  sample_id: Mapped[str] = mapped_column(String(32), index=True)
  status: Mapped[str] = mapped_column(String(16), default="pending")
  progress: Mapped[float] = mapped_column(Float, default=0.0)
  celery_task_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
  report_json: Mapped[str | None] = mapped_column(Text, nullable=True)
  error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
  created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
  completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
