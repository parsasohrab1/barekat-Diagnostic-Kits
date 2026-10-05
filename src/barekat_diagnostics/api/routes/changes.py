"""Medical software change control API."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from barekat_diagnostics.api.deps import CurrentUser, require_permission
from barekat_diagnostics.core.database import get_db
from barekat_diagnostics.core.rbac import Permission
from barekat_diagnostics.schemas import (
  ChangeRequestApplyResponse,
  ChangeRequestCreate,
  ChangeRequestDecision,
  ChangeRequestResponse,
)
from barekat_diagnostics.services.change_control_service import ChangeControlError, ChangeControlService

router = APIRouter(prefix="/changes")


def _actor(user: CurrentUser) -> dict:
  return {"actor_id": str(user.id), "actor_email": user.email, "actor_role": user.role}


@router.post("/", response_model=ChangeRequestResponse, status_code=201)
def create_change(
  body: ChangeRequestCreate,
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(require_permission(Permission.ML_MANAGE)),
) -> ChangeRequestResponse:
  service = ChangeControlService(db)
  try:
    row = service.create(body, **_actor(user))
  except ChangeControlError as exc:
    raise HTTPException(status_code=400, detail=exc.message) from exc
  return service.to_response(row)


@router.get("/", response_model=list[ChangeRequestResponse])
def list_changes(
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(require_permission(Permission.AUDIT_READ)),
) -> list[ChangeRequestResponse]:
  _ = user
  service = ChangeControlService(db)
  return [service.to_response(r) for r in service.list_requests()]


@router.get("/{change_id}", response_model=ChangeRequestResponse)
def get_change(
  change_id: str,
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(require_permission(Permission.AUDIT_READ)),
) -> ChangeRequestResponse:
  _ = user
  service = ChangeControlService(db)
  row = service.get(change_id)
  if not row:
    raise HTTPException(status_code=404, detail="Request not found")
  return service.to_response(row)


@router.post("/{change_id}/decide", response_model=ChangeRequestResponse)
def decide_change(
  change_id: str,
  body: ChangeRequestDecision,
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(require_permission(Permission.CHANGE_APPROVE)),
) -> ChangeRequestResponse:
  service = ChangeControlService(db)
  try:
    row = service.decide(change_id, body, **_actor(user))
  except ChangeControlError as exc:
    raise HTTPException(status_code=400, detail=exc.message) from exc
  return service.to_response(row)


@router.post("/{change_id}/apply", response_model=ChangeRequestApplyResponse)
def apply_change(
  change_id: str,
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(require_permission(Permission.ML_PROMOTE)),
) -> ChangeRequestApplyResponse:
  service = ChangeControlService(db)
  try:
    return service.apply(change_id, **_actor(user))
  except ChangeControlError as exc:
    raise HTTPException(status_code=400, detail=exc.message) from exc
