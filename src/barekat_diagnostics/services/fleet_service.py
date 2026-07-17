"""مدیریت ناوگان مدل — انتشار امن ONNX و به‌روزرسانی دستگاه‌ها."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from barekat_diagnostics.core.config import get_settings
from barekat_diagnostics.edge.bundle import build_locked_edge_bundle
from barekat_diagnostics.models.fleet import EdgeDevice, FleetModelRelease
from barekat_diagnostics.schemas import (
  DeviceModelAck,
  EdgeDeviceCreate,
  EdgeDeviceResponse,
  FleetManifestResponse,
  FleetReleaseCreate,
  FleetReleaseResponse,
)
from barekat_diagnostics.services.audit_trail import AuditTrailService


class FleetError(Exception):
  def __init__(self, message: str) -> None:
    self.message = message
    super().__init__(message)


def _hash_token(token: str) -> str:
  return hashlib.sha256(token.encode("utf-8")).hexdigest()


class FleetService:
  def __init__(self, db: Session) -> None:
    self.db = db
    self.settings = get_settings()
    self.audit = AuditTrailService(db)

  def register_device(self, body: EdgeDeviceCreate, **actor) -> EdgeDevice:
    if self.db.query(EdgeDevice).filter(EdgeDevice.device_id == body.device_id).first():
      raise FleetError(f"دستگاه تکراری: {body.device_id}")
    row = EdgeDevice(
      device_id=body.device_id,
      center_id=body.center_id,
      tenant_id=body.tenant_id,
      label=body.label,
      device_token_hash=_hash_token(body.device_token) if body.device_token else None,
      status="registered",
    )
    self.db.add(row)
    self.db.commit()
    self.db.refresh(row)
    self.audit.log(
      "fleet.device_registered",
      resource_type="edge_device",
      resource_id=body.device_id,
      **actor,
    )
    return row

  def list_devices(self, tenant_id: str | None = None, center_id: str | None = None) -> list[EdgeDevice]:
    q = self.db.query(EdgeDevice)
    if tenant_id:
      q = q.filter(EdgeDevice.tenant_id == tenant_id)
    if center_id:
      q = q.filter(EdgeDevice.center_id == center_id)
    return q.order_by(EdgeDevice.created_at.desc()).all()

  def create_release(self, body: FleetReleaseCreate, **actor) -> FleetModelRelease:
    bundle = build_locked_edge_bundle(
      model_version=body.model_version,
      settings=self.settings,
      run_benchmark=True,
    )
    release_id = f"REL-{uuid.uuid4().hex[:10].upper()}"
    bench = bundle.get("benchmark") or {}
    row = FleetModelRelease(
      release_id=release_id,
      model_version=body.model_version,
      onnx_path=bundle["onnx_path"],
      checksum_sha256=bundle["checksum_sha256"],
      signature=bundle["signature"],
      locked=True,
      status="published" if body.publish else "staged",
      min_latency_p95_ms=bench.get("p95_ms"),
      target_tenant_id=body.target_tenant_id,
      rollout_pct=body.rollout_pct,
      manifest_json=json.dumps(bundle, ensure_ascii=False),
      published_at=datetime.now(timezone.utc) if body.publish else None,
    )
    self.db.add(row)
    self.db.commit()
    self.db.refresh(row)
    self.audit.log(
      "fleet.release_created",
      resource_type="fleet_release",
      resource_id=release_id,
      model_version=body.model_version,
      detail={"publish": body.publish, "sla_ok": bundle.get("sla_ok")},
      **actor,
    )
    return row

  def publish_release(self, release_id: str, **actor) -> FleetModelRelease:
    row = self.db.query(FleetModelRelease).filter(FleetModelRelease.release_id == release_id).first()
    if not row:
      raise FleetError("release یافت نشد")
    row.status = "published"
    row.published_at = datetime.now(timezone.utc)
    self.db.commit()
    self.db.refresh(row)
    self.audit.log(
      "fleet.release_published",
      resource_type="fleet_release",
      resource_id=release_id,
      model_version=row.model_version,
      **actor,
    )
    return row

  def get_manifest_for_device(self, device_id: str) -> FleetManifestResponse:
    device = self.db.query(EdgeDevice).filter(EdgeDevice.device_id == device_id).first()
    if not device:
      raise FleetError(f"دستگاه یافت نشد: {device_id}")

    q = (
      self.db.query(FleetModelRelease)
      .filter(FleetModelRelease.status == "published")
      .order_by(FleetModelRelease.published_at.desc())
    )
    release = None
    for cand in q.all():
      if cand.target_tenant_id and cand.target_tenant_id != device.tenant_id:
        continue
      # rollout sticky by device_id hash
      bucket = int(hashlib.md5(device_id.encode()).hexdigest(), 16) % 100
      if bucket < int(cand.rollout_pct):
        release = cand
        break
    if not release:
      raise FleetError("هیچ release منتشرشده‌ای برای این دستگاه نیست")

    device.last_seen_at = datetime.now(timezone.utc)
    device.status = "online"
    self.db.commit()

    return FleetManifestResponse(
      model_version=release.model_version,
      release_id=release.release_id,
      checksum_sha256=release.checksum_sha256,
      signature=release.signature,
      download_path=release.onnx_path,
      locked=release.locked,
      latency_sla_ms=self.settings.edge_latency_sla_ms,
    )

  def ack_model_update(self, body: DeviceModelAck, **actor) -> EdgeDevice:
    device = self.db.query(EdgeDevice).filter(EdgeDevice.device_id == body.device_id).first()
    if not device:
      raise FleetError("دستگاه یافت نشد")
    device.model_version = body.model_version
    device.onnx_checksum = body.checksum_sha256
    device.last_latency_p95_ms = body.latency_p95_ms
    device.sla_ok = body.sla_ok
    device.last_seen_at = datetime.now(timezone.utc)
    device.status = "online" if body.sla_ok is not False else "quarantined"
    self.db.commit()
    self.db.refresh(device)
    self.audit.log(
      "fleet.model_acked",
      resource_type="edge_device",
      resource_id=body.device_id,
      model_version=body.model_version,
      detail={"sla_ok": body.sla_ok, "p95": body.latency_p95_ms},
      **actor,
    )
    return device

  def apply_model_to_local(self, download_path: str, target_onnx: str | None = None) -> dict:
    """کپی امن مدل از release به مسیر ONNX دستگاه (برای CLI/agent)."""
    src = Path(download_path)
    if not src.exists():
      raise FleetError(f"فایل مدل یافت نشد: {src}")
    dest = Path(target_onnx or self.settings.onnx_model_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(src.read_bytes())
    # copy lockfile if present
    lock_src = src.parent / "model.lock.json"
    if lock_src.exists():
      (dest.parent / "model.lock.json").write_text(
        lock_src.read_text(encoding="utf-8"), encoding="utf-8"
      )
    meta_src = src.with_suffix(".onnx.json")
    if meta_src.exists():
      dest.with_suffix(".onnx.json").write_text(
        meta_src.read_text(encoding="utf-8"), encoding="utf-8"
      )
    return {"onnx_path": str(dest), "checksum": hashlib.sha256(dest.read_bytes()).hexdigest()[:32]}

  def to_device_response(self, row: EdgeDevice) -> EdgeDeviceResponse:
    return EdgeDeviceResponse(
      device_id=row.device_id,
      center_id=row.center_id,
      tenant_id=row.tenant_id,
      label=row.label,
      model_version=row.model_version,
      onnx_checksum=row.onnx_checksum,
      status=row.status,
      last_seen_at=row.last_seen_at,
      last_sync_at=row.last_sync_at,
      last_latency_p95_ms=row.last_latency_p95_ms,
      sla_ok=row.sla_ok,
      created_at=row.created_at,
    )

  def to_release_response(self, row: FleetModelRelease) -> FleetReleaseResponse:
    return FleetReleaseResponse(
      release_id=row.release_id,
      model_version=row.model_version,
      onnx_path=row.onnx_path,
      checksum_sha256=row.checksum_sha256,
      signature=row.signature,
      locked=row.locked,
      status=row.status,
      rollout_pct=row.rollout_pct,
      target_tenant_id=row.target_tenant_id,
      min_latency_p95_ms=row.min_latency_p95_ms,
      created_at=row.created_at,
      published_at=row.published_at,
    )
