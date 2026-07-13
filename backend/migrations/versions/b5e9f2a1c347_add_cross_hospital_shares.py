"""add cross-hospital sharing

Revision ID: b5e9f2a1c347
Revises: b8f4c2d19a70
Create Date: 2026-07-12
"""

from alembic import op
import sqlalchemy as sa


revision = "b5e9f2a1c347"
down_revision = "b8f4c2d19a70"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "cross_hospital_shares",
        sa.Column("share_id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("patient_profile_id", sa.Integer(), nullable=False),
        sa.Column("source_hospital_id", sa.Integer(), nullable=False),
        sa.Column("requesting_hospital_id", sa.Integer(), nullable=False),
        sa.Column("requesting_doctor_profile_id", sa.Integer(), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("purpose", sa.String(length=500), nullable=False),
        sa.Column("operation", sa.String(length=80), nullable=False),
        sa.Column("requested_duration_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("status", sa.String(length=24), nullable=False,
                  server_default="pending"),
        sa.Column("access_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("access_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("denied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("denied_reason", sa.String(length=500), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_reason", sa.String(length=500), nullable=True),
        sa.Column("is_break_glass", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("break_glass_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending','granted','denied','revoked','expired','break_glass')",
            name="ck_cross_hospital_share_status",
        ),
        sa.CheckConstraint(
            "operation IN ('treatment','second_opinion','research_review',"
            "'referral','emergency','other')",
            name="ck_cross_hospital_share_operation",
        ),
        sa.CheckConstraint(
            "source_hospital_id != requesting_hospital_id",
            name="ck_cross_hospital_share_different_hospitals",
        ),
        sa.ForeignKeyConstraint(
            ["patient_profile_id"],
            ["patient_profiles.patient_profile_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_hospital_id"],
            ["hospitals.hospital_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["requesting_hospital_id"],
            ["hospitals.hospital_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["requesting_doctor_profile_id"],
            ["doctor_profiles.doctor_profile_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("share_id"),
        sa.UniqueConstraint("public_id"),
    )
    op.create_index(
        "ix_cross_hospital_shares_patient_status",
        "cross_hospital_shares",
        ["patient_profile_id", "status"],
    )
    op.create_index(
        "ix_cross_hospital_shares_requesting",
        "cross_hospital_shares",
        ["requesting_hospital_id", "requesting_doctor_profile_id"],
    )
    op.create_index(
        "ix_cross_hospital_shares_expiry",
        "cross_hospital_shares",
        ["access_expires_at", "status"],
    )
    op.create_table(
        "cross_hospital_share_history",
        sa.Column("share_history_id", sa.Integer(), nullable=False),
        sa.Column("share_id", sa.Integer(), nullable=False),
        sa.Column("from_status", sa.String(length=24), nullable=True),
        sa.Column("to_status", sa.String(length=24), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.user_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["share_id"], ["cross_hospital_shares.share_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("share_history_id"),
    )
    op.create_index(
        "ix_cross_hospital_share_history_share",
        "cross_hospital_share_history",
        ["share_id", "created_at"],
    )


def downgrade():
    op.drop_index("ix_cross_hospital_share_history_share", table_name="cross_hospital_share_history")
    op.drop_table("cross_hospital_share_history")
    op.drop_index("ix_cross_hospital_shares_expiry",
                  table_name="cross_hospital_shares")
    op.drop_index("ix_cross_hospital_shares_requesting",
                  table_name="cross_hospital_shares")
    op.drop_index("ix_cross_hospital_shares_patient_status",
                  table_name="cross_hospital_shares")
    op.drop_table("cross_hospital_shares")
