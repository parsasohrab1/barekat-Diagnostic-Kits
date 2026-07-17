"""Phase 1 clinical-lab schema: users, audit, assay batches, approval fields."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.create_table(
    "users",
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("email", sa.String(255), nullable=False),
    sa.Column("hashed_password", sa.String(255), nullable=False),
    sa.Column("full_name", sa.String(255), nullable=False),
    sa.Column("role", sa.String(50), nullable=False, server_default="technician"),
    sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
  )
  op.create_index("ix_users_email", "users", ["email"], unique=True)

  op.create_table(
    "audit_logs",
    sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
    sa.Column("event_type", sa.String(64), nullable=False),
    sa.Column("actor_id", sa.String(36), nullable=True),
    sa.Column("actor_email", sa.String(255), nullable=True),
    sa.Column("actor_role", sa.String(50), nullable=True),
    sa.Column("resource_type", sa.String(64), nullable=True),
    sa.Column("resource_id", sa.String(128), nullable=True),
    sa.Column("model_version", sa.String(64), nullable=True),
    sa.Column("detail_json", sa.Text(), nullable=True),
    sa.Column("prev_hash", sa.String(64), nullable=False),
    sa.Column("entry_hash", sa.String(64), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.PrimaryKeyConstraint("id"),
  )
  op.create_index("ix_audit_logs_event_type", "audit_logs", ["event_type"])
  op.create_index("ix_audit_logs_actor_id", "audit_logs", ["actor_id"])
  op.create_index("ix_audit_logs_resource_id", "audit_logs", ["resource_id"])
  op.create_index("ix_audit_logs_entry_hash", "audit_logs", ["entry_hash"])
  op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])

  op.create_table(
    "assay_batches",
    sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
    sa.Column("batch_id", sa.String(64), nullable=False),
    sa.Column("lot_number", sa.String(64), nullable=False),
    sa.Column("kit_type", sa.String(32), server_default="qpcr"),
    sa.Column("label", sa.String(128), nullable=True),
    sa.Column("status", sa.String(24), server_default="open"),
    sa.Column("pos_control_ct_max", sa.Float(), server_default="32.0"),
    sa.Column("neg_control_ct_min", sa.Float(), server_default="38.0"),
    sa.Column("positive_control_sample_id", sa.String(32), nullable=True),
    sa.Column("negative_control_sample_id", sa.String(32), nullable=True),
    sa.Column("positive_control_ct", sa.Float(), nullable=True),
    sa.Column("negative_control_ct", sa.Float(), nullable=True),
    sa.Column("positive_control_passed", sa.Boolean(), server_default=sa.text("false")),
    sa.Column("negative_control_passed", sa.Boolean(), server_default=sa.text("false")),
    sa.Column("controls_validated", sa.Boolean(), server_default=sa.text("false")),
    sa.Column("validation_message", sa.Text(), nullable=True),
    sa.Column("created_by", sa.String(36), nullable=True),
    sa.Column("validated_by", sa.String(36), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint("id"),
  )
  op.create_index("ix_assay_batches_batch_id", "assay_batches", ["batch_id"], unique=True)
  op.create_index("ix_assay_batches_lot_number", "assay_batches", ["lot_number"])

  op.add_column("kit_calibrations", sa.Column("pos_control_ct_max", sa.Float(), nullable=True))
  op.add_column("kit_calibrations", sa.Column("neg_control_ct_min", sa.Float(), nullable=True))
  op.add_column(
    "kit_calibrations",
    sa.Column("require_controls", sa.Boolean(), server_default=sa.text("true")),
  )

  op.add_column("samples", sa.Column("batch_id", sa.String(64), nullable=True))
  op.add_column(
    "samples",
    sa.Column("sample_role", sa.String(32), server_default="patient"),
  )
  op.create_index("ix_samples_batch_id", "samples", ["batch_id"])

  op.add_column(
    "diagnoses",
    sa.Column("approval_status", sa.String(16), server_default="pending"),
  )
  op.add_column("diagnoses", sa.Column("approved_by", sa.String(36), nullable=True))
  op.add_column("diagnoses", sa.Column("approved_by_email", sa.String(255), nullable=True))
  op.add_column("diagnoses", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))
  op.add_column("diagnoses", sa.Column("approval_note", sa.Text(), nullable=True))


def downgrade() -> None:
  op.drop_column("diagnoses", "approval_note")
  op.drop_column("diagnoses", "approved_at")
  op.drop_column("diagnoses", "approved_by_email")
  op.drop_column("diagnoses", "approved_by")
  op.drop_column("diagnoses", "approval_status")

  op.drop_index("ix_samples_batch_id", table_name="samples")
  op.drop_column("samples", "sample_role")
  op.drop_column("samples", "batch_id")

  op.drop_column("kit_calibrations", "require_controls")
  op.drop_column("kit_calibrations", "neg_control_ct_min")
  op.drop_column("kit_calibrations", "pos_control_ct_max")

  op.drop_table("assay_batches")
  op.drop_table("audit_logs")
  op.drop_table("users")
