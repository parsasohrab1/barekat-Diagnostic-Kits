"""مدل‌های چندمرکزی، دستگاه‌های edge و ناوگان مدل."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from barekat_diagnostics.core.database import Base


class Tenant(Base):
  __tablename__ = "tenants"

  id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
  tenant_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
  name: Mapped[str] = mapped_column(String(256))
  status: Mapped[str] = mapped_column(String(16), default="active")
  created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Center(Base):
  __tablename__ = "centers"

  id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
  center_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
  tenant_id: Mapped[str] = mapped_column(String(64), index=True)
  name: Mapped[str] = mapped_column(String(256))
  region: Mapped[str | None] = mapped_column(String(128), nullable=True)
  status: Mapped[str] = mapped_column(String(16), default="active")
  created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EdgeDevice(Base):
  __tablename__ = "edge_devices"

  id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
  device_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
  center_id: Mapped[str] = mapped_column(String(64), index=True)
  tenant_id: Mapped[str] = mapped_column(String(64), index=True)
  label: Mapped[str | None] = mapped_column(String(128), nullable=True)
  device_token_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
  model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
  onnx_checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
  status: Mapped[str] = mapped_column(String(24), default="registered")
  # registered|online|offline|updating|quarantined
  last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
  last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
  last_latency_p95_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
  sla_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
  created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FleetModelRelease(Base):
  """انتشار امن مدل ONNX برای ناوگان edge."""

  __tablename__ = "fleet_model_releases"

  id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
  release_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
  model_version: Mapped[str] = mapped_column(String(64), index=True)
  onnx_path: Mapped[str] = mapped_column(String(512))
  checksum_sha256: Mapped[str] = mapped_column(String(64))
  signature: Mapped[str | None] = mapped_column(String(128), nullable=True)
  locked: Mapped[bool] = mapped_column(Boolean, default=True)
  status: Mapped[str] = mapped_column(String(24), default="staged")
  # staged|published|retired|yanked
  min_latency_p95_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
  target_tenant_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
  rollout_pct: Mapped[float] = mapped_column(Float, default=100.0)
  manifest_json: Mapped[str | None] = mapped_column(Text, nullable=True)
  created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
  published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SyncConflictLog(Base):
  __tablename__ = "sync_conflict_logs"

  id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
  conflict_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
  client_report_id: Mapped[str] = mapped_column(String(64), index=True)
  sample_id: Mapped[str] = mapped_column(String(32), index=True)
  device_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
  center_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
  resolution: Mapped[str] = mapped_column(String(32))
  # accepted|rejected_duplicate|server_wins|client_wins|merged
  detail_json: Mapped[str | None] = mapped_column(Text, nullable=True)
  created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
