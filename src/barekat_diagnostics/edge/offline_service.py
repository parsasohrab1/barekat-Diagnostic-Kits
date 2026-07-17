"""Offline diagnosis runner with locked ONNX for bedside / kiosk."""

from __future__ import annotations

from pathlib import Path

from barekat_diagnostics.core.config import Settings, get_settings
from barekat_diagnostics.edge.bundle import BundleError, load_and_verify_locked_model
from barekat_diagnostics.edge.offline_store import OfflineStore
from barekat_diagnostics.kits.registry import get_kit_adapter
from barekat_diagnostics.ml.classifier import DiagnosticPredictor
from barekat_diagnostics.ml.onnx_export import EdgeOnnxPredictor
from barekat_diagnostics.pipeline.report import build_diagnosis_report, sample_to_raw_data
from barekat_diagnostics.schemas import DiagnosisReport, SampleInput


class OfflineDiagnosisService:
  """Analyze samples locally without API — for bedside / no-network labs."""

  def __init__(self, settings: Settings | None = None):
    self.settings = settings or get_settings()
    self.store = OfflineStore(settings=self.settings)
    self.store.set_device_context(
      device_id=self.settings.edge_device_id or None,
      center_id=self.settings.edge_center_id or None,
      tenant_id=self.settings.edge_tenant_id or None,
    )
    self._onnx: EdgeOnnxPredictor | None = None
    self._sklearn = DiagnosticPredictor(settings=self.settings)
    self._bundle_meta: dict | None = None
    self.last_latency_ms: float | None = None

  def _get_onnx(self) -> EdgeOnnxPredictor | None:
    if self._onnx is not None:
      return self._onnx
    onnx_path = Path(self.settings.onnx_model_path)
    if not onnx_path.exists():
      return None
    try:
      self._bundle_meta = load_and_verify_locked_model(onnx_path, settings=self.settings)
      self._onnx = EdgeOnnxPredictor(onnx_path, settings=self.settings)
      # warm-up for weak CPU
      if self.settings.edge_warmup_iterations > 0 and self._onnx.feature_columns:
        warm = {c: 0.5 for c in self._onnx.feature_columns}
        for _ in range(self.settings.edge_warmup_iterations):
          self._onnx.predict(warm)
      return self._onnx
    except ImportError:
      return None
    except BundleError:
      if self.settings.edge_require_locked_model:
        raise
      return None

  def analyze(self, sample: SampleInput) -> DiagnosisReport:
    # enrich multi-tenant fields on sample if present in settings
    if not sample.center_id and self.settings.edge_center_id:
      sample.center_id = self.settings.edge_center_id
    if not sample.tenant_id and self.settings.edge_tenant_id:
      sample.tenant_id = self.settings.edge_tenant_id
    if not sample.device_id and self.settings.edge_device_id:
      sample.device_id = self.settings.edge_device_id

    self.store.enqueue_sample(sample)
    adapter = get_kit_adapter(sample.kit_type)
    raw_data = sample_to_raw_data(sample)
    features = adapter.extract_features(raw_data)
    qc = adapter.run_qc(raw_data, features)

    if not qc.is_reliable:
      report = build_diagnosis_report(
        sample=sample, result="inconclusive", confidence=0.0, qc=qc,
      )
      self.store.save_diagnosis(report)
      return report

    latency_ms = None
    onnx = self._get_onnx()
    if onnx and self.settings.inference_backend == "onnx":
      result, confidence, version, latency_ms = onnx.predict(features)
      self.last_latency_ms = latency_ms
      if (
        self.settings.edge_enforce_latency_sla
        and latency_ms > self.settings.edge_latency_sla_ms
      ):
        # still return result but flag via QC-like recommendation path
        pass
    else:
      try:
        result, confidence, version = self._sklearn.predict(features, sample.sample_id)
      except FileNotFoundError:
        result, confidence, version = self._sklearn.predict_rule_based(features)

    report = build_diagnosis_report(
      sample=sample,
      result=result,
      confidence=confidence,
      qc=qc,
      model_version=version,
    )
    # attach latency into explanation-less extension via clinical note not available —
    # store as model_version suffix if needed; schemas may not have latency field
    self.store.save_diagnosis(report)
    return report

  def pending_sync_count(self) -> int:
    return self.store.pending_sync_count()
