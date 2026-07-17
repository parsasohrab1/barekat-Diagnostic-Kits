"""Phase 3: multi-tenant, edge fleet, sync conflict, locked ONNX metadata."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.create_table(
    "tenants",
    sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
    sa.Column("tenant_id", sa.String(64), nullable=False),
    sa.Column("name", sa.String(256), nullable=False),
    sa.Column("status", sa.String(16), server_default="active"),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    sa.PrimaryKeyConstraint("id"),
  )
  op.create_index("ix_tenants_tenant_id", "tenants", ["tenant_id"], unique=True)

  op.create_table(
    "centers",
    sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
    sa.Column("center_id", sa.String(64), nullable=False),
    sa.Column("tenant_id", sa.String(64), nullable=False),
    sa.Column("name", sa.String(256), nullable=False),
    sa.Column("region", sa.String(128), nullable=True),
    sa.Column("status", sa.String(16), server_default="active"),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    sa.PrimaryKeyConstraint("id"),
  )
  op.create_index("ix_centers_center_id", "centers", ["center_id"], unique=True)
  op.create_index("ix_centers_tenant_id", "centers", ["tenant_id"])

  op.create_table(
    "edge_devices",
    sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
    sa.Column("device_id", sa.String(64), nullable=False),
    sa.Column("center_id", sa.String(64), nullable=False),
    sa.Column("tenant_id", sa.String(64), nullable=False),
    sa.Column("label", sa.String(128), nullable=True),
    sa.Column("device_token_hash", sa.String(128), nullable=True),
    sa.Column("model_version", sa.String(64), nullable=True),
    sa.Column("onnx_checksum", sa.String(64), nullable=True),
    sa.Column("status", sa.String(24), server_default="registered"),
    sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("last_latency_p95_ms", sa.Float(), nullable=True),
    sa.Column("sla_ok", sa.Boolean(), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    sa.PrimaryKeyConstraint("id"),
  )
  op.create_index("ix_edge_devices_device_id", "edge_devices", ["device_id"], unique=True)
  op.create_index("ix_edge_devices_center_id", "edge_devices", ["center_id"])
  op.create_index("ix_edge_devices_tenant_id", "edge_devices", ["tenant_id"])

  op.create_table(
    "fleet_model_releases",
    sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
    sa.Column("release_id", sa.String(64), nullable=False),
    sa.Column("model_version", sa.String(64), nullable=False),
    sa.Column("onnx_path", sa.String(512), nullable=False),
    sa.Column("checksum_sha256", sa.String(64), nullable=False),
    sa.Column("signature", sa.String(128), nullable=True),
    sa.Column("locked", sa.Boolean(), server_default=sa.text("true")),
    sa.Column("status", sa.String(24), server_default="staged"),
    sa.Column("min_latency_p95_ms", sa.Float(), nullable=True),
    sa.Column("target_tenant_id", sa.String(64), nullable=True),
    sa.Column("rollout_pct", sa.Float(), server_default="100.0"),
    sa.Column("manifest_json", sa.Text(), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint("id"),
  )
  op.create_index("ix_fleet_model_releases_release_id", "fleet_model_releases", ["release_id"], unique=True)
  op.create_index("ix_fleet_model_releases_model_version", "fleet_model_releases", ["model_version"])

  op.create_table(
    "sync_conflict_logs",
    sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
    sa.Column("conflict_id", sa.String(64), nullable=False),
    sa.Column("client_report_id", sa.String(64), nullable=False),
    sa.Column("sample_id", sa.String(32), nullable=False),
    sa.Column("device_id", sa.String(64), nullable=True),
    sa.Column("center_id", sa.String(64), nullable=True),
    sa.Column("resolution", sa.String(32), nullable=False),
    sa.Column("detail_json", sa.Text(), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    sa.PrimaryKeyConstraint("id"),
  )
  op.create_index("ix_sync_conflict_logs_conflict_id", "sync_conflict_logs", ["conflict_id"], unique=True)
  op.create_index("ix_sync_conflict_logs_client_report_id", "sync_conflict_logs", ["client_report_id"])
  op.create_index("ix_sync_conflict_logs_sample_id", "sync_conflict_logs", ["sample_id"])

  op.add_column("samples", sa.Column("tenant_id", sa.String(64), nullable=True))
  op.add_column("samples", sa.Column("center_id", sa.String(64), nullable=True))
  op.add_column("samples", sa.Column("device_id", sa.String(64), nullable=True))
  op.create_index("ix_samples_tenant_id", "samples", ["tenant_id"])
  op.create_index("ix_samples_center_id", "samples", ["center_id"])
  op.create_index("ix_samples_device_id", "samples", ["device_id"])

  op.add_column("diagnoses", sa.Column("client_report_id", sa.String(64), nullable=True))
  op.add_column("diagnoses", sa.Column("tenant_id", sa.String(64), nullable=True))
  op.add_column("diagnoses", sa.Column("center_id", sa.String(64), nullable=True))
  op.add_column("diagnoses", sa.Column("device_id", sa.String(64), nullable=True))
  op.create_index("ix_diagnoses_client_report_id", "diagnoses", ["client_report_id"], unique=True)
  op.create_index("ix_diagnoses_tenant_id", "diagnoses", ["tenant_id"])
  op.create_index("ix_diagnoses_center_id", "diagnoses", ["center_id"])
  op.create_index("ix_diagnoses_device_id", "diagnoses", ["device_id"])


def downgrade() -> None:
  op.drop_index("ix_diagnoses_device_id", table_name="diagnoses")
  op.drop_index("ix_diagnoses_center_id", table_name="diagnoses")
  op.drop_index("ix_diagnoses_tenant_id", table_name="diagnoses")
  op.drop_index("ix_diagnoses_client_report_id", table_name="diagnoses")
  op.drop_column("diagnoses", "device_id")
  op.drop_column("diagnoses", "center_id")
  op.drop_column("diagnoses", "tenant_id")
  op.drop_column("diagnoses", "client_report_id")

  op.drop_index("ix_samples_device_id", table_name="samples")
  op.drop_index("ix_samples_center_id", table_name="samples")
  op.drop_index("ix_samples_tenant_id", table_name="samples")
  op.drop_column("samples", "device_id")
  op.drop_column("samples", "center_id")
  op.drop_column("samples", "tenant_id")

  op.drop_table("sync_conflict_logs")
  op.drop_table("fleet_model_releases")
  op.drop_table("edge_devices")
  op.drop_table("centers")
  op.drop_table("tenants")
