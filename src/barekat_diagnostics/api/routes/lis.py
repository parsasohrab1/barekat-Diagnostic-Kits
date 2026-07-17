"""API یکپارچگی LIS / HL7 / FHIR."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from barekat_diagnostics.api.deps import CurrentUser, require_permission
from barekat_diagnostics.core.database import get_db
from barekat_diagnostics.core.rbac import Permission
from barekat_diagnostics.schemas import (
  Hl7ExportResponse,
  LabOrderCreate,
  LabOrderResponse,
  LisExportRequest,
)
from barekat_diagnostics.services.lis_service import LisError, LisService

router = APIRouter(prefix="/lis")


def _actor(user: CurrentUser) -> dict:
  return {"actor_id": str(user.id), "actor_email": user.email, "actor_role": user.role}


@router.post("/orders", response_model=LabOrderResponse, status_code=201)
def create_order(
  body: LabOrderCreate,
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(require_permission(Permission.FHIR_IMPORT)),
) -> LabOrderResponse:
  service = LisService(db)
  try:
    order = service.create_order(body, **_actor(user))
  except LisError as exc:
    raise HTTPException(status_code=409, detail=exc.message) from exc
  return service.to_order_response(order)


@router.get("/orders", response_model=list[LabOrderResponse])
def list_orders(
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(require_permission(Permission.DIAGNOSIS_READ)),
) -> list[LabOrderResponse]:
  _ = user
  service = LisService(db)
  return [service.to_order_response(o) for o in service.list_orders()]


@router.post("/export", response_model=Hl7ExportResponse)
def export_result(
  body: LisExportRequest,
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(require_permission(Permission.LIS_EXPORT)),
) -> Hl7ExportResponse:
  service = LisService(db)
  try:
    return service.export_result(body, **_actor(user))
  except LisError as exc:
    raise HTTPException(status_code=404, detail=exc.message) from exc


@router.post("/export/hl7/{sample_id}")
def export_hl7_raw(
  sample_id: str,
  report_id: int | None = None,
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(require_permission(Permission.LIS_EXPORT)),
) -> PlainTextResponse:
  service = LisService(db)
  try:
    result = service.export_result(
      LisExportRequest(sample_id=sample_id, report_id=report_id, format="hl7"),
      **_actor(user),
    )
  except LisError as exc:
    raise HTTPException(status_code=404, detail=exc.message) from exc
  return PlainTextResponse(result.payload, media_type="application/hl7-v2")
