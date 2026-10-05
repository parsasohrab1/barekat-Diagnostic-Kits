"""Reassessment suggestion and execution after suspicious QC."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from barekat_diagnostics.models.clinical import ReassessmentRequest
from barekat_diagnostics.models.sample import Diagnosis
from barekat_diagnostics.schemas import (
  DiagnosisReport,
  ReassessmentAcceptRequest,
  ReassessmentCompareResponse,
  ReassessmentResponse,
)
from barekat_diagnostics.services.audit_trail import AuditTrailService


class ReassessmentError(Exception):
  def __init__(self, message: str) -> None:
    self.message = message
    super().__init__(message)


def should_suggest_reassessment(report: DiagnosisReport) -> bool:
  """Is the QC/result suspicious and should reassessment be suggested?"""
  if report.recommendation in {"retest", "invalid", "reassess"}:
    return True
  if not report.qc_passed:
    return True
  warning_count = sum(1 for f in report.qc_flags if f.severity == "warning")
  if warning_count >= 2 and report.confidence < 0.85:
    return True
  if report.result == "inconclusive":
    return True
  # borderline confidence with any QC flag
  if report.qc_flags and report.confidence < 0.7:
    return True
  return False


class ReassessmentService:
  def __init__(self, db: Session) -> None:
    self.db = db
    self.audit = AuditTrailService(db)

  @property
  def diagnosis(self):
    from barekat_diagnostics.services.diagnosis_service import DiagnosisService

    return DiagnosisService(self.db)

  def suggest_from_report(
    self,
    report: DiagnosisReport,
    **actor,
  ) -> ReassessmentRequest | None:
    if not should_suggest_reassessment(report):
      return None
    rid = f"RA-{uuid.uuid4().hex[:10].upper()}"
    codes = [f.code for f in report.qc_flags]
    reason_parts = []
    if report.recommendation != "report":
      reason_parts.append(f"recommendation={report.recommendation}")
    if codes:
      reason_parts.append(f"QC={','.join(codes)}")
    if report.confidence < 0.75:
      reason_parts.append(f"low confidence={report.confidence:.2f}")
    reason = "; ".join(reason_parts) or "suspicious QC pattern"

    row = ReassessmentRequest(
      reassessment_id=rid,
      original_sample_id=report.sample_id,
      original_report_id=report.report_id,
      reason=reason,
      qc_codes=json.dumps(codes),
      status="suggested",
      created_by=actor.get("actor_id"),
    )
    self.db.add(row)
    self.db.commit()
    self.db.refresh(row)
    self.audit.log(
      "reassessment.suggested",
      resource_type="reassessment",
      resource_id=rid,
      detail={"sample_id": report.sample_id, "reason": reason},
      **{k: v for k, v in actor.items() if k.startswith("actor_")},
    )
    return row

  def list_requests(self, status: str | None = None, limit: int = 50) -> list[ReassessmentRequest]:
    q = self.db.query(ReassessmentRequest).order_by(ReassessmentRequest.created_at.desc())
    if status:
      q = q.filter(ReassessmentRequest.status == status)
    return q.limit(limit).all()

  def get(self, reassessment_id: str) -> ReassessmentRequest | None:
    return (
      self.db.query(ReassessmentRequest)
      .filter(ReassessmentRequest.reassessment_id == reassessment_id)
      .first()
    )

  def accept_and_run(
    self,
    reassessment_id: str,
    body: ReassessmentAcceptRequest,
    **actor,
  ) -> ReassessmentCompareResponse:
    row = self.get(reassessment_id)
    if not row:
      raise ReassessmentError("Reassessment request not found")
    if row.status not in {"suggested", "accepted"}:
      raise ReassessmentError(f"Status {row.status} cannot be executed")

    sample = body.sample
    if sample is None:
      # Build a retest sample from the previous sample with a suffix
      from barekat_diagnostics.services.sample_service import SampleService

      original = SampleService(self.db).get_sample(row.original_sample_id)
      if not original:
        raise ReassessmentError("Original sample not found — send the sample in the body")
      base = SampleService(self.db).sample_to_input(original)
      sample = base.model_copy(
        update={"sample_id": f"{row.original_sample_id}-RT{uuid.uuid4().hex[:4].upper()}"}
      )
      if body.override_fields:
        sample = sample.model_copy(update=body.override_fields)

    row.status = "running"
    row.retest_sample_id = sample.sample_id
    self.db.commit()

    report = self.diagnosis.analyze(
      sample,
      actor_id=actor.get("actor_id"),
      actor_email=actor.get("actor_email"),
      actor_role=actor.get("actor_role"),
    )

    original_report = None
    if row.original_report_id:
      orig = self.db.query(Diagnosis).filter(Diagnosis.id == row.original_report_id).first()
      if orig and orig.report_json:
        original_report = DiagnosisReport.model_validate(json.loads(orig.report_json))

    comparison = {
      "original_result": original_report.result if original_report else None,
      "original_confidence": original_report.confidence if original_report else None,
      "retest_result": report.result,
      "retest_confidence": report.confidence,
      "concordant": (
        original_report.result == report.result if original_report else None
      ),
    }
    row.retest_report_id = report.report_id
    row.comparison_json = json.dumps(comparison, ensure_ascii=False)
    row.status = "completed"
    row.completed_at = datetime.now(timezone.utc)
    self.db.commit()
    self.db.refresh(row)

    self.audit.log(
      "reassessment.completed",
      resource_type="reassessment",
      resource_id=reassessment_id,
      detail=comparison,
      **{k: v for k, v in actor.items() if k.startswith("actor_")},
    )

    return ReassessmentCompareResponse(
      reassessment_id=reassessment_id,
      status=row.status,
      original_sample_id=row.original_sample_id,
      retest_sample_id=row.retest_sample_id,
      original_result=comparison["original_result"],
      retest_result=report.result,  # type: ignore[arg-type]
      concordant=comparison["concordant"],
      retest_report=report,
      comparison=comparison,
    )

  def to_response(self, row: ReassessmentRequest) -> ReassessmentResponse:
    return ReassessmentResponse(
      reassessment_id=row.reassessment_id,
      original_sample_id=row.original_sample_id,
      original_report_id=row.original_report_id,
      retest_sample_id=row.retest_sample_id,
      retest_report_id=row.retest_report_id,
      reason=row.reason,
      qc_codes=json.loads(row.qc_codes) if row.qc_codes else [],
      status=row.status,
      created_at=row.created_at,
      completed_at=row.completed_at,
    )
