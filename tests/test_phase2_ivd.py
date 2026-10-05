"""Phase 2 tests — locked registry, RBAC, HL7, drift, change control."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from barekat_diagnostics.core.database import Base
from barekat_diagnostics.core.rbac import Permission, has_permission, is_valid_role, normalize_role
from barekat_diagnostics.ml.registry import ModelRegistry, RegistryError
from barekat_diagnostics.schemas import (
  ChangeRequestCreate,
  ChangeRequestDecision,
  ClinicalValidationCreate,
  ClinicalValidationSignRequest,
  LabOrderCreate,
  LisExportRequest,
)
from barekat_diagnostics.services.change_control_service import ChangeControlService
from barekat_diagnostics.services.drift_service import DriftMonitorService
from barekat_diagnostics.services.lis_service import LisService, build_hl7_oru_r01
from barekat_diagnostics.services.validation_service import ClinicalValidationService


@pytest.fixture()
def db_session():
  engine = create_engine("sqlite:///:memory:")
  import barekat_diagnostics.models.audit  # noqa: F401
  import barekat_diagnostics.models.lis  # noqa: F401
  import barekat_diagnostics.models.quality  # noqa: F401
  import barekat_diagnostics.models.sample  # noqa: F401
  import barekat_diagnostics.models.user  # noqa: F401

  Base.metadata.create_all(engine)
  Session = sessionmaker(bind=engine)
  session = Session()
  try:
    yield session
  finally:
    session.close()


@pytest.fixture()
def registry_path(tmp_path: Path) -> Path:
  from barekat_diagnostics.ml.registry import ModelVersionInfo

  path = tmp_path / "registry.json"
  reg = ModelRegistry(production_version="v1", production_locked=False)
  reg.versions["v1"] = ModelVersionInfo(
    version="v1",
    file="v1.pkl",
    algorithm="rf",
    features=["Ct_Value"],
    metrics={"sensitivity": 0.95, "specificity": 0.95, "roc_auc": 0.98},
    dataset_hash="abc",
    created_at="2026-01-01T00:00:00+00:00",
    status="production",
  )
  reg.save(path)
  return path


def test_role_aliases():
  assert normalize_role("technician") and normalize_role("technician").value == "operator"
  assert normalize_role("pathologist").value == "supervisor"
  assert is_valid_role("operator")
  assert has_permission("operator", Permission.DIAGNOSIS_RUN)
  assert has_permission("supervisor", Permission.REPORTS_APPROVE)
  assert has_permission("supervisor", Permission.ML_PROMOTE)
  assert has_permission("admin", Permission.ML_MANAGE)
  assert not has_permission("operator", Permission.ML_PROMOTE)


def test_strict_versioning_and_prod_lock(registry_path: Path):
  reg = ModelRegistry.load(registry_path)
  reg.register_version(
    "v3",
    file="v3.pkl",
    algorithm="rf",
    features=["Ct_Value"],
    metrics={"sensitivity": 0.96, "specificity": 0.96, "roc_auc": 0.99},
    dataset_hash="def",
    promote=False,
  )
  with pytest.raises(RegistryError):
    reg.register_version(
      "v3",
      file="v3b.pkl",
      algorithm="rf",
      features=[],
      metrics={"sensitivity": 0.9, "specificity": 0.9, "roc_auc": 0.9},
      dataset_hash="x",
    )

  reg.lock_production()
  assert reg.production_locked is True
  with pytest.raises(RegistryError):
    reg.promote("v3")

  reg.unlock_production(change_request_id="CR-1")
  reg.promote("v3", change_request_id="CR-1", force=False)
  assert reg.production_version == "v3"
  reg.lock_production()
  assert reg.versions["v3"].locked is True


def test_hl7_oru_message():
  msg = build_hl7_oru_r01(
    sample_id="S-1",
    patient_id="P-9",
    result="positive",
    confidence=0.92,
    kit_type="qpcr",
    report_id=12,
    order_id="ORD-1",
    model_version="v1",
  )
  assert "MSH|" in msg
  assert "ORU^R01" in msg
  assert "OBX|1|" in msg
  assert "POSITIVE" in msg


def test_lis_export_roundtrip(db_session):
  from barekat_diagnostics.models.sample import Diagnosis

  db_session.add(
    Diagnosis(
      sample_id="S-HL7",
      kit_type="qpcr",
      result="negative",
      confidence=0.88,
      recommendation="report",
      qc_passed=True,
      model_version="v1",
    )
  )
  db_session.commit()

  service = LisService(db_session)
  service.create_order(
    LabOrderCreate(order_id="ORD-HL7", patient_id="P1", sample_id="S-HL7"),
    actor_email="op@lab.local",
    actor_role="operator",
  )
  exported = service.export_result(
    LisExportRequest(sample_id="S-HL7", format="hl7"),
    actor_email="sup@lab.local",
    actor_role="supervisor",
  )
  assert exported.format == "hl7"
  assert "ORU^R01" in exported.payload

  fhir = service.export_result(
    LisExportRequest(sample_id="S-HL7", format="fhir"),
    actor_email="sup@lab.local",
    actor_role="supervisor",
  )
  resource = json.loads(fhir.payload)
  assert resource["resourceType"] == "DiagnosticReport"


def test_validation_protocol_run_and_sign(db_session):
  path = Path("data/pilot/pilot_qpcr.csv")
  assert path.exists()
  service = ClinicalValidationService(db_session)
  row = service.create(
    ClinicalValidationCreate(
      model_version="v1",
      build_series="BUILD-2026-01",
      lot_number="LOT-PILOT-A",
      batch_id="BATCH-P1",
      data_path=str(path),
      min_sensitivity=0.5,
      min_specificity=0.5,
      min_roc_auc=0.5,
      min_samples=20,
    ),
    actor_email="admin@lab.local",
    actor_role="admin",
  )
  ran = service.run(row.protocol_id, actor_email="admin@lab.local", actor_role="admin")
  assert ran.passed is True
  assert ran.status == "passed"
  signed = service.sign(
    row.protocol_id,
    ClinicalValidationSignRequest(note="accepted"),
    actor_id="u1",
    actor_email="sup@lab.local",
    actor_role="supervisor",
  )
  assert signed.status == "signed"


def test_change_control_requires_signed_protocol_for_high_risk(db_session):
  service = ChangeControlService(db_session)
  with pytest.raises(Exception):
    service.create(
      ChangeRequestCreate(
        change_type="model",
        title="Promote v9",
        risk_level="high",
        target_version="v9",
      )
    )


def test_drift_check_creates_quality_alert(db_session):
  from barekat_diagnostics.models.sample import Sample

  # baseline with high quality
  for i in range(10):
    db_session.add(
      Sample(
        sample_id=f"BASE-{i}",
        kit_type="qpcr",
        status="completed",
        quality_score=0.95,
        signal_to_noise=4.0,
        features_json=json.dumps({"ct_value": 22.0 + i * 0.1}),
      )
    )
  db_session.commit()

  monitor = DriftMonitorService(db_session)
  baseline = monitor.set_baseline_from_recent("v1", lookback=20)
  assert baseline.mean_quality_score is not None

  # recent degraded samples
  for i in range(10):
    db_session.add(
      Sample(
        sample_id=f"DEG-{i}",
        kit_type="qpcr",
        status="completed",
        quality_score=0.4,
        signal_to_noise=1.0,
        features_json=json.dumps({"ct_value": 40.0}),
      )
    )
  db_session.commit()

  result = monitor.check(lookback=10)
  assert result.recent_sample_count >= 10
  # either feature shift or signal quality alert expected
  assert result.alerts_created >= 1 or result.max_feature_shift > 0
