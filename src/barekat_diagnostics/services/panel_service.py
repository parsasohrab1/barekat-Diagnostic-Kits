"""Multi-marker / multi-disease panel service."""

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy.orm import Session

from barekat_diagnostics.models.clinical import MarkerPanel, PanelMarkerResult
from barekat_diagnostics.schemas import (
  MarkerDefinition,
  MarkerPanelCreate,
  MarkerPanelResponse,
  MarkerResultSchema,
  PanelAnalyzeRequest,
  PanelAnalyzeResponse,
  SampleInput,
)
from barekat_diagnostics.services.audit_trail import AuditTrailService


# Default respiratory panel (multi-disease)
DEFAULT_RESPIRATORY_PANEL = [
  {"marker_id": "SARS_COV2", "name": "SARS-CoV-2", "kit_type": "qpcr", "disease_code": "COVID19", "cutoff": 35.0, "unit": "Ct", "field": "ct_sars"},
  {"marker_id": "FLU_A", "name": "Influenza A", "kit_type": "qpcr", "disease_code": "FLUA", "cutoff": 35.0, "unit": "Ct", "field": "ct_flu_a"},
  {"marker_id": "FLU_B", "name": "Influenza B", "kit_type": "qpcr", "disease_code": "FLUB", "cutoff": 35.0, "unit": "Ct", "field": "ct_flu_b"},
  {"marker_id": "RSV", "name": "RSV", "kit_type": "qpcr", "disease_code": "RSV", "cutoff": 35.0, "unit": "Ct", "field": "ct_rsv"},
]


class PanelError(Exception):
  def __init__(self, message: str) -> None:
    self.message = message
    super().__init__(message)


def _call_marker(value: float | None, cutoff: float, kit_type: str) -> tuple[str, float]:
  """Positive/negative/borderline decision for one marker."""
  if value is None:
    return "inconclusive", 0.0
  if kit_type == "qpcr":
    # Lower Ct = positive
    if value <= cutoff - 2:
      return "positive", min(0.99, 0.7 + (cutoff - value) * 0.03)
    if value <= cutoff:
      return "borderline", 0.55
    if value >= cutoff + 3:
      return "negative", min(0.99, 0.7 + (value - cutoff) * 0.02)
    return "negative", 0.6
  # ELISA / spectroscopy: value above the cutoff = positive
  if value >= cutoff * 1.2:
    return "positive", min(0.99, 0.7 + (value - cutoff) * 0.1)
  if value >= cutoff:
    return "borderline", 0.55
  if value <= cutoff * 0.7:
    return "negative", 0.85
  return "negative", 0.65


