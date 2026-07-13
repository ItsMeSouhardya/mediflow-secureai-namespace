"""add encrypted document pipeline

Revision ID: e1f4b2c9d035
Revises: d923ec4a71b0
Create Date: 2026-07-12
"""

from alembic import op
import sqlalchemy as sa


revision = "e1f4b2c9d035"
down_revision = "d923ec4a71b0"
branch_labels = None
depends_on = None


def upgrade():
    # ------------------------------------------------------------------
    # medical_documents — top-level document record owned by a patient.
    # File bytes are stored in the encrypted storage backend; only
    # metadata and an opaque storage reference live here.
    # ------------------------------------------------------------------
    op.create_table(
        "medical_documents",
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("patient_profile_id", sa.Integer(), nullable=False),
        sa.Column("uploaded_by_user_id", sa.Integer(), nullable=False),
        sa.Column("encounter_id", sa.Integer(), nullable=True),
        sa.Column("document_type", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("document_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="upload"),
        sa.Column("verified_by_doctor_profile_id", sa.Integer(), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verification_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('upload','processing','ready','failed','quarantined','archived')",
            name="ck_medical_document_status",
        ),
        sa.CheckConstraint(
            "document_type IN ("
            "'lab_report','imaging','prescription','discharge_summary',"
            "'referral','vaccination_certificate','insurance','other')",
            name="ck_medical_document_type",
        ),
        sa.ForeignKeyConstraint(
            ["encounter_id"], ["encounters.encounter_id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["patient_profile_id"],
            ["patient_profiles.patient_profile_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by_user_id"], ["users.user_id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["verified_by_doctor_profile_id"],
            ["doctor_profiles.doctor_profile_id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("document_id"),
        sa.UniqueConstraint("public_id"),
    )
    op.create_index(
        "ix_medical_documents_patient_status",
        "medical_documents",
        ["patient_profile_id", "status"],
    )
    op.create_index(
        "ix_medical_documents_patient_created",
        "medical_documents",
        ["patient_profile_id", "created_at"],
    )

    # ------------------------------------------------------------------
    # document_versions — immutable per-upload snapshot.
    # SHA-256 is of plaintext bytes; storage_key is an opaque backend ref.
    # ------------------------------------------------------------------
    op.create_table(
        "document_versions",
        sa.Column("document_version_id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("mime_type", sa.String(length=120), nullable=False),
        sa.Column("sha256_hash", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("storage_backend", sa.String(length=32), nullable=False),
        sa.Column("encryption_key_id", sa.String(length=80), nullable=False),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("extraction_method", sa.String(length=40), nullable=True),
        sa.Column("extraction_confidence", sa.Float(), nullable=True),
        sa.Column("extraction_warnings", sa.Text(), nullable=True),
        sa.Column("uploaded_by_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["medical_documents.document_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by_user_id"], ["users.user_id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("document_version_id"),
        sa.UniqueConstraint("public_id"),
        sa.UniqueConstraint("document_id", "version_number", name="uq_document_version"),
    )
    op.create_index(
        "ix_document_versions_document",
        "document_versions",
        ["document_id", "version_number"],
    )
    op.create_index(
        "ix_document_versions_hash",
        "document_versions",
        ["sha256_hash"],
    )

    # ------------------------------------------------------------------
    # document_analysis_results — AI-generated, decision-support only.
    # Requires explicit doctor review before clinical acceptance.
    # ------------------------------------------------------------------
    op.create_table(
        "document_analysis_results",
        sa.Column("analysis_result_id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("document_version_id", sa.Integer(), nullable=False),
        sa.Column("analysis_type", sa.String(length=80), nullable=False),
        sa.Column("model_version", sa.String(length=80), nullable=True),
        sa.Column("rule_version", sa.String(length=80), nullable=True),
        sa.Column("extracted_biomarkers", sa.JSON(), nullable=True),
        sa.Column("abnormal_flags", sa.JSON(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("caveats", sa.JSON(), nullable=True),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("review_status", sa.String(length=24), nullable=False, server_default="pending"),
        sa.Column("reviewed_by_doctor_profile_id", sa.Integer(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewer_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "review_status IN ('pending','accepted','rejected','corrected')",
            name="ck_analysis_review_status",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["medical_documents.document_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_version_id"],
            ["document_versions.document_version_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by_doctor_profile_id"],
            ["doctor_profiles.doctor_profile_id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("analysis_result_id"),
        sa.UniqueConstraint("public_id"),
    )
    op.create_index(
        "ix_analysis_results_document",
        "document_analysis_results",
        ["document_id", "created_at"],
    )
    op.create_index(
        "ix_analysis_results_review",
        "document_analysis_results",
        ["review_status", "document_id"],
    )


def downgrade():
    op.drop_index("ix_analysis_results_review", table_name="document_analysis_results")
    op.drop_index("ix_analysis_results_document", table_name="document_analysis_results")
    op.drop_table("document_analysis_results")

    op.drop_index("ix_document_versions_hash", table_name="document_versions")
    op.drop_index("ix_document_versions_document", table_name="document_versions")
    op.drop_table("document_versions")

    op.drop_index("ix_medical_documents_patient_created", table_name="medical_documents")
    op.drop_index("ix_medical_documents_patient_status", table_name="medical_documents")
    op.drop_table("medical_documents")
