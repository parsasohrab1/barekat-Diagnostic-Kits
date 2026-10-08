"""Pydantic schemas for the API."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
  status: str
  version: str
  services: dict[str, str] = {}


class QCFlagSchema(BaseModel):
  code: str
  message: str
  severity: Literal["info", "warning", "critical"]


class ClinicalMetricsSchema(BaseModel):
  primary_value: float | None = None
  cutoff: float | None = None
  confidence_interval: tuple[float, float] | None = None
  unit: str = ""
  label: str = ""


class SampleInput(BaseModel):
  sample_id: str
  patient_id: str | None = None
  kit_type: str = "qpcr"
  calibration_lot: str | None = None
  batch_id: str | None = None
  sample_role: Literal["patient", "positive_control", "negative_control"] = "patient"
  tenant_id: str | None = None
  center_id: str | None = None
  device_id: str | None = None
  ct_value: float | None = None
  od_450: float | None = None
  od_620: float | None = None
  od_ratio: float | None = None
  peak_intensity: float | None = None
  wavelength_bands: dict[str, float] = Field(default_factory=dict)
  spectrum: list[float] | None = None
  features: dict[str, float] = Field(default_factory=dict)
  signal_to_noise: float | None = None
  amplification_efficiency: float | None = None
  quality_score: float | None = None
  blank_od: float | None = None
  calibration_error: bool = False
  curve_data: list[float] | None = None


class SampleCreateRequest(BaseModel):
  sample: SampleInput


class SampleResponse(BaseModel):
  sample_id: str
  patient_id: str | None = None
  kit_type: str
  status: str
  calibration_lot: str | None = None
  batch_id: str | None = None
  sample_role: str = "patient"
  raw_data_path: str | None = None
  curve_object_key: str | None = None
  created_at: datetime | None = None


class CalibrationCreate(BaseModel):
  lot_number: str
  kit_type: str = "qpcr"
  expiry_date: date | None = None
  cutoff_value: float | None = None
  standard_curve: list[dict[str, float]] | None = None


class CalibrationResponse(BaseModel):
  lot_number: str
  kit_type: str
  expiry_date: date | None = None
  cutoff_value: float | None = None
  standard_curve_path: str | None = None
  created_at: datetime | None = None


class ImportedQpcrWell(BaseModel):
  sample: SampleInput
  well: str | None = None
  target: str | None = None
  role: Literal["patient", "positive_control", "negative_control"] = "patient"
  source_format: Literal["csv", "rdml"] = "csv"
  raw_row: dict[str, str] = Field(default_factory=dict)


class QpcrImportResponse(BaseModel):
  imported: int
  batch_id: str | None = None
  summary: dict = Field(default_factory=dict)
  samples: list[SampleResponse] = Field(default_factory=list)
  wells: list[ImportedQpcrWell] = Field(default_factory=list)


class AssayBatchCreate(BaseModel):
  batch_id: str
  lot_number: str
  kit_type: str = "qpcr"
  label: str | None = None
  pos_control_ct_max: float = 32.0
  neg_control_ct_min: float = 38.0


class BatchControlUpdate(BaseModel):
  positive_control_sample_id: str | None = None
  negative_control_sample_id: str | None = None
  positive_control_ct: float | None = None
  negative_control_ct: float | None = None


class AssayBatchResponse(BaseModel):
  batch_id: str
  lot_number: str
  kit_type: str
  label: str | None = None
  status: str
  pos_control_ct_max: float
  neg_control_ct_min: float
  positive_control_sample_id: str | None = None
  negative_control_sample_id: str | None = None
  positive_control_ct: float | None = None
  negative_control_ct: float | None = None
  positive_control_passed: bool = False
  negative_control_passed: bool = False
  controls_validated: bool = False
  validation_message: str | None = None
  created_at: datetime | None = None
  validated_at: datetime | None = None


class ReportApprovalRequest(BaseModel):
  decision: Literal["approved", "rejected"] = "approved"
  note: str | None = None


class ReportApprovalResponse(BaseModel):
  report_id: int
  sample_id: str
  approval_status: str
  approved_by: str | None = None
  approved_by_email: str | None = None
  approved_at: datetime | None = None
  note: str | None = None


class AuditLogResponse(BaseModel):
  id: int
  event_type: str
  actor_id: str | None = None
  actor_email: str | None = None
  actor_role: str | None = None
  resource_type: str | None = None
  resource_id: str | None = None
  model_version: str | None = None
  detail_json: str | None = None
  entry_hash: str
  created_at: datetime | None = None


class AuthLoginResponse(BaseModel):
  access_token: str
  token_type: str = "bearer"
  role: str
  email: str
  full_name: str


class UserCreateRequest(BaseModel):
  email: str
  password: str
  full_name: str
  role: str = "operator"


class DashboardSummary(BaseModel):
  samples_total: int
  samples_pending: int
  jobs_running: int
  jobs_completed: int
  batches_open: int
  batches_validated: int
  reports_pending_approval: int
  recent_qc_failures: int


class PilotEvaluationRequest(BaseModel):
  data_path: str = "data/pilot/pilot_qpcr.csv"


class ClinicalValidationCreate(BaseModel):
  protocol_id: str | None = None
  model_version: str
  build_series: str
  batch_id: str | None = None
  lot_number: str | None = None
  data_path: str = "data/pilot/pilot_qpcr.csv"
  min_sensitivity: float = 0.90
  min_specificity: float = 0.90
  min_roc_auc: float = 0.85
  min_samples: int = 30


class ClinicalValidationSignRequest(BaseModel):
  note: str | None = None


class ClinicalValidationResponse(BaseModel):
  protocol_id: str
  model_version: str
  build_series: str
  batch_id: str | None = None
  lot_number: str | None = None
  data_path: str
  status: str
  min_sensitivity: float
  min_specificity: float
  min_roc_auc: float
  min_samples: int
  sample_count: int | None = None
  sensitivity: float | None = None
  specificity: float | None = None
  roc_auc: float | None = None
  passed: bool | None = None
  failure_reason: str | None = None
  signed_by_email: str | None = None
  signed_at: datetime | None = None
  created_at: datetime | None = None


class ChangeRequestCreate(BaseModel):
  change_id: str | None = None
  change_type: Literal["model", "pipeline", "config", "cutoff"] = "model"
  title: str
  description: str | None = None
  risk_level: Literal["low", "medium", "high", "critical"] = "medium"
  mitigation: str | None = None
  target_version: str | None = None
  previous_version: str | None = None
  protocol_id: str | None = None
  detail: dict = Field(default_factory=dict)


class ChangeRequestDecision(BaseModel):
  decision: Literal["approved", "rejected"]
  note: str | None = None


class ChangeRequestResponse(BaseModel):
  change_id: str
  change_type: str
  title: str
  description: str | None = None
  risk_level: str
  mitigation: str | None = None
  target_version: str | None = None
  previous_version: str | None = None
  protocol_id: str | None = None
  status: str
  requested_by_email: str | None = None
  approved_by_email: str | None = None
  approved_at: datetime | None = None
  applied_at: datetime | None = None
  created_at: datetime | None = None


class ChangeRequestApplyResponse(BaseModel):
  change_id: str
  status: str
  message: str
  production_version: str
  production_locked: bool


class LabOrderCreate(BaseModel):
  order_id: str
  patient_id: str
  sample_id: str | None = None
  kit_type: str = "qpcr"
  fhir: dict | None = None


class LabOrderResponse(BaseModel):
  order_id: str
  patient_id: str
  sample_id: str | None = None
  kit_type: str
  status: str
  created_at: datetime | None = None
  updated_at: datetime | None = None


class LisExportRequest(BaseModel):
  sample_id: str
  report_id: int | None = None
  patient_id: str | None = None
  order_id: str | None = None
  format: Literal["hl7", "fhir"] = "hl7"
  destination: str | None = None


class Hl7ExportResponse(BaseModel):
  export_id: int
  sample_id: str
  report_id: int | None = None
  format: str
  content_type: str
  payload: str
  destination: str | None = None
  created_at: datetime | None = None


class DriftAlertResponse(BaseModel):
  alert_id: str
  alert_type: str
  severity: str
  model_version: str | None = None
  metric_name: str
  baseline_value: float | None = None
  observed_value: float | None = None
  threshold: float | None = None
  message: str
  status: str
  created_at: datetime | None = None


class DriftCheckResponse(BaseModel):
  model_version: str
  alerts_created: int
  max_feature_shift: float = 0.0
  alerts: list[DriftAlertResponse] = Field(default_factory=list)
  baseline_sample_count: int = 0
  recent_sample_count: int = 0


class PromoteRequest(BaseModel):
  change_request_id: str | None = None
  validation_protocol_id: str | None = None
  force: bool = False


class FeatureContribution(BaseModel):
  feature: str
  value: float
  contribution: float
  direction: Literal["positive", "negative"]


class ModelExplanation(BaseModel):
  model_version: str
  predicted_class: str
  confidence: float
  top_features: list[FeatureContribution] = Field(default_factory=list)
  method: str = "feature_importance"


class ClinicalInsight(BaseModel):
  category: str
  title: str
  detail: str
  severity: Literal["info", "warning", "critical"] = "info"


class ClinicalExplanation(BaseModel):
  summary: str
  audience: str = "physician_biologist"
  insights: list[ClinicalInsight] = Field(default_factory=list)
  model_explanation: ModelExplanation | None = None
  confidence_note: str = ""


class DiagnosisReport(BaseModel):
  report_id: int | None = None
  sample_id: str
  kit_type: str
  result: Literal["positive", "negative", "inconclusive"]
  confidence: float
  qc_passed: bool
  qc_flags: list[QCFlagSchema] = Field(default_factory=list)
  recommendation: Literal["report", "retest", "invalid", "reassess"]
  clinical_metrics: ClinicalMetricsSchema
  model_version: str = "v1"
  explanation: ModelExplanation | None = None
  clinical_explanation: ClinicalExplanation | None = None
  reassessment_suggested: bool = False
  reassessment_id: str | None = None
  created_at: datetime | None = None
  client_report_id: str | None = None
  device_id: str | None = None
  center_id: str | None = None
  tenant_id: str | None = None
  latency_ms: float | None = None


class DiagnosisResponse(DiagnosisReport):
  """Compatibility with the previous API version."""

  @property
  def qc_warnings(self) -> list[str]:
    return [f.message for f in self.qc_flags]


class DiagnosisRequest(BaseModel):
  sample: SampleInput


class BatchAnalyzeRequest(BaseModel):
  sample_ids: list[str] = Field(..., min_length=1, max_length=500)


class BatchJobResponse(BaseModel):
  job_id: str
  status: str
  total_samples: int
  completed_samples: int
  reports: list[DiagnosisReport] = Field(default_factory=list)


class DiagnosisJobResponse(BaseModel):
  job_id: str
  sample_id: str
  status: Literal["pending", "running", "completed", "failed"]
  progress: float = 0.0
  report: DiagnosisReport | None = None
  error_message: str | None = None
  created_at: datetime | None = None
  completed_at: datetime | None = None


class DiagnosisJobSubmitResponse(BaseModel):
  job_id: str
  sample_id: str
  status: str = "pending"
  message: str = "Analysis queued"


class OfflineSyncResponse(BaseModel):
  synced: int
  failed: int
  pending: int
  conflicts: int = 0
  errors: list[str] = Field(default_factory=list)


class OnnxExportResponse(BaseModel):
  onnx_path: str
  metadata_path: str
  benchmark: dict | None = None
  locked: bool = False
  checksum_sha256: str | None = None


class TrainingMetrics(BaseModel):
  accuracy: float
  sensitivity: float
  specificity: float
  f1_score: float
  model_path: str
  roc_auc: float = 0.0
  ppv: float = 0.0
  npv: float = 0.0
  model_version: str = "v1"
  promoted: bool = False


class MetricWithCI(BaseModel):
  value: float
  ci_lower: float
  ci_upper: float


class ConfusionMatrixSchema(BaseModel):
  tn: int
  fp: int
  fn: int
  tp: int


class CrossValidationFold(BaseModel):
  fold: int
  group: str
  accuracy: float
  sensitivity: float
  specificity: float
  roc_auc: float


class PerLotEvaluation(BaseModel):
  kit_lot: str
  sample_count: int
  confusion_matrix: ConfusionMatrixSchema
  sensitivity: float
  specificity: float


class IVDEvaluationResult(BaseModel):
  accuracy: float
  sensitivity: MetricWithCI
  specificity: MetricWithCI
  ppv: MetricWithCI
  npv: MetricWithCI
  roc_auc: float
  confusion_matrix: ConfusionMatrixSchema
  roc_curve: dict = Field(default_factory=dict)
  cross_validation: list[CrossValidationFold] = Field(default_factory=list)
  per_lot: list[PerLotEvaluation] = Field(default_factory=list)
  feature_columns: list[str] = Field(default_factory=list)
  evaluation_basis: str = "resubstitution"  # out_of_fold_by_group | out_of_fold_stratified | resubstitution


class ModelVersionResponse(BaseModel):
  version: str
  file: str
  algorithm: str
  status: str
  metrics: dict = Field(default_factory=dict)
  dataset_hash: str = ""
  created_at: str = ""
  file_checksum: str = ""
  locked: bool = False
  validation_protocol_id: str | None = None
  change_request_id: str | None = None


class ModelRegistryResponse(BaseModel):
  production_version: str
  production_locked: bool = False
  ab_test_enabled: bool
  challenger_version: str
  traffic_pct: float
  versions: list[ModelVersionResponse] = Field(default_factory=list)


# --- Phase 3: fleet / fleet / multi-tenant ---


class TenantCreate(BaseModel):
  tenant_id: str
  name: str


class TenantResponse(BaseModel):
  tenant_id: str
  name: str
  status: str
  created_at: datetime | None = None


class CenterCreate(BaseModel):
  center_id: str
  tenant_id: str
  name: str
  region: str | None = None


class CenterResponse(BaseModel):
  center_id: str
  tenant_id: str
  name: str
  region: str | None = None
  status: str
  created_at: datetime | None = None


class EdgeDeviceCreate(BaseModel):
  device_id: str
  center_id: str
  tenant_id: str
  label: str | None = None
  device_token: str | None = None


class EdgeDeviceResponse(BaseModel):
  device_id: str
  center_id: str
  tenant_id: str
  label: str | None = None
  model_version: str | None = None
  onnx_checksum: str | None = None
  status: str
  last_seen_at: datetime | None = None
  last_sync_at: datetime | None = None
  last_latency_p95_ms: float | None = None
  sla_ok: bool | None = None
  created_at: datetime | None = None


class FleetReleaseCreate(BaseModel):
  model_version: str
  target_tenant_id: str | None = None
  rollout_pct: float = 100.0
  publish: bool = False


class FleetReleaseResponse(BaseModel):
  release_id: str
  model_version: str
  onnx_path: str
  checksum_sha256: str
  signature: str | None = None
  locked: bool
  status: str
  rollout_pct: float
  target_tenant_id: str | None = None
  min_latency_p95_ms: float | None = None
  created_at: datetime | None = None
  published_at: datetime | None = None


class FleetManifestResponse(BaseModel):
  model_version: str
  release_id: str
  checksum_sha256: str
  signature: str | None = None
  download_path: str
  locked: bool = True
  latency_sla_ms: float = 100.0


class DeviceModelAck(BaseModel):
  device_id: str
  model_version: str
  checksum_sha256: str
  latency_p95_ms: float | None = None
  sla_ok: bool | None = None


class EdgeSyncIngestRequest(BaseModel):
  report: DiagnosisReport
  client_report_id: str | None = None
  device_id: str | None = None
  center_id: str | None = None
  tenant_id: str | None = None
  conflict_policy: Literal["server_wins", "client_wins", "reject_duplicate"] = "reject_duplicate"


class EdgeSyncIngestResponse(BaseModel):
  sample_id: str
  synced: bool
  report_id: int | None = None
  resolution: str
  conflict: bool = False


class CenterAggregateReport(BaseModel):
  center_id: str
  tenant_id: str | None = None
  samples: int = 0
  diagnoses: int = 0
  positive: int = 0
  negative: int = 0
  inconclusive: int = 0
  qc_failures: int = 0
  pending_approvals: int = 0
  devices_online: int = 0
  devices_total: int = 0


class TenantAggregateReport(BaseModel):
  tenant_id: str
  centers: int = 0
  samples: int = 0
  diagnoses: int = 0
  positive_rate: float = 0.0
  qc_failure_rate: float = 0.0
  centers_detail: list[CenterAggregateReport] = Field(default_factory=list)


class EdgeBundleResponse(BaseModel):
  bundle_dir: str
  onnx_path: str
  lock_path: str
  model_version: str
  checksum_sha256: str
  signature: str
  locked: bool
  sla_ok: bool
  benchmark: dict | None = None


# --- Phase 4: panels / multi-kit cases / reassessment / HITL ---


class MarkerDefinition(BaseModel):
  marker_id: str
  name: str
  kit_type: str = "qpcr"
  disease_code: str | None = None
  cutoff: float = 35.0
  unit: str = "Ct"
  field: str | None = None


class MarkerPanelCreate(BaseModel):
  panel_id: str
  name: str
  description: str | None = None
  markers: list[MarkerDefinition] = Field(default_factory=list)


class MarkerPanelResponse(BaseModel):
  panel_id: str
  name: str
  description: str | None = None
  markers: list[MarkerDefinition] = Field(default_factory=list)
  status: str = "active"
  created_at: datetime | None = None


class MarkerResultSchema(BaseModel):
  marker_id: str
  marker_name: str
  disease_code: str | None = None
  kit_type: str = "qpcr"
  result: Literal["positive", "negative", "inconclusive", "borderline"]
  value: float | None = None
  cutoff: float | None = None
  unit: str = ""
  confidence: float = 0.0


class PanelAnalyzeRequest(BaseModel):
  panel_id: str
  sample_id: str | None = None
  sample: SampleInput | None = None
  marker_values: dict[str, float] = Field(default_factory=dict)


class PanelAnalyzeResponse(BaseModel):
  panel_run_id: str
  panel_id: str
  sample_id: str | None = None
  overall_result: Literal["positive", "negative", "inconclusive"]
  detected_diseases: list[str] = Field(default_factory=list)
  markers: list[MarkerResultSchema] = Field(default_factory=list)
  positive_count: int = 0
  borderline_count: int = 0


class CaseCreate(BaseModel):
  case_id: str | None = None
  patient_id: str | None = None
  panel_id: str | None = None
  fusion_policy: Literal["concordance", "any_positive", "weighted", "qpcr_primary"] = "concordance"


class CaseAddAssayRequest(BaseModel):
  sample_id: str | None = None
  kit_type: str | None = None
  marker_id: str | None = None
  report_id: int | None = None
  result: str | None = None
  confidence: float | None = None
  role: str = "primary"
  sample: SampleInput | None = None
  analyze: bool = False


class CaseResponse(BaseModel):
  case_id: str
  patient_id: str | None = None
  panel_id: str | None = None
  status: str
  consensus_result: str | None = None
  consensus_confidence: float | None = None
  fusion_policy: str
  clinical_narrative: str | None = None
  assays: list[dict] = Field(default_factory=list)
  created_at: datetime | None = None


class CaseFuseResponse(BaseModel):
  case_id: str
  consensus_result: Literal["positive", "negative", "inconclusive"]
  consensus_confidence: float
  fusion_policy: str
  rationale: str
  assays: list[dict] = Field(default_factory=list)
  clinical_narrative: str | None = None


class ReassessmentResponse(BaseModel):
  reassessment_id: str
  original_sample_id: str
  original_report_id: int | None = None
  retest_sample_id: str | None = None
  retest_report_id: int | None = None
  reason: str
  qc_codes: list[str] = Field(default_factory=list)
  status: str
  created_at: datetime | None = None
  completed_at: datetime | None = None


class ReassessmentAcceptRequest(BaseModel):
  sample: SampleInput | None = None
  override_fields: dict | None = None


class ReassessmentCompareResponse(BaseModel):
  reassessment_id: str
  status: str
  original_sample_id: str
  retest_sample_id: str | None = None
  original_result: str | None = None
  retest_result: Literal["positive", "negative", "inconclusive"]
  concordant: bool | None = None
  retest_report: DiagnosisReport
  comparison: dict = Field(default_factory=dict)


class ExpertFeedbackCreate(BaseModel):
  sample_id: str
  report_id: int | None = None
  model_result: str | None = None
  expert_result: Literal["positive", "negative", "inconclusive"]
  marker_labels: dict[str, str] | None = None
  note: str | None = None
  features: dict[str, float] | None = None


class ExpertFeedbackResponse(BaseModel):
  feedback_id: str
  sample_id: str
  report_id: int | None = None
  model_result: str
  expert_result: str
  agree_with_model: bool
  note: str | None = None
  used_for_training: bool = False
  expert_email: str | None = None
  created_at: datetime | None = None


class HitlExportResponse(BaseModel):
  path: str
  rows: int
  positives: int
  negatives: int


class HitlRetrainRequest(BaseModel):
  version: str = "hitl-v1"
  promote: bool = False
  export_path: str | None = None
  merge_with_path: str | None = None
