"""add cybersecurity event and response domain

Revision ID: e6a1c9f42b70
Revises: d4b8e3c7a129
Create Date: 2026-07-12
"""

from alembic import op
import sqlalchemy as sa

revision = "e6a1c9f42b70"
down_revision = "d4b8e3c7a129"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "security_events",
        sa.Column("security_event_id", sa.Integer(), primary_key=True),
        sa.Column("public_id", sa.Uuid(), nullable=False, unique=True),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False, server_default="info"),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("actor_user_id", sa.Integer()), sa.Column("subject_user_id", sa.Integer()),
        sa.Column("auth_session_id", sa.Integer()),
        sa.Column("resource_type", sa.String(80)), sa.Column("resource_id", sa.String(160)),
        sa.Column("request_id", sa.String(64)), sa.Column("ip_hash", sa.String(64)),
        sa.Column("device_hash", sa.String(64)),
        sa.Column("safe_metadata", sa.JSON(), nullable=False),
        sa.Column("feature_vector", sa.JSON(), nullable=False),
        sa.Column("anomaly_score", sa.Float()), sa.Column("anomaly_model", sa.String(80)),
        sa.Column("anomaly_advisory", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("training_label", sa.String(24)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("severity IN ('info','low','medium','high','critical')", name="ck_security_event_severity"),
        sa.CheckConstraint("outcome IN ('success','denied','failure')", name="ck_security_event_outcome"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.user_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["subject_user_id"], ["users.user_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["auth_session_id"], ["auth_sessions.auth_session_id"], ondelete="SET NULL"),
    )
    op.create_index("ix_security_events_type_created", "security_events", ["event_type", "created_at"])
    op.create_index("ix_security_events_actor_created", "security_events", ["actor_user_id", "created_at"])
    op.create_index("ix_security_events_ip_created", "security_events", ["ip_hash", "created_at"])
    op.create_index("ix_security_events_category_severity", "security_events", ["category", "severity", "created_at"])
    op.create_table(
        "security_alerts",
        sa.Column("security_alert_id", sa.Integer(), primary_key=True),
        sa.Column("public_id", sa.Uuid(), nullable=False, unique=True),
        sa.Column("rule_code", sa.String(80), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.String(700), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("anomaly_score", sa.Float()),
        sa.Column("anomaly_advisory", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("subject_user_id", sa.Integer()), sa.Column("subject_ip_hash", sa.String(64)),
        sa.Column("assigned_user_id", sa.Integer()),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("severity IN ('low','medium','high','critical')", name="ck_security_alert_severity"),
        sa.CheckConstraint("status IN ('open','acknowledged','investigating','resolved','dismissed')", name="ck_security_alert_status"),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_security_alert_confidence"),
        sa.ForeignKeyConstraint(["subject_user_id"], ["users.user_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["assigned_user_id"], ["users.user_id"], ondelete="SET NULL"),
    )
    op.create_index("ix_security_alerts_status_severity", "security_alerts", ["status", "severity", "created_at"])
    op.create_index("ix_security_alerts_rule_subject", "security_alerts", ["rule_code", "subject_user_id", "created_at"])
    op.create_table(
        "security_block_actions",
        sa.Column("security_block_action_id", sa.Integer(), primary_key=True),
        sa.Column("public_id", sa.Uuid(), nullable=False, unique=True),
        sa.Column("target_type", sa.String(16), nullable=False), sa.Column("target_hash", sa.String(64)),
        sa.Column("target_user_id", sa.Integer()), sa.Column("target_session_id", sa.Integer()),
        sa.Column("rule_code", sa.String(80), nullable=False), sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("automated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_by_user_id", sa.Integer()), sa.Column("released_at", sa.DateTime(timezone=True)),
        sa.Column("released_by_user_id", sa.Integer()), sa.Column("release_reason", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("target_type IN ('account','session','ip')", name="ck_security_block_target"),
        sa.ForeignKeyConstraint(["target_user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_session_id"], ["auth_sessions.auth_session_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.user_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["released_by_user_id"], ["users.user_id"], ondelete="SET NULL"),
    )
    op.create_index("ix_security_blocks_active_expiry", "security_block_actions", ["is_active", "expires_at"])
    op.create_index("ix_security_blocks_user_active", "security_block_actions", ["target_user_id", "is_active"])
    op.create_index("ix_security_blocks_hash_active", "security_block_actions", ["target_hash", "is_active"])
    op.create_table(
        "security_alert_resolutions",
        sa.Column("security_alert_resolution_id", sa.Integer(), primary_key=True),
        sa.Column("security_alert_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(24), nullable=False), sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("action IN ('acknowledged','investigating','resolved','dismissed','reopened')", name="ck_security_resolution_action"),
        sa.ForeignKeyConstraint(["security_alert_id"], ["security_alerts.security_alert_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.user_id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_security_resolutions_alert_created", "security_alert_resolutions", ["security_alert_id", "created_at"])
    op.create_table(
        "security_allowlist_entries",
        sa.Column("security_allowlist_entry_id", sa.Integer(), primary_key=True),
        sa.Column("target_type", sa.String(16), nullable=False), sa.Column("target_hash", sa.String(64), nullable=False),
        sa.Column("description", sa.String(300), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by_user_id", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("target_type IN ('account','ip','device')", name="ck_security_allowlist_target"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.user_id"], ondelete="SET NULL"),
        sa.UniqueConstraint("target_type", "target_hash", name="uq_security_allowlist_target"),
    )


def downgrade():
    op.drop_table("security_allowlist_entries")
    op.drop_index("ix_security_resolutions_alert_created", table_name="security_alert_resolutions")
    op.drop_table("security_alert_resolutions")
    op.drop_index("ix_security_blocks_hash_active", table_name="security_block_actions")
    op.drop_index("ix_security_blocks_user_active", table_name="security_block_actions")
    op.drop_index("ix_security_blocks_active_expiry", table_name="security_block_actions")
    op.drop_table("security_block_actions")
    op.drop_index("ix_security_alerts_rule_subject", table_name="security_alerts")
    op.drop_index("ix_security_alerts_status_severity", table_name="security_alerts")
    op.drop_table("security_alerts")
    op.drop_index("ix_security_events_category_severity", table_name="security_events")
    op.drop_index("ix_security_events_ip_created", table_name="security_events")
    op.drop_index("ix_security_events_actor_created", table_name="security_events")
    op.drop_index("ix_security_events_type_created", table_name="security_events")
    op.drop_table("security_events")
