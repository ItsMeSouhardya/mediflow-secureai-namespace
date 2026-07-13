"""add consent and authorization domain

Revision ID: a3d8e1f5c620
Revises: f2a7c3e8b194
Create Date: 2026-07-12
"""

from alembic import op
import sqlalchemy as sa


revision = "a3d8e1f5c620"
down_revision = "f2a7c3e8b194"
branch_labels = None
depends_on = None


def upgrade():
    # ------------------------------------------------------------------
    # consent_grants — core consent lifecycle table (7.1)
    # ------------------------------------------------------------------
    op.create_table(
        "consent_grants",
        sa.Column("consent_grant_id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("patient_profile_id", sa.Integer(), nullable=False),
        sa.Column("requesting_doctor_profile_id", sa.Integer(), nullable=False),
        sa.Column("requesting_hospital_id", sa.Integer(), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("purpose", sa.String(length=500), nullable=False),
        sa.Column("operation", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="pending"),
        sa.Column("access_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("access_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("denied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("denied_reason", sa.String(length=500), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_reason", sa.String(length=500), nullable=True),
        sa.Column("is_break_glass", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("break_glass_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending','granted','denied','revoked','expired','break_glass')",
            name="ck_consent_grant_status",
        ),
        sa.CheckConstraint(
            "operation IN ('treatment','second_opinion','research_review','referral','emergency','other')",
            name="ck_consent_grant_operation",
        ),
        sa.ForeignKeyConstraint(
            ["patient_profile_id"], ["patient_profiles.patient_profile_id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["requesting_doctor_profile_id"], ["doctor_profiles.doctor_profile_id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["requesting_hospital_id"], ["hospitals.hospital_id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("consent_grant_id"),
        sa.UniqueConstraint("public_id"),
    )
    op.create_index(
        "ix_consent_grants_patient_status", "consent_grants", ["patient_profile_id", "status"]
    )
    op.create_index(
        "ix_consent_grants_doctor_patient",
        "consent_grants",
        ["requesting_doctor_profile_id", "patient_profile_id"],
    )
    op.create_index(
        "ix_consent_grants_expiry", "consent_grants", ["access_expires_at", "status"]
    )

    # ------------------------------------------------------------------
    # consent_status_history — immutable audit log of transitions (7.1)
    # ------------------------------------------------------------------
    op.create_table(
        "consent_status_history",
        sa.Column("consent_status_history_id", sa.Integer(), nullable=False),
        sa.Column("consent_grant_id", sa.Integer(), nullable=False),
        sa.Column("from_status", sa.String(length=24), nullable=False),
        sa.Column("to_status", sa.String(length=24), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["consent_grant_id"], ["consent_grants.consent_grant_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["users.user_id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("consent_status_history_id"),
    )
    op.create_index(
        "ix_consent_status_history_grant",
        "consent_status_history",
        ["consent_grant_id", "created_at"],
    )

    # ------------------------------------------------------------------
    # consent_notifications — in-app notification events (7.8)
    # ------------------------------------------------------------------
    op.create_table(
        "consent_notifications",
        sa.Column("consent_notification_id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("consent_grant_id", sa.Integer(), nullable=False),
        sa.Column("recipient_user_id", sa.Integer(), nullable=False),
        sa.Column("notification_type", sa.String(length=60), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "notification_type IN ("
            "'access_requested','access_granted','access_denied',"
            "'access_revoked','consent_expired','break_glass_used')",
            name="ck_consent_notification_type",
        ),
        sa.ForeignKeyConstraint(
            ["consent_grant_id"], ["consent_grants.consent_grant_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["recipient_user_id"], ["users.user_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("consent_notification_id"),
        sa.UniqueConstraint("public_id"),
    )
    op.create_index(
        "ix_consent_notifications_recipient_read",
        "consent_notifications",
        ["recipient_user_id", "is_read", "created_at"],
    )
    op.create_index(
        "ix_consent_notifications_grant",
        "consent_notifications",
        ["consent_grant_id"],
    )


def downgrade():
    op.drop_index("ix_consent_notifications_grant", table_name="consent_notifications")
    op.drop_index("ix_consent_notifications_recipient_read", table_name="consent_notifications")
    op.drop_table("consent_notifications")

    op.drop_index("ix_consent_status_history_grant", table_name="consent_status_history")
    op.drop_table("consent_status_history")

    op.drop_index("ix_consent_grants_expiry", table_name="consent_grants")
    op.drop_index("ix_consent_grants_doctor_patient", table_name="consent_grants")
    op.drop_index("ix_consent_grants_patient_status", table_name="consent_grants")
    op.drop_table("consent_grants")
