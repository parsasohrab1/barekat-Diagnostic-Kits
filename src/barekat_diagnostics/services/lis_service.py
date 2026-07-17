"""یکپارچگی LIS — FHIR DiagnosticReport و HL7 v2 ORU^R01."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from barekat_diagnostics.models.lis import FhirExport, LabOrder
from barekat_diagnostics.models.sample import Diagnosis, Sample
from barekat_diagnostics.schemas import (
  Hl7ExportResponse,
  LabOrderCreate,
  LabOrderResponse,
  LisExportRequest,
)
from barekat_diagnostics.services.audit_trail import AuditTrailService


class LisError(Exception):
  def __init__(self, message: str) -> None:
    self.message = message
    super().__init__(message)


def _hl7_escape(value: str) -> str:
  return (
    value.replace("\\", "\\E\\")
    .replace("|", "\\F\\")
    .replace("^", "\\S\\")
    .replace("&", "\\T\\")
    .replace("~", "\\R\\")
  )


def build_hl7_oru_r01(
  *,
  sample_id: str,
  patient_id: str | None,
  result: str,
  confidence: float,
  kit_type: str,
  report_id: int | None,
  order_id: str | None = None,
  model_version: str = "v1",
  observation_dt: datetime | None = None,
) -> str:
  """ساخت پیام HL7 v2.5 ORU^R01 برای نتیجه تشخیص."""
  now = observation_dt or datetime.now(timezone.utc)
  ts = now.strftime("%Y%m%d%H%M%S")
  msg_id = f"BKT{uuid.uuid4().hex[:12].upper()}"
  pid = _hl7_escape(patient_id or "UNKNOWN")
  sid = _hl7_escape(sample_id)
  oid = _hl7_escape(order_id or sample_id)
  obx_result = result.upper()
  conf_pct = f"{confidence * 100:.1f}"

  segments = [
    f"MSH|^~\\&|BAREKAT|LAB|LIS|HOSPITAL|{ts}||ORU^R01|{msg_id}|P|2.5",
    f"PID|1||{pid}^^^BAREKAT^MR||",
    f"OBR|1|{oid}|{oid}^BAREKAT|DIAG^{kit_type.upper()}^L|||{ts}|||||||||{ts}|||F",
    (
      f"OBX|1|ST|RESULT^{kit_type}^L||{obx_result}|||N|||F|||{ts}"
      f"||BAREKAT^{model_version}"
    ),
    f"OBX|2|NM|CONF^Confidence^L||{conf_pct}|%||||F|||{ts}",
  ]
  if report_id is not None:
    segments.append(f"OBX|3|ST|RPTID^ReportId^L||{report_id}||||F|||{ts}")
  return "\r".join(segments) + "\r"


def build_fhir_diagnostic_report(
  *,
  sample_id: str,
  patient_id: str | None,
  result: str,
  confidence: float,
  kit_type: str,
  report_id: int | None,
  order_id: str | None = None,
  model_version: str = "v1",
  qc_passed: bool = True,
) -> dict:
  """ساخت FHIR R4 DiagnosticReport."""
  now = datetime.now(timezone.utc).isoformat()
  return {
    "resourceType": "DiagnosticReport",
    "id": f"barekat-{report_id or sample_id}",
    "status": "final" if qc_passed else "preliminary",
    "code": {
      "coding": [
        {
          "system": "http://barekat.local/CodeSystem/kit-type",
          "code": kit_type,
          "display": f"Barekat {kit_type} diagnosis",
        }
      ],
      "text": f"Barekat diagnostic kit ({kit_type})",
    },
    "subject": {"reference": f"Patient/{patient_id or 'unknown'}"},
    "effectiveDateTime": now,
    "issued": now,
    "basedOn": [{"reference": f"ServiceRequest/{order_id}"}] if order_id else [],
    "specimen": [{"display": sample_id}],
    "conclusion": result,
    "conclusionCode": [
      {
        "coding": [
          {
            "system": "http://barekat.local/CodeSystem/result",
            "code": result,
          }
        ]
      }
    ],
    "extension": [
      {
        "url": "http://barekat.local/fhir/StructureDefinition/model-version",
        "valueString": model_version,
      },
      {
        "url": "http://barekat.local/fhir/StructureDefinition/confidence",
        "valueDecimal": confidence,
      },
    ],
  }


class LisService:
  def __init__(self, db: Session) -> None:
    self.db = db
    self.audit = AuditTrailService(db)

  def create_order(
    self,
    body: LabOrderCreate,
    *,
    actor_id: str | None = None,
    actor_email: str | None = None,
    actor_role: str | None = None,
  ) -> LabOrder:
    if self.db.query(LabOrder).filter(LabOrder.order_id == body.order_id).first():
      raise LisError(f"سفارش {body.order_id} تکراری است")
    order = LabOrder(
      order_id=body.order_id,
      patient_id=body.patient_id,
      sample_id=body.sample_id,
      kit_type=body.kit_type,
      status="received",
      fhir_json=json.dumps(body.fhir or {}, ensure_ascii=False) if body.fhir else None,
    )
    self.db.add(order)
    self.db.commit()
    self.db.refresh(order)
    self.audit.log(
      "lis.order_received",
      actor_id=actor_id,
      actor_email=actor_email,
      actor_role=actor_role,
      resource_type="lab_order",
      resource_id=order.order_id,
      detail={"patient_id": order.patient_id, "sample_id": order.sample_id},
    )
    return order

  def list_orders(self, limit: int = 50) -> list[LabOrder]:
    return self.db.query(LabOrder).order_by(LabOrder.created_at.desc()).limit(limit).all()

  def export_result(
    self,
    body: LisExportRequest,
    *,
    actor_id: str | None = None,
    actor_email: str | None = None,
    actor_role: str | None = None,
  ) -> Hl7ExportResponse:
    diagnosis = None
    if body.report_id:
      diagnosis = self.db.query(Diagnosis).filter(Diagnosis.id == body.report_id).first()
    if not diagnosis:
      diagnosis = (
        self.db.query(Diagnosis)
        .filter(Diagnosis.sample_id == body.sample_id)
        .order_by(Diagnosis.created_at.desc())
        .first()
      )
    if not diagnosis:
      raise LisError("گزارش تشخیص برای export یافت نشد")

    sample = self.db.query(Sample).filter(Sample.sample_id == body.sample_id).first()
    patient_id = body.patient_id or (sample.patient_id if sample else None)
    order_id = body.order_id
    if not order_id:
      order = (
        self.db.query(LabOrder)
        .filter(LabOrder.sample_id == body.sample_id)
        .order_by(LabOrder.created_at.desc())
        .first()
      )
      order_id = order.order_id if order else None

    fmt = body.format.lower()
    if fmt == "hl7":
      payload = build_hl7_oru_r01(
        sample_id=diagnosis.sample_id,
        patient_id=patient_id,
        result=diagnosis.result,
        confidence=diagnosis.confidence,
        kit_type=diagnosis.kit_type,
        report_id=diagnosis.id,
        order_id=order_id,
        model_version=diagnosis.model_version,
        observation_dt=diagnosis.created_at,
      )
      content_type = "application/hl7-v2"
    elif fmt == "fhir":
      resource = build_fhir_diagnostic_report(
        sample_id=diagnosis.sample_id,
        patient_id=patient_id,
        result=diagnosis.result,
        confidence=diagnosis.confidence,
        kit_type=diagnosis.kit_type,
        report_id=diagnosis.id,
        order_id=order_id,
        model_version=diagnosis.model_version,
        qc_passed=diagnosis.qc_passed,
      )
      payload = json.dumps(resource, ensure_ascii=False, indent=2)
      content_type = "application/fhir+json"
    else:
      raise LisError("فرمت باید hl7 یا fhir باشد")

    export = FhirExport(
      sample_id=diagnosis.sample_id,
      report_id=diagnosis.id,
      patient_id=patient_id,
      order_id=order_id,
      fhir_json=payload,
      destination=body.destination or fmt,
      status="exported",
    )
    self.db.add(export)
    if order_id:
      order_row = self.db.query(LabOrder).filter(LabOrder.order_id == order_id).first()
      if order_row:
        order_row.status = "result_exported"
        order_row.updated_at = datetime.now(timezone.utc)
    self.db.commit()
    self.db.refresh(export)

    self.audit.log(
      "lis.exported",
      actor_id=actor_id,
      actor_email=actor_email,
      actor_role=actor_role,
      resource_type="diagnosis",
      resource_id=str(diagnosis.id),
      model_version=diagnosis.model_version,
      detail={"format": fmt, "sample_id": diagnosis.sample_id, "export_id": export.id},
    )

    return Hl7ExportResponse(
      export_id=export.id,
      sample_id=diagnosis.sample_id,
      report_id=diagnosis.id,
      format=fmt,
      content_type=content_type,
      payload=payload,
      destination=export.destination,
      created_at=export.created_at,
    )

  def to_order_response(self, order: LabOrder) -> LabOrderResponse:
    return LabOrderResponse(
      order_id=order.order_id,
      patient_id=order.patient_id,
      sample_id=order.sample_id,
      kit_type=order.kit_type,
      status=order.status,
      created_at=order.created_at,
      updated_at=order.updated_at,
    )
