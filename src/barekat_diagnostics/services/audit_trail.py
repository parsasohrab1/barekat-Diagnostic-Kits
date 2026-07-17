"""سرویس Audit Trail — لاگ append-only با زنجیره هش."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from barekat_diagnostics.core.config import get_settings
from barekat_diagnostics.models.audit import AuditLog


GENESIS_HASH = "0" * 64


class AuditTrailService:
  def __init__(self, db: Session) -> None:
    self.db = db

  def _last_hash(self) -> str:
    last = self.db.query(AuditLog).order_by(AuditLog.id.desc()).first()
    return last.entry_hash if last else GENESIS_HASH

  @staticmethod
  def _normalize_ts(created_at: datetime) -> str:
    # SQLite اغلب timezone را حذف می‌کند — هش باید پایدار بماند
    if created_at.tzinfo is not None:
      created_at = created_at.astimezone(timezone.utc).replace(tzinfo=None)
    return created_at.isoformat(timespec="microseconds")

  @staticmethod
  def _compute_hash(
    prev_hash: str,
    event_type: str,
    actor_id: str | None,
    resource_type: str | None,
    resource_id: str | None,
    detail_json: str | None,
    created_at: datetime,
  ) -> str:
    payload = "|".join(
      [
        prev_hash,
        event_type,
        actor_id or "",
        resource_type or "",
        resource_id or "",
        detail_json or "",
        AuditTrailService._normalize_ts(created_at),
      ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

  def log(
    self,
    event_type: str,
    *,
    actor_id: str | None = None,
    actor_email: str | None = None,
    actor_role: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    model_version: str | None = None,
    detail: dict[str, Any] | None = None,
  ) -> AuditLog:
    created_at = datetime.now(timezone.utc)
    detail_json = json.dumps(detail, ensure_ascii=False, sort_keys=True) if detail else None
    prev_hash = self._last_hash()
    entry_hash = self._compute_hash(
      prev_hash,
      event_type,
      actor_id,
      resource_type,
      resource_id,
      detail_json,
      created_at,
    )
    entry = AuditLog(
      event_type=event_type,
      actor_id=actor_id,
      actor_email=actor_email,
      actor_role=actor_role,
      resource_type=resource_type,
      resource_id=resource_id,
      model_version=model_version,
      detail_json=detail_json,
      prev_hash=prev_hash,
      entry_hash=entry_hash,
      created_at=created_at,
    )
    self.db.add(entry)
    self.db.commit()
    self.db.refresh(entry)
    return entry

  def list_events(
    self,
    *,
    resource_id: str | None = None,
    event_type: str | None = None,
    limit: int = 100,
  ) -> list[AuditLog]:
    q = self.db.query(AuditLog).order_by(AuditLog.id.desc())
    if resource_id:
      q = q.filter(AuditLog.resource_id == resource_id)
    if event_type:
      q = q.filter(AuditLog.event_type == event_type)
    return q.limit(limit).all()

  def verify_chain(self, limit: int = 10_000) -> dict[str, Any]:
    rows = self.db.query(AuditLog).order_by(AuditLog.id.asc()).limit(limit).all()
    expected_prev = GENESIS_HASH
    for row in rows:
      if row.prev_hash != expected_prev:
        return {"valid": False, "broken_at_id": row.id, "reason": "prev_hash mismatch"}
      recomputed = self._compute_hash(
        row.prev_hash,
        row.event_type,
        row.actor_id,
        row.resource_type,
        row.resource_id,
        row.detail_json,
        row.created_at,
      )
      if recomputed != row.entry_hash:
        return {"valid": False, "broken_at_id": row.id, "reason": "entry_hash mismatch"}
      expected_prev = row.entry_hash
    return {"valid": True, "checked": len(rows)}

  def expire_before(self) -> int:
    """حذف رکوردهای قدیمی‌تر از retention (فقط برای نگهداری قانونی)."""
    years = get_settings().audit_retention_years
    cutoff = datetime.now(timezone.utc) - timedelta(days=365 * years)
    q = self.db.query(AuditLog).filter(AuditLog.created_at < cutoff)
    count = q.count()
    q.delete(synchronize_session=False)
    self.db.commit()
    return count
