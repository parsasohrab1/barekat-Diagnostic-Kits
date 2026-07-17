"""Migration: kit calibrations, batch jobs, expanded sample/diagnosis columns."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.create_table(
    "kit_calibrations",
    sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
    sa.Column("lot_number", sa.String(64), nullable=False),
    sa.Column("kit_type", sa.String(32), nullable=False),
    sa.Column("expiry_date", sa.Date(), nullable=True),
    sa.Column("cutoff_value", sa.Float(), nullable=True),
    sa.Column("standard_curve_path", sa.String(512), nullable=True),
    sa.Column("standard_curve_json", sa.Text(), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    sa.PrimaryKeyConstraint("id"),
  )
  op.create_index("ix_kit_calibrations_lot_number", "kit_calibrations", ["lot_number"], unique=True)

  op.create_table(
    "batch_jobs",
    sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
    sa.Column("job_id", sa.String(36), nullable=False),
    sa.Column("status", sa.String(16), nullable=False),
    sa.Column("total_samples", sa.Integer(), nullable=False),
    sa.Column("completed_samples", sa.Integer(), nullable=False),
    sa.Column("results_json", sa.Text(), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint("id"),
  )
  op.create_index("ix_batch_jobs_job_id", "batch_jobs", ["job_id"], unique=True)

  op.add_column("samples", sa.Column("status", sa.String(16), server_default="pending"))
  op.add_column("samples", sa.Column("calibration_lot", sa.String(64), nullable=True))
  op.add_column("samples", sa.Column("od_ratio", sa.Float(), nullable=True))
  op.add_column("samples", sa.Column("peak_intensity", sa.Float(), nullable=True))
  op.add_column("samples", sa.Column("curve_object_key", sa.String(512), nullable=True))
  op.add_column("samples", sa.Column("features_json", sa.Text(), nullable=True))

  op.add_column("diagnoses", sa.Column("kit_type", sa.String(32), server_default="qpcr"))
  op.add_column("diagnoses", sa.Column("recommendation", sa.String(16), server_default="report"))
  op.add_column("diagnoses", sa.Column("report_json", sa.Text(), nullable=True))
  op.add_column("diagnoses", sa.Column("pdf_path", sa.String(512), nullable=True))


def downgrade() -> None:
  op.drop_column("diagnoses", "pdf_path")
  op.drop_column("diagnoses", "report_json")
  op.drop_column("diagnoses", "recommendation")
  op.drop_column("diagnoses", "kit_type")

  op.drop_column("samples", "features_json")
  op.drop_column("samples", "curve_object_key")
  op.drop_column("samples", "peak_intensity")
  op.drop_column("samples", "od_ratio")
  op.drop_column("samples", "calibration_lot")
  op.drop_column("samples", "status")

  op.drop_table("batch_jobs")
  op.drop_table("kit_calibrations")
