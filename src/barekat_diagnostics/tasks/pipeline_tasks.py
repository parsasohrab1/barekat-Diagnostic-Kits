"""Asynchronous processing tasks."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from barekat_diagnostics.core.database import SessionLocal
from barekat_diagnostics.data.synthetic import generate_diagnostic_kit_data
from barekat_diagnostics.ml.classifier import train_classifier
from barekat_diagnostics.models.sample import DiagnosisJob
from barekat_diagnostics.pipeline.runner import report_to_json
from barekat_diagnostics.schemas import SampleInput
from barekat_diagnostics.services.diagnosis_service import DiagnosisService
from barekat_diagnostics.tasks.celery_app import celery_app


@celery_app.task(name="barekat_diagnostics.generate_data")
def generate_data_task(n_samples: int = 800, output_path: str = "data/raw/synthetic.csv") -> dict:
  df = generate_diagnostic_kit_data(n_samples=n_samples)
  path = Path(output_path)
  path.parent.mkdir(parents=True, exist_ok=True)
  df.to_csv(path, index=False)
  return {"samples": len(df), "path": str(path)}


@celery_app.task(name="barekat_diagnostics.train_model")
def train_model_task(data_path: str = "data/raw/synthetic.csv") -> dict:
  df = pd.read_csv(data_path)
  _, metrics = train_classifier(df)
  return metrics.model_dump()


@celery_app.task(bind=True, name="barekat_diagnostics.analyze_diagnosis")
def analyze_diagnosis_task(self, job_id: str, sample_json: str) -> dict:
  """Asynchronous processing of a diagnostic sample."""
  db = SessionLocal()
  job = None
  try:
    job = db.query(DiagnosisJob).filter(DiagnosisJob.job_id == job_id).first()
    if not job:
      return {"error": "job not found"}

    job.status = "running"
    job.progress = 10.0
    job.celery_task_id = self.request.id
    db.commit()

    sample = SampleInput.model_validate(json.loads(sample_json))
    job.progress = 30.0
    db.commit()

    service = DiagnosisService(db)
    report = service.analyze(sample, save=True)

    job.status = "completed"
    job.progress = 100.0
    job.report_json = report_to_json(report)
    job.completed_at = datetime.now(timezone.utc)
    db.commit()
    return {"job_id": job_id, "status": "completed", "sample_id": sample.sample_id}
  except Exception as exc:
    if job:
      job.status = "failed"
      job.error_message = str(exc)
      job.completed_at = datetime.now(timezone.utc)
      db.commit()
    return {"job_id": job_id, "status": "failed", "error": str(exc)}
  finally:
    db.close()
