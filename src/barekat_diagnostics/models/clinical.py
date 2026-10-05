"""Phase 4 models — marker panel, multi-kit case, HITL, reassessment."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from barekat_diagnostics.core.database import Base


class MarkerPanel(Base):
  """Definition of a multi-marker / multi-disease panel."""

  __tablename__ = "marker_panels"

  id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
  panel_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
  name: Mapped[str] = mapped_column(String(256))
  description: Mapped[str | None] = mapped_column(Text, nullable=True)
  # JSON list of markers: [{marker_id, name, kit_type, disease_code, cutoff, unit}]
  markers_json: Mapped[str] = mapped_column(Text)
  status: Mapped[str] = mapped_column(String(16), default="active")
  created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ClinicalCase(Base):
  """Clinical case combining several samples/kits."""

  __tablename__ = "clinical_cases"

  id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
  case_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
  patient_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
  panel_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
  status: Mapped[str] = mapped_column(String(24), default="open")
  # open|analyzing|pending_review|reassessment|closed
  consensus_result: Mapped[str | None] = mapped_column(String(32), nullable=True)
  consensus_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
  fusion_policy: Mapped[str] = mapped_column(String(32), default="concordance")
  # concordance|any_positive|weighted|qpcr_primary
  summary_json: Mapped[str | None] = mapped_column(Text, nullable=True)
  clinical_narrative: Mapped[str | None] = mapped_column(Text, nullable=True)
  created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
  created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
  closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CaseAssay(Base):
  """Linking a sample/kit to a clinical case."""

  __tablename__ = "case_assays"

  id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
  case_id: Mapped[str] = mapped_column(String(64), index=True)
  sample_id: Mapped[str] = mapped_column(String(32), index=True)
  kit_type: Mapped[str] = mapped_column(String(32))
  marker_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
  report_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
  result: Mapped[str | None] = mapped_column(String(32), nullable=True)
  confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
  role: Mapped[str] = mapped_column(String(24), default="primary")
  # primary|confirmatory|reflex
  created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PanelMarkerResult(Base):
  """Single-marker result in a panel run."""

  __tablename__ = "panel_marker_results"

  id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
  panel_run_id: Mapped[str] = mapped_column(String(64), index=True)
  sample_id: Mapped[str] = mapped_column(String(32), index=True)
  marker_id: Mapped[str] = mapped_column(String(64), index=True)
  marker_name: Mapped[str] = mapped_column(String(128))
  disease_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
  kit_type: Mapped[str] = mapped_column(String(32), default="qpcr")
  result: Mapped[str] = mapped_column(String(32))  # positive|negative|inconclusive|borderline
  value: Mapped[float | None] = mapped_column(Float, nullable=True)
  cutoff: Mapped[float | None] = mapped_column(Float, nullable=True)
  unit: Mapped[str] = mapped_column(String(32), default="")
  confidence: Mapped[float] = mapped_column(Float, default=0.0)
  created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReassessmentRequest(Base):
  """Reassessment request after suspicious QC."""

  __tablename__ = "reassessment_requests"

  id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
  reassessment_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
  original_sample_id: Mapped[str] = mapped_column(String(32), index=True)
  original_report_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
  retest_sample_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
  retest_report_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
  reason: Mapped[str] = mapped_column(Text)
  qc_codes: Mapped[str | None] = mapped_column(Text, nullable=True)
  status: Mapped[str] = mapped_column(String(24), default="suggested")
  # suggested|accepted|running|completed|cancelled
  comparison_json: Mapped[str | None] = mapped_column(Text, nullable=True)
  created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
  created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
  completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ExpertFeedback(Base):
  """Expert-corrected label for supervised learning (HITL)."""

  __tablename__ = "expert_feedback"

  id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
  feedback_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
  sample_id: Mapped[str] = mapped_column(String(32), index=True)
  report_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
  model_result: Mapped[str] = mapped_column(String(32))
  expert_result: Mapped[str] = mapped_column(String(32))
  # positive|negative|inconclusive|or disease/marker specific
  expert_labels_json: Mapped[str | None] = mapped_column(Text, nullable=True)
  # optional multi-marker corrections
  agree_with_model: Mapped[bool] = mapped_column(Boolean, default=False)
  note: Mapped[str | None] = mapped_column(Text, nullable=True)
  features_json: Mapped[str | None] = mapped_column(Text, nullable=True)
  kit_type: Mapped[str] = mapped_column(String(32), default="qpcr")
  used_for_training: Mapped[bool] = mapped_column(Boolean, default=False)
  expert_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
  expert_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
  created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
