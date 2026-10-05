"""Clinical validation protocol service."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from sqlalchemy.orm import Session

from barekat_diagnostics.ml.evaluation import evaluate_model
from barekat_diagnostics.ml.features import build_model, prepare_features
from barekat_diagnostics.ml.registry import ModelRegistry, RegistryError
from barekat_diagnostics.models.quality import ClinicalValidationProtocol
from barekat_diagnostics.schemas import (
  ClinicalValidationCreate,
  ClinicalValidationResponse,
  ClinicalValidationSignRequest,
)
from barekat_diagnostics.services.audit_trail import AuditTrailService


class ValidationError(Exception):
  def __init__(self, message: str) -> None:
    self.message = message
    super().__init__(message)


class ClinicalValidationService:
  def __init__(self, db: Session) -> None:
    self.db = db
    self.audit = AuditTrailService(db)

  def create(
    self,
    body: ClinicalValidationCreate,
    *,
    actor_id: str | None = None,
    actor_email: str | None = None,
    actor_role: str | None = None,
  ) -> ClinicalValidationProtocol:
    protocol_id = body.protocol_id or f"VAL-{uuid.uuid4().hex[:10].upper()}"
    existing = (
      self.db.query(ClinicalValidationProtocol)
      .filter(ClinicalValidationProtocol.protocol_id == protocol_id)
      .first()
    )
    if existing:
      raise ValidationError(f"Protocol {protocol_id} has already been registered")

    row = ClinicalValidationProtocol(
      protocol_id=protocol_id,
      model_version=body.model_version,
      build_series=body.build_series,
      batch_id=body.batch_id,
      lot_number=body.lot_number,
      data_path=body.data_path,
      status="draft",
      min_sensitivity=body.min_sensitivity,
      min_specificity=body.min_specificity,
      min_roc_auc=body.min_roc_auc,
      min_samples=body.min_samples,
      created_by=actor_id,
    )
    self.db.add(row)
    self.db.commit()
    self.db.refresh(row)

    self.audit.log(
      "validation.created",
      actor_id=actor_id,
      actor_email=actor_email,
      actor_role=actor_role,
      resource_type="validation_protocol",
      resource_id=protocol_id,
      model_version=body.model_version,
      detail={
        "build_series": body.build_series,
        "batch_id": body.batch_id,
        "lot_number": body.lot_number,
      },
    )
    return row

  def get(self, protocol_id: str) -> ClinicalValidationProtocol | None:
    return (
      self.db.query(ClinicalValidationProtocol)
      .filter(ClinicalValidationProtocol.protocol_id == protocol_id)
      .first()
    )

  def list_protocols(self, limit: int = 50) -> list[ClinicalValidationProtocol]:
    return (
      self.db.query(ClinicalValidationProtocol)
      .order_by(ClinicalValidationProtocol.created_at.desc())
      .limit(limit)
      .all()
    )

  def run(
    self,
    protocol_id: str,
    *,
    actor_id: str | None = None,
    actor_email: str | None = None,
    actor_role: str | None = None,
  ) -> ClinicalValidationProtocol:
    row = self.get(protocol_id)
    if not row:
      raise ValidationError("Protocol not found")

    path = Path(row.data_path)
    if not path.exists():
      raise ValidationError(f"Data file not found: {path}")

    df = pd.read_csv(path)
    if "True_Status" not in df.columns:
      raise ValidationError("The True_Status column is required for validation")
    if "Kit_Lot" not in df.columns and row.lot_number:
      df["Kit_Lot"] = row.lot_number
    if "Lab_Device" not in df.columns:
      df["Lab_Device"] = row.build_series

    if len(df) < row.min_samples:
      row.status = "failed"
      row.passed = False
      row.sample_count = len(df)
      row.failure_reason = f"Number of samples ({len(df)}) is less than the minimum ({row.min_samples})"
      self.db.commit()
      raise ValidationError(row.failure_reason)

    X, y, _ = prepare_features(df)
    model = build_model()
    model.fit(X, y)
    result = evaluate_model(df, model=model)

    row.sample_count = len(df)
    row.sensitivity = result.sensitivity.value
    row.specificity = result.specificity.value
    row.roc_auc = result.roc_auc
    row.result_json = result.model_dump_json()

    failures = []
    if result.sensitivity.value < row.min_sensitivity:
      failures.append(f"Se={result.sensitivity.value:.3f} < {row.min_sensitivity}")
    if result.specificity.value < row.min_specificity:
      failures.append(f"Sp={result.specificity.value:.3f} < {row.min_specificity}")
    if result.roc_auc < row.min_roc_auc:
      failures.append(f"AUC={result.roc_auc:.3f} < {row.min_roc_auc}")

    row.passed = len(failures) == 0
    row.status = "passed" if row.passed else "failed"
    row.failure_reason = "; ".join(failures) if failures else None
    self.db.commit()
    self.db.refresh(row)

    self.audit.log(
      "validation.ran",
      actor_id=actor_id,
      actor_email=actor_email,
      actor_role=actor_role,
      resource_type="validation_protocol",
      resource_id=protocol_id,
      model_version=row.model_version,
      detail={"passed": row.passed, "sensitivity": row.sensitivity, "specificity": row.specificity},
    )
    return row

  def sign(
    self,
    protocol_id: str,
    body: ClinicalValidationSignRequest,
    *,
    actor_id: str,
    actor_email: str,
    actor_role: str,
  ) -> ClinicalValidationProtocol:
    row = self.get(protocol_id)
    if not row:
      raise ValidationError("Protocol not found")
    if row.status != "passed" or not row.passed:
      raise ValidationError("Only a successful protocol can be signed")

    row.status = "signed"
    row.signed_by = actor_id
    row.signed_by_email = actor_email
    row.signed_at = datetime.now(timezone.utc)
    self.db.commit()
    self.db.refresh(row)

    try:
      registry = ModelRegistry.load()
      registry.mark_validated(row.model_version, row.protocol_id)
    except RegistryError:
      pass

    self.audit.log(
      "validation.signed",
      actor_id=actor_id,
      actor_email=actor_email,
      actor_role=actor_role,
      resource_type="validation_protocol",
      resource_id=protocol_id,
      model_version=row.model_version,
      detail={"note": body.note},
    )
    return row

  def to_response(self, row: ClinicalValidationProtocol) -> ClinicalValidationResponse:
    return ClinicalValidationResponse(
      protocol_id=row.protocol_id,
      model_version=row.model_version,
      build_series=row.build_series,
      batch_id=row.batch_id,
      lot_number=row.lot_number,
      data_path=row.data_path,
      status=row.status,
      min_sensitivity=row.min_sensitivity,
      min_specificity=row.min_specificity,
      min_roc_auc=row.min_roc_auc,
      min_samples=row.min_samples,
      sample_count=row.sample_count,
      sensitivity=row.sensitivity,
      specificity=row.specificity,
      roc_auc=row.roc_auc,
      passed=row.passed,
      failure_reason=row.failure_reason,
      signed_by_email=row.signed_by_email,
      signed_at=row.signed_at,
      created_at=row.created_at,
    )
