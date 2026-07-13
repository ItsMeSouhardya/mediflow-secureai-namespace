"""add patient monitoring and realtime alerts

Revision ID: c2f7a4d91e60
Revises: b5e9f2a1c347
Create Date: 2026-07-12
"""

from alembic import op
import sqlalchemy as sa

revision = "c2f7a4d91e60"
down_revision = "b5e9f2a1c347"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "observation_definitions",
        sa.Column("observation_definition_id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(40), nullable=False, unique=True),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("unit", sa.String(24), nullable=False),
        sa.Column("secondary_unit", sa.String(24)),
        sa.Column("value_min", sa.Float(), nullable=False),
        sa.Column("value_max", sa.Float(), nullable=False),
        sa.Column("secondary_value_min", sa.Float()),
        sa.Column("secondary_value_max", sa.Float()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("value_max > value_min", name="ck_observation_definition_range"),
    )
    op.create_table(
        "patient_observations",
        sa.Column("observation_id", sa.Integer(), primary_key=True),
        sa.Column("public_id", sa.Uuid(), nullable=False, unique=True),
        sa.Column("patient_profile_id", sa.Integer(), nullable=False),
        sa.Column("observation_type", sa.String(40), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("secondary_value", sa.Float()),
        sa.Column("unit", sa.String(24), nullable=False),
        sa.Column("source", sa.String(24), nullable=False),
        sa.Column("source_reference", sa.String(160)),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_by_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("observation_type IN ('heart_rate','blood_pressure','blood_oxygen','temperature','blood_glucose')", name="ck_patient_observation_type"),
        sa.CheckConstraint("source IN ('manual','device','simulator')", name="ck_patient_observation_source"),
        sa.ForeignKeyConstraint(["patient_profile_id"], ["patient_profiles.patient_profile_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recorded_by_user_id"], ["users.user_id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_patient_observations_patient_recorded", "patient_observations", ["patient_profile_id", "recorded_at"])
    op.create_index("ix_patient_observations_type_recorded", "patient_observations", ["observation_type", "recorded_at"])
    op.create_table(
        "monitoring_rules",
        sa.Column("monitoring_rule_id", sa.Integer(), primary_key=True),
        sa.Column("public_id", sa.Uuid(), nullable=False, unique=True),
        sa.Column("hospital_id", sa.Integer()),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("observation_type", sa.String(40), nullable=False),
        sa.Column("minimum_value", sa.Float()),
        sa.Column("maximum_value", sa.Float()),
        sa.Column("secondary_minimum_value", sa.Float()),
        sa.Column("secondary_maximum_value", sa.Float()),
        sa.Column("trend_window_count", sa.Integer()),
        sa.Column("trend_delta", sa.Float()),
        sa.Column("severity", sa.String(16), nullable=False, server_default="warning"),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by_user_id", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("observation_type IN ('heart_rate','blood_pressure','blood_oxygen','temperature','blood_glucose')", name="ck_monitoring_rule_type"),
        sa.CheckConstraint("severity IN ('info','warning','critical')", name="ck_monitoring_rule_severity"),
        sa.ForeignKeyConstraint(["hospital_id"], ["hospitals.hospital_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.user_id"], ondelete="SET NULL"),
    )
    op.create_index("ix_monitoring_rules_hospital_type", "monitoring_rules", ["hospital_id", "observation_type", "is_enabled"])
    op.create_table(
        "monitoring_alerts",
        sa.Column("monitoring_alert_id", sa.Integer(), primary_key=True),
        sa.Column("public_id", sa.Uuid(), nullable=False, unique=True),
        sa.Column("patient_profile_id", sa.Integer(), nullable=False),
        sa.Column("observation_id", sa.Integer(), nullable=False),
        sa.Column("monitoring_rule_id", sa.Integer(), nullable=False),
        sa.Column("hospital_id", sa.Integer()),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("message", sa.String(500), nullable=False),
        sa.Column("assigned_doctor_profile_id", sa.Integer()),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True)),
        sa.Column("acknowledged_by_user_id", sa.Integer()),
        sa.Column("escalated_at", sa.DateTime(timezone=True)),
        sa.Column("resolution_notes", sa.Text()),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_by_user_id", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("severity IN ('info','warning','critical')", name="ck_monitoring_alert_severity"),
        sa.CheckConstraint("status IN ('open','acknowledged','escalated','resolved')", name="ck_monitoring_alert_status"),
        sa.ForeignKeyConstraint(["patient_profile_id"], ["patient_profiles.patient_profile_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["observation_id"], ["patient_observations.observation_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["monitoring_rule_id"], ["monitoring_rules.monitoring_rule_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["hospital_id"], ["hospitals.hospital_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["assigned_doctor_profile_id"], ["doctor_profiles.doctor_profile_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["acknowledged_by_user_id"], ["users.user_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["resolved_by_user_id"], ["users.user_id"], ondelete="SET NULL"),
    )
    op.create_index("ix_monitoring_alerts_hospital_status", "monitoring_alerts", ["hospital_id", "status", "created_at"])
    op.create_index("ix_monitoring_alerts_patient_created", "monitoring_alerts", ["patient_profile_id", "created_at"])


def downgrade():
    op.drop_index("ix_monitoring_alerts_patient_created", table_name="monitoring_alerts")
    op.drop_index("ix_monitoring_alerts_hospital_status", table_name="monitoring_alerts")
    op.drop_table("monitoring_alerts")
    op.drop_index("ix_monitoring_rules_hospital_type", table_name="monitoring_rules")
    op.drop_table("monitoring_rules")
    op.drop_index("ix_patient_observations_type_recorded", table_name="patient_observations")
    op.drop_index("ix_patient_observations_patient_recorded", table_name="patient_observations")
    op.drop_table("patient_observations")
    op.drop_table("observation_definitions")
