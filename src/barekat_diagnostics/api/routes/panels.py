"""Multi-marker / multi-disease panel API."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from barekat_diagnostics.api.deps import CurrentUser, require_permission
from barekat_diagnostics.core.database import get_db
from barekat_diagnostics.core.rbac import Permission
from barekat_diagnostics.schemas import (
  MarkerPanelCreate,
  MarkerPanelResponse,
  PanelAnalyzeRequest,
  PanelAnalyzeResponse,
)
from barekat_diagnostics.services.panel_service import PanelError, PanelService

router = APIRouter(prefix="/panels")


def _actor(user: CurrentUser) -> dict:
  return {
    "actor_id": str(user.id),
    "actor_email": user.email,
    "actor_role": user.role,
  }


@router.post("/", response_model=MarkerPanelResponse, status_code=201)
def create_panel(
  body: MarkerPanelCreate,
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(require_permission(Permission.ML_MANAGE)),
) -> MarkerPanelResponse:
  service = PanelService(db)
  try:
    row = service.create_panel(body, **_actor(user))
  except PanelError as exc:
    raise HTTPException(status_code=400, detail=exc.message) from exc
  return service.to_response(row)


@router.get("/", response_model=list[MarkerPanelResponse])
def list_panels(
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(require_permission(Permission.DIAGNOSIS_READ)),
) -> list[MarkerPanelResponse]:
  _ = user
  service = PanelService(db)
  return [service.to_response(p) for p in service.list_panels()]


@router.get("/{panel_id}", response_model=MarkerPanelResponse)
def get_panel(
  panel_id: str,
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(require_permission(Permission.DIAGNOSIS_READ)),
) -> MarkerPanelResponse:
  _ = user
  service = PanelService(db)
  row = service.get_panel(panel_id)
  if not row:
    raise HTTPException(status_code=404, detail="Panel not found")
  return service.to_response(row)


@router.post("/analyze", response_model=PanelAnalyzeResponse)
def analyze_panel(
  body: PanelAnalyzeRequest,
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(require_permission(Permission.DIAGNOSIS_RUN)),
) -> PanelAnalyzeResponse:
  service = PanelService(db)
  try:
    return service.analyze(body, **_actor(user))
  except PanelError as exc:
    raise HTTPException(status_code=400, detail=exc.message) from exc
