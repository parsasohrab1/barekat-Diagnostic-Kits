"""Multi-center and aggregate reports API."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from barekat_diagnostics.api.deps import CurrentUser, require_permission
from barekat_diagnostics.core.database import get_db
from barekat_diagnostics.core.rbac import Permission
from barekat_diagnostics.schemas import (
  CenterAggregateReport,
  CenterCreate,
  CenterResponse,
  TenantAggregateReport,
  TenantCreate,
  TenantResponse,
)
from barekat_diagnostics.services.tenant_service import TenantError, TenantService

router = APIRouter(prefix="/tenants")


def _actor(user: CurrentUser) -> dict:
  return {
    "actor_id": str(user.id),
    "actor_email": user.email,
    "actor_role": user.role,
  }


@router.post("/", response_model=TenantResponse, status_code=201)
def create_tenant(
  body: TenantCreate,
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(require_permission(Permission.ADMIN_SETTINGS)),
) -> TenantResponse:
  service = TenantService(db)
  try:
    row = service.create_tenant(body, **_actor(user))
  except TenantError as exc:
    raise HTTPException(status_code=409, detail=exc.message) from exc
  return service.to_tenant_response(row)


@router.get("/", response_model=list[TenantResponse])
def list_tenants(
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(require_permission(Permission.DIAGNOSIS_READ)),
) -> list[TenantResponse]:
  _ = user
  service = TenantService(db)
  return [service.to_tenant_response(t) for t in service.list_tenants()]


@router.post("/centers", response_model=CenterResponse, status_code=201)
def create_center(
  body: CenterCreate,
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(require_permission(Permission.ADMIN_SETTINGS)),
) -> CenterResponse:
  service = TenantService(db)
  try:
    row = service.create_center(body, **_actor(user))
  except TenantError as exc:
    raise HTTPException(status_code=400, detail=exc.message) from exc
  return service.to_center_response(row)


@router.get("/centers", response_model=list[CenterResponse])
def list_centers(
  tenant_id: str | None = Query(None),
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(require_permission(Permission.DIAGNOSIS_READ)),
) -> list[CenterResponse]:
  _ = user
  service = TenantService(db)
  return [service.to_center_response(c) for c in service.list_centers(tenant_id)]


@router.get("/centers/{center_id}/aggregate", response_model=CenterAggregateReport)
def center_aggregate(
  center_id: str,
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(require_permission(Permission.DIAGNOSIS_READ)),
) -> CenterAggregateReport:
  _ = user
  return TenantService(db).center_aggregate(center_id)


@router.get("/{tenant_id}/aggregate", response_model=TenantAggregateReport)
def tenant_aggregate(
  tenant_id: str,
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(require_permission(Permission.DIAGNOSIS_READ)),
) -> TenantAggregateReport:
  _ = user
  return TenantService(db).tenant_aggregate(tenant_id)
