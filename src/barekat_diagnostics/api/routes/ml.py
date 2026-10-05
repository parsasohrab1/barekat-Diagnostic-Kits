"""ML model evaluation and management API endpoints."""

from pathlib import Path

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from barekat_diagnostics.api.deps import CurrentUser, require_permission
from barekat_diagnostics.core.database import get_db
from barekat_diagnostics.core.rbac import Permission
from barekat_diagnostics.ml.classifier import DiagnosticPredictor, train_classifier
from barekat_diagnostics.ml.evaluation import evaluate_model
from barekat_diagnostics.ml.features import build_model, prepare_features
from barekat_diagnostics.ml.registry import ModelRegistry, RegistryError
from barekat_diagnostics.schemas import (
  IVDEvaluationResult,
  ModelExplanation,
  ModelRegistryResponse,
  ModelVersionResponse,
  PilotEvaluationRequest,
  PromoteRequest,
  TrainingMetrics,
)
from barekat_diagnostics.services.audit_trail import AuditTrailService

router = APIRouter(prefix="/ml")


class TrainRequest(BaseModel):
  data_path: str = "data/raw/synthetic.csv"
  version: str = "v1"
  promote: bool = False


class EvaluateRequest(BaseModel):
  data_path: str = "data/raw/synthetic.csv"


class ExplainRequest(BaseModel):
  features: dict[str, float]
  sample_id: str | None = None


class ABTestConfigRequest(BaseModel):
  enabled: bool = False
  challenger_version: str = "v2"
  traffic_pct: float = Field(0.1, ge=0.0, le=1.0)


def _registry_response(registry: ModelRegistry) -> ModelRegistryResponse:
  return ModelRegistryResponse(
    production_version=registry.production_version,
    production_locked=registry.production_locked,
    ab_test_enabled=registry.ab_test.enabled,
    challenger_version=registry.ab_test.challenger_version,
    traffic_pct=registry.ab_test.traffic_pct,
    versions=[
      ModelVersionResponse(
        version=v.version,
        file=v.file,
        algorithm=v.algorithm,
        status=v.status,
        metrics=v.metrics,
        dataset_hash=v.dataset_hash,
        created_at=v.created_at,
        file_checksum=v.file_checksum,
        locked=v.locked,
        validation_protocol_id=v.validation_protocol_id,
        change_request_id=v.change_request_id,
      )
      for v in registry.versions.values()
    ],
  )


def _actor(user: CurrentUser) -> dict:
  return {"actor_id": str(user.id), "actor_email": user.email, "actor_role": user.role}


@router.post("/train", response_model=TrainingMetrics)
def train_model_endpoint(
  body: TrainRequest,
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(require_permission(Permission.ML_MANAGE)),
) -> TrainingMetrics:
  """Train the model — staging recording; direct promote only if production is not locked."""
  path = Path(body.data_path)
  if not path.exists():
    raise HTTPException(status_code=404, detail=f"Data file not found: {path}")
  df = pd.read_csv(path)
  try:
    _, metrics = train_classifier(df, version=body.version, promote=body.promote)
  except RuntimeError as exc:
    raise HTTPException(status_code=409, detail=str(exc)) from exc

  AuditTrailService(db).log(
    "ml.trained",
    **_actor(user),
    resource_type="model",
    resource_id=body.version,
    model_version=body.version,
    detail={"promoted": metrics.promoted, "data_path": body.data_path},
  )
  return metrics


@router.post("/evaluate", response_model=IVDEvaluationResult)
def evaluate_model_endpoint(
  body: EvaluateRequest,
  user: CurrentUser = Depends(require_permission(Permission.ML_MANAGE)),
) -> IVDEvaluationResult:
  _ = user
  path = Path(body.data_path)
  if not path.exists():
    raise HTTPException(status_code=404, detail=f"Data file not found: {path}")
  df = pd.read_csv(path)
  X, y, _ = prepare_features(df)
  model = build_model()
  model.fit(X, y)
  return evaluate_model(df, model=model)


@router.post("/evaluate-pilot", response_model=IVDEvaluationResult)
def evaluate_pilot_endpoint(
  body: PilotEvaluationRequest | None = None,
  user: CurrentUser = Depends(require_permission(Permission.ML_MANAGE)),
) -> IVDEvaluationResult:
  from barekat_diagnostics.core.config import get_settings

  _ = user
  path = Path((body.data_path if body else None) or get_settings().pilot_data_path)
  if not path.exists():
    raise HTTPException(status_code=404, detail=f"Pilot file not found: {path}")
  df = pd.read_csv(path)
  if "True_Status" not in df.columns:
    raise HTTPException(status_code=400, detail="The True_Status column is required in the pilot data")
  X, y, _ = prepare_features(df)
  model = build_model()
  model.fit(X, y)
  return evaluate_model(df, model=model)


