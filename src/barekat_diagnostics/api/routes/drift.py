"""API مانیتورینگ drift و کیفیت سیگنال."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from barekat_diagnostics.api.deps import CurrentUser, require_permission
from barekat_diagnostics.core.database import get_db
from barekat_diagnostics.core.rbac import Permission
from barekat_diagnostics.schemas import DriftAlertResponse, DriftCheckResponse
from barekat_diagnostics.services.drift_service import DriftMonitorService

router = APIRouter(prefix="/drift")


def _actor(user: CurrentUser) -> dict:
  return {"actor_id": str(user.id), "actor_email": user.email, "actor_role": user.role}


@router.post("/baseline")
def set_baseline(
  model_version: str | None = None,
  lookback: int = Query(200, ge=10, le=2000),
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(require_permission(Permission.DRIFT_MANAGE)),
) -> dict:
  _ = user
  row = DriftMonitorService(db).set_baseline_from_recent(model_version, lookback=lookback)
  return {
    "model_version": row.model_version,
    "sample_count": row.sample_count,
    "positive_rate": row.positive_rate,
    "mean_quality_score": row.mean_quality_score,
    "mean_snr": row.mean_snr,
  }


@router.post("/check", response_model=DriftCheckResponse)
def check_drift(
  lookback: int = Query(50, ge=5, le=500),
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(require_permission(Permission.DRIFT_MANAGE)),
) -> DriftCheckResponse:
  return DriftMonitorService(db).check(lookback=lookback, **_actor(user))


@router.get("/alerts", response_model=list[DriftAlertResponse])
def list_alerts(
  status: str | None = Query("open"),
  limit: int = Query(50, ge=1, le=200),
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(require_permission(Permission.AUDIT_READ)),
) -> list[DriftAlertResponse]:
  _ = user
  service = DriftMonitorService(db)
  return [service.to_alert_response(a) for a in service.list_alerts(status=status, limit=limit)]


@router.post("/alerts/{alert_id}/ack", response_model=DriftAlertResponse)
def ack_alert(
  alert_id: str,
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(require_permission(Permission.DRIFT_MANAGE)),
) -> DriftAlertResponse:
  service = DriftMonitorService(db)
  try:
    row = service.acknowledge(alert_id, actor_id=str(user.id), actor_email=user.email)
  except ValueError as exc:
    raise HTTPException(status_code=404, detail=str(exc)) from exc
  return service.to_alert_response(row)
