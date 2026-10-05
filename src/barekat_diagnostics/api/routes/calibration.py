"""Kit calibration API endpoints."""

import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from barekat_diagnostics.core.database import get_db
from barekat_diagnostics.core.storage import get_storage
from barekat_diagnostics.models.sample import KitCalibration
from barekat_diagnostics.schemas import CalibrationCreate, CalibrationResponse

router = APIRouter(prefix="/calibration")


@router.post("/", response_model=CalibrationResponse, status_code=201)
def register_calibration(
  body: CalibrationCreate,
  db: Session = Depends(get_db),
) -> CalibrationResponse:
  """Record kit calibration (lot number, expiry, cutoff, standard curve)."""
  existing = db.query(KitCalibration).filter(KitCalibration.lot_number == body.lot_number).first()
  if existing:
    raise HTTPException(status_code=409, detail="This lot has already been registered")

  storage = get_storage()
  curve_path = None
  curve_json = None
  if body.standard_curve:
    curve_json = json.dumps(body.standard_curve, ensure_ascii=False)
    curve_path = storage.upload_json(body.standard_curve, storage.calibration_key(body.lot_number))

  record = KitCalibration(
    lot_number=body.lot_number,
    kit_type=body.kit_type,
    expiry_date=body.expiry_date,
    cutoff_value=body.cutoff_value,
    standard_curve_path=curve_path,
    standard_curve_json=curve_json,
  )
  db.add(record)
  db.commit()
  db.refresh(record)

  return CalibrationResponse(
    lot_number=record.lot_number,
    kit_type=record.kit_type,
    expiry_date=record.expiry_date,
    cutoff_value=record.cutoff_value,
    standard_curve_path=record.standard_curve_path,
    created_at=record.created_at,
  )


@router.post("/upload", response_model=CalibrationResponse, status_code=201)
async def upload_calibration(
  lot_number: str = Form(...),
  kit_type: str = Form("qpcr"),
  cutoff_value: float | None = Form(None),
  curve_file: UploadFile = File(...),
  db: Session = Depends(get_db),
) -> CalibrationResponse:
  """Upload the standard curve file to MinIO."""
  content = await curve_file.read()
  standard_curve = json.loads(content)
  if not isinstance(standard_curve, list):
    raise HTTPException(status_code=400, detail="Invalid standard curve format")

  body = CalibrationCreate(
    lot_number=lot_number,
    kit_type=kit_type,
    cutoff_value=cutoff_value,
    standard_curve=standard_curve,
  )
  return register_calibration(body, db)


@router.get("/{lot_number}", response_model=CalibrationResponse)
def get_calibration(lot_number: str, db: Session = Depends(get_db)) -> CalibrationResponse:
  """Get calibration information."""
  record = db.query(KitCalibration).filter(KitCalibration.lot_number == lot_number).first()
  if not record:
    raise HTTPException(status_code=404, detail="Calibration not found")
  return CalibrationResponse(
    lot_number=record.lot_number,
    kit_type=record.kit_type,
    expiry_date=record.expiry_date,
    cutoff_value=record.cutoff_value,
    standard_curve_path=record.standard_curve_path,
    created_at=record.created_at,
  )