@router.get("/registry", response_model=ModelRegistryResponse)
def get_registry(
  user: CurrentUser = Depends(require_permission(Permission.DIAGNOSIS_READ)),
) -> ModelRegistryResponse:
  _ = user
  return _registry_response(ModelRegistry.load())


@router.post("/registry/promote/{version}", response_model=ModelRegistryResponse)
def promote_version(
  version: str,
  body: PromoteRequest | None = None,
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(require_permission(Permission.ML_PROMOTE)),
) -> ModelRegistryResponse:
  """Explicit promotion — if production is locked, force only with change control."""
  body = body or PromoteRequest()
  registry = ModelRegistry.load()
  try:
    registry.promote(
      version,
      change_request_id=body.change_request_id,
      validation_protocol_id=body.validation_protocol_id,
      force=body.force,
    )
  except RegistryError as exc:
    raise HTTPException(status_code=409, detail=exc.message) from exc

  AuditTrailService(db).log(
    "ml.promoted",
    **_actor(user),
    resource_type="model",
    resource_id=version,
    model_version=version,
    detail=body.model_dump(),
  )
  return _registry_response(registry)


@router.post("/registry/lock", response_model=ModelRegistryResponse)
def lock_production(
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(require_permission(Permission.ML_PROMOTE)),
) -> ModelRegistryResponse:
  registry = ModelRegistry.load()
  try:
    registry.lock_production()
  except RegistryError as exc:
    raise HTTPException(status_code=400, detail=exc.message) from exc
  AuditTrailService(db).log(
    "ml.production_locked",
    **_actor(user),
    resource_type="model",
    resource_id=registry.production_version,
    model_version=registry.production_version,
  )
  return _registry_response(registry)


@router.post("/registry/unlock", response_model=ModelRegistryResponse)
def unlock_production(
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(require_permission(Permission.ADMIN_SETTINGS)),
) -> ModelRegistryResponse:
  registry = ModelRegistry.load()
  registry.unlock_production()
  AuditTrailService(db).log(
    "ml.production_unlocked",
    **_actor(user),
    resource_type="model",
    resource_id=registry.production_version,
    model_version=registry.production_version,
  )
  return _registry_response(registry)


@router.post("/registry/ab-test", response_model=ModelRegistryResponse)
def configure_ab_test(
  body: ABTestConfigRequest,
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(require_permission(Permission.ML_MANAGE)),
) -> ModelRegistryResponse:
  registry = ModelRegistry.load()
  if registry.production_locked and body.enabled:
    raise HTTPException(
      status_code=409,
      detail="With production locked, A/B is only enabled through change control",
    )
  registry.ab_test.enabled = body.enabled
  registry.ab_test.challenger_version = body.challenger_version
  registry.ab_test.traffic_pct = body.traffic_pct
  registry.save()
  AuditTrailService(db).log(
    "ml.ab_test_configured",
    **_actor(user),
    resource_type="model",
    resource_id=registry.production_version,
    detail=body.model_dump(),
  )
  return _registry_response(registry)


@router.post("/registry/rollback/{version}")
def rollback_model(
  version: str,
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(require_permission(Permission.ML_PROMOTE)),
) -> dict:
  registry = ModelRegistry.load()
  rolled = registry.rollback_if_degraded(version)
  if not rolled:
    raise HTTPException(
      status_code=400,
      detail="Automatic rollback is not possible — use change control or force_rollback",
    )
  AuditTrailService(db).log(
    "ml.rolled_back",
    **_actor(user),
    resource_type="model",
    resource_id=version,
    model_version=registry.production_version,
  )
  return {"rolled_back_from": version, "production_version": registry.production_version}


@router.post("/explain", response_model=ModelExplanation)
def explain_prediction_endpoint(
  body: ExplainRequest,
  user: CurrentUser = Depends(require_permission(Permission.DIAGNOSIS_READ)),
) -> ModelExplanation:
  _ = user
  predictor = DiagnosticPredictor()
  try:
    return predictor.explain(body.features, sample_id=body.sample_id)
  except FileNotFoundError as exc:
    raise HTTPException(status_code=404, detail=str(exc)) from exc
