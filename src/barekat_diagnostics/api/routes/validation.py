"""API پروتکل اعتبارسنجی بالینی."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from barekat_diagnostics.api.deps import CurrentUser, require_permission
from barekat_diagnostics.core.database import get_db
from barekat_diagnostics.core.rbac import Permission
from barekat_diagnostics.schemas import (
  ClinicalValidationCreate,
  ClinicalValidationResponse,
  ClinicalValidationSignRequest,
)
from barekat_diagnostics.services.validation_service import ClinicalValidationService, ValidationError

router = APIRouter(prefix="/validation")


def _actor(user: CurrentUser) -> dict:
  return {"actor_id": str(user.id), "actor_email": user.email, "actor_role": user.role}


@router.post("/", response_model=ClinicalValidationResponse, status_code=201)
def create_protocol(
  body: ClinicalValidationCreate,
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(require_permission(Permission.ML_MANAGE)),
) -> ClinicalValidationResponse:
  service = ClinicalValidationService(db)
  try:
    row = service.create(body, **_actor(user))
  except ValidationError as exc:
    raise HTTPException(status_code=409, detail=exc.message) from exc
  return service.to_response(row)


@router.get("/", response_model=list[ClinicalValidationResponse])
def list_protocols(
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(require_permission(Permission.DIAGNOSIS_READ)),
) -> list[ClinicalValidationResponse]:
  _ = user
  service = ClinicalValidationService(db)
  return [service.to_response(r) for r in service.list_protocols()]


@router.get("/{protocol_id}", response_model=ClinicalValidationResponse)
def get_protocol(
  protocol_id: str,
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(require_permission(Permission.DIAGNOSIS_READ)),
) -> ClinicalValidationResponse:
  _ = user
  service = ClinicalValidationService(db)
  row = service.get(protocol_id)
  if not row:
    raise HTTPException(status_code=404, detail="پروتکل یافت نشد")
  return service.to_response(row)


@router.post("/{protocol_id}/run", response_model=ClinicalValidationResponse)
def run_protocol(
  protocol_id: str,
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(require_permission(Permission.ML_MANAGE)),
) -> ClinicalValidationResponse:
  service = ClinicalValidationService(db)
  try:
    row = service.run(protocol_id, **_actor(user))
  except ValidationError as exc:
    raise HTTPException(status_code=400, detail=exc.message) from exc
  return service.to_response(row)


@router.post("/{protocol_id}/sign", response_model=ClinicalValidationResponse)
def sign_protocol(
  protocol_id: str,
  body: ClinicalValidationSignRequest,
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(require_permission(Permission.VALIDATION_SIGN)),
) -> ClinicalValidationResponse:
  service = ClinicalValidationService(db)
  try:
    row = service.sign(protocol_id, body, **_actor(user))
  except ValidationError as exc:
    raise HTTPException(status_code=400, detail=exc.message) from exc
  return service.to_response(row)
