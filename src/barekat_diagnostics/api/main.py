"""FastAPI application."""

from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from barekat_diagnostics import __version__
from barekat_diagnostics.api.routes import (
  audit,
  auth,
  batches,
  calibration,
  cases,
  changes,
  dashboard,
  diagnosis,
  drift,
  edge,
  fleet,
  health,
  hitl,
  import_qpcr,
  lis,
  ml,
  panels,
  reassessments,
  samples,
  tenants,
  validation,
)
from barekat_diagnostics.core.config import get_settings

logger = structlog.get_logger(__name__)

STATIC_DIR = Path(__file__).resolve().parent.parent.parent.parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
  settings = get_settings()
  logger.info("starting_app", env=settings.app_env, version=__version__)
  yield
  logger.info("shutting_down_app")


def create_app() -> FastAPI:
  settings = get_settings()

  app = FastAPI(
    title="barekat-Diagnostic-Kits",
    description="Intelligent platform for analyzing diagnostic kit data",
    version=__version__,
    lifespan=lifespan,
    docs_url="/docs" if settings.debug else None,
  )

  app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.debug else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
  )

  prefix = settings.api_prefix
  app.include_router(health.router, prefix=prefix, tags=["Health"])
  app.include_router(auth.router, prefix=prefix, tags=["Auth"])
  app.include_router(samples.router, prefix=prefix, tags=["Samples"])
  app.include_router(calibration.router, prefix=prefix, tags=["Calibration"])
  app.include_router(batches.router, prefix=prefix, tags=["Batches"])
  app.include_router(import_qpcr.router, prefix=prefix, tags=["Import"])
  app.include_router(diagnosis.router, prefix=prefix, tags=["Diagnosis"])
  app.include_router(validation.router, prefix=prefix, tags=["Validation"])
  app.include_router(changes.router, prefix=prefix, tags=["Change Control"])
  app.include_router(lis.router, prefix=prefix, tags=["LIS"])
  app.include_router(drift.router, prefix=prefix, tags=["Drift"])
  app.include_router(tenants.router, prefix=prefix, tags=["Tenants"])
  app.include_router(fleet.router, prefix=prefix, tags=["Fleet"])
  app.include_router(audit.router, prefix=prefix, tags=["Audit"])
  app.include_router(dashboard.router, prefix=prefix, tags=["Dashboard"])
  app.include_router(ml.router, prefix=prefix, tags=["ML"])
  app.include_router(edge.router, prefix=prefix, tags=["Edge"])
  app.include_router(panels.router, prefix=prefix, tags=["Panels"])
  app.include_router(cases.router, prefix=prefix, tags=["Cases"])
  app.include_router(reassessments.router, prefix=prefix, tags=["Reassessment"])
  app.include_router(hitl.router, prefix=prefix, tags=["HITL"])

  if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

  @app.get("/dashboard", include_in_schema=False)
  def lab_dashboard():
    page = STATIC_DIR / "dashboard.html"
    if not page.exists():
      return {"detail": "dashboard not found"}
    return FileResponse(page)

  return app


app = create_app()
