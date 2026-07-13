"""Add respiratory-rate monitoring.

Revision ID: 7d9e2a4b6c10
Revises: 4a6c8e2d1f90
"""

from alembic import op


revision = "7d9e2a4b6c10"
down_revision = "4a6c8e2d1f90"
branch_labels = None
depends_on = None


OBSERVATION_TYPES = "'heart_rate','blood_pressure','blood_oxygen','temperature','blood_glucose','respiratory_rate'"
LEGACY_TYPES = "'heart_rate','blood_pressure','blood_oxygen','temperature','blood_glucose'"


def upgrade() -> None:
    op.drop_constraint("ck_patient_observation_type", "patient_observations", type_="check")
    op.create_check_constraint("ck_patient_observation_type", "patient_observations", f"observation_type IN ({OBSERVATION_TYPES})")
    op.drop_constraint("ck_monitoring_rule_type", "monitoring_rules", type_="check")
    op.create_check_constraint("ck_monitoring_rule_type", "monitoring_rules", f"observation_type IN ({OBSERVATION_TYPES})")


def downgrade() -> None:
    op.drop_constraint("ck_monitoring_rule_type", "monitoring_rules", type_="check")
    op.create_check_constraint("ck_monitoring_rule_type", "monitoring_rules", f"observation_type IN ({LEGACY_TYPES})")
    op.drop_constraint("ck_patient_observation_type", "patient_observations", type_="check")
    op.create_check_constraint("ck_patient_observation_type", "patient_observations", f"observation_type IN ({LEGACY_TYPES})")
