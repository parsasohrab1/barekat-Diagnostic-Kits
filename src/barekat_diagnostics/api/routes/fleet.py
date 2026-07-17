"""API ناوگان مدل و دستگاه‌های edge."""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pathlib import Path
from sqlalchemy.orm import Session

from barekat_diagnostics.api.deps import CurrentUser, require_permission
from barekat_diagnostics.core.database import get_db
from barekat_diagnostics.core.rbac import Permission
from barekat_diagnostics.schemas import (
  DeviceModelAck,
  EdgeDeviceCreate,
  EdgeDeviceResponse,
  FleetManifestResponse,
  FleetReleaseCreate,
  FleetReleaseResponse,
)
from barekat_diagnostics.services.fleet_service import FleetError, FleetService

router = APIRouter(prefix="/fleet")


def _actor(user: CurrentUser) -> dict:
  return {
    "actor_id": str(user.id),
    "actor_email": user.email,
    "actor_role": user.role,
  }


@router.post("/devices", response_model=EdgeDeviceResponse, status_code=201)
def register_device(
  body: EdgeDeviceCreate,
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(require_permission(Permission.EDGE_OPERATE)),
) -> EdgeDeviceResponse:
  service = FleetService(db)
  try:
    row = service.register_device(body, **_actor(user))
  except FleetError as exc:
    raise HTTPException(status_code=409, detail=exc.message) from exc
  return service.to_device_response(row)


@router.get("/devices", response_model=list[EdgeDeviceResponse])
def list_devices(
  tenant_id: str | None = Query(None),
  center_id: str | None = Query(None),
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(require_permission(Permission.DIAGNOSIS_READ)),
) -> list[EdgeDeviceResponse]:
  _ = user
  service = FleetService(db)
  return [
    service.to_device_response(d)
    for d in service.list_devices(tenant_id=tenant_id, center_id=center_id)
  ]


@router.post("/releases", response_model=FleetReleaseResponse, status_code=201)
def create_release(
  body: FleetReleaseCreate,
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(require_permission(Permission.ML_MANAGE)),
) -> FleetReleaseResponse:
  service = FleetService(db)
  try:
    row = service.create_release(body, **_actor(user))
  except Exception as exc:
    raise HTTPException(status_code=400, detail=str(exc)) from exc
  return service.to_release_response(row)


@router.post("/releases/{release_id}/publish", response_model=FleetReleaseResponse)
def publish_release(
  release_id: str,
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(require_permission(Permission.ML_PROMOTE)),
) -> FleetReleaseResponse:
  service = FleetService(db)
  try:
    row = service.publish_release(release_id, **_actor(user))
  except FleetError as exc:
    raise HTTPException(status_code=404, detail=exc.message) from exc
  return service.to_release_response(row)


@router.get("/manifest/{device_id}", response_model=FleetManifestResponse)
def get_manifest(
  device_id: str,
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(require_permission(Permission.EDGE_OPERATE)),
) -> FleetManifestResponse:
  _ = user
  try:
    return FleetService(db).get_manifest_for_device(device_id)
  except FleetError as exc:
    raise HTTPException(status_code=404, detail=exc.message) from exc


@router.get("/download")
def download_model(
  path: str = Query(..., description="مسیر فایل ONNX از manifest"),
  user: CurrentUser = Depends(require_permission(Permission.EDGE_OPERATE)),
):
  _ = user
  file_path = Path(path)
  if not file_path.exists():
    raise HTTPException(status_code=404, detail="فایل مدل یافت نشد")
  return FileResponse(file_path, filename=file_path.name, media_type="application/octet-stream")


@router.post("/ack", response_model=EdgeDeviceResponse)
def ack_update(
  body: DeviceModelAck,
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(require_permission(Permission.EDGE_OPERATE)),
) -> EdgeDeviceResponse:
  service = FleetService(db)
  try:
    row = service.ack_model_update(body, **_actor(user))
  except FleetError as exc:
    raise HTTPException(status_code=404, detail=exc.message) from exc
  return service.to_device_response(row)
