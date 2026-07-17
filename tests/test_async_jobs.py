"""Tests for async diagnosis job service."""

from unittest.mock import MagicMock, patch

from barekat_diagnostics.models.sample import DiagnosisJob
from barekat_diagnostics.schemas import SampleInput
from barekat_diagnostics.services.diagnosis_service import DiagnosisService


class MockSession:
  def __init__(self):
    self._jobs: dict[str, DiagnosisJob] = {}
    self._committed = 0

  def add(self, obj):
    if isinstance(obj, DiagnosisJob):
      self._jobs[obj.job_id] = obj

  def commit(self):
    self._committed += 1

  def refresh(self, obj):
    pass

  def query(self, model):
    return QueryMock(self._jobs, model)


class QueryMock:
  def __init__(self, jobs, model):
    self._jobs = jobs
    self._model = model

  def filter(self, *args):
    return FilterMock(self._jobs)


class FilterMock:
  def __init__(self, jobs):
    self._jobs = jobs
    self._job_id = None

  def filter(self, condition):
    return self

  def first(self):
    if self._jobs:
      return next(iter(self._jobs.values()))
    return None


def test_get_job_not_found():
  db = MockSession()
  service = DiagnosisService(db)  # type: ignore[arg-type]
  assert service.get_job("nonexistent") is None


def test_submit_async_creates_job():
  db = MockSession()
  service = DiagnosisService(db)  # type: ignore[arg-type]
  service.sample_service = MagicMock()

  mock_task = MagicMock()
  mock_task.id = "celery-task-123"

  with patch("barekat_diagnostics.tasks.pipeline_tasks.analyze_diagnosis_task") as mock_celery:
    mock_celery.delay.return_value = mock_task
    sample = SampleInput(sample_id="ASYNC-001", kit_type="qpcr", ct_value=22.0)
    result = service.submit_async(sample)

  assert result.job_id
  assert result.sample_id == "ASYNC-001"
  assert result.status == "pending"
  assert len(db._jobs) == 1
