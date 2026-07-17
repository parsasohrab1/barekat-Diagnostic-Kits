"""سرویس مدیریت نمونه."""

import json

from sqlalchemy.orm import Session

from barekat_diagnostics.core.storage import StorageService, get_storage
from barekat_diagnostics.kits.registry import get_kit_adapter
from barekat_diagnostics.models.sample import KitCalibration, Sample
from barekat_diagnostics.pipeline.report import sample_to_raw_data
from barekat_diagnostics.schemas import SampleInput, SampleResponse


class SampleService:
  def __init__(self, db: Session, storage: StorageService | None = None) -> None:
    self.db = db
    self.storage = storage or get_storage()

  def get_calibration(self, lot_number: str | None) -> dict | None:
    if not lot_number:
      return None
    cal = self.db.query(KitCalibration).filter(KitCalibration.lot_number == lot_number).first()
    if not cal:
      return None
    result: dict = {
      "lot_number": cal.lot_number,
      "kit_type": cal.kit_type,
      "cutoff_value": cal.cutoff_value,
    }
    if cal.standard_curve_json:
      result["standard_curve"] = json.loads(cal.standard_curve_json)
    return result

  def create_sample(self, sample_input: SampleInput, curve_data: list[float] | None = None) -> Sample:
    existing = self.db.query(Sample).filter(Sample.sample_id == sample_input.sample_id).first()
    if existing:
      return existing

    adapter = get_kit_adapter(sample_input.kit_type)
    raw_data = sample_to_raw_data(sample_input)
    if curve_data:
      raw_data["curve_data"] = curve_data
      sample_input.curve_data = curve_data
    features = adapter.extract_features(raw_data)

    curve_key = None
    raw_path = None
    if curve_data:
      curve_key = self.storage.curve_key(sample_input.sample_id)
      raw_path = self.storage.upload_json(curve_data, curve_key)

    record = Sample(
      sample_id=sample_input.sample_id,
      patient_id=sample_input.patient_id,
      kit_type=sample_input.kit_type,
      status="pending",
      calibration_lot=sample_input.calibration_lot,
      batch_id=sample_input.batch_id,
      sample_role=sample_input.sample_role,
      tenant_id=sample_input.tenant_id,
      center_id=sample_input.center_id,
      device_id=sample_input.device_id,
      ct_value=features.get("ct_value") if features.get("ct_value") is not None else sample_input.ct_value,
      od_ratio=features.get("od_ratio"),
      peak_intensity=features.get("peak_intensity"),
      quality_score=sample_input.quality_score,
      signal_to_noise=sample_input.signal_to_noise,
      amplification_efficiency=sample_input.amplification_efficiency,
      calibration_error=sample_input.calibration_error,
      raw_data_path=raw_path,
      curve_object_key=curve_key,
      features_json=json.dumps(features, ensure_ascii=False),
    )
    self.db.add(record)
    self.db.commit()
    self.db.refresh(record)
    return record

  def load_curve(self, sample: Sample) -> list[float] | None:
    if not sample.curve_object_key:
      return None
    try:
      data = self.storage.download_json(sample.curve_object_key)
      return data if isinstance(data, list) else None
    except Exception:
      return None

  def sample_to_input(self, sample: Sample) -> SampleInput:
    features = json.loads(sample.features_json) if sample.features_json else {}
    curve = self.load_curve(sample)
    return SampleInput(
      sample_id=sample.sample_id,
      patient_id=sample.patient_id,
      kit_type=sample.kit_type,
      calibration_lot=sample.calibration_lot,
      batch_id=sample.batch_id,
      sample_role=sample.sample_role or "patient",  # type: ignore[arg-type]
      tenant_id=sample.tenant_id,
      center_id=sample.center_id,
      device_id=sample.device_id,
      ct_value=sample.ct_value,
      od_ratio=sample.od_ratio,
      peak_intensity=sample.peak_intensity,
      quality_score=sample.quality_score,
      signal_to_noise=sample.signal_to_noise,
      amplification_efficiency=sample.amplification_efficiency,
      calibration_error=sample.calibration_error,
      curve_data=curve,
      features=features,
    )

  def to_response(self, sample: Sample) -> SampleResponse:
    return SampleResponse(
      sample_id=sample.sample_id,
      patient_id=sample.patient_id,
      kit_type=sample.kit_type,
      status=sample.status,
      calibration_lot=sample.calibration_lot,
      batch_id=sample.batch_id,
      sample_role=sample.sample_role or "patient",
      raw_data_path=sample.raw_data_path,
      curve_object_key=sample.curve_object_key,
      created_at=sample.created_at,
    )

  def list_samples(self, limit: int = 50) -> list[SampleResponse]:
    rows = self.db.query(Sample).order_by(Sample.created_at.desc()).limit(limit).all()
    return [self.to_response(s) for s in rows]

  def get_sample(self, sample_id: str) -> Sample | None:
    return self.db.query(Sample).filter(Sample.sample_id == sample_id).first()

  def mark_status(self, sample_id: str, status: str) -> None:
    sample = self.get_sample(sample_id)
    if sample:
      sample.status = status
      self.db.commit()
