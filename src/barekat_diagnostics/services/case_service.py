"""Multi-kit case — combining qPCR + ELISA and concordance policy."""

from __future__ import annotations

import json
import uuid

from sqlalchemy.orm import Session

from barekat_diagnostics.models.clinical import CaseAssay, ClinicalCase
from barekat_diagnostics.schemas import (
  CaseAddAssayRequest,
  CaseCreate,
  CaseFuseResponse,
  CaseResponse,
)
from barekat_diagnostics.services.audit_trail import AuditTrailService
from barekat_diagnostics.services.sample_service import SampleService


class CaseError(Exception):
  def __init__(self, message: str) -> None:
    self.message = message
    super().__init__(message)


def fuse_kit_results(
  assays: list[dict],
  policy: str = "concordance",
) -> tuple[str, float, str]:
  """Combine multi-kit results → (consensus, confidence, rationale)."""
  usable = [a for a in assays if a.get("result") in {"positive", "negative", "inconclusive"}]
  if not usable:
    return "inconclusive", 0.0, "No assay results available"

  results = [a["result"] for a in usable]
  confs = [float(a.get("confidence") or 0.0) for a in usable]
  kits = {a.get("kit_type") for a in usable}

  if policy == "any_positive":
    if any(r == "positive" for r in results):
      return "positive", max(confs), "Any-positive policy triggered"
    if all(r == "negative" for r in results):
      return "negative", sum(confs) / len(confs), "All assays negative"
    return "inconclusive", sum(confs) / len(confs), "Mixed/inconclusive under any-positive"

  if policy == "qpcr_primary":
    qpcr = [a for a in usable if a.get("kit_type") == "qpcr"]
    if qpcr:
      best = max(qpcr, key=lambda a: a.get("confidence") or 0)
      return best["result"], float(best.get("confidence") or 0), "qPCR primary policy"
    # fall through

  if policy == "weighted":
    # weight qpcr higher
    weights = {"qpcr": 0.6, "elisa": 0.3, "spectroscopy": 0.1}
    score = 0.0
    wsum = 0.0
    for a in usable:
      w = weights.get(a.get("kit_type", ""), 0.2)
      val = 1.0 if a["result"] == "positive" else (0.5 if a["result"] == "inconclusive" else 0.0)
      score += w * val * float(a.get("confidence") or 0.5)
      wsum += w
    norm = score / (wsum or 1.0)
    if norm >= 0.55:
      return "positive", min(0.99, norm), f"Weighted fusion score={norm:.2f}"
    if norm <= 0.35:
      return "negative", min(0.99, 1 - norm), f"Weighted fusion score={norm:.2f}"
    return "inconclusive", 0.5, f"Weighted fusion borderline score={norm:.2f}"

  # concordance (default)
  unique = set(results)
  if unique == {"positive"}:
    return "positive", sum(confs) / len(confs), f"Concordant positive across {sorted(kits)}"
  if unique == {"negative"}:
    return "negative", sum(confs) / len(confs), f"Concordant negative across {sorted(kits)}"
  if "positive" in unique and "negative" in unique:
    return "inconclusive", sum(confs) / len(confs), "Discordant kit results — expert review required"
  return "inconclusive", sum(confs) / len(confs), "Incomplete concordance"


