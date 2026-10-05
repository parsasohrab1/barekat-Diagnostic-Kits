"""Edge and Offline-First API endpoints + kiosk bundle."""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from barekat_diagnostics.api.deps import CurrentUser, require_permission
from barekat_diagnostics.core.config import get_settings
from barekat_diagnostics.core.database import get_db
from barekat_diagnostics.core.rbac import Permission
from barekat_diagnostics.edge.bundle import BundleError, build_locked_edge_bundle
from barekat_diagnostics.edge.offline_service import OfflineDiagnosisService
from barekat_diagnostics.edge.sync import OfflineSyncService
from barekat_diagnostics.ml.onnx_export import benchmark_onnx, export_sklearn_to_onnx
from barekat_diagnostics.schemas import (
  DiagnosisReport,
  EdgeBundleResponse,
  OfflineSyncResponse,
  OnnxExportResponse,
  SampleInput,
)

router = APIRouter(prefix="/edge")


class OfflineAnalyzeRequest(BaseModel):
  sample: SampleInput


@router.post("/offline/analyze", response_model=DiagnosisReport)
def offline_analyze(
  request: OfflineAnalyzeRequest,
  user: CurrentUser = Depends(require_permission(Permission.EDGE_OPERATE)),
) -> DiagnosisReport:
  """Local analysis without needing the central API."""
  _ = user
  service = OfflineDiagnosisService()
  report = service.analyze(request.sample)
  if service.last_latency_ms is not None:
    report.latency_ms = service.last_latency_ms
  return report


@router.get("/offline/pending")
def offline_pending_count(
  user: CurrentUser = Depends(require_permission(Permission.EDGE_OPERATE)),
) -> dict:
  _ = user
  service = OfflineDiagnosisService()
  return {
    "pending_samples": service.store.pending_count(),
    "pending_sync": service.pending_sync_count(),
  }


@router.post("/offline/sync", response_model=OfflineSyncResponse)
def offline_sync(
  user: CurrentUser = Depends(require_permission(Permission.EDGE_OPERATE)),
) -> OfflineSyncResponse:
  """Resilient synchronization with retry/backoff and conflict resolution."""
  _ = user
  result = OfflineSyncService().sync_all()
  return OfflineSyncResponse(**result)


@router.post("/bundle", response_model=EdgeBundleResponse)
def build_kiosk_bundle(
  model_version: str | None = None,
  enforce_sla: bool = False,
  user: CurrentUser = Depends(require_permission(Permission.ML_MANAGE)),
) -> EdgeBundleResponse:
  """Package the kiosk with a locked ONNX model."""
  _ = user
  settings = get_settings()
  if enforce_sla:
    settings.edge_enforce_latency_sla = True
  try:
    result = build_locked_edge_bundle(model_version=model_version, settings=settings)
  except BundleError as exc:
    raise HTTPException(status_code=400, detail=exc.message) from exc
  except ImportError as exc:
    raise HTTPException(status_code=501, detail=str(exc)) from exc
  return EdgeBundleResponse(**result)


@router.post("/onnx/export", response_model=OnnxExportResponse)
def export_onnx(
  model_path: str | None = None,
  benchmark: bool = True,
  user: CurrentUser = Depends(require_permission(Permission.ML_MANAGE)),
) -> OnnxExportResponse:
  _ = user
  settings = get_settings()
  src = Path(model_path or settings.model_path) / settings.classifier_model
  if not src.exists():
    raise HTTPException(status_code=404, detail=f"Model not found: {src}")

  try:
    out = export_sklearn_to_onnx(src, settings.onnx_model_path, settings=settings)
    bench = benchmark_onnx(out, settings=settings) if benchmark else None
  except ImportError as exc:
    raise HTTPException(status_code=501, detail=str(exc)) from exc

  return OnnxExportResponse(
    onnx_path=str(out),
    metadata_path=str(out.with_suffix(".onnx.json")),
    benchmark=bench,
  )


@router.post("/onnx/benchmark")
def onnx_benchmark(
  user: CurrentUser = Depends(require_permission(Permission.EDGE_OPERATE)),
) -> dict:
  _ = user
  settings = get_settings()
  path = Path(settings.onnx_model_path)
  if not path.exists():
    raise HTTPException(status_code=404, detail="ONNX model not found")
  try:
    return benchmark_onnx(path, settings=settings)
  except ImportError as exc:
    raise HTTPException(status_code=501, detail=str(exc)) from exc
