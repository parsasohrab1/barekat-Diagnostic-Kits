"""Multi-center / multi-tenant service and aggregate report."""

from __future__ import annotations

from sqlalchemy.orm import Session

from barekat_diagnostics.models.fleet import Center, EdgeDevice, Tenant
from barekat_diagnostics.models.sample import Diagnosis, Sample
from barekat_diagnostics.schemas import (
  CenterAggregateReport,
  CenterCreate,
  CenterResponse,
  TenantAggregateReport,
  TenantCreate,
  TenantResponse,
)
from barekat_diagnostics.services.audit_trail import AuditTrailService


class TenantError(Exception):
  def __init__(self, message: str) -> None:
    self.message = message
    super().__init__(message)


class TenantService:
  def __init__(self, db: Session) -> None:
    self.db = db
    self.audit = AuditTrailService(db)

  def create_tenant(self, body: TenantCreate, **actor) -> Tenant:
    if self.db.query(Tenant).filter(Tenant.tenant_id == body.tenant_id).first():
      raise TenantError(f"Duplicate tenant: {body.tenant_id}")
    row = Tenant(tenant_id=body.tenant_id, name=body.name)
    self.db.add(row)
    self.db.commit()
    self.db.refresh(row)
    self.audit.log("tenant.created", resource_type="tenant", resource_id=body.tenant_id, **actor)
    return row

  def create_center(self, body: CenterCreate, **actor) -> Center:
    if not self.db.query(Tenant).filter(Tenant.tenant_id == body.tenant_id).first():
      raise TenantError(f"Tenant not found: {body.tenant_id}")
    if self.db.query(Center).filter(Center.center_id == body.center_id).first():
      raise TenantError(f"Duplicate center: {body.center_id}")
    row = Center(
      center_id=body.center_id,
      tenant_id=body.tenant_id,
      name=body.name,
      region=body.region,
    )
    self.db.add(row)
    self.db.commit()
    self.db.refresh(row)
    self.audit.log("center.created", resource_type="center", resource_id=body.center_id, **actor)
    return row

  def list_tenants(self) -> list[Tenant]:
    return self.db.query(Tenant).order_by(Tenant.created_at.desc()).all()

  def list_centers(self, tenant_id: str | None = None) -> list[Center]:
    q = self.db.query(Center)
    if tenant_id:
      q = q.filter(Center.tenant_id == tenant_id)
    return q.order_by(Center.created_at.desc()).all()

  def center_aggregate(self, center_id: str) -> CenterAggregateReport:
    center = self.db.query(Center).filter(Center.center_id == center_id).first()
    tenant_id = center.tenant_id if center else None

    samples = self.db.query(Sample).filter(Sample.center_id == center_id).count()
    diagnoses = self.db.query(Diagnosis).filter(Diagnosis.center_id == center_id).all()
    pos = sum(1 for d in diagnoses if d.result == "positive")
    neg = sum(1 for d in diagnoses if d.result == "negative")
    inc = sum(1 for d in diagnoses if d.result == "inconclusive")
    qc_fail = sum(1 for d in diagnoses if not d.qc_passed)
    pending = sum(1 for d in diagnoses if d.approval_status == "pending")

    devices = self.db.query(EdgeDevice).filter(EdgeDevice.center_id == center_id).all()
    online = sum(1 for d in devices if d.status in {"online", "updating"})

    return CenterAggregateReport(
      center_id=center_id,
      tenant_id=tenant_id,
      samples=samples,
      diagnoses=len(diagnoses),
      positive=pos,
      negative=neg,
      inconclusive=inc,
      qc_failures=qc_fail,
      pending_approvals=pending,
      devices_online=online,
      devices_total=len(devices),
    )

  def tenant_aggregate(self, tenant_id: str) -> TenantAggregateReport:
    centers = self.list_centers(tenant_id)
    details = [self.center_aggregate(c.center_id) for c in centers]
    samples = sum(d.samples for d in details)
    diagnoses = sum(d.diagnoses for d in details)
    positive = sum(d.positive for d in details)
    qc_fail = sum(d.qc_failures for d in details)
    return TenantAggregateReport(
      tenant_id=tenant_id,
      centers=len(centers),
      samples=samples,
      diagnoses=diagnoses,
      positive_rate=(positive / diagnoses) if diagnoses else 0.0,
      qc_failure_rate=(qc_fail / diagnoses) if diagnoses else 0.0,
      centers_detail=details,
    )

  def to_tenant_response(self, row: Tenant) -> TenantResponse:
    return TenantResponse(
      tenant_id=row.tenant_id,
      name=row.name,
      status=row.status,
      created_at=row.created_at,
    )

  def to_center_response(self, row: Center) -> CenterResponse:
    return CenterResponse(
      center_id=row.center_id,
      tenant_id=row.tenant_id,
      name=row.name,
      region=row.region,
      status=row.status,
      created_at=row.created_at,
    )
