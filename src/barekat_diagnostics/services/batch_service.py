"""Laboratory batch service and positive/negative control validation."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from barekat_diagnostics.models.sample import AssayBatch, Sample
from barekat_diagnostics.schemas import (
  AssayBatchCreate,
  AssayBatchResponse,
  BatchControlUpdate,
)
from barekat_diagnostics.services.audit_trail import AuditTrailService


class BatchValidationError(Exception):
  def __init__(self, message: str) -> None:
    self.message = message
    super().__init__(message)


class BatchService:
  def __init__(self, db: Session) -> None:
    self.db = db
    self.audit = AuditTrailService(db)

  def create_batch(
    self,
    body: AssayBatchCreate,
    *,
    actor_id: str | None = None,
    actor_email: str | None = None,
    actor_role: str | None = None,
  ) -> AssayBatch:
    existing = self.db.query(AssayBatch).filter(AssayBatch.batch_id == body.batch_id).first()
    if existing:
      raise BatchValidationError(f"Batch {body.batch_id} has already been registered")

    batch = AssayBatch(
      batch_id=body.batch_id,
      lot_number=body.lot_number,
      kit_type=body.kit_type,
      label=body.label,
      status="controls_pending",
      pos_control_ct_max=body.pos_control_ct_max,
      neg_control_ct_min=body.neg_control_ct_min,
      created_by=actor_id,
    )
    self.db.add(batch)
    self.db.commit()
    self.db.refresh(batch)

    self.audit.log(
      "batch.created",
      actor_id=actor_id,
      actor_email=actor_email,
      actor_role=actor_role,
      resource_type="assay_batch",
      resource_id=batch.batch_id,
      detail={"lot_number": batch.lot_number, "kit_type": batch.kit_type},
    )
    return batch

  def get_batch(self, batch_id: str) -> AssayBatch | None:
    return self.db.query(AssayBatch).filter(AssayBatch.batch_id == batch_id).first()

  def list_batches(self, limit: int = 50) -> list[AssayBatch]:
    return self.db.query(AssayBatch).order_by(AssayBatch.created_at.desc()).limit(limit).all()

  def register_controls(
    self,
    batch_id: str,
    body: BatchControlUpdate,
    *,
    actor_id: str | None = None,
    actor_email: str | None = None,
    actor_role: str | None = None,
  ) -> AssayBatch:
    batch = self.get_batch(batch_id)
    if not batch:
      raise BatchValidationError("Batch not found")

    if body.positive_control_sample_id:
      batch.positive_control_sample_id = body.positive_control_sample_id
      pos = self.db.query(Sample).filter(Sample.sample_id == body.positive_control_sample_id).first()
      if pos:
        pos.sample_role = "positive_control"
        pos.batch_id = batch.batch_id
        batch.positive_control_ct = pos.ct_value

    if body.negative_control_sample_id:
      batch.negative_control_sample_id = body.negative_control_sample_id
      neg = self.db.query(Sample).filter(Sample.sample_id == body.negative_control_sample_id).first()
      if neg:
        neg.sample_role = "negative_control"
        neg.batch_id = batch.batch_id
        batch.negative_control_ct = neg.ct_value

    if body.positive_control_ct is not None:
      batch.positive_control_ct = body.positive_control_ct
    if body.negative_control_ct is not None:
      batch.negative_control_ct = body.negative_control_ct

    self.db.commit()
    self.db.refresh(batch)

    self.audit.log(
      "batch.controls_registered",
      actor_id=actor_id,
      actor_email=actor_email,
      actor_role=actor_role,
      resource_type="assay_batch",
      resource_id=batch.batch_id,
      detail={
        "positive_control_sample_id": batch.positive_control_sample_id,
        "negative_control_sample_id": batch.negative_control_sample_id,
        "positive_control_ct": batch.positive_control_ct,
        "negative_control_ct": batch.negative_control_ct,
      },
    )
    return batch

  def validate_controls(
    self,
    batch_id: str,
    *,
    actor_id: str | None = None,
    actor_email: str | None = None,
    actor_role: str | None = None,
  ) -> AssayBatch:
    batch = self.get_batch(batch_id)
    if not batch:
      raise BatchValidationError("Batch not found")

    if batch.positive_control_ct is None or batch.negative_control_ct is None:
      raise BatchValidationError("Recording the positive and negative control Ct is required before validation")

    pos_ok = batch.positive_control_ct <= batch.pos_control_ct_max
    neg_ok = batch.negative_control_ct >= batch.neg_control_ct_min

    batch.positive_control_passed = pos_ok
    batch.negative_control_passed = neg_ok
    batch.controls_validated = pos_ok and neg_ok
    batch.validated_by = actor_id
    batch.validated_at = datetime.now(timezone.utc)

    messages = []
    if not pos_ok:
      messages.append(
        f"Positive control failed: Ct={batch.positive_control_ct} > max={batch.pos_control_ct_max}"
      )
    if not neg_ok:
      messages.append(
        f"Negative control failed: Ct={batch.negative_control_ct} < min={batch.neg_control_ct_min}"
      )

    if batch.controls_validated:
      batch.status = "validated"
      batch.validation_message = "Positive and negative controls accepted"
    else:
      batch.status = "failed"
      batch.validation_message = "; ".join(messages)

    self.db.commit()
    self.db.refresh(batch)

    self.audit.log(
      "batch.controls_validated" if batch.controls_validated else "batch.controls_failed",
      actor_id=actor_id,
      actor_email=actor_email,
      actor_role=actor_role,
      resource_type="assay_batch",
      resource_id=batch.batch_id,
      detail={
        "controls_validated": batch.controls_validated,
        "positive_control_passed": batch.positive_control_passed,
        "negative_control_passed": batch.negative_control_passed,
        "message": batch.validation_message,
      },
    )
    return batch

  def require_validated(self, batch_id: str | None) -> AssayBatch | None:
    if not batch_id:
      return None
    batch = self.get_batch(batch_id)
    if not batch:
      raise BatchValidationError(f"Batch {batch_id} not found")
    if not batch.controls_validated:
      raise BatchValidationError(
        f"Batch {batch_id} does not yet have valid positive/negative controls — analysis of patient samples is not allowed"
      )
    return batch

  def to_response(self, batch: AssayBatch) -> AssayBatchResponse:
    return AssayBatchResponse(
      batch_id=batch.batch_id,
      lot_number=batch.lot_number,
      kit_type=batch.kit_type,
      label=batch.label,
      status=batch.status,
      pos_control_ct_max=batch.pos_control_ct_max,
      neg_control_ct_min=batch.neg_control_ct_min,
      positive_control_sample_id=batch.positive_control_sample_id,
      negative_control_sample_id=batch.negative_control_sample_id,
      positive_control_ct=batch.positive_control_ct,
      negative_control_ct=batch.negative_control_ct,
      positive_control_passed=batch.positive_control_passed,
      negative_control_passed=batch.negative_control_passed,
      controls_validated=batch.controls_validated,
      validation_message=batch.validation_message,
      created_at=batch.created_at,
      validated_at=batch.validated_at,
    )
