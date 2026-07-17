"""API بچ آزمایشگاهی و کنترل مثبت/منفی."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from barekat_diagnostics.api.deps import CurrentUser, get_current_user, require_permission
from barekat_diagnostics.core.database import get_db
from barekat_diagnostics.core.rbac import Permission
from barekat_diagnostics.schemas import AssayBatchCreate, AssayBatchResponse, BatchControlUpdate
from barekat_diagnostics.services.batch_service import BatchService, BatchValidationError

router = APIRouter(prefix="/batches")


def _actor(user: CurrentUser) -> dict:
  return {"actor_id": str(user.id), "actor_email": user.email, "actor_role": user.role}


@router.post("/", response_model=AssayBatchResponse, status_code=201)
def create_batch(
  body: AssayBatchCreate,
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(require_permission(Permission.CALIBRATION_MANAGE)),
) -> AssayBatchResponse:
  service = BatchService(db)
  try:
    batch = service.create_batch(body, **_actor(user))
  except BatchValidationError as exc:
    raise HTTPException(status_code=409, detail=exc.message) from exc
  return service.to_response(batch)


@router.get("/", response_model=list[AssayBatchResponse])
def list_batches(
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(get_current_user),
) -> list[AssayBatchResponse]:
  _ = user
  service = BatchService(db)
  return [service.to_response(b) for b in service.list_batches()]


@router.get("/{batch_id}", response_model=AssayBatchResponse)
def get_batch(
  batch_id: str,
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(get_current_user),
) -> AssayBatchResponse:
  _ = user
  service = BatchService(db)
  batch = service.get_batch(batch_id)
  if not batch:
    raise HTTPException(status_code=404, detail="بچ یافت نشد")
  return service.to_response(batch)


@router.post("/{batch_id}/controls", response_model=AssayBatchResponse)
def register_controls(
  batch_id: str,
  body: BatchControlUpdate,
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(require_permission(Permission.CALIBRATION_MANAGE)),
) -> AssayBatchResponse:
  service = BatchService(db)
  try:
    batch = service.register_controls(batch_id, body, **_actor(user))
  except BatchValidationError as exc:
    raise HTTPException(status_code=400, detail=exc.message) from exc
  return service.to_response(batch)


@router.post("/{batch_id}/validate", response_model=AssayBatchResponse)
def validate_controls(
  batch_id: str,
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(require_permission(Permission.CALIBRATION_MANAGE)),
) -> AssayBatchResponse:
  service = BatchService(db)
  try:
    batch = service.validate_controls(batch_id, **_actor(user))
  except BatchValidationError as exc:
    raise HTTPException(status_code=400, detail=exc.message) from exc
  return service.to_response(batch)
