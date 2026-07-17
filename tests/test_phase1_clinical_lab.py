"""تست‌های واردسازی CSV/RDML و فاز ۱ کلینیکال-لاب."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from barekat_diagnostics.core.database import Base
from barekat_diagnostics.importers.qpcr_csv import parse_qpcr_csv, wells_summary
from barekat_diagnostics.importers.qpcr_rdml import parse_qpcr_rdml
from barekat_diagnostics.ml.evaluation import evaluate_model
from barekat_diagnostics.ml.features import build_model, prepare_features
from barekat_diagnostics.schemas import AssayBatchCreate, BatchControlUpdate, ReportApprovalRequest
from barekat_diagnostics.services.audit_trail import AuditTrailService
from barekat_diagnostics.services.batch_service import BatchService, BatchValidationError


CSV_FIXTURE = """Sample Name,Well,Ct,Target,Sample Type
PAT-001,A1,22.4,ORF1ab,Unknown
PC-001,H11,24.1,ORF1ab,Positive
NC-001,H12,40.2,ORF1ab,Negative
PAT-002,A2,35.8,ORF1ab,Unknown
"""

RDML_FIXTURE = """<?xml version="1.0" encoding="UTF-8"?>
<rdml version="1.2" xmlns="http://www.rdml.org">
  <sample id="PC-RDML"><type>pos</type></sample>
  <sample id="NC-RDML"><type>ntc</type></sample>
  <sample id="PAT-RDML"><type>unkn</type></sample>
  <react id="1">
    <sample id="PC-RDML"/>
    <data>
      <tar id="ORF1ab"/>
      <cq>23.5</cq>
      <adp><datapoint><cyc>1</cyc><fluor>0.1</fluor></datapoint>
      <datapoint><cyc>2</cyc><fluor>0.2</fluor></datapoint></adp>
    </data>
  </react>
  <react id="2">
    <sample id="NC-RDML"/>
    <data><cq>41.0</cq></data>
  </react>
  <react id="3">
    <sample id="PAT-RDML"/>
    <data><cq>19.8</cq></data>
  </react>
</rdml>
"""


@pytest.fixture()
def db_session():
  engine = create_engine("sqlite:///:memory:")
  # import models so metadata is populated
  from barekat_diagnostics.models import audit as _audit  # noqa: F401
  from barekat_diagnostics.models import sample as _sample  # noqa: F401
  from barekat_diagnostics.models import user as _user  # noqa: F401

  Base.metadata.create_all(engine)
  Session = sessionmaker(bind=engine)
  session = Session()
  try:
    yield session
  finally:
    session.close()


def test_parse_qpcr_csv():
  wells = parse_qpcr_csv(CSV_FIXTURE, calibration_lot="LOT-A")
  summary = wells_summary(wells)
  assert summary["total"] == 4
  assert summary["positive_control"] == 1
  assert summary["negative_control"] == 1
  assert summary["patient"] == 2
  assert wells[0].sample.ct_value == 22.4
  assert wells[0].sample.calibration_lot == "LOT-A"


def test_parse_qpcr_rdml():
  wells = parse_qpcr_rdml(RDML_FIXTURE)
  assert len(wells) == 3
  roles = {w.sample.sample_id: w.role for w in wells}
  # roles assigned via sample meta / id heuristics
  assert any(w.role == "positive_control" for w in wells)
  assert any(w.role == "negative_control" for w in wells)
  cts = {w.sample.sample_id: w.sample.ct_value for w in wells}
  assert cts["PAT-RDML"] == 19.8


def test_batch_controls_gate(db_session):
  service = BatchService(db_session)
  batch = service.create_batch(
    AssayBatchCreate(batch_id="B1", lot_number="LOT-A"),
    actor_id="u1",
    actor_email="tech@lab.local",
    actor_role="technician",
  )
  assert batch.controls_validated is False

  with pytest.raises(BatchValidationError):
    service.require_validated("B1")

  service.register_controls(
    "B1",
    BatchControlUpdate(positive_control_ct=24.0, negative_control_ct=40.0),
    actor_id="u1",
    actor_email="tech@lab.local",
    actor_role="technician",
  )
  validated = service.validate_controls(
    "B1",
    actor_id="u1",
    actor_email="tech@lab.local",
    actor_role="technician",
  )
  assert validated.controls_validated is True
  assert service.require_validated("B1") is not None


def test_batch_controls_fail_when_pos_too_high(db_session):
  service = BatchService(db_session)
  service.create_batch(AssayBatchCreate(batch_id="B2", lot_number="LOT-A"))
  service.register_controls(
    "B2",
    BatchControlUpdate(positive_control_ct=36.0, negative_control_ct=40.0),
  )
  failed = service.validate_controls("B2")
  assert failed.controls_validated is False
  assert failed.status == "failed"


def test_audit_chain_and_approval_log(db_session):
  audit = AuditTrailService(db_session)
  e1 = audit.log("diagnosis.completed", actor_email="a@b.c", resource_id="1", detail={"result": "positive"})
  e2 = audit.log(
    "diagnosis.approved",
    actor_id="u1",
    actor_email="path@lab.local",
    actor_role="pathologist",
    resource_type="diagnosis",
    resource_id="1",
    detail={"decision": "approved"},
  )
  assert e1.entry_hash
  assert e2.prev_hash == e1.entry_hash
  assert audit.verify_chain()["valid"] is True

  from barekat_diagnostics.models.sample import Diagnosis

  diag = Diagnosis(
    sample_id="S1",
    kit_type="qpcr",
    result="positive",
    confidence=0.9,
    recommendation="report",
    qc_passed=True,
  )
  db_session.add(diag)
  db_session.commit()

  from barekat_diagnostics.services.diagnosis_service import DiagnosisService

  # Avoid MinIO/PDF side effects: only approve path
  svc = DiagnosisService.__new__(DiagnosisService)
  svc.db = db_session
  svc.audit = audit
  resp = DiagnosisService.approve_report(
    svc,
    diag.id,
    ReportApprovalRequest(decision="approved", note="OK"),
    actor_id="u1",
    actor_email="path@lab.local",
    actor_role="pathologist",
  )
  assert resp.approval_status == "approved"
  assert resp.approved_by_email == "path@lab.local"
  events = audit.list_events(resource_id=str(diag.id))
  assert any(e.event_type == "diagnosis.approved" for e in events)


def test_pilot_evaluation_se_sp_ci():
  path = Path("data/pilot/pilot_qpcr.csv")
  assert path.exists(), "pilot dataset missing"
  df = pd.read_csv(path)
  X, y, _ = prepare_features(df)
  model = build_model()
  model.fit(X, y)
  result = evaluate_model(df, model=model)
  assert 0.0 <= result.sensitivity.value <= 1.0
  assert result.sensitivity.ci_lower <= result.sensitivity.value <= result.sensitivity.ci_upper
  assert result.specificity.ci_lower <= result.specificity.value <= result.specificity.ci_upper
  assert result.confusion_matrix.tp + result.confusion_matrix.fn == int((y == 1).sum())


def test_dashboard_page_exists():
  assert Path("static/dashboard.html").exists()
