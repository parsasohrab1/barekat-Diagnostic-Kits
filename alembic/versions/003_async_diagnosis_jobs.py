"""Add diagnosis_jobs table for async analysis."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.create_table(
    "diagnosis_jobs",
    sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
    sa.Column("job_id", sa.String(36), nullable=False),
    sa.Column("sample_id", sa.String(32), nullable=False),
    sa.Column("status", sa.String(16), nullable=False),
    sa.Column("progress", sa.Float(), nullable=False),
    sa.Column("celery_task_id", sa.String(64), nullable=True),
    sa.Column("report_json", sa.Text(), nullable=True),
    sa.Column("error_message", sa.Text(), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint("id"),
  )
  op.create_index("ix_diagnosis_jobs_job_id", "diagnosis_jobs", ["job_id"], unique=True)
  op.create_index("ix_diagnosis_jobs_sample_id", "diagnosis_jobs", ["sample_id"])


def downgrade() -> None:
  op.drop_table("diagnosis_jobs")
