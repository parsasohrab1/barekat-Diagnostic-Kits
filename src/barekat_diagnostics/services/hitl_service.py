"""یادگیری نظارت‌شده با تأیید متخصص (human-in-the-loop)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pandas as pd
from sqlalchemy.orm import Session

from barekat_diagnostics.core.config import get_settings
from barekat_diagnostics.models.clinical import ExpertFeedback
from barekat_diagnostics.models.sample import Diagnosis
from barekat_diagnostics.schemas import (
  ExpertFeedbackCreate,
  ExpertFeedbackResponse,
  HitlExportResponse,
  HitlRetrainRequest,
  TrainingMetrics,
)
from barekat_diagnostics.services.audit_trail import AuditTrailService


class HitlError(Exception):
  def __init__(self, message: str) -> None:
    self.message = message
    super().__init__(message)


class HitlService:
  def __init__(self, db: Session) -> None:
    self.db = db
    self.audit = AuditTrailService(db)
    self.settings = get_settings()

  def submit_feedback(self, body: ExpertFeedbackCreate, **actor) -> ExpertFeedback:
    diagnosis = None
    if body.report_id:
      diagnosis = self.db.query(Diagnosis).filter(Diagnosis.id == body.report_id).first()
    if not diagnosis:
      diagnosis = (
        self.db.query(Diagnosis)
        .filter(Diagnosis.sample_id == body.sample_id)
        .order_by(Diagnosis.created_at.desc())
        .first()
      )
    if not diagnosis:
      raise HitlError("گزارش تشخیص برای بازخورد یافت نشد")

    model_result = body.model_result or diagnosis.result
    agree = model_result == body.expert_result
    features = body.features
    if not features and diagnosis.features_json:
      try:
        features = json.loads(diagnosis.features_json).get("features") or json.loads(
          diagnosis.features_json
        )
      except json.JSONDecodeError:
        features = None

    # اگر features از sample dump باشد، فقط اعداد را نگه دار
    if isinstance(features, dict):
      features = {k: float(v) for k, v in features.items() if isinstance(v, (int, float))}

    row = ExpertFeedback(
      feedback_id=f"FB-{uuid.uuid4().hex[:10].upper()}",
      sample_id=body.sample_id,
      report_id=diagnosis.id,
      model_result=model_result,
      expert_result=body.expert_result,
      expert_labels_json=json.dumps(body.marker_labels or {}, ensure_ascii=False)
      if body.marker_labels
      else None,
      agree_with_model=agree,
      note=body.note,
      features_json=json.dumps(features, ensure_ascii=False) if features else diagnosis.features_json,
      kit_type=diagnosis.kit_type,
      expert_id=actor.get("actor_id"),
      expert_email=actor.get("actor_email"),
    )
    self.db.add(row)

    # به‌روزرسانی وضعیت تأیید گزارش با برچسب متخصص
    diagnosis.approval_status = "expert_labeled"
    diagnosis.approval_note = (
      f"expert_result={body.expert_result}; model={model_result}; note={body.note or ''}"
    )
    diagnosis.approved_by = actor.get("actor_id")
    diagnosis.approved_by_email = actor.get("actor_email")
    from datetime import datetime, timezone

    diagnosis.approved_at = datetime.now(timezone.utc)
    self.db.commit()
    self.db.refresh(row)

    self.audit.log(
      "hitl.feedback",
      resource_type="expert_feedback",
      resource_id=row.feedback_id,
      detail={
        "sample_id": body.sample_id,
        "model_result": model_result,
        "expert_result": body.expert_result,
        "agree": agree,
      },
      **{k: v for k, v in actor.items() if k.startswith("actor_")},
    )
    return row

  def list_feedback(
    self,
    *,
    unused_only: bool = False,
    limit: int = 100,
  ) -> list[ExpertFeedback]:
    q = self.db.query(ExpertFeedback).order_by(ExpertFeedback.created_at.desc())
    if unused_only:
      q = q.filter(ExpertFeedback.used_for_training.is_(False))
    return q.limit(limit).all()

  def export_training_csv(self, path: str | Path | None = None) -> HitlExportResponse:
    rows = self.list_feedback(unused_only=False, limit=10_000)
    if not rows:
      raise HitlError("هیچ بازخورد متخصصی برای export نیست")

    records = []
    for r in rows:
      if r.expert_result not in {"positive", "negative"}:
        continue  # فقط binary برای مدل فعلی
      feats: dict = {}
      if r.features_json:
        try:
          raw = json.loads(r.features_json)
          if isinstance(raw, dict):
            # ممکن است sample dump کامل باشد
            if "features" in raw and isinstance(raw["features"], dict):
              feats = raw["features"]
            else:
              feats = {
                k: v
                for k, v in raw.items()
                if isinstance(v, (int, float)) and k
                not in {"calibration_error"}
              }
              # map common fields
              if "ct_value" in raw and isinstance(raw["ct_value"], (int, float)):
                feats["Ct_Value"] = float(raw["ct_value"])
              if "signal_to_noise" in raw:
                feats["Signal_to_Noise"] = float(raw["signal_to_noise"])
              if "amplification_efficiency" in raw:
                feats["Amplification_Efficiency"] = float(raw["amplification_efficiency"])
              if "quality_score" in raw:
                feats["Quality_Score"] = float(raw["quality_score"])
        except json.JSONDecodeError:
          continue

      # اطمینان از Feature_1..12 برای سازگاری با train
      for i in range(1, 13):
        key = f"Feature_{i}"
        if key not in feats:
          # از ct مشتق‌شده یا مقدار پیش‌فرض
          ct = feats.get("Ct_Value", feats.get("ct_value", 30.0))
          feats[key] = max(0.0, min(1.5, (40 - float(ct)) / 30 + (0.05 * i)))

      record = {
        **{k: feats.get(k, 0.0) for k in [f"Feature_{i}" for i in range(1, 13)]},
        "Ct_Value": feats.get("Ct_Value", feats.get("ct_value", 30.0)),
        "Signal_to_Noise": feats.get("Signal_to_Noise", feats.get("signal_to_noise", 2.0)),
        "Amplification_Efficiency": feats.get(
          "Amplification_Efficiency", feats.get("amplification_efficiency", 0.9)
        ),
        "Quality_Score": feats.get("Quality_Score", feats.get("quality_score", 0.8)),
        "True_Status": 1 if r.expert_result == "positive" else 0,
        "Lab_Device": "HITL",
        "Kit_Lot": "HITL",
        "Sample_ID": r.sample_id,
        "Feedback_ID": r.feedback_id,
      }
      records.append(record)

    if not records:
      raise HitlError("بازخورد قابل‌آموزش (positive/negative) یافت نشد")

    out = Path(path or Path(self.settings.model_path) / "hitl_training.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(records)
    df.to_csv(out, index=False)

    return HitlExportResponse(
      path=str(out),
      rows=len(df),
      positives=int(df["True_Status"].sum()),
      negatives=int((df["True_Status"] == 0).sum()),
    )

  def retrain_from_feedback(self, body: HitlRetrainRequest, **actor) -> TrainingMetrics:
    export = self.export_training_csv(body.export_path)
    from barekat_diagnostics.ml.classifier import train_classifier

    df = pd.read_csv(export.path)
    # اختیاری: ترکیب با synthetic
    if body.merge_with_path:
      base = Path(body.merge_with_path)
      if base.exists():
        base_df = pd.read_csv(base)
        df = pd.concat([base_df, df], ignore_index=True)

    try:
      _, metrics = train_classifier(
        df,
        version=body.version,
        promote=body.promote,
      )
    except RuntimeError as exc:
      raise HitlError(str(exc)) from exc

    # علامت‌گذاری feedbackهای استفاده‌شده
    unused = self.list_feedback(unused_only=True, limit=10_000)
    for r in unused:
      if r.expert_result in {"positive", "negative"}:
        r.used_for_training = True
    self.db.commit()

    self.audit.log(
      "hitl.retrained",
      resource_type="model",
      resource_id=body.version,
      model_version=body.version,
      detail={"rows": export.rows, "promoted": metrics.promoted},
      **{k: v for k, v in actor.items() if k.startswith("actor_")},
    )
    return metrics

  def to_response(self, row: ExpertFeedback) -> ExpertFeedbackResponse:
    return ExpertFeedbackResponse(
      feedback_id=row.feedback_id,
      sample_id=row.sample_id,
      report_id=row.report_id,
      model_result=row.model_result,
      expert_result=row.expert_result,
      agree_with_model=row.agree_with_model,
      note=row.note,
      used_for_training=row.used_for_training,
      expert_email=row.expert_email,
      created_at=row.created_at,
    )
