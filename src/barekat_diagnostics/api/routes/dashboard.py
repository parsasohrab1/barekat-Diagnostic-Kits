"""Laboratory operator dashboard API."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from barekat_diagnostics.api.deps import CurrentUser, get_current_user
from barekat_diagnostics.core.database import get_db
from barekat_diagnostics.models.sample import AssayBatch, Diagnosis, DiagnosisJob, Sample
from barekat_diagnostics.schemas import DashboardSummary

router = APIRouter(prefix="/dashboard")


@router.get("/summary", response_model=DashboardSummary)
def dashboard_summary(
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(get_current_user),
) -> DashboardSummary:
  _ = user
  samples_total = db.query(Sample).count()
  samples_pending = db.query(Sample).filter(Sample.status == "pending").count()
  jobs_running = db.query(DiagnosisJob).filter(DiagnosisJob.status.in_(["pending", "running"])).count()
  jobs_completed = db.query(DiagnosisJob).filter(DiagnosisJob.status == "completed").count()
  batches_open = db.query(AssayBatch).filter(AssayBatch.status.in_(["open", "controls_pending"])).count()
  batches_validated = db.query(AssayBatch).filter(AssayBatch.controls_validated.is_(True)).count()
  reports_pending = db.query(Diagnosis).filter(Diagnosis.approval_status == "pending").count()
  qc_failures = db.query(Diagnosis).filter(Diagnosis.qc_passed.is_(False)).count()

  return DashboardSummary(
    samples_total=samples_total,
    samples_pending=samples_pending,
    jobs_running=jobs_running,
    jobs_completed=jobs_completed,
    batches_open=batches_open,
    batches_validated=batches_validated,
    reports_pending_approval=reports_pending,
    recent_qc_failures=qc_failures,
  )
