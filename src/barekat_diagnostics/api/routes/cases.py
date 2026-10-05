"""Multi-kit clinical case API."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from barekat_diagnostics.api.deps import CurrentUser, require_permission
from barekat_diagnostics.core.database import get_db
from barekat_diagnostics.core.rbac import Permission
from barekat_diagnostics.schemas import (
  CaseAddAssayRequest,
  CaseCreate,
  CaseFuseResponse,
  CaseResponse,
)
from barekat_diagnostics.services.case_service import CaseError, CaseService

router = APIRouter(prefix="/cases")


def _actor(user: CurrentUser) -> dict:
  return {
    "actor_id": str(user.id),
    "actor_email": user.email,
    "actor_role": user.role,
  }


@router.post("/", response_model=CaseResponse, status_code=201)
def create_case(
  body: CaseCreate,
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(require_permission(Permission.DIAGNOSIS_RUN)),
) -> CaseResponse:
  service = CaseService(db)
  try:
    row = service.create_case(body, **_actor(user))
  except CaseError as exc:
    raise HTTPException(status_code=400, detail=exc.message) from exc
  return service.to_response(row)


@router.get("/", response_model=list[CaseResponse])
def list_cases(
  limit: int = Query(50, ge=1, le=200),
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(require_permission(Permission.DIAGNOSIS_READ)),
) -> list[CaseResponse]:
  _ = user
  service = CaseService(db)
  return [service.to_response(c) for c in service.list_cases(limit=limit)]


@router.get("/{case_id}", response_model=CaseResponse)
def get_case(
  case_id: str,
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(require_permission(Permission.DIAGNOSIS_READ)),
) -> CaseResponse:
  _ = user
  service = CaseService(db)
  row = service.get(case_id)
  if not row:
    raise HTTPException(status_code=404, detail="Case not found")
  return service.to_response(row)


@router.post("/{case_id}/assays", response_model=CaseResponse)
def add_assay(
  case_id: str,
  body: CaseAddAssayRequest,
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(require_permission(Permission.DIAGNOSIS_RUN)),
) -> CaseResponse:
  service = CaseService(db)
  try:
    service.add_assay(case_id, body, **_actor(user))
  except CaseError as exc:
    raise HTTPException(status_code=400, detail=exc.message) from exc
  case = service.get(case_id)
  assert case is not None
  return service.to_response(case)


@router.post("/{case_id}/fuse", response_model=CaseFuseResponse)
def fuse_case(
  case_id: str,
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(require_permission(Permission.DIAGNOSIS_RUN)),
) -> CaseFuseResponse:
  service = CaseService(db)
  try:
    return service.fuse(case_id, **_actor(user))
  except CaseError as exc:
    raise HTTPException(status_code=400, detail=exc.message) from exc
