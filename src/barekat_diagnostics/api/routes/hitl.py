"""Supervised learning with expert approval (HITL) API."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from barekat_diagnostics.api.deps import CurrentUser, require_permission
from barekat_diagnostics.core.database import get_db
from barekat_diagnostics.core.rbac import Permission
from barekat_diagnostics.schemas import (
  ExpertFeedbackCreate,
  ExpertFeedbackResponse,
  HitlExportResponse,
  HitlRetrainRequest,
  TrainingMetrics,
)
from barekat_diagnostics.services.hitl_service import HitlError, HitlService

router = APIRouter(prefix="/hitl")


def _actor(user: CurrentUser) -> dict:
  return {
    "actor_id": str(user.id),
    "actor_email": user.email,
    "actor_role": user.role,
  }


@router.post("/feedback", response_model=ExpertFeedbackResponse, status_code=201)
def submit_feedback(
  body: ExpertFeedbackCreate,
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(require_permission(Permission.REPORTS_APPROVE)),
) -> ExpertFeedbackResponse:
  service = HitlService(db)
  try:
    row = service.submit_feedback(body, **_actor(user))
  except HitlError as exc:
    raise HTTPException(status_code=400, detail=exc.message) from exc
  return service.to_response(row)


@router.get("/feedback", response_model=list[ExpertFeedbackResponse])
def list_feedback(
  unused_only: bool = Query(False),
  limit: int = Query(100, ge=1, le=1000),
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(require_permission(Permission.DIAGNOSIS_READ)),
) -> list[ExpertFeedbackResponse]:
  _ = user
  service = HitlService(db)
  return [
    service.to_response(r)
    for r in service.list_feedback(unused_only=unused_only, limit=limit)
  ]


@router.post("/export", response_model=HitlExportResponse)
def export_training(
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(require_permission(Permission.ML_MANAGE)),
) -> HitlExportResponse:
  _ = user
  service = HitlService(db)
  try:
    return service.export_training_csv()
  except HitlError as exc:
    raise HTTPException(status_code=400, detail=exc.message) from exc


@router.post("/retrain", response_model=TrainingMetrics)
def retrain(
  body: HitlRetrainRequest,
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(require_permission(Permission.ML_MANAGE)),
) -> TrainingMetrics:
  service = HitlService(db)
  try:
    return service.retrain_from_feedback(body, **_actor(user))
  except HitlError as exc:
    raise HTTPException(status_code=400, detail=exc.message) from exc
