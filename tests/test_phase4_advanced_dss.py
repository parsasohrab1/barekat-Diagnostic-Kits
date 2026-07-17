"""تست‌های فاز ۴ — پنل چندمارکری، پرونده چندکیتی، reassessment، HITL."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from barekat_diagnostics.core.database import Base
from barekat_diagnostics.kits.base import QCFlag, QCResult, QCSeverity
from barekat_diagnostics.pipeline.clinical_explain import build_clinical_explanation
from barekat_diagnostics.pipeline.report import determine_recommendation
from barekat_diagnostics.schemas import (
  CaseAddAssayRequest,
  CaseCreate,
  ClinicalMetricsSchema,
  DiagnosisReport,
  ExpertFeedbackCreate,
  MarkerDefinition,
  MarkerPanelCreate,
  PanelAnalyzeRequest,
  QCFlagSchema,
  SampleInput,
)
from barekat_diagnostics.services.case_service import CaseService, fuse_kit_results
from barekat_diagnostics.services.hitl_service import HitlService
from barekat_diagnostics.services.panel_service import PanelService
from barekat_diagnostics.services.reassessment_service import (
  ReassessmentService,
  should_suggest_reassessment,
)
from barekat_diagnostics.models.sample import Diagnosis, Sample


@pytest.fixture()
def db_session():
  engine = create_engine("sqlite:///:memory:")
  import barekat_diagnostics.models.audit  # noqa: F401
  import barekat_diagnostics.models.clinical  # noqa: F401
  import barekat_diagnostics.models.sample  # noqa: F401
  import barekat_diagnostics.models.user  # noqa: F401

  Base.metadata.create_all(engine)
  Session = sessionmaker(bind=engine)
  session = Session()
  try:
    yield session
  finally:
    session.close()


def _report(**kwargs) -> DiagnosisReport:
  data = dict(
    sample_id="S1",
    kit_type="qpcr",
    result="positive",
    confidence=0.9,
    qc_passed=True,
    recommendation="report",
    clinical_metrics=ClinicalMetricsSchema(primary_value=22.0, cutoff=35.0, unit="Ct", label="Ct"),
    model_version="v1",
  )
  data.update(kwargs)
  return DiagnosisReport(**data)


def test_panel_multi_disease(db_session):
  service = PanelService(db_session)
  service.ensure_defaults()
  panels = service.list_panels()
  assert any(p.panel_id == "RESP-V1" for p in panels)

  result = service.analyze(
    PanelAnalyzeRequest(
      panel_id="RESP-V1",
      sample_id="PANEL-1",
      marker_values={
        "SARS_COV2": 28.0,
        "FLU_A": 40.0,
        "FLU_B": 39.0,
        "RSV": 22.0,
      },
    )
  )
  assert result.overall_result == "positive"
  assert "COVID19" in result.detected_diseases
  assert "RSV" in result.detected_diseases
  assert result.positive_count == 2
  assert len(result.markers) == 4


def test_custom_panel_elisa_markers(db_session):
  service = PanelService(db_session)
  service.create_panel(
    MarkerPanelCreate(
      panel_id="SERO-V1",
      name="Serology duo",
      markers=[
        MarkerDefinition(
          marker_id="IgM",
          name="IgM",
          kit_type="elisa",
          disease_code="ACUTE",
          cutoff=1.0,
          unit="S/CO",
          field="od_igm",
        ),
        MarkerDefinition(
          marker_id="IgG",
          name="IgG",
          kit_type="elisa",
          disease_code="PAST",
          cutoff=1.0,
          unit="S/CO",
          field="od_igg",
        ),
      ],
    )
  )
  out = service.analyze(
    PanelAnalyzeRequest(
      panel_id="SERO-V1",
      sample_id="E1",
      marker_values={"IgM": 1.5, "IgG": 0.4},
    )
  )
  assert out.overall_result == "positive"
  assert "ACUTE" in out.detected_diseases


def test_clinical_explanation_for_physician():
  report = _report(
    result="positive",
    confidence=0.82,
    qc_flags=[QCFlagSchema(code="LOW_SNR", message="low snr", severity="warning")],
    recommendation="retest",
  )
  expl = build_clinical_explanation(report)
  assert expl.audience == "physician_biologist"
  assert "positive" in expl.summary.lower() or "POSITIVE" in expl.summary
  assert any(i.category == "qc" for i in expl.insights)
  assert any(i.category == "recommendation" for i in expl.insights)
  assert "expert" in expl.confidence_note.lower() or "Moderate" in expl.confidence_note


def test_fuse_qpcr_elisa_concordance():
  consensus, conf, rationale = fuse_kit_results(
    [
      {"kit_type": "qpcr", "result": "positive", "confidence": 0.9},
      {"kit_type": "elisa", "result": "positive", "confidence": 0.8},
    ],
    policy="concordance",
  )
  assert consensus == "positive"
  assert "Concordant" in rationale

  consensus2, _, rationale2 = fuse_kit_results(
    [
      {"kit_type": "qpcr", "result": "positive", "confidence": 0.9},
      {"kit_type": "elisa", "result": "negative", "confidence": 0.8},
    ],
    policy="concordance",
  )
  assert consensus2 == "inconclusive"
  assert "Discordant" in rationale2


def test_multi_kit_case_service(db_session):
  service = CaseService(db_session)
  case = service.create_case(
    CaseCreate(patient_id="P1", fusion_policy="concordance")
  )
  service.add_assay(
    case.case_id,
    CaseAddAssayRequest(
      sample_id="Q1",
      kit_type="qpcr",
      result="positive",
      confidence=0.91,
      role="primary",
    ),
  )
  service.add_assay(
    case.case_id,
    CaseAddAssayRequest(
      sample_id="E1",
      kit_type="elisa",
      result="positive",
      confidence=0.88,
      role="confirmatory",
    ),
  )
  fused = service.fuse(case.case_id)
  assert fused.consensus_result == "positive"
  assert len(fused.assays) == 2
  assert "qPCR" in fused.clinical_narrative or "ELISA" in fused.clinical_narrative


def test_reassessment_suggestion_on_suspicious_qc():
  report = _report(
    result="positive",
    confidence=0.65,
    qc_passed=False,
    qc_flags=[
      QCFlagSchema(code="LOW_SNR", message="a", severity="warning"),
      QCFlagSchema(code="LOW_AMP_EFF", message="b", severity="warning"),
    ],
    recommendation="reassess",
  )
  assert should_suggest_reassessment(report) is True

  clean = _report(result="negative", confidence=0.95, recommendation="report")
  assert should_suggest_reassessment(clean) is False


def test_determine_recommendation_reassess():
  qc = QCResult(
    passed=True,
    flags=[
      QCFlag(code="LOW_SNR", message="snr", severity=QCSeverity.WARNING),
      QCFlag(code="LOW_QUALITY", message="q", severity=QCSeverity.WARNING),
    ],
  )
  assert determine_recommendation("positive", qc, 0.7) == "reassess"


def test_reassessment_service_persist(db_session):
  service = ReassessmentService(db_session)
  report = _report(
    sample_id="S-RA",
    report_id=1,
    recommendation="retest",
    confidence=0.5,
    qc_passed=False,
    qc_flags=[QCFlagSchema(code="LOW_QUALITY", message="q", severity="warning")],
  )
  row = service.suggest_from_report(report)
  assert row is not None
  assert row.status == "suggested"
  listed = service.list_requests(status="suggested")
  assert len(listed) == 1


def test_hitl_feedback_and_export(db_session, tmp_path):
  sample = Sample(
    sample_id="HITL-1",
    kit_type="qpcr",
    status="completed",
  )
  db_session.add(sample)
  diagnosis = Diagnosis(
    sample_id="HITL-1",
    kit_type="qpcr",
    result="positive",
    confidence=0.8,
    recommendation="report",
    qc_passed=True,
    features_json='{"ct_value": 24.0, "signal_to_noise": 4.0, "amplification_efficiency": 0.95, "quality_score": 0.9}',
    approval_status="pending",
  )
  db_session.add(diagnosis)
  db_session.commit()
  db_session.refresh(diagnosis)

  hitl = HitlService(db_session)
  fb = hitl.submit_feedback(
    ExpertFeedbackCreate(
      sample_id="HITL-1",
      report_id=diagnosis.id,
      expert_result="negative",
      note="False positive after clinical review",
    ),
    actor_id="expert-1",
    actor_email="expert@lab.test",
  )
  assert fb.agree_with_model is False
  assert fb.expert_result == "negative"

  export = hitl.export_training_csv(tmp_path / "hitl.csv")
  assert export.rows == 1
  assert export.negatives == 1
  assert (tmp_path / "hitl.csv").exists()
