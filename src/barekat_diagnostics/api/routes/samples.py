"""Sample management API endpoints."""

import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from barekat_diagnostics.core.database import get_db
from barekat_diagnostics.schemas import SampleCreateRequest, SampleInput, SampleResponse
from barekat_diagnostics.services.sample_service import SampleService

router = APIRouter(prefix="/samples")


@router.post("/", response_model=SampleResponse, status_code=201)
def create_sample(
  request: SampleCreateRequest,
  db: Session = Depends(get_db),
) -> SampleResponse:
  """Register a new sample."""
  service = SampleService(db)
  record = service.create_sample(request.sample, curve_data=request.sample.curve_data)
  return service.to_response(record)


@router.post("/upload", response_model=SampleResponse, status_code=201)
async def upload_sample(
  sample_id: str = Form(...),
  kit_type: str = Form("qpcr"),
  patient_id: str | None = Form(None),
  calibration_lot: str | None = Form(None),
  quality_score: float | None = Form(None),
  ct_value: float | None = Form(None),
  curve_file: UploadFile | None = File(None),
  db: Session = Depends(get_db),
) -> SampleResponse:
  """Upload a sample with a raw curve (40 qPCR cycles)."""
  curve_data = None
  if curve_file:
    content = await curve_file.read()
    try:
      parsed = json.loads(content)
      curve_data = parsed if isinstance(parsed, list) else parsed.get("curve_data")
    except json.JSONDecodeError:
      text = content.decode("utf-8").strip()
      curve_data = [float(x) for x in text.replace(",", " ").split()]

  sample_input = SampleInput(
    sample_id=sample_id,
    patient_id=patient_id,
    kit_type=kit_type,
    calibration_lot=calibration_lot,
    ct_value=ct_value,
    quality_score=quality_score,
    curve_data=curve_data,
  )
  service = SampleService(db)
  record = service.create_sample(sample_input, curve_data=curve_data)
  return service.to_response(record)


@router.get("/", response_model=list[SampleResponse])
def list_samples(limit: int = 50, db: Session = Depends(get_db)) -> list[SampleResponse]:
  """List samples."""
  return SampleService(db).list_samples(limit=limit)


@router.get("/{sample_id}", response_model=SampleResponse)
def get_sample(sample_id: str, db: Session = Depends(get_db)) -> SampleResponse:
  """Get sample details."""
  service = SampleService(db)
  record = service.get_sample(sample_id)
  if not record:
    raise HTTPException(status_code=404, detail="Sample not found")
  return service.to_response(record)
