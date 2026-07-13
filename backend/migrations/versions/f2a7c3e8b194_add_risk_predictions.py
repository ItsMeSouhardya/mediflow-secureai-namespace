"""add risk predictions

Revision ID: f2a7c3e8b194
Revises: e1f4b2c9d035
Create Date: 2026-07-12
"""

from alembic import op
import sqlalchemy as sa


revision = "f2a7c3e8b194"
down_revision = "e1f4b2c9d035"
branch_labels = None
depends_on = None


def upgrade():
    # ------------------------------------------------------------------
    # risk_predictions — immutable prediction snapshots for disease-risk
    # decision support.  Input + output stored as JSON so results are
    # fully reproducible from the DB alone.
    # ------------------------------------------------------------------
    op.create_table(
        "risk_predictions",
        sa.Column("risk_prediction_id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("patient_profile_id", sa.Integer(), nullable=False),
        sa.Column("requested_by_user_id", sa.Integer(), nullable=False),
        sa.Column("source_document_id", sa.Integer(), nullable=True),
        sa.Column("model_name", sa.String(length=80), nullable=False),
        sa.Column("model_version", sa.String(length=80), nullable=False),
        sa.Column("input_snapshot", sa.JSON(), nullable=False),
        sa.Column("output_snapshot", sa.JSON(), nullable=False),
        sa.Column("risk_score", sa.Float(), nullable=False),
        sa.Column("risk_band", sa.String(length=24), nullable=False),
        sa.Column(
            "review_status",
            sa.String(length=24),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("reviewed_by_doctor_profile_id", sa.Integer(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewer_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "review_status IN ('pending','accepted','rejected','corrected')",
            name="ck_risk_prediction_review_status",
        ),
        sa.CheckConstraint(
            "risk_band IN ('low','moderate','high','very_high')",
            name="ck_risk_prediction_band",
        ),
        sa.ForeignKeyConstraint(
            ["patient_profile_id"],
            ["patient_profiles.patient_profile_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_user_id"],
            ["users.user_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_document_id"],
            ["medical_documents.document_id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by_doctor_profile_id"],
            ["doctor_profiles.doctor_profile_id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("risk_prediction_id"),
        sa.UniqueConstraint("public_id"),
    )
    op.create_index(
        "ix_risk_predictions_patient",
        "risk_predictions",
        ["patient_profile_id", "created_at"],
    )
    op.create_index(
        "ix_risk_predictions_model",
        "risk_predictions",
        ["model_name", "model_version"],
    )
    op.create_index(
        "ix_risk_predictions_review",
        "risk_predictions",
        ["review_status", "patient_profile_id"],
    )


def downgrade():
    op.drop_index("ix_risk_predictions_review", table_name="risk_predictions")
    op.drop_index("ix_risk_predictions_model", table_name="risk_predictions")
    op.drop_index("ix_risk_predictions_patient", table_name="risk_predictions")
    op.drop_table("risk_predictions")
