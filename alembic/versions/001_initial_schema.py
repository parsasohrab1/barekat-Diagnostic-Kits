"""Initial schema

Revision ID: 001
Revises:
Create Date: 2026-07-13
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.create_table(
    "samples",
    sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
    sa.Column("sample_id", sa.String(32), nullable=False),
    sa.Column("patient_id", sa.String(64), nullable=True),
    sa.Column("kit_type", sa.String(32), nullable=False),
    sa.Column("ct_value", sa.Float(), nullable=True),
    sa.Column("quality_score", sa.Float(), nullable=True),
    sa.Column("signal_to_noise", sa.Float(), nullable=True),
    sa.Column("amplification_efficiency", sa.Float(), nullable=True),
    sa.Column("calibration_error", sa.Boolean(), nullable=False),
    sa.Column("is_reliable", sa.Boolean(), nullable=False),
    sa.Column("raw_data_path", sa.String(512), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    sa.PrimaryKeyConstraint("id"),
  )
  op.create_index("ix_samples_sample_id", "samples", ["sample_id"], unique=True)
  op.create_index("ix_samples_patient_id", "samples", ["patient_id"])

  op.create_table(
    "diagnoses",
    sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
    sa.Column("sample_id", sa.String(32), nullable=False),
    sa.Column("result", sa.String(16), nullable=False),
    sa.Column("confidence", sa.Float(), nullable=False),
    sa.Column("model_version", sa.String(64), nullable=False),
    sa.Column("qc_passed", sa.Boolean(), nullable=False),
    sa.Column("qc_warnings", sa.Text(), nullable=True),
    sa.Column("features_json", sa.Text(), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    sa.PrimaryKeyConstraint("id"),
  )
  op.create_index("ix_diagnoses_sample_id", "diagnoses", ["sample_id"])


def downgrade() -> None:
  op.drop_table("diagnoses")
  op.drop_table("samples")
