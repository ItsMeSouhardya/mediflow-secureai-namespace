"""add telemedicine sessions

Revision ID: d4b8e3c7a129
Revises: c2f7a4d91e60
Create Date: 2026-07-12
"""

from alembic import op
import sqlalchemy as sa


revision = "d4b8e3c7a129"
down_revision = "c2f7a4d91e60"
branch_labels = None
depends_on = None


def upgrade():
    # ------------------------------------------------------------------
    # 11.1 — Add consultation_mode to appointments.
    # Nullable so existing rows are unaffected.  NULL means in-person.
    # ------------------------------------------------------------------
    op.add_column(
        "appointments",
        sa.Column(
            "consultation_mode",
            sa.String(length=24),
            nullable=True,
            server_default="in_person",
        ),
    )
    op.add_column(
        "appointments",
        sa.Column("telemedicine_status", sa.String(length=32), nullable=True),
    )
    op.create_check_constraint(
        "ck_appointment_consultation_mode",
        "appointments",
        "consultation_mode IN ('in_person', 'telemedicine')",
    )

    # ------------------------------------------------------------------
    # 11.2 — Telemedicine session metadata table.
    # room_reference is opaque; it is never returned without a signed
    # room token so direct object-storage / room URLs are never exposed.
    # recording_enabled defaults to FALSE (11.8).
    # ------------------------------------------------------------------
    op.create_table(
        "telemedicine_sessions",
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("appointment_id", sa.Integer(), nullable=False),
        sa.Column("encounter_id", sa.Integer(), nullable=True),
        sa.Column("patient_profile_id", sa.Integer(), nullable=False),
        sa.Column("doctor_profile_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False,
                  server_default="jitsi"),
        sa.Column("room_reference", sa.String(length=255), nullable=False),
        sa.Column("scheduled_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scheduled_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("patient_joined_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("patient_left_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("doctor_joined_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("doctor_left_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False,
                  server_default="scheduled"),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by_user_id", sa.Integer(), nullable=True),
        sa.Column("cancel_reason", sa.String(length=500), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consultation_summary", sa.Text(), nullable=True),
        sa.Column("recording_enabled", sa.Boolean(), nullable=False,
                  server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ("
            "'scheduled','confirmed','patient_waiting','doctor_waiting',"
            "'in_progress','completed','cancelled')",
            name="ck_telemedicine_session_status",
        ),
        sa.CheckConstraint(
            "provider IN ('jitsi','webrtc_custom')",
            name="ck_telemedicine_session_provider",
        ),
        sa.ForeignKeyConstraint(
            ["appointment_id"], ["appointments.appointment_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["encounter_id"], ["encounters.encounter_id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["patient_profile_id"], ["patient_profiles.patient_profile_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["doctor_profile_id"], ["doctor_profiles.doctor_profile_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["cancelled_by_user_id"], ["users.user_id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("session_id"),
        sa.UniqueConstraint("public_id"),
        sa.UniqueConstraint("appointment_id"),
        sa.UniqueConstraint("encounter_id"),
    )
    op.create_index(
        "ix_telemedicine_sessions_patient",
        "telemedicine_sessions",
        ["patient_profile_id", "status"],
    )
    op.create_index(
        "ix_telemedicine_sessions_doctor",
        "telemedicine_sessions",
        ["doctor_profile_id", "status"],
    )
    op.create_index(
        "ix_telemedicine_sessions_scheduled",
        "telemedicine_sessions",
        ["scheduled_start", "status"],
    )


def downgrade():
    op.drop_index("ix_telemedicine_sessions_scheduled",
                  table_name="telemedicine_sessions")
    op.drop_index("ix_telemedicine_sessions_doctor",
                  table_name="telemedicine_sessions")
    op.drop_index("ix_telemedicine_sessions_patient",
                  table_name="telemedicine_sessions")
    op.drop_table("telemedicine_sessions")
    op.drop_constraint("ck_appointment_consultation_mode", "appointments",
                       type_="check")
    op.drop_column("appointments", "telemedicine_status")
    op.drop_column("appointments", "consultation_mode")
