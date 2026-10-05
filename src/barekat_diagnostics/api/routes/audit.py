"""Audit log API."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from barekat_diagnostics.api.deps import CurrentUser, require_permission
from barekat_diagnostics.core.database import get_db
from barekat_diagnostics.core.rbac import Permission
from barekat_diagnostics.schemas import AuditLogResponse
from barekat_diagnostics.services.audit_trail import AuditTrailService

router = APIRouter(prefix="/audit")


@router.get("/", response_model=list[AuditLogResponse])
def list_audit_events(
  resource_id: str | None = Query(None),
  event_type: str | None = Query(None),
  limit: int = Query(100, ge=1, le=500),
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(require_permission(Permission.AUDIT_READ)),
) -> list[AuditLogResponse]:
  _ = user
  rows = AuditTrailService(db).list_events(
    resource_id=resource_id,
    event_type=event_type,
    limit=limit,
  )
  return [
    AuditLogResponse(
      id=r.id,
      event_type=r.event_type,
      actor_id=r.actor_id,
      actor_email=r.actor_email,
      actor_role=r.actor_role,
      resource_type=r.resource_type,
      resource_id=r.resource_id,
      model_version=r.model_version,
      detail_json=r.detail_json,
      entry_hash=r.entry_hash,
      created_at=r.created_at,
    )
    for r in rows
  ]


@router.get("/verify")
def verify_audit_chain(
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(require_permission(Permission.AUDIT_READ)),
) -> dict:
  _ = user
  return AuditTrailService(db).verify_chain()