class CaseService:
  def __init__(self, db: Session) -> None:
    self.db = db
    self.audit = AuditTrailService(db)
    self.samples = SampleService(db)

  @property
  def diagnosis(self):
    from barekat_diagnostics.services.diagnosis_service import DiagnosisService

    return DiagnosisService(self.db)

  def create_case(self, body: CaseCreate, **actor) -> ClinicalCase:
    case_id = body.case_id or f"CASE-{uuid.uuid4().hex[:10].upper()}"
    if self.db.query(ClinicalCase).filter(ClinicalCase.case_id == case_id).first():
      raise CaseError(f"Duplicate case: {case_id}")
    row = ClinicalCase(
      case_id=case_id,
      patient_id=body.patient_id,
      panel_id=body.panel_id,
      fusion_policy=body.fusion_policy,
      status="open",
      created_by=actor.get("actor_id"),
    )
    self.db.add(row)
    self.db.commit()
    self.db.refresh(row)
    self.audit.log(
      "case.created",
      resource_type="clinical_case",
      resource_id=case_id,
      **{k: v for k, v in actor.items() if k.startswith("actor_")},
    )
    return row

  def get(self, case_id: str) -> ClinicalCase | None:
    return self.db.query(ClinicalCase).filter(ClinicalCase.case_id == case_id).first()

  def list_cases(self, limit: int = 50) -> list[ClinicalCase]:
    return self.db.query(ClinicalCase).order_by(ClinicalCase.created_at.desc()).limit(limit).all()

  def add_assay(
    self,
    case_id: str,
    body: CaseAddAssayRequest,
    **actor,
  ) -> CaseAssay:
    case = self.get(case_id)
    if not case:
      raise CaseError("Case not found")

    sample_id = body.sample_id
    report_id = body.report_id
    result = body.result
    confidence = body.confidence
    kit_type = body.kit_type

    if body.sample:
      sample_id = body.sample.sample_id
      kit_type = body.sample.kit_type
      self.samples.create_sample(body.sample, curve_data=body.sample.curve_data)
      if body.analyze:
        report = self.diagnosis.analyze(
          body.sample,
          actor_id=actor.get("actor_id"),
          actor_email=actor.get("actor_email"),
          actor_role=actor.get("actor_role"),
        )
        report_id = report.report_id
        result = report.result
        confidence = report.confidence

    if not sample_id:
      raise CaseError("sample_id or sample is required")

    assay = CaseAssay(
      case_id=case_id,
      sample_id=sample_id,
      kit_type=kit_type or "qpcr",
      marker_id=body.marker_id,
      report_id=report_id,
      result=result,
      confidence=confidence,
      role=body.role,
    )
    self.db.add(assay)
    case.status = "analyzing"
    self.db.commit()
    self.db.refresh(assay)
    self.audit.log(
      "case.assay_added",
      resource_type="clinical_case",
      resource_id=case_id,
      detail={"sample_id": sample_id, "kit_type": kit_type},
      **{k: v for k, v in actor.items() if k.startswith("actor_")},
    )
    return assay

  def fuse(self, case_id: str, **actor) -> CaseFuseResponse:
    case = self.get(case_id)
    if not case:
      raise CaseError("Case not found")
    assays = self.db.query(CaseAssay).filter(CaseAssay.case_id == case_id).all()
    if len(assays) < 1:
      raise CaseError("At least one assay is required")

    payload = [
      {
        "sample_id": a.sample_id,
        "kit_type": a.kit_type,
        "result": a.result,
        "confidence": a.confidence,
        "role": a.role,
      }
      for a in assays
    ]
    consensus, conf, rationale = fuse_kit_results(payload, case.fusion_policy)
    case.consensus_result = consensus
    case.consensus_confidence = conf
    case.status = "pending_review"
    case.summary_json = json.dumps(
      {"assays": payload, "rationale": rationale, "policy": case.fusion_policy},
      ensure_ascii=False,
    )

    # clinical narrative for multi-kit
    kit_list = ", ".join(sorted({a.kit_type.upper() for a in assays}))
    narrative = (
      f"Multi-kit case {case_id} ({kit_list}): consensus={consensus} "
      f"(confidence {conf * 100:.0f}%). {rationale}."
    )
    case.clinical_narrative = narrative
    self.db.commit()
    self.db.refresh(case)

    self.audit.log(
      "case.fused",
      resource_type="clinical_case",
      resource_id=case_id,
      detail={"consensus": consensus, "policy": case.fusion_policy},
      **{k: v for k, v in actor.items() if k.startswith("actor_")},
    )

    return CaseFuseResponse(
      case_id=case_id,
      consensus_result=consensus,  # type: ignore[arg-type]
      consensus_confidence=conf,
      fusion_policy=case.fusion_policy,
      rationale=rationale,
      assays=payload,
      clinical_narrative=narrative,
    )

  def to_response(self, case: ClinicalCase) -> CaseResponse:
    assays = self.db.query(CaseAssay).filter(CaseAssay.case_id == case.case_id).all()
    return CaseResponse(
      case_id=case.case_id,
      patient_id=case.patient_id,
      panel_id=case.panel_id,
      status=case.status,
      consensus_result=case.consensus_result,
      consensus_confidence=case.consensus_confidence,
      fusion_policy=case.fusion_policy,
      clinical_narrative=case.clinical_narrative,
      assays=[
        {
          "sample_id": a.sample_id,
          "kit_type": a.kit_type,
          "marker_id": a.marker_id,
          "report_id": a.report_id,
          "result": a.result,
          "confidence": a.confidence,
          "role": a.role,
        }
        for a in assays
      ],
      created_at=case.created_at,
    )
