"""API پیشنهاد و اجرای reassessment."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from barekat_diagnostics.api.deps import CurrentUser, require_permission
from barekat_diagnostics.core.database import get_db
from barekat_diagnostics.core.rbac import Permission
from barekat_diagnostics.schemas import (
  ReassessmentAcceptRequest,
  ReassessmentCompareResponse,
  ReassessmentResponse,
)
from barekat_diagnostics.services.reassessment_service import (
  ReassessmentError,
  ReassessmentService,
)

router = APIRouter(prefix="/reassessments")


def _actor(user: CurrentUser) -> dict:
  return {
    "actor_id": str(user.id),
    "actor_email": user.email,
    "actor_role": user.role,
  }


@router.get("/", response_model=list[ReassessmentResponse])
def list_reassessments(
  status: str | None = Query(None),
  limit: int = Query(50, ge=1, le=200),
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(require_permission(Permission.DIAGNOSIS_READ)),
) -> list[ReassessmentResponse]:
  _ = user
  service = ReassessmentService(db)
  return [service.to_response(r) for r in service.list_requests(status=status, limit=limit)]


@router.get("/{reassessment_id}", response_model=ReassessmentResponse)
def get_reassessment(
  reassessment_id: str,
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(require_permission(Permission.DIAGNOSIS_READ)),
) -> ReassessmentResponse:
  _ = user
  service = ReassessmentService(db)
  row = service.get(reassessment_id)
  if not row:
    raise HTTPException(status_code=404, detail="درخواست reassessment یافت نشد")
  return service.to_response(row)


@router.post("/{reassessment_id}/accept", response_model=ReassessmentCompareResponse)
def accept_reassessment(
  reassessment_id: str,
  body: ReassessmentAcceptRequest,
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(require_permission(Permission.DIAGNOSIS_RUN)),
) -> ReassessmentCompareResponse:
  service = ReassessmentService(db)
  try:
    return service.accept_and_run(reassessment_id, body, **_actor(user))
  except ReassessmentError as exc:
    raise HTTPException(status_code=400, detail=exc.message) from exc
