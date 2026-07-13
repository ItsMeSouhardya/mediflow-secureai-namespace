"""add blockchain proof outbox and audit anchors

Revision ID: b8f4c2d19a70
Revises: a3d8e1f5c620
Create Date: 2026-07-12
"""

from alembic import op
import sqlalchemy as sa


revision = "b8f4c2d19a70"
down_revision = "a3d8e1f5c620"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "blockchain_transactions",
        sa.Column("blockchain_transaction_id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("operation", sa.String(length=40), nullable=False),
        sa.Column("entity_type", sa.String(length=60), nullable=False),
        sa.Column("entity_reference_hash", sa.String(length=64), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("proof_payload", sa.JSON(), nullable=False),
        sa.Column("document_version_id", sa.Integer(), nullable=True),
        sa.Column("consent_grant_id", sa.Integer(), nullable=True),
        sa.Column("chain_id", sa.Integer(), nullable=True),
        sa.Column("contract_address", sa.String(length=42), nullable=True),
        sa.Column("transaction_hash", sa.String(length=66), nullable=True),
        sa.Column("block_number", sa.Integer(), nullable=True),
        sa.Column("state", sa.String(length=24), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("attempts >= 0", name="ck_blockchain_transaction_attempts"),
        sa.CheckConstraint(
            "operation IN ('record_register','consent_grant','consent_revoke','audit_anchor')",
            name="ck_blockchain_transaction_operation",
        ),
        sa.CheckConstraint(
            "state IN ('pending','submitted','confirmed','failed','retry')",
            name="ck_blockchain_transaction_state",
        ),
        sa.ForeignKeyConstraint(
            ["consent_grant_id"], ["consent_grants.consent_grant_id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["document_version_id"], ["document_versions.document_version_id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("blockchain_transaction_id"),
        sa.UniqueConstraint("operation", "entity_reference_hash", name="uq_blockchain_operation_entity"),
        sa.UniqueConstraint("public_id"),
        sa.UniqueConstraint("transaction_hash"),
    )
    op.create_index(
        "ix_blockchain_transactions_consent",
        "blockchain_transactions",
        ["consent_grant_id", "operation"],
    )
    op.create_index(
        "ix_blockchain_transactions_document",
        "blockchain_transactions",
        ["document_version_id", "operation"],
    )
    op.create_index(
        "ix_blockchain_transactions_state_retry",
        "blockchain_transactions",
        ["state", "next_retry_at"],
    )
    op.create_table(
        "blockchain_audit_anchors",
        sa.Column("blockchain_audit_anchor_id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_reference_hash", sa.String(length=64), nullable=False),
        sa.Column("merkle_root", sa.String(length=64), nullable=False),
        sa.Column("event_count", sa.Integer(), nullable=False),
        sa.Column("blockchain_transaction_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("event_count >= 0", name="ck_blockchain_audit_anchor_event_count"),
        sa.CheckConstraint("period_end > period_start", name="ck_blockchain_audit_anchor_period"),
        sa.ForeignKeyConstraint(
            ["blockchain_transaction_id"],
            ["blockchain_transactions.blockchain_transaction_id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("blockchain_audit_anchor_id"),
        sa.UniqueConstraint("blockchain_transaction_id"),
        sa.UniqueConstraint("period_reference_hash"),
        sa.UniqueConstraint("public_id"),
    )
    op.create_index(
        "ix_blockchain_audit_anchors_period",
        "blockchain_audit_anchors",
        ["period_start", "period_end"],
    )


def downgrade():
    op.drop_index("ix_blockchain_audit_anchors_period", table_name="blockchain_audit_anchors")
    op.drop_table("blockchain_audit_anchors")
    op.drop_index("ix_blockchain_transactions_state_retry", table_name="blockchain_transactions")
    op.drop_index("ix_blockchain_transactions_document", table_name="blockchain_transactions")
    op.drop_index("ix_blockchain_transactions_consent", table_name="blockchain_transactions")
    op.drop_table("blockchain_transactions")
