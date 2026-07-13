"""add electronic health record domain

Revision ID: d923ec4a71b0
Revises: c84e3a1f0d92
Create Date: 2026-07-12
"""

from alembic import op
import sqlalchemy as sa


revision = "d923ec4a71b0"
down_revision = "c84e3a1f0d92"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "patient_profiles",
        sa.Column("patient_profile_id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("medical_record_number", sa.String(length=32), nullable=False),
        sa.Column("blood_group", sa.String(length=8), nullable=True),
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column("emergency_contact", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("patient_profile_id"),
        sa.UniqueConstraint("medical_record_number"),
        sa.UniqueConstraint("public_id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_table(
        "doctor_profiles",
        sa.Column("doctor_profile_id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("hospital_id", sa.Integer(), nullable=False),
        sa.Column("doctor_id", sa.Integer(), nullable=False),
        sa.Column("license_number", sa.String(length=80), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('active','suspended','inactive')", name="ck_doctor_profile_status"),
        sa.ForeignKeyConstraint(["doctor_id"], ["doctors.doctor_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["hospital_id"], ["hospitals.hospital_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("doctor_profile_id"),
        sa.UniqueConstraint("doctor_id"),
        sa.UniqueConstraint("license_number"),
        sa.UniqueConstraint("public_id"),
        sa.UniqueConstraint("user_id"),
    )
    op.execute(
        sa.text(
            "INSERT INTO patient_profiles "
            "(public_id, user_id, medical_record_number, created_at, updated_at) "
            "SELECT users.public_id, users.user_id, "
            "'MRN-' || UPPER(SUBSTRING(REPLACE(users.public_id::text, '-', '') FROM 1 FOR 12)), "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP "
            "FROM users JOIN user_roles ON user_roles.user_id = users.user_id "
            "JOIN roles ON roles.role_id = user_roles.role_id WHERE roles.name = 'patient'"
        )
    )
    op.execute(
        sa.text(
            "INSERT INTO doctor_profiles "
            "(public_id, user_id, hospital_id, doctor_id, status, created_at, updated_at) "
            "SELECT users.public_id, staff_profiles.user_id, staff_profiles.hospital_id, staff_profiles.doctor_id, "
            "staff_profiles.status, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP "
            "FROM staff_profiles JOIN users ON users.user_id = staff_profiles.user_id "
            "JOIN user_roles ON user_roles.user_id = staff_profiles.user_id "
            "JOIN roles ON roles.role_id = user_roles.role_id "
            "WHERE roles.name = 'doctor' AND staff_profiles.doctor_id IS NOT NULL"
        )
    )

    op.add_column("appointments", sa.Column("patient_profile_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_appointments_patient_profile", "appointments", "patient_profiles",
        ["patient_profile_id"], ["patient_profile_id"], ondelete="RESTRICT",
    )
    op.add_column("tokens", sa.Column("patient_profile_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_tokens_patient_profile", "tokens", "patient_profiles",
        ["patient_profile_id"], ["patient_profile_id"], ondelete="RESTRICT",
    )
    op.execute(
        sa.text(
            "UPDATE appointments SET patient_profile_id = patient_profiles.patient_profile_id "
            "FROM patient_profiles WHERE patient_profiles.user_id = appointments.user_id"
        )
    )
    op.execute(
        sa.text(
            "UPDATE tokens SET patient_profile_id = patient_profiles.patient_profile_id "
            "FROM patient_profiles WHERE patient_profiles.user_id = tokens.user_id"
        )
    )

    op.create_table(
        "encounters",
        sa.Column("encounter_id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("patient_profile_id", sa.Integer(), nullable=False),
        sa.Column("hospital_id", sa.Integer(), nullable=False),
        sa.Column("dept_id", sa.Integer(), nullable=False),
        sa.Column("doctor_profile_id", sa.Integer(), nullable=True),
        sa.Column("appointment_id", sa.Integer(), nullable=True),
        sa.Column("token_id", sa.Integer(), nullable=True),
        sa.Column("encounter_type", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("chief_complaint", sa.Text(), nullable=True),
        sa.Column("clinical_notes", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("encounter_type IN ('outpatient','emergency','inpatient','telemedicine')", name="ck_encounter_type"),
        sa.CheckConstraint("status IN ('planned','in_progress','completed','cancelled')", name="ck_encounter_status"),
        sa.ForeignKeyConstraint(["appointment_id"], ["appointments.appointment_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["dept_id"], ["departments.dept_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["doctor_profile_id"], ["doctor_profiles.doctor_profile_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["hospital_id"], ["hospitals.hospital_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["patient_profile_id"], ["patient_profiles.patient_profile_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["token_id"], ["tokens.token_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("encounter_id"),
        sa.UniqueConstraint("appointment_id"),
        sa.UniqueConstraint("public_id"),
        sa.UniqueConstraint("token_id"),
    )
    op.create_index("ix_encounters_doctor_status", "encounters", ["doctor_profile_id", "status"])
    op.create_index("ix_encounters_patient_created", "encounters", ["patient_profile_id", "created_at"])

    op.create_table(
        "diagnoses",
        sa.Column("diagnosis_id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("encounter_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=True),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("author_doctor_profile_id", sa.Integer(), nullable=False),
        sa.Column("review_status", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("review_status IN ('draft','confirmed','rejected')", name="ck_diagnosis_review_status"),
        sa.ForeignKeyConstraint(["author_doctor_profile_id"], ["doctor_profiles.doctor_profile_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["encounter_id"], ["encounters.encounter_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("diagnosis_id"),
        sa.UniqueConstraint("public_id"),
    )
    op.create_index("ix_diagnoses_encounter_status", "diagnoses", ["encounter_id", "review_status"])

    op.create_table(
        "allergies",
        sa.Column("allergy_id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("patient_profile_id", sa.Integer(), nullable=False),
        sa.Column("substance", sa.String(length=160), nullable=False),
        sa.Column("severity", sa.String(length=24), nullable=False),
        sa.Column("reaction", sa.String(length=500), nullable=True),
        sa.Column("verification_status", sa.String(length=24), nullable=False),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("recorded_by_doctor_profile_id", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("severity IN ('unknown','mild','moderate','severe')", name="ck_allergy_severity"),
        sa.CheckConstraint("verification_status IN ('unverified','confirmed','rejected')", name="ck_allergy_verification"),
        sa.ForeignKeyConstraint(["patient_profile_id"], ["patient_profiles.patient_profile_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recorded_by_doctor_profile_id"], ["doctor_profiles.doctor_profile_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("allergy_id"),
        sa.UniqueConstraint("public_id"),
    )
    op.create_index("ix_allergies_patient_active", "allergies", ["patient_profile_id", "is_active"])

    op.create_table(
        "prescriptions",
        sa.Column("prescription_id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("encounter_id", sa.Integer(), nullable=False),
        sa.Column("patient_profile_id", sa.Integer(), nullable=False),
        sa.Column("author_doctor_profile_id", sa.Integer(), nullable=False),
        sa.Column("medicine", sa.String(length=200), nullable=False),
        sa.Column("dosage", sa.String(length=120), nullable=False),
        sa.Column("frequency", sa.String(length=120), nullable=False),
        sa.Column("duration", sa.String(length=120), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('active','completed','cancelled')", name="ck_prescription_status"),
        sa.ForeignKeyConstraint(["author_doctor_profile_id"], ["doctor_profiles.doctor_profile_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["encounter_id"], ["encounters.encounter_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["patient_profile_id"], ["patient_profiles.patient_profile_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("prescription_id"),
        sa.UniqueConstraint("public_id"),
    )
    op.create_index("ix_prescriptions_patient_status", "prescriptions", ["patient_profile_id", "status"])

    op.create_table(
        "vaccinations",
        sa.Column("vaccination_id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("patient_profile_id", sa.Integer(), nullable=False),
        sa.Column("vaccine_name", sa.String(length=200), nullable=False),
        sa.Column("administered_on", sa.Date(), nullable=False),
        sa.Column("dose_number", sa.String(length=40), nullable=True),
        sa.Column("lot_number", sa.String(length=80), nullable=True),
        sa.Column("provider_name", sa.String(length=160), nullable=True),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("verification_status", sa.String(length=24), nullable=False),
        sa.Column("recorded_by_doctor_profile_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("verification_status IN ('unverified','confirmed','rejected')", name="ck_vaccination_verification"),
        sa.ForeignKeyConstraint(["patient_profile_id"], ["patient_profiles.patient_profile_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recorded_by_doctor_profile_id"], ["doctor_profiles.doctor_profile_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("vaccination_id"),
        sa.UniqueConstraint("public_id"),
    )
    op.create_index("ix_vaccinations_patient_date", "vaccinations", ["patient_profile_id", "administered_on"])

    op.create_table(
        "clinical_changes",
        sa.Column("clinical_change_id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("entity_type", sa.String(length=60), nullable=False),
        sa.Column("entity_id", sa.String(length=80), nullable=False),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("context", sa.JSON(), nullable=False),
        sa.Column("before_snapshot", sa.JSON(), nullable=True),
        sa.Column("after_snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("action IN ('created','updated','status_changed','corrected')", name="ck_clinical_change_action"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.user_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("clinical_change_id"),
        sa.UniqueConstraint("public_id"),
    )
    op.create_index("ix_clinical_changes_actor_time", "clinical_changes", ["actor_user_id", "created_at"])
    op.create_index("ix_clinical_changes_entity_time", "clinical_changes", ["entity_type", "entity_id", "created_at"])


def downgrade():
    op.drop_index("ix_clinical_changes_entity_time", table_name="clinical_changes")
    op.drop_index("ix_clinical_changes_actor_time", table_name="clinical_changes")
    op.drop_table("clinical_changes")
    op.drop_index("ix_vaccinations_patient_date", table_name="vaccinations")
    op.drop_table("vaccinations")
    op.drop_index("ix_prescriptions_patient_status", table_name="prescriptions")
    op.drop_table("prescriptions")
    op.drop_index("ix_allergies_patient_active", table_name="allergies")
    op.drop_table("allergies")
    op.drop_index("ix_diagnoses_encounter_status", table_name="diagnoses")
    op.drop_table("diagnoses")
    op.drop_index("ix_encounters_patient_created", table_name="encounters")
    op.drop_index("ix_encounters_doctor_status", table_name="encounters")
    op.drop_table("encounters")
    op.drop_constraint("fk_tokens_patient_profile", "tokens", type_="foreignkey")
    op.drop_column("tokens", "patient_profile_id")
    op.drop_constraint("fk_appointments_patient_profile", "appointments", type_="foreignkey")
    op.drop_column("appointments", "patient_profile_id")
    op.drop_table("doctor_profiles")
    op.drop_table("patient_profiles")
