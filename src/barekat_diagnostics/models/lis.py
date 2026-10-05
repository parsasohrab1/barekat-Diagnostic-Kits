"""LIS order model and EHR synchronization."""

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from barekat_diagnostics.core.database import Base


class LabOrder(Base):
  """Order received from LIS (ServiceRequest)."""

  __tablename__ = "lab_orders"

  id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
  order_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
  patient_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
  sample_id: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True)
  kit_type: Mapped[str] = mapped_column(String(32), default="qpcr")
  status: Mapped[str] = mapped_column(String(32), default="received")
  fhir_json: Mapped[str | None] = mapped_column(Text, nullable=True)
  created_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
  )
  updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class FhirExport(Base):
  """FHIR DiagnosticReport export log to LIS/EHR."""

  __tablename__ = "fhir_exports"

  id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
  sample_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
  report_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
  patient_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
  order_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
  fhir_json: Mapped[str] = mapped_column(Text, nullable=False)
  destination: Mapped[str | None] = mapped_column(String(256), nullable=True)
  status: Mapped[str] = mapped_column(String(32), default="exported")
  created_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
  )
