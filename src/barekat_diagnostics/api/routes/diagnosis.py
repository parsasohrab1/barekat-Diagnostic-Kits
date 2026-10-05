"""Diagnosis API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from barekat_diagnostics.api.deps import CurrentUser, get_current_user, require_permission
from barekat_diagnostics.core.database import get_db
from barekat_diagnostics.core.rbac import Permission
from barekat_diagnostics.schemas import (
  BatchAnalyzeRequest,
  BatchJobResponse,
  DiagnosisJobResponse,
  DiagnosisJobSubmitResponse,
  DiagnosisReport,
  DiagnosisRequest,
  ReportApprovalRequest,
  ReportApprovalResponse,
)
from barekat_diagnostics.services.batch_service import BatchValidationError
from barekat_diagnostics.services.diagnosis_service import DiagnosisService
from barekat_diagnostics.services.sample_service import SampleService

router = APIRouter(prefix="/diagnosis")


@router.post("/analyze", response_model=DiagnosisReport | DiagnosisJobSubmitResponse)
def analyze_sample(
  request: DiagnosisRequest,
  async_mode: bool = Query(False, description="Queue analysis as background job"),
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(require_permission(Permission.DIAGNOSIS_RUN)),
):
  """Analyze a sample — sync or async (with async_mode=true)."""
  service = DiagnosisService(db)
  try:
    if async_mode:
      return service.submit_async(request.sample)

    sample_service = SampleService(db)
    sample_service.create_sample(request.sample, curve_data=request.sample.curve_data)
    return service.analyze(
      request.sample,
      actor_id=str(user.id),
      actor_email=user.email,
      actor_role=user.role,
    )
  except BatchValidationError as exc:
    raise HTTPException(status_code=409, detail=exc.message) from exc


@router.get("/jobs", response_model=list[DiagnosisJobResponse])
def list_diagnosis_jobs(
  limit: int = Query(50, ge=1, le=200),
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(require_permission(Permission.DIAGNOSIS_READ)),
) -> list[DiagnosisJobResponse]:
  _ = user
  return DiagnosisService(db).list_jobs(limit=limit)


@router.get("/jobs/{job_id}", response_model=DiagnosisJobResponse)
def get_diagnosis_job(
  job_id: str,
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(require_permission(Permission.DIAGNOSIS_READ)),
) -> DiagnosisJobResponse:
  _ = user
  result = DiagnosisService(db).get_job(job_id)
  if not result:
    raise HTTPException(status_code=404, detail="Job not found")
  return result


@router.get("/history/{sample_id}", response_model=list[DiagnosisReport])
def get_diagnosis_history(
  sample_id: str,
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(require_permission(Permission.DIAGNOSIS_READ)),
) -> list[DiagnosisReport]:
  _ = user
  reports = DiagnosisService(db).get_history(sample_id)
  if not reports:
    raise HTTPException(status_code=404, detail="Diagnosis not found")
  return reports


@router.post("/reports/{report_id}/approve", response_model=ReportApprovalResponse)
def approve_report(
  report_id: int,
  body: ReportApprovalRequest,
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(require_permission(Permission.REPORTS_APPROVE)),
) -> ReportApprovalResponse:
  try:
    return DiagnosisService(db).approve_report(
      report_id,
      body,
      actor_id=str(user.id),
      actor_email=user.email,
      actor_role=user.role,
    )
  except ValueError as exc:
    raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/reports/{sample_id}/{report_id}/pdf")
def download_report_pdf(
  sample_id: str,
  report_id: int,
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(require_permission(Permission.DIAGNOSIS_READ)),
) -> Response:
  _ = user
  pdf_bytes = DiagnosisService(db).get_pdf_bytes(sample_id, report_id)
  if not pdf_bytes:
    raise HTTPException(status_code=404, detail="PDF report not found")
  return Response(
    content=pdf_bytes,
    media_type="application/pdf",
    headers={"Content-Disposition": f'attachment; filename="report_{sample_id}.pdf"'},
  )


@router.post("/batch", response_model=BatchJobResponse)
def analyze_batch(
  request: BatchAnalyzeRequest,
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(require_permission(Permission.DIAGNOSIS_RUN)),
) -> BatchJobResponse:
  _ = user
  try:
    return DiagnosisService(db).analyze_batch(request.sample_ids)
  except BatchValidationError as exc:
    raise HTTPException(status_code=409, detail=exc.message) from exc


@router.get("/batch/{job_id}", response_model=BatchJobResponse)
def get_batch_status(
  job_id: str,
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(require_permission(Permission.DIAGNOSIS_READ)),
) -> BatchJobResponse:
  _ = user
  result = DiagnosisService(db).get_batch_job(job_id)
  if not result:
    raise HTTPException(status_code=404, detail="Job not found")
  return result


@router.post("/sync", status_code=201)
def sync_offline_report(
  request: dict,
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(get_current_user),
) -> dict:
  """Receive a report from an offline device with conflict resolution and idempotency."""
  _ = user
  report_data = request.get("report")
  if not report_data:
    raise HTTPException(status_code=400, detail="report required")
  report = DiagnosisReport.model_validate(report_data)
  result = DiagnosisService(db).ingest_edge_report(
    report=report,
    client_report_id=request.get("client_report_id") or report.client_report_id,
    device_id=request.get("device_id") or report.device_id,
    center_id=request.get("center_id") or report.center_id,
    tenant_id=request.get("tenant_id") or report.tenant_id,
    conflict_policy=request.get("conflict_policy") or "reject_duplicate",
  )
  status = 409 if result["conflict"] and result["resolution"] != "client_wins" else 201
  payload = {
    "sample_id": report.sample_id,
    "synced": True,
    "report_id": result["report_id"],
    "resolution": result["resolution"],
    "conflict": result["conflict"],
  }
  if status == 409:
    raise HTTPException(status_code=409, detail=payload)
  return payload
