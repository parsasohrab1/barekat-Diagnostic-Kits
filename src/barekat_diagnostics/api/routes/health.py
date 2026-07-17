"""Health check endpoints."""

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from barekat_diagnostics import __version__
from barekat_diagnostics.core.database import engine
from barekat_diagnostics.schemas import HealthResponse

router = APIRouter()


def _check_database() -> str:
  try:
    with engine.connect() as conn:
      conn.execute(text("SELECT 1"))
    return "healthy"
  except Exception:
    return "unhealthy"


@router.get("/health/live")
def liveness() -> dict:
  return {"status": "alive", "version": __version__}


@router.get("/health/ready")
def readiness(response: Response) -> dict:
  db_status = _check_database()
  overall = "healthy" if db_status == "healthy" else "degraded"
  if db_status == "unhealthy":
    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    overall = "unhealthy"
  return {
    "status": overall,
    "version": __version__,
    "services": {"database": db_status},
  }


@router.get("/health", response_model=HealthResponse)
def health_check(response: Response) -> HealthResponse:
  db_status = _check_database()
  overall = "healthy" if db_status == "healthy" else "unhealthy"
  if overall == "unhealthy":
    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
  return HealthResponse(
    status=overall,
    version=__version__,
    services={"database": db_status},
  )
