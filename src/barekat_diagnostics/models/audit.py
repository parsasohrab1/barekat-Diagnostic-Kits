"""Audit Trail model — immutable log for compliance."""

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from barekat_diagnostics.core.database import Base


class AuditLog(Base):
  """Append-only audit record. Application never UPDATEs or DELETEs rows.

  Integrity: each row stores prev_hash + entry_hash (SHA-256 chain).
  Retention: purge only via expire_before() after audit_retention_years.
  """

  __tablename__ = "audit_logs"

  id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
  event_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
  actor_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
  actor_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
  actor_role: Mapped[str | None] = mapped_column(String(50), nullable=True)
  resource_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
  resource_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
  model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
  detail_json: Mapped[str | None] = mapped_column(Text, nullable=True)
  prev_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="0" * 64)
  entry_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
  created_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True),
    default=lambda: datetime.now(timezone.utc),
    index=True,
    nullable=False,
  )