class PanelService:
  def __init__(self, db: Session) -> None:
    self.db = db
    self.audit = AuditTrailService(db)

  def ensure_defaults(self) -> None:
    existing = self.db.query(MarkerPanel).filter(MarkerPanel.panel_id == "RESP-V1").first()
    if existing:
      return
    self.create_panel(
      MarkerPanelCreate(
        panel_id="RESP-V1",
        name="Respiratory viral panel",
        description="SARS-CoV-2 / Flu A / Flu B / RSV",
        markers=[MarkerDefinition(**m) for m in DEFAULT_RESPIRATORY_PANEL],
      )
    )

  def create_panel(self, body: MarkerPanelCreate, **actor) -> MarkerPanel:
    if self.db.query(MarkerPanel).filter(MarkerPanel.panel_id == body.panel_id).first():
      raise PanelError(f"Duplicate panel: {body.panel_id}")
    if not body.markers:
      raise PanelError("At least one marker is required")
    row = MarkerPanel(
      panel_id=body.panel_id,
      name=body.name,
      description=body.description,
      markers_json=json.dumps([m.model_dump() for m in body.markers], ensure_ascii=False),
    )
    self.db.add(row)
    self.db.commit()
    self.db.refresh(row)
    self.audit.log(
      "panel.created",
      resource_type="marker_panel",
      resource_id=body.panel_id,
      detail={"markers": len(body.markers)},
      **{k: v for k, v in actor.items() if k.startswith("actor_")},
    )
    return row

  def get_panel(self, panel_id: str) -> MarkerPanel | None:
    return self.db.query(MarkerPanel).filter(MarkerPanel.panel_id == panel_id).first()

  def list_panels(self) -> list[MarkerPanel]:
    self.ensure_defaults()
    return self.db.query(MarkerPanel).order_by(MarkerPanel.created_at.desc()).all()

  def analyze(self, body: PanelAnalyzeRequest, **actor) -> PanelAnalyzeResponse:
    panel = self.get_panel(body.panel_id)
    if not panel:
      self.ensure_defaults()
      panel = self.get_panel(body.panel_id)
    if not panel:
      raise PanelError(f"Panel not found: {body.panel_id}")

    markers = [MarkerDefinition.model_validate(m) for m in json.loads(panel.markers_json)]
    values = body.marker_values or {}
    # fallback from SampleInput if the field is on the sample
    sample = body.sample
    run_id = f"PRUN-{uuid.uuid4().hex[:10].upper()}"
    results: list[MarkerResultSchema] = []

    for marker in markers:
      raw_val = values.get(marker.marker_id)
      if raw_val is None and marker.field:
        raw_val = values.get(marker.field)
      if raw_val is None and sample:
        # Search in features or attribute
        if sample.features and marker.field in sample.features:
          raw_val = sample.features[marker.field]
        elif marker.field == "ct_value" or marker.kit_type == "qpcr":
          raw_val = sample.ct_value if len(markers) == 1 else values.get(marker.marker_id)
        elif marker.kit_type == "elisa":
          raw_val = sample.od_ratio

      result, confidence = _call_marker(raw_val, marker.cutoff, marker.kit_type)
      item = MarkerResultSchema(
        marker_id=marker.marker_id,
        marker_name=marker.name,
        disease_code=marker.disease_code,
        kit_type=marker.kit_type,
        result=result,  # type: ignore[arg-type]
        value=raw_val,
        cutoff=marker.cutoff,
        unit=marker.unit,
        confidence=round(confidence, 3),
      )
      results.append(item)
      self.db.add(
        PanelMarkerResult(
          panel_run_id=run_id,
          sample_id=sample.sample_id if sample else body.sample_id or "PANEL",
          marker_id=marker.marker_id,
          marker_name=marker.name,
          disease_code=marker.disease_code,
          kit_type=marker.kit_type,
          result=result,
          value=raw_val,
          cutoff=marker.cutoff,
          unit=marker.unit,
          confidence=confidence,
        )
      )

    self.db.commit()

    positives = [r for r in results if r.result == "positive"]
    borderlines = [r for r in results if r.result == "borderline"]
    overall = "negative"
    if positives:
      overall = "positive"
    elif borderlines:
      overall = "inconclusive"
    elif any(r.result == "inconclusive" for r in results):
      overall = "inconclusive"

    diseases = sorted({r.disease_code for r in positives if r.disease_code})

    self.audit.log(
      "panel.analyzed",
      resource_type="panel_run",
      resource_id=run_id,
      detail={"panel_id": body.panel_id, "overall": overall, "diseases": diseases},
      **{k: v for k, v in actor.items() if k.startswith("actor_")},
    )

    return PanelAnalyzeResponse(
      panel_run_id=run_id,
      panel_id=body.panel_id,
      sample_id=sample.sample_id if sample else body.sample_id,
      overall_result=overall,  # type: ignore[arg-type]
      detected_diseases=diseases,
      markers=results,
      positive_count=len(positives),
      borderline_count=len(borderlines),
    )

  def to_response(self, row: MarkerPanel) -> MarkerPanelResponse:
    markers = [MarkerDefinition.model_validate(m) for m in json.loads(row.markers_json)]
    return MarkerPanelResponse(
      panel_id=row.panel_id,
      name=row.name,
      description=row.description,
      markers=markers,
      status=row.status,
      created_at=row.created_at,
    )
