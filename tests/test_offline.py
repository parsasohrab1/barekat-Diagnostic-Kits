"""Tests for offline-first SQLite store."""

import pytest
from pathlib import Path

from barekat_diagnostics.edge.offline_store import OfflineStore
from barekat_diagnostics.edge.offline_service import OfflineDiagnosisService
from barekat_diagnostics.schemas import SampleInput


@pytest.fixture
def offline_db(tmp_path: Path):
  return OfflineStore(db_path=tmp_path / "test_offline.db")


def test_enqueue_and_pending(offline_db: OfflineStore):
  sample = SampleInput(sample_id="OFF-001", kit_type="qpcr", ct_value=22.0, quality_score=0.9)
  offline_db.enqueue_sample(sample)
  assert offline_db.pending_count() == 1


def test_offline_analyze(tmp_path: Path):
  service = OfflineDiagnosisService()
  service.store = OfflineStore(db_path=tmp_path / "offline.db")
  sample = SampleInput(sample_id="OFF-002", kit_type="qpcr", ct_value=20.0, quality_score=0.95)
  report = service.analyze(sample)
  assert report.sample_id == "OFF-002"
  assert report.result in ("positive", "negative", "inconclusive")
  assert service.pending_sync_count() >= 1
