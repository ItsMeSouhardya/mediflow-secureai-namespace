"""Add booking-time patient demographics to queue tokens.

Revision ID: 4a6c8e2d1f90
Revises: e6a1c9f42b70
"""

from alembic import op
import sqlalchemy as sa


revision = "4a6c8e2d1f90"
down_revision = "e6a1c9f42b70"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tokens", sa.Column("booked_patient_name", sa.String(length=120), nullable=True))
    op.add_column("tokens", sa.Column("booked_patient_age", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("tokens", "booked_patient_age")
    op.drop_column("tokens", "booked_patient_name")
