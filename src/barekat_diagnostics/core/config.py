"""Central platform settings."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        protected_namespaces=("settings_",),
    )

    # Application
    app_name: str = "barekat-diagnostics"
    app_env: Literal["development", "staging", "production"] = "development"
    debug: bool = False
    api_prefix: str = "/api/v1"

    # Auth / Security
    auth_enabled: bool = False
    secret_key: str = "dev-secret-change-me-barekat-diagnostics"
    access_token_expire_minutes: int = 480
    audit_retention_years: int = 7

    # Lab batch controls
    require_batch_controls: bool = True
    default_pos_control_ct_max: float = 32.0
    default_neg_control_ct_min: float = 38.0

    # Pilot validation
    pilot_data_path: str = "data/pilot/pilot_qpcr.csv"

    # Database
    database_url: str = "postgresql://barekat:barekat@localhost:5432/barekat_diagnostics"

    # Redis & Celery
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # Object Storage
    s3_endpoint: str = "http://localhost:9000"
    s3_access_key: str = "barekat"
    s3_secret_key: str = "barekatsecret"
    s3_bucket: str = "barekat-diagnostics"
    s3_region: str = "us-east-1"

    # Pipeline
    pipeline_mode: Literal["simulated", "production"] = "simulated"
    pipeline_work_dir: str = "/data/processed"

    # Quality Control thresholds
    qc_min_quality_score: float = 0.5
    qc_min_signal_to_noise: float = 1.2
    qc_min_amplification_efficiency: float = 0.8

    # ML Models
    model_path: str = "data/models"
    classifier_model: str = "diagnostic_classifier_v1.pkl"
    classifier_type: Literal["random_forest", "svm"] = "random_forest"
    ml_ab_test_enabled: bool = False
    ml_ab_test_challenger: str = "v2"
    ml_ab_test_traffic_pct: float = 0.1
    ml_rollback_threshold: float = 0.05

    # Drift / signal quality monitoring
    drift_psi_threshold: float = 2.0  # z-score mean shift
    drift_positive_rate_threshold: float = 0.15
    signal_quality_drop_threshold: float = 0.15

    # Edge / Offline
    inference_backend: Literal["sklearn", "onnx"] = "sklearn"
    onnx_model_path: str = "data/models/diagnostic_classifier_v1.onnx"
    offline_sqlite_path: str = "data/offline/local.db"
    offline_sync_api_url: str = "http://localhost:8000/api/v1"
    edge_device_id: str = ""
    edge_center_id: str = ""
    edge_tenant_id: str = ""
    edge_sync_token: str = ""
    edge_sync_max_retries: int = 3
    edge_sync_backoff_seconds: float = 1.0
    edge_sync_timeout_seconds: int = 30
    edge_sync_batch_size: int = 50
    edge_conflict_policy: Literal["server_wins", "client_wins", "reject_duplicate"] = "reject_duplicate"
    edge_bundle_dir: str = "data/edge_bundles"
    edge_bundle_secret: str = "edge-bundle-dev-secret"
    edge_require_locked_model: bool = False
    edge_latency_sla_ms: float = 100.0
    edge_enforce_latency_sla: bool = False
    edge_benchmark_iterations: int = 50
    edge_warmup_iterations: int = 3
    edge_ort_intra_op_threads: int = 1
    edge_ort_inter_op_threads: int = 1

    # Observability
    metrics_enabled: bool = True
    log_json: bool = False
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
