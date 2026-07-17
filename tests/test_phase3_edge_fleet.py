"""تست‌های فاز ۳ — edge sync، تعارض، multi-tenant، bundle lock."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from barekat_diagnostics.core.database import Base
from barekat_diagnostics.edge.bundle import verify_bundle_signature
from barekat_diagnostics.edge.offline_store import OfflineStore
from barekat_diagnostics.schemas import (
  CenterCreate,
  ClinicalMetricsSchema,
  DiagnosisReport,
  EdgeDeviceCreate,
  SampleInput,
  TenantCreate,
)
from barekat_diagnostics.services.diagnosis_service import DiagnosisService
from barekat_diagnostics.services.fleet_service import FleetService
from barekat_diagnostics.services.tenant_service import TenantService


@pytest.fixture()
def db_session():
  engine = create_engine("sqlite:///:memory:")
  import barekat_diagnostics.models.audit  # noqa: F401
  import barekat_diagnostics.models.fleet  # noqa: F401
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
def offline_db(tmp_path: Path) -> OfflineStore:
  return OfflineStore(db_path=tmp_path / "offline.db")


def _report(sample_id: str = "S1", **kwargs) -> DiagnosisReport:
  data = dict(
    sample_id=sample_id,
    kit_type="qpcr",
    result="positive",
    confidence=0.9,
    qc_passed=True,
    recommendation="report",
    clinical_metrics=ClinicalMetricsSchema(primary_value=22.0, cutoff=30.0, unit="Ct"),
    model_version="v1",
  )
  data.update(kwargs)
  return DiagnosisReport(**data)


def test_offline_store_client_report_and_retry(offline_db: OfflineStore):
  offline_db.set_device_context(device_id="DEV-1", center_id="CTR-1", tenant_id="T-1")
  sample = SampleInput(sample_id="S-OFF-1", ct_value=22.0, quality_score=0.9)
  offline_db.enqueue_sample(sample)
  crid = offline_db.save_diagnosis(_report("S-OFF-1"))
  assert crid.startswith("CRPT-")
  pending = offline_db.list_pending_sync()
  assert len(pending) == 1
  assert pending[0]["client_report_id"] == crid
  assert pending[0]["report"]["device_id"] == "DEV-1"

  offline_db.mark_failed(crid, "network down")
  pending2 = offline_db.list_pending_sync()
  assert pending2[0]["sync_attempts"] >= 1

  offline_db.mark_synced("S-OFF-1", crid, resolution="accepted")
  assert offline_db.pending_sync_count() == 0


def test_sync_conflict_reject_duplicate(db_session):
  svc = DiagnosisService(db_session)
  report = _report("S-CONF", client_report_id="CRPT-SAME")
  first = svc.ingest_edge_report(
    report=report,
    client_report_id="CRPT-SAME",
    device_id="DEV-1",
    center_id="CTR-1",
    tenant_id="T-1",
    conflict_policy="reject_duplicate",
  )
  assert first["conflict"] is False
  assert first["resolution"] == "accepted"

  second = svc.ingest_edge_report(
    report=_report("S-CONF", client_report_id="CRPT-SAME", result="negative"),
    client_report_id="CRPT-SAME",
    conflict_policy="reject_duplicate",
  )
  assert second["conflict"] is True
  assert second["resolution"] == "rejected_duplicate"
  assert second["report_id"] == first["report_id"]


def test_sync_conflict_client_wins(db_session):
  svc = DiagnosisService(db_session)
  svc.ingest_edge_report(
    report=_report("S-CW", client_report_id="CRPT-CW", result="positive"),
    client_report_id="CRPT-CW",
  )
  updated = svc.ingest_edge_report(
    report=_report("S-CW", client_report_id="CRPT-CW", result="negative"),
    client_report_id="CRPT-CW",
    conflict_policy="client_wins",
  )
  assert updated["resolution"] == "client_wins"
  from barekat_diagnostics.models.sample import Diagnosis

  row = db_session.query(Diagnosis).filter(Diagnosis.client_report_id == "CRPT-CW").first()
  assert row is not None
  assert row.result == "negative"


def test_multi_tenant_aggregates(db_session):
  tenants = TenantService(db_session)
  tenants.create_tenant(TenantCreate(tenant_id="T1", name="Network A"))
  tenants.create_center(
    CenterCreate(center_id="C1", tenant_id="T1", name="Lab North", region="Tehran")
  )
  tenants.create_center(CenterCreate(center_id="C2", tenant_id="T1", name="Lab South"))

  from barekat_diagnostics.models.sample import Diagnosis, Sample

  db_session.add(Sample(sample_id="S1", kit_type="qpcr", center_id="C1", tenant_id="T1"))
  db_session.add(Sample(sample_id="S2", kit_type="qpcr", center_id="C1", tenant_id="T1"))
  db_session.add(
    Diagnosis(
      sample_id="S1",
      kit_type="qpcr",
      result="positive",
      confidence=0.9,
      center_id="C1",
      tenant_id="T1",
      qc_passed=True,
    )
  )
  db_session.add(
    Diagnosis(
      sample_id="S2",
      kit_type="qpcr",
      result="negative",
      confidence=0.8,
      center_id="C1",
      tenant_id="T1",
      qc_passed=False,
    )
  )
  db_session.commit()

  agg = tenants.center_aggregate("C1")
  assert agg.samples == 2
  assert agg.diagnoses == 2
  assert agg.positive == 1
  assert agg.qc_failures == 1

  tagg = tenants.tenant_aggregate("T1")
  assert tagg.centers == 2
  assert tagg.samples == 2
  assert tagg.positive_rate == 0.5


def test_fleet_device_register_and_manifest_empty(db_session):
  tenants = TenantService(db_session)
  tenants.create_tenant(TenantCreate(tenant_id="T1", name="Net"))
  tenants.create_center(CenterCreate(center_id="C1", tenant_id="T1", name="Lab"))
  fleet = FleetService(db_session)
  device = fleet.register_device(
    EdgeDeviceCreate(device_id="DEV-99", center_id="C1", tenant_id="T1", label="Kiosk A")
  )
  assert device.status == "registered"
  with pytest.raises(Exception):
    fleet.get_manifest_for_device("DEV-99")


def test_bundle_signature_roundtrip():
  from barekat_diagnostics.edge.bundle import _sign

  checksum = "abc123"
  secret = "edge-bundle-dev-secret"
  sig = _sign(checksum, secret)
  assert verify_bundle_signature(checksum, sig, secret)
  assert not verify_bundle_signature(checksum, "deadbeef", secret)


def test_edge_latency_config():
  from barekat_diagnostics.core.config import get_settings

  s = get_settings()
  assert s.edge_latency_sla_ms == 100.0
  assert s.edge_ort_intra_op_threads == 1
