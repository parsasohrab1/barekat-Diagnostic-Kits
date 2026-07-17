"""Phase 4: multi-disease panels, clinical cases, reassessment, HITL."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.create_table(
    "marker_panels",
    sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
    sa.Column("panel_id", sa.String(64), nullable=False),
    sa.Column("name", sa.String(256), nullable=False),
    sa.Column("description", sa.Text(), nullable=True),
    sa.Column("markers_json", sa.Text(), nullable=False),
    sa.Column("status", sa.String(16), server_default="active"),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    sa.PrimaryKeyConstraint("id"),
  )
  op.create_index("ix_marker_panels_panel_id", "marker_panels", ["panel_id"], unique=True)

  op.create_table(
    "clinical_cases",
    sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
    sa.Column("case_id", sa.String(64), nullable=False),
    sa.Column("patient_id", sa.String(64), nullable=True),
    sa.Column("panel_id", sa.String(64), nullable=True),
    sa.Column("status", sa.String(24), server_default="open"),
    sa.Column("consensus_result", sa.String(32), nullable=True),
    sa.Column("consensus_confidence", sa.Float(), nullable=True),
    sa.Column("fusion_policy", sa.String(32), server_default="concordance"),
    sa.Column("summary_json", sa.Text(), nullable=True),
    sa.Column("clinical_narrative", sa.Text(), nullable=True),
    sa.Column("created_by", sa.String(36), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint("id"),
  )
  op.create_index("ix_clinical_cases_case_id", "clinical_cases", ["case_id"], unique=True)
  op.create_index("ix_clinical_cases_patient_id", "clinical_cases", ["patient_id"])

  op.create_table(
    "case_assays",
    sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
    sa.Column("case_id", sa.String(64), nullable=False),
    sa.Column("sample_id", sa.String(32), nullable=False),
    sa.Column("kit_type", sa.String(32), nullable=False),
    sa.Column("marker_id", sa.String(64), nullable=True),
    sa.Column("report_id", sa.Integer(), nullable=True),
    sa.Column("result", sa.String(32), nullable=True),
    sa.Column("confidence", sa.Float(), nullable=True),
    sa.Column("role", sa.String(24), server_default="primary"),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    sa.PrimaryKeyConstraint("id"),
  )
  op.create_index("ix_case_assays_case_id", "case_assays", ["case_id"])
  op.create_index("ix_case_assays_sample_id", "case_assays", ["sample_id"])

  op.create_table(
    "panel_marker_results",
    sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
    sa.Column("panel_run_id", sa.String(64), nullable=False),
    sa.Column("sample_id", sa.String(32), nullable=False),
    sa.Column("marker_id", sa.String(64), nullable=False),
    sa.Column("marker_name", sa.String(128), nullable=False),
    sa.Column("disease_code", sa.String(64), nullable=True),
    sa.Column("kit_type", sa.String(32), server_default="qpcr"),
    sa.Column("result", sa.String(32), nullable=False),
    sa.Column("value", sa.Float(), nullable=True),
    sa.Column("cutoff", sa.Float(), nullable=True),
    sa.Column("unit", sa.String(32), server_default=""),
    sa.Column("confidence", sa.Float(), server_default="0"),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    sa.PrimaryKeyConstraint("id"),
  )
  op.create_index("ix_panel_marker_results_panel_run_id", "panel_marker_results", ["panel_run_id"])
  op.create_index("ix_panel_marker_results_sample_id", "panel_marker_results", ["sample_id"])
  op.create_index("ix_panel_marker_results_marker_id", "panel_marker_results", ["marker_id"])

  op.create_table(
    "reassessment_requests",
    sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
    sa.Column("reassessment_id", sa.String(64), nullable=False),
    sa.Column("original_sample_id", sa.String(32), nullable=False),
    sa.Column("original_report_id", sa.Integer(), nullable=True),
    sa.Column("retest_sample_id", sa.String(32), nullable=True),
    sa.Column("retest_report_id", sa.Integer(), nullable=True),
    sa.Column("reason", sa.Text(), nullable=False),
    sa.Column("qc_codes", sa.Text(), nullable=True),
    sa.Column("status", sa.String(24), server_default="suggested"),
    sa.Column("comparison_json", sa.Text(), nullable=True),
    sa.Column("created_by", sa.String(36), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint("id"),
  )
  op.create_index(
    "ix_reassessment_requests_reassessment_id",
    "reassessment_requests",
    ["reassessment_id"],
    unique=True,
  )
  op.create_index(
    "ix_reassessment_requests_original_sample_id",
    "reassessment_requests",
    ["original_sample_id"],
  )

  op.create_table(
    "expert_feedback",
    sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
    sa.Column("feedback_id", sa.String(64), nullable=False),
    sa.Column("sample_id", sa.String(32), nullable=False),
    sa.Column("report_id", sa.Integer(), nullable=True),
    sa.Column("model_result", sa.String(32), nullable=False),
    sa.Column("expert_result", sa.String(32), nullable=False),
    sa.Column("expert_labels_json", sa.Text(), nullable=True),
    sa.Column("agree_with_model", sa.Boolean(), server_default=sa.false()),
    sa.Column("note", sa.Text(), nullable=True),
    sa.Column("features_json", sa.Text(), nullable=True),
    sa.Column("kit_type", sa.String(32), server_default="qpcr"),
    sa.Column("used_for_training", sa.Boolean(), server_default=sa.false()),
    sa.Column("expert_id", sa.String(36), nullable=True),
    sa.Column("expert_email", sa.String(255), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    sa.PrimaryKeyConstraint("id"),
  )
  op.create_index("ix_expert_feedback_feedback_id", "expert_feedback", ["feedback_id"], unique=True)
  op.create_index("ix_expert_feedback_sample_id", "expert_feedback", ["sample_id"])


def downgrade() -> None:
  op.drop_table("expert_feedback")
  op.drop_table("reassessment_requests")
  op.drop_table("panel_marker_results")
  op.drop_table("case_assays")
  op.drop_table("clinical_cases")
  op.drop_table("marker_panels")
