"""API واردسازی خروجی دستگاه qPCR (CSV / RDML)."""

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from barekat_diagnostics.api.deps import CurrentUser, require_permission
from barekat_diagnostics.core.database import get_db
from barekat_diagnostics.core.rbac import Permission
from barekat_diagnostics.importers.qpcr_csv import parse_qpcr_csv, wells_summary
from barekat_diagnostics.importers.qpcr_rdml import parse_qpcr_rdml
from barekat_diagnostics.schemas import QpcrImportResponse
from barekat_diagnostics.services.audit_trail import AuditTrailService
from barekat_diagnostics.services.sample_service import SampleService

router = APIRouter(prefix="/import")


@router.post("/qpcr", response_model=QpcrImportResponse, status_code=201)
async def import_qpcr_file(
  file: UploadFile = File(...),
  format: str = Form("auto"),
  calibration_lot: str | None = Form(None),
  batch_id: str | None = Form(None),
  persist: bool = Form(True),
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(require_permission(Permission.SAMPLES_WRITE)),
) -> QpcrImportResponse:
  """آپلود خروجی دستگاه qPCR — فرمت CSV یا RDML."""
  content = await file.read()
  if not content:
    raise HTTPException(status_code=400, detail="فایل خالی است")

  filename = (file.filename or "").lower()
  fmt = format.lower().strip()
  if fmt == "auto":
    if filename.endswith(".rdml") or filename.endswith(".xml"):
      fmt = "rdml"
    else:
      fmt = "csv"

  try:
    if fmt == "rdml":
      wells = parse_qpcr_rdml(content, calibration_lot=calibration_lot)
    elif fmt == "csv":
      wells = parse_qpcr_csv(content, calibration_lot=calibration_lot)
    else:
      raise HTTPException(status_code=400, detail="فرمت باید csv یا rdml باشد")
  except ValueError as exc:
    raise HTTPException(status_code=400, detail=str(exc)) from exc

  sample_service = SampleService(db)
  saved = []
  for well in wells:
    well.sample.batch_id = batch_id
    well.sample.sample_role = well.role
    well.sample.calibration_lot = calibration_lot or well.sample.calibration_lot
    if persist:
      record = sample_service.create_sample(well.sample, curve_data=well.sample.curve_data)
      saved.append(sample_service.to_response(record))

  AuditTrailService(db).log(
    "qpcr.imported",
    actor_id=str(user.id),
    actor_email=user.email,
    actor_role=user.role,
    resource_type="import",
    resource_id=batch_id or filename or "qpcr",
    detail={
      "format": fmt,
      "filename": file.filename,
      "imported": len(wells),
      "batch_id": batch_id,
      "calibration_lot": calibration_lot,
    },
  )

  return QpcrImportResponse(
    imported=len(wells),
    batch_id=batch_id,
    summary=wells_summary(wells),
    samples=saved,
    wells=wells if not persist else [],
  )
