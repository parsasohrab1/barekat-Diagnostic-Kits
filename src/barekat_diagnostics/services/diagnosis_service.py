"""سرویس تشخیص و گزارش."""

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from barekat_diagnostics.core.config import get_settings
from barekat_diagnostics.core.storage import StorageService, get_storage
from barekat_diagnostics.ml.classifier import DiagnosticPredictor
from barekat_diagnostics.models.sample import BatchJob, Diagnosis, DiagnosisJob
from barekat_diagnostics.pipeline.runner import process_sample, report_to_json
from barekat_diagnostics.reports.pdf import generate_report_pdf
from barekat_diagnostics.schemas import (
  BatchJobResponse,
  ClinicalMetricsSchema,
  DiagnosisJobResponse,
  DiagnosisJobSubmitResponse,
  DiagnosisReport,
  ReportApprovalRequest,
  ReportApprovalResponse,
  SampleInput,
)
from barekat_diagnostics.services.audit_trail import AuditTrailService
from barekat_diagnostics.services.batch_service import BatchService, BatchValidationError
from barekat_diagnostics.services.sample_service import SampleService


class DiagnosisService:
  def __init__(self, db: Session, storage: StorageService | None = None) -> None:
    self.db = db
    self.storage = storage or get_storage()
    self.sample_service = SampleService(db, self.storage)
    self.batch_service = BatchService(db)
    self.audit = AuditTrailService(db)

  def _get_predictor(self) -> DiagnosticPredictor:
    return DiagnosticPredictor()

  def _enforce_batch_controls(self, sample: SampleInput) -> None:
    settings = get_settings()
    if not settings.require_batch_controls:
      return
    # کنترل‌ها خودشان نیاز به اعتبار بچ ندارند
    if sample.sample_role in {"positive_control", "negative_control"}:
      return
    if sample.batch_id:
      self.batch_service.require_validated(sample.batch_id)

  def analyze(
    self,
    sample: SampleInput,
    save: bool = True,
    *,
    actor_id: str | None = None,
    actor_email: str | None = None,
    actor_role: str | None = None,
  ) -> DiagnosisReport:
    self._enforce_batch_controls(sample)
    calibration = self.sample_service.get_calibration(sample.calibration_lot)
    predictor = self._get_predictor()

    def predict_fn(features):
      try:
        return predictor.predict(features, sample_id=sample.sample_id)
      except FileNotFoundError:
        return predictor.predict_rule_based(features)

    def explain_fn(features):
      try:
        return predictor.explain(features, sample_id=sample.sample_id)
      except FileNotFoundError:
        return None

    report = process_sample(sample, predict_fn, calibration=calibration, explain_fn=explain_fn)

    from barekat_diagnostics.pipeline.clinical_explain import build_clinical_explanation

    report.clinical_explanation = build_clinical_explanation(
      report, sample=sample, calibration=calibration
    )

    if save:
      diagnosis = Diagnosis(
        sample_id=report.sample_id,
        kit_type=report.kit_type,
        result=report.result,
        confidence=report.confidence,
        recommendation=report.recommendation,
        qc_passed=report.qc_passed,
        qc_warnings="; ".join(f.message for f in report.qc_flags) or None,
        report_json=report_to_json(report),
        features_json=json.dumps(sample.model_dump(exclude_none=True), ensure_ascii=False),
        approval_status="pending",
      )
      self.db.add(diagnosis)
      self.db.commit()
      self.db.refresh(diagnosis)
      report.report_id = diagnosis.id

      from barekat_diagnostics.services.reassessment_service import ReassessmentService

      ra = ReassessmentService(self.db).suggest_from_report(
        report,
        actor_id=actor_id,
        actor_email=actor_email,
        actor_role=actor_role,
      )
      if ra:
        report.reassessment_suggested = True
        report.reassessment_id = ra.reassessment_id
        diagnosis.recommendation = report.recommendation
        diagnosis.report_json = report_to_json(report)
        self.db.commit()

      pdf_bytes = generate_report_pdf(report)
      pdf_key = self.storage.report_key(report.sample_id, diagnosis.id)
      pdf_path = self.storage.upload_bytes(pdf_bytes, pdf_key, content_type="application/pdf")
      diagnosis.pdf_path = pdf_path
      self.db.commit()

      self.sample_service.mark_status(sample.sample_id, "completed")
      self.audit.log(
        "diagnosis.completed",
        actor_id=actor_id,
        actor_email=actor_email,
        actor_role=actor_role,
        resource_type="diagnosis",
        resource_id=str(diagnosis.id),
        model_version=report.model_version,
        detail={
          "sample_id": report.sample_id,
          "result": report.result,
          "confidence": report.confidence,
          "qc_passed": report.qc_passed,
          "reassessment_suggested": report.reassessment_suggested,
        },
      )

    return report

  def approve_report(
    self,
    report_id: int,
    body: ReportApprovalRequest,
    *,
    actor_id: str,
    actor_email: str,
    actor_role: str,
  ) -> ReportApprovalResponse:
    record = self.db.query(Diagnosis).filter(Diagnosis.id == report_id).first()
    if not record:
      raise ValueError("گزارش یافت نشد")

    record.approval_status = body.decision
    record.approved_by = actor_id
    record.approved_by_email = actor_email
    record.approved_at = datetime.now(timezone.utc)
    record.approval_note = body.note
    self.db.commit()
    self.db.refresh(record)

    self.audit.log(
      f"diagnosis.{body.decision}",
      actor_id=actor_id,
      actor_email=actor_email,
      actor_role=actor_role,
      resource_type="diagnosis",
      resource_id=str(record.id),
      model_version=record.model_version,
      detail={
        "sample_id": record.sample_id,
        "result": record.result,
        "decision": body.decision,
        "note": body.note,
      },
    )

    return ReportApprovalResponse(
      report_id=record.id,
      sample_id=record.sample_id,
      approval_status=record.approval_status,
      approved_by=record.approved_by,
      approved_by_email=record.approved_by_email,
      approved_at=record.approved_at,
      note=record.approval_note,
    )

  def save_report(self, report: DiagnosisReport) -> DiagnosisReport:
    """ذخیره گزارش از دستگاه offline بدون تحلیل مجدد."""
    result = self.ingest_edge_report(
      report=report,
      client_report_id=getattr(report, "client_report_id", None),
      device_id=getattr(report, "device_id", None),
      center_id=getattr(report, "center_id", None),
      tenant_id=getattr(report, "tenant_id", None),
      conflict_policy="reject_duplicate",
    )
    return result["report"]

  def ingest_edge_report(
    self,
    *,
    report: DiagnosisReport,
    client_report_id: str | None = None,
    device_id: str | None = None,
    center_id: str | None = None,
    tenant_id: str | None = None,
    conflict_policy: str = "reject_duplicate",
  ) -> dict:
    """همگام‌سازی idempotent با حل تعارض."""
    from barekat_diagnostics.models.fleet import EdgeDevice

    client_report_id = client_report_id or report.client_report_id
    device_id = device_id or report.device_id
    center_id = center_id or report.center_id
    tenant_id = tenant_id or report.tenant_id

    existing = None
    if client_report_id:
      existing = (
        self.db.query(Diagnosis)
        .filter(Diagnosis.client_report_id == client_report_id)
        .first()
      )

    resolution = "accepted"
    conflict = False

    if existing is not None:
      conflict = True
      if conflict_policy == "client_wins":
        resolution = "client_wins"
        existing.result = report.result
        existing.confidence = report.confidence
        existing.recommendation = report.recommendation
        existing.qc_passed = report.qc_passed
        existing.report_json = report_to_json(report)
        existing.model_version = report.model_version
        self.db.commit()
        self._log_conflict(client_report_id, report, device_id, center_id, resolution)
        report.report_id = existing.id
        return {"report": report, "resolution": resolution, "conflict": True, "report_id": existing.id}

      resolution = "server_wins" if conflict_policy == "server_wins" else "rejected_duplicate"
      self._log_conflict(client_report_id, report, device_id, center_id, resolution)
      report.report_id = existing.id
      return {"report": report, "resolution": resolution, "conflict": True, "report_id": existing.id}

    diagnosis = Diagnosis(
      sample_id=report.sample_id,
      kit_type=report.kit_type,
      result=report.result,
      confidence=report.confidence,
      recommendation=report.recommendation,
      qc_passed=report.qc_passed,
      qc_warnings="; ".join(f.message for f in report.qc_flags) or None,
      report_json=report_to_json(report),
      model_version=report.model_version,
      approval_status="pending",
      client_report_id=client_report_id,
      tenant_id=tenant_id,
      center_id=center_id,
      device_id=device_id,
    )
    self.db.add(diagnosis)
    self.db.commit()
    self.db.refresh(diagnosis)
    report.report_id = diagnosis.id

    try:
      pdf_bytes = generate_report_pdf(report)
      pdf_key = self.storage.report_key(report.sample_id, diagnosis.id)
      pdf_path = self.storage.upload_bytes(pdf_bytes, pdf_key, content_type="application/pdf")
      diagnosis.pdf_path = pdf_path
      self.db.commit()
    except Exception:
      pass

    if device_id:
      device = self.db.query(EdgeDevice).filter(EdgeDevice.device_id == device_id).first()
      if device:
        device.last_sync_at = datetime.now(timezone.utc)
        device.last_seen_at = datetime.now(timezone.utc)
        device.status = "online"
        self.db.commit()

    return {
      "report": report,
      "resolution": resolution,
      "conflict": conflict,
      "report_id": diagnosis.id,
    }

  def _log_conflict(
    self,
    client_report_id: str | None,
    report: DiagnosisReport,
    device_id: str | None,
    center_id: str | None,
    resolution: str,
  ) -> None:
    from barekat_diagnostics.models.fleet import SyncConflictLog

    entry = SyncConflictLog(
      conflict_id=f"SCF-{uuid.uuid4().hex[:10].upper()}",
      client_report_id=client_report_id or report.sample_id,
      sample_id=report.sample_id,
      device_id=device_id,
      center_id=center_id,
      resolution=resolution,
      detail_json=json.dumps({"result": report.result, "model_version": report.model_version}),
    )
    self.db.add(entry)
    self.db.commit()

  def submit_async(self, sample: SampleInput) -> DiagnosisJobSubmitResponse:
    """ثبت job ناهمزمان برای تحلیل نمونه."""
    from barekat_diagnostics.tasks.pipeline_tasks import analyze_diagnosis_task

    self._enforce_batch_controls(sample)
    self.sample_service.create_sample(sample, curve_data=sample.curve_data)
    job_id = str(uuid.uuid4())
    job = DiagnosisJob(
      job_id=job_id,
      sample_id=sample.sample_id,
      status="pending",
      progress=0.0,
    )
    self.db.add(job)
    self.db.commit()

    sample_json = json.dumps(sample.model_dump(), ensure_ascii=False)
    task = analyze_diagnosis_task.delay(job_id, sample_json)
    job.celery_task_id = task.id
    self.db.commit()

    return DiagnosisJobSubmitResponse(
      job_id=job_id,
      sample_id=sample.sample_id,
      status="pending",
      message="Analysis queued for async processing",
    )

  def get_job(self, job_id: str) -> DiagnosisJobResponse | None:
    job = self.db.query(DiagnosisJob).filter(DiagnosisJob.job_id == job_id).first()
    if not job:
      return None
    report = None
    if job.report_json:
      report = DiagnosisReport.model_validate(json.loads(job.report_json))
    return DiagnosisJobResponse(
      job_id=job.job_id,
      sample_id=job.sample_id,
      status=job.status,  # type: ignore[arg-type]
      progress=job.progress,
      report=report,
      error_message=job.error_message,
      created_at=job.created_at,
      completed_at=job.completed_at,
    )

  def list_jobs(self, limit: int = 50) -> list[DiagnosisJobResponse]:
    rows = (
      self.db.query(DiagnosisJob)
      .order_by(DiagnosisJob.created_at.desc())
      .limit(limit)
      .all()
    )
    results = []
    for job in rows:
      report = None
      if job.report_json:
        report = DiagnosisReport.model_validate(json.loads(job.report_json))
      results.append(
        DiagnosisJobResponse(
          job_id=job.job_id,
          sample_id=job.sample_id,
          status=job.status,  # type: ignore[arg-type]
          progress=job.progress,
          report=report,
          error_message=job.error_message,
          created_at=job.created_at,
          completed_at=job.completed_at,
        )
      )
    return results

  def get_history(self, sample_id: str) -> list[DiagnosisReport]:
    records = (
      self.db.query(Diagnosis)
      .filter(Diagnosis.sample_id == sample_id)
      .order_by(Diagnosis.created_at.desc())
      .limit(20)
      .all()
    )
    reports = []
    for r in records:
      if r.report_json:
        reports.append(DiagnosisReport.model_validate(json.loads(r.report_json)))
      else:
        reports.append(DiagnosisReport(
          report_id=r.id,
          sample_id=r.sample_id,
          kit_type=r.kit_type,
          result=r.result,  # type: ignore[arg-type]
          confidence=r.confidence,
          qc_passed=r.qc_passed,
          recommendation=r.recommendation,  # type: ignore[arg-type]
          clinical_metrics=ClinicalMetricsSchema(),
          model_version=r.model_version,
          created_at=r.created_at,
        ))
    return reports

  def get_pdf_bytes(self, sample_id: str, report_id: int) -> bytes | None:
    record = (
      self.db.query(Diagnosis)
      .filter(Diagnosis.id == report_id, Diagnosis.sample_id == sample_id)
      .first()
    )
    if not record or not record.pdf_path:
      return None
    if record.pdf_path.startswith("s3://"):
      key = record.pdf_path.split("/", 3)[-1]
      return self.storage.download_bytes(key)
    from pathlib import Path
    return Path(record.pdf_path).read_bytes()

  def analyze_batch(self, sample_ids: list[str]) -> BatchJobResponse:
    job_id = str(uuid.uuid4())
    job = BatchJob(
      job_id=job_id,
      status="running",
      total_samples=len(sample_ids),
      completed_samples=0,
    )
    self.db.add(job)
    self.db.commit()

    reports: list[DiagnosisReport] = []
    for sid in sample_ids:
      sample_record = self.sample_service.get_sample(sid)
      if not sample_record:
        continue
      sample_input = self.sample_service.sample_to_input(sample_record)
      report = self.analyze(sample_input)
      reports.append(report)
      job.completed_samples += 1

    job.status = "completed"
    job.completed_at = datetime.now(timezone.utc)
    job.results_json = json.dumps([r.model_dump(mode="json") for r in reports], ensure_ascii=False)
    self.db.commit()

    return BatchJobResponse(
      job_id=job.job_id,
      status=job.status,
      total_samples=job.total_samples,
      completed_samples=job.completed_samples,
      reports=reports,
    )

  def get_batch_job(self, job_id: str) -> BatchJobResponse | None:
    job = self.db.query(BatchJob).filter(BatchJob.job_id == job_id).first()
    if not job:
      return None
    reports = []
    if job.results_json:
      reports = [DiagnosisReport.model_validate(r) for r in json.loads(job.results_json)]
    return BatchJobResponse(
      job_id=job.job_id,
      status=job.status,
      total_samples=job.total_samples,
      completed_samples=job.completed_samples,
      reports=reports,
    )


# Re-export for callers that catch batch gate errors
__all__ = ["DiagnosisService", "BatchValidationError"]
