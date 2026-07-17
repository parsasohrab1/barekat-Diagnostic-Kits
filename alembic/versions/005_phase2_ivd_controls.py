"""Phase 2 IVD: LIS, validation, change control, drift, role remap."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  # نقش‌ها: technician→operator، pathologist→supervisor
  op.execute("UPDATE users SET role = 'operator' WHERE role = 'technician'")
  op.execute("UPDATE users SET role = 'supervisor' WHERE role = 'pathologist'")

  op.create_table(
    "lab_orders",
    sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
    sa.Column("order_id", sa.String(64), nullable=False),
    sa.Column("patient_id", sa.String(64), nullable=False),
    sa.Column("sample_id", sa.String(32), nullable=True),
    sa.Column("kit_type", sa.String(32), server_default="qpcr"),
    sa.Column("status", sa.String(32), server_default="received"),
    sa.Column("fhir_json", sa.Text(), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint("id"),
  )
  op.create_index("ix_lab_orders_order_id", "lab_orders", ["order_id"], unique=True)
  op.create_index("ix_lab_orders_patient_id", "lab_orders", ["patient_id"])
  op.create_index("ix_lab_orders_sample_id", "lab_orders", ["sample_id"])

  op.create_table(
    "fhir_exports",
    sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
    sa.Column("sample_id", sa.String(32), nullable=False),
    sa.Column("report_id", sa.Integer(), nullable=True),
    sa.Column("patient_id", sa.String(64), nullable=True),
    sa.Column("order_id", sa.String(64), nullable=True),
    sa.Column("fhir_json", sa.Text(), nullable=False),
    sa.Column("destination", sa.String(256), nullable=True),
    sa.Column("status", sa.String(32), server_default="exported"),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    sa.PrimaryKeyConstraint("id"),
  )
  op.create_index("ix_fhir_exports_sample_id", "fhir_exports", ["sample_id"])

  op.create_table(
    "clinical_validation_protocols",
    sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
    sa.Column("protocol_id", sa.String(64), nullable=False),
    sa.Column("model_version", sa.String(64), nullable=False),
    sa.Column("build_series", sa.String(64), nullable=False),
    sa.Column("batch_id", sa.String(64), nullable=True),
    sa.Column("lot_number", sa.String(64), nullable=True),
    sa.Column("data_path", sa.String(512), nullable=False),
    sa.Column("status", sa.String(24), server_default="draft"),
    sa.Column("min_sensitivity", sa.Float(), server_default="0.9"),
    sa.Column("min_specificity", sa.Float(), server_default="0.9"),
    sa.Column("min_roc_auc", sa.Float(), server_default="0.85"),
    sa.Column("min_samples", sa.Integer(), server_default="30"),
    sa.Column("sample_count", sa.Integer(), nullable=True),
    sa.Column("sensitivity", sa.Float(), nullable=True),
    sa.Column("specificity", sa.Float(), nullable=True),
    sa.Column("roc_auc", sa.Float(), nullable=True),
    sa.Column("passed", sa.Boolean(), nullable=True),
    sa.Column("result_json", sa.Text(), nullable=True),
    sa.Column("failure_reason", sa.Text(), nullable=True),
    sa.Column("created_by", sa.String(36), nullable=True),
    sa.Column("signed_by", sa.String(36), nullable=True),
    sa.Column("signed_by_email", sa.String(255), nullable=True),
    sa.Column("signed_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    sa.PrimaryKeyConstraint("id"),
  )
  op.create_index(
    "ix_clinical_validation_protocols_protocol_id",
    "clinical_validation_protocols",
    ["protocol_id"],
    unique=True,
  )
  op.create_index(
    "ix_clinical_validation_protocols_model_version",
    "clinical_validation_protocols",
    ["model_version"],
  )

  op.create_table(
    "change_requests",
    sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
    sa.Column("change_id", sa.String(64), nullable=False),
    sa.Column("change_type", sa.String(32), nullable=False),
    sa.Column("title", sa.String(256), nullable=False),
    sa.Column("description", sa.Text(), nullable=True),
    sa.Column("risk_level", sa.String(16), server_default="medium"),
    sa.Column("mitigation", sa.Text(), nullable=True),
    sa.Column("target_version", sa.String(64), nullable=True),
    sa.Column("previous_version", sa.String(64), nullable=True),
    sa.Column("protocol_id", sa.String(64), nullable=True),
    sa.Column("status", sa.String(24), server_default="draft"),
    sa.Column("detail_json", sa.Text(), nullable=True),
    sa.Column("requested_by", sa.String(36), nullable=True),
    sa.Column("requested_by_email", sa.String(255), nullable=True),
    sa.Column("approved_by", sa.String(36), nullable=True),
    sa.Column("approved_by_email", sa.String(255), nullable=True),
    sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    sa.PrimaryKeyConstraint("id"),
  )
  op.create_index("ix_change_requests_change_id", "change_requests", ["change_id"], unique=True)

  op.create_table(
    "drift_alerts",
    sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
    sa.Column("alert_id", sa.String(64), nullable=False),
    sa.Column("alert_type", sa.String(32), nullable=False),
    sa.Column("severity", sa.String(16), server_default="warning"),
    sa.Column("model_version", sa.String(64), nullable=True),
    sa.Column("metric_name", sa.String(64), nullable=False),
    sa.Column("baseline_value", sa.Float(), nullable=True),
    sa.Column("observed_value", sa.Float(), nullable=True),
    sa.Column("threshold", sa.Float(), nullable=True),
    sa.Column("message", sa.Text(), nullable=False),
    sa.Column("status", sa.String(16), server_default="open"),
    sa.Column("detail_json", sa.Text(), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    sa.Column("acknowledged_by", sa.String(36), nullable=True),
    sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint("id"),
  )
  op.create_index("ix_drift_alerts_alert_id", "drift_alerts", ["alert_id"], unique=True)

  op.create_table(
    "model_baselines",
    sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
    sa.Column("model_version", sa.String(64), nullable=False),
    sa.Column("feature_stats_json", sa.Text(), nullable=False),
    sa.Column("positive_rate", sa.Float(), nullable=True),
    sa.Column("mean_confidence", sa.Float(), nullable=True),
    sa.Column("mean_quality_score", sa.Float(), nullable=True),
    sa.Column("mean_snr", sa.Float(), nullable=True),
    sa.Column("sample_count", sa.Integer(), server_default="0"),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    sa.PrimaryKeyConstraint("id"),
  )
  op.create_index(
    "ix_model_baselines_model_version",
    "model_baselines",
    ["model_version"],
    unique=True,
  )


def downgrade() -> None:
  op.drop_table("model_baselines")
  op.drop_table("drift_alerts")
  op.drop_table("change_requests")
  op.drop_table("clinical_validation_protocols")
  op.drop_table("fhir_exports")
  op.drop_table("lab_orders")
  op.execute("UPDATE users SET role = 'technician' WHERE role = 'operator'")
  op.execute("UPDATE users SET role = 'pathologist' WHERE role = 'supervisor'")
