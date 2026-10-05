"""Risk management and medical software change control."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from barekat_diagnostics.ml.registry import ModelRegistry, RegistryError
from barekat_diagnostics.models.quality import ChangeRequest, ClinicalValidationProtocol
from barekat_diagnostics.schemas import (
  ChangeRequestApplyResponse,
  ChangeRequestCreate,
  ChangeRequestDecision,
  ChangeRequestResponse,
)
from barekat_diagnostics.services.audit_trail import AuditTrailService


class ChangeControlError(Exception):
  def __init__(self, message: str) -> None:
    self.message = message
    super().__init__(message)


class ChangeControlService:
  def __init__(self, db: Session) -> None:
    self.db = db
    self.audit = AuditTrailService(db)

  def create(
    self,
    body: ChangeRequestCreate,
    *,
    actor_id: str | None = None,
    actor_email: str | None = None,
    actor_role: str | None = None,
  ) -> ChangeRequest:
    change_id = body.change_id or f"CR-{uuid.uuid4().hex[:10].upper()}"
    if self.db.query(ChangeRequest).filter(ChangeRequest.change_id == change_id).first():
      raise ChangeControlError(f"Duplicate change_id: {change_id}")

    if body.change_type == "model" and body.risk_level in {"high", "critical"}:
      if not body.protocol_id:
        raise ChangeControlError("For a high-risk model change, a validation protocol_id is required")

    row = ChangeRequest(
      change_id=change_id,
      change_type=body.change_type,
      title=body.title,
      description=body.description,
      risk_level=body.risk_level,
      mitigation=body.mitigation,
      target_version=body.target_version,
      previous_version=body.previous_version,
      protocol_id=body.protocol_id,
      status="pending",
      detail_json=json.dumps(body.detail or {}, ensure_ascii=False),
      requested_by=actor_id,
      requested_by_email=actor_email,
    )
    self.db.add(row)
    self.db.commit()
    self.db.refresh(row)

    self.audit.log(
      "change.created",
      actor_id=actor_id,
      actor_email=actor_email,
      actor_role=actor_role,
      resource_type="change_request",
      resource_id=change_id,
      model_version=body.target_version,
      detail={"change_type": body.change_type, "risk_level": body.risk_level},
    )
    return row

  def get(self, change_id: str) -> ChangeRequest | None:
    return self.db.query(ChangeRequest).filter(ChangeRequest.change_id == change_id).first()

  def list_requests(self, limit: int = 50) -> list[ChangeRequest]:
    return self.db.query(ChangeRequest).order_by(ChangeRequest.created_at.desc()).limit(limit).all()

  def decide(
    self,
    change_id: str,
    body: ChangeRequestDecision,
    *,
    actor_id: str,
    actor_email: str,
    actor_role: str,
  ) -> ChangeRequest:
    row = self.get(change_id)
    if not row:
      raise ChangeControlError("Change request not found")
    if row.status not in {"pending", "draft"}:
      raise ChangeControlError(f"The current status ({row.status}) cannot be decided on")

    if body.decision == "approved" and row.change_type == "model" and row.risk_level in {
      "high",
      "critical",
    }:
      if not row.protocol_id:
        raise ChangeControlError("Signing the validation protocol is required for approval")
      protocol = (
        self.db.query(ClinicalValidationProtocol)
        .filter(ClinicalValidationProtocol.protocol_id == row.protocol_id)
        .first()
      )
      if not protocol or protocol.status != "signed" or not protocol.passed:
        raise ChangeControlError("The validation protocol must be signed and successful")

    row.status = body.decision
    row.approved_by = actor_id
    row.approved_by_email = actor_email
    row.approved_at = datetime.now(timezone.utc)
    if body.note:
      detail = json.loads(row.detail_json or "{}")
      detail["decision_note"] = body.note
      row.detail_json = json.dumps(detail, ensure_ascii=False)
    self.db.commit()
    self.db.refresh(row)

    self.audit.log(
      f"change.{body.decision}",
      actor_id=actor_id,
      actor_email=actor_email,
      actor_role=actor_role,
      resource_type="change_request",
      resource_id=change_id,
      model_version=row.target_version,
      detail={"note": body.note},
    )
    return row

  def apply(
    self,
    change_id: str,
    *,
    actor_id: str,
    actor_email: str,
    actor_role: str,
  ) -> ChangeRequestApplyResponse:
    row = self.get(change_id)
    if not row:
      raise ChangeControlError("Change request not found")
    if row.status != "approved":
      raise ChangeControlError("Only an approved request can be applied")

    message = "applied"
    registry = ModelRegistry.load()

    try:
      if row.change_type == "model" and row.target_version:
        registry.unlock_production(change_request_id=row.change_id)
        message = registry.promote(
          row.target_version,
          change_request_id=row.change_id,
          validation_protocol_id=row.protocol_id,
          force=True,
        )
        registry.lock_production()
      elif row.change_type == "model" and row.previous_version and not row.target_version:
        message = registry.force_rollback(row.previous_version)
        registry.lock_production()
      else:
        # pipeline/config: only record the application (settings are read from detail_json)
        message = f"change type {row.change_type} recorded as applied"
    except RegistryError as exc:
      raise ChangeControlError(exc.message) from exc

    row.status = "applied"
    row.applied_at = datetime.now(timezone.utc)
    self.db.commit()
    self.db.refresh(row)

    self.audit.log(
      "change.applied",
      actor_id=actor_id,
      actor_email=actor_email,
      actor_role=actor_role,
      resource_type="change_request",
      resource_id=change_id,
      model_version=row.target_version or registry.production_version,
      detail={"message": message},
    )

    return ChangeRequestApplyResponse(
      change_id=row.change_id,
      status=row.status,
      message=message,
      production_version=registry.production_version,
      production_locked=registry.production_locked,
    )

  def to_response(self, row: ChangeRequest) -> ChangeRequestResponse:
    return ChangeRequestResponse(
      change_id=row.change_id,
      change_type=row.change_type,
      title=row.title,
      description=row.description,
      risk_level=row.risk_level,
      mitigation=row.mitigation,
      target_version=row.target_version,
      previous_version=row.previous_version,
      protocol_id=row.protocol_id,
      status=row.status,
      requested_by_email=row.requested_by_email,
      approved_by_email=row.approved_by_email,
      approved_at=row.approved_at,
      applied_at=row.applied_at,
      created_at=row.created_at,
    )
