"""add identity, RBAC, tenancy, and rotating auth sessions

Revision ID: c84e3a1f0d92
Revises: b3d56a65a637
Create Date: 2026-07-12
"""

from alembic import op
import sqlalchemy as sa


revision = "c84e3a1f0d92"
down_revision = "b3d56a65a637"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("email", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("password_hash", sa.String(length=512), nullable=True))
    op.add_column("users", sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False))
    op.add_column("users", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("phone_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("mfa_enabled", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("users", sa.Column("mfa_secret_encrypted", sa.String(length=512), nullable=True))
    op.add_column("users", sa.Column("mfa_enforced_at", sa.DateTime(timezone=True), nullable=True))
    op.create_unique_constraint("uq_users_email", "users", ["email"])

    op.add_column("tokens", sa.Column("tracking_code_hash", sa.String(length=64), nullable=True))
    op.add_column("tokens", sa.Column("tracking_code_last4", sa.String(length=4), nullable=True))
    op.create_unique_constraint("uq_tokens_tracking_code_hash", "tokens", ["tracking_code_hash"])

    op.create_table(
        "roles",
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=40), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("role_id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "user_roles",
        sa.Column("user_role_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("hospital_id", sa.Integer(), nullable=True),
        sa.Column("assigned_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["assigned_by_user_id"], ["users.user_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["hospital_id"], ["hospitals.hospital_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["roles.role_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_role_id"),
        sa.UniqueConstraint("user_id", "role_id", "hospital_id", name="uq_user_role_hospital"),
    )
    op.create_index("ix_user_roles_user_hospital", "user_roles", ["user_id", "hospital_id"])
    op.execute(
        sa.text(
            "INSERT INTO roles (name, description, created_at) VALUES "
            "('patient', 'Patient self-service access', CURRENT_TIMESTAMP), "
            "('doctor', 'Hospital-scoped clinical access', CURRENT_TIMESTAMP), "
            "('hospital_admin', 'Hospital-scoped operational administration', CURRENT_TIMESTAMP), "
            "('security_admin', 'Global security administration without clinical access', CURRENT_TIMESTAMP)"
        )
    )
    op.execute(
        sa.text(
            "INSERT INTO user_roles (user_id, role_id, hospital_id, assigned_by_user_id, created_at) "
            "SELECT users.user_id, roles.role_id, NULL, NULL, CURRENT_TIMESTAMP "
            "FROM users CROSS JOIN roles WHERE roles.name = 'patient'"
        )
    )
    op.create_table(
        "staff_profiles",
        sa.Column("staff_profile_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("hospital_id", sa.Integer(), nullable=False),
        sa.Column("doctor_id", sa.Integer(), nullable=True),
        sa.Column("employee_code", sa.String(length=80), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('active','suspended','inactive')", name="ck_staff_status"),
        sa.ForeignKeyConstraint(["doctor_id"], ["doctors.doctor_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["hospital_id"], ["hospitals.hospital_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("staff_profile_id"),
        sa.UniqueConstraint("doctor_id"),
        sa.UniqueConstraint("hospital_id", "employee_code", name="uq_staff_hospital_employee"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_table(
        "auth_sessions",
        sa.Column("auth_session_id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("refresh_token_hash", sa.String(length=64), nullable=False),
        sa.Column("replaced_by_session_id", sa.Integer(), nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoke_reason", sa.String(length=120), nullable=True),
        sa.Column("remote_addr", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.Column("mfa_verified", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["replaced_by_session_id"], ["auth_sessions.auth_session_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("auth_session_id"),
        sa.UniqueConstraint("public_id"),
        sa.UniqueConstraint("refresh_token_hash"),
    )
    op.create_index("ix_auth_sessions_family", "auth_sessions", ["family_id"])
    op.create_index("ix_auth_sessions_user_expiry", "auth_sessions", ["user_id", "expires_at"])
    op.create_table(
        "password_reset_tokens",
        sa.Column("password_reset_token_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("requested_ip", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("password_reset_token_id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_password_reset_user_expiry", "password_reset_tokens", ["user_id", "expires_at"])
    op.create_table(
        "account_activation_tokens",
        sa.Column("account_activation_token_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("account_activation_token_id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_account_activation_user_expiry", "account_activation_tokens", ["user_id", "expires_at"])
    op.create_table(
        "login_attempts",
        sa.Column("login_attempt_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("identifier_hash", sa.String(length=64), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.String(length=80), nullable=True),
        sa.Column("remote_addr", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.Column("session_public_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("login_attempt_id"),
    )
    op.create_index("ix_login_attempt_identifier_time", "login_attempts", ["identifier_hash", "created_at"])
    op.create_index("ix_login_attempt_ip_time", "login_attempts", ["remote_addr", "created_at"])


def downgrade():
    op.drop_index("ix_login_attempt_ip_time", table_name="login_attempts")
    op.drop_index("ix_login_attempt_identifier_time", table_name="login_attempts")
    op.drop_table("login_attempts")
    op.drop_index("ix_account_activation_user_expiry", table_name="account_activation_tokens")
    op.drop_table("account_activation_tokens")
    op.drop_index("ix_password_reset_user_expiry", table_name="password_reset_tokens")
    op.drop_table("password_reset_tokens")
    op.drop_index("ix_auth_sessions_user_expiry", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_family", table_name="auth_sessions")
    op.drop_table("auth_sessions")
    op.drop_table("staff_profiles")
    op.drop_index("ix_user_roles_user_hospital", table_name="user_roles")
    op.drop_table("user_roles")
    op.drop_table("roles")
    op.drop_constraint("uq_tokens_tracking_code_hash", "tokens", type_="unique")
    op.drop_column("tokens", "tracking_code_last4")
    op.drop_column("tokens", "tracking_code_hash")
    op.drop_constraint("uq_users_email", "users", type_="unique")
    for column in (
        "mfa_enforced_at", "mfa_secret_encrypted", "mfa_enabled", "deactivated_at", "locked_until",
        "last_login_at", "phone_verified_at", "email_verified_at", "is_active", "password_hash", "email",
    ):
        op.drop_column("users", column)
