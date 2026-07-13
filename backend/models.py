"""SQLAlchemy models for the PostgreSQL-backed MediFlow domain."""

from __future__ import annotations

import uuid
from datetime import date, datetime, time, timezone
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Float,
    Index,
    Integer,
    JSON,
    String,
    Text,
    Time,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from extensions import db


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def utc_today() -> date:
    return utcnow().date()


class SerializableMixin:
    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for column in self.__table__.columns:
            value = getattr(self, column.name)
            if isinstance(value, (datetime, date, time)):
                value = value.isoformat()
            elif isinstance(value, uuid.UUID):
                value = str(value)
            result[column.name] = value
        return result


class User(SerializableMixin, db.Model):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[uuid.UUID] = mapped_column(Uuid, default=uuid.uuid4, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), unique=True)
    phone: Mapped[str | None] = mapped_column(String(32), unique=True)
    password_hash: Mapped[str | None] = mapped_column(String(512))
    age: Mapped[int | None] = mapped_column(Integer)
    gender: Mapped[str | None] = mapped_column(String(32))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    phone_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    mfa_secret_encrypted: Mapped[str | None] = mapped_column(String(512))
    mfa_enforced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    tokens: Mapped[list["Token"]] = relationship(back_populates="user")
    role_assignments: Mapped[list["UserRole"]] = relationship(
        back_populates="user",
        foreign_keys="UserRole.user_id",
        cascade="all, delete-orphan",
    )
    auth_sessions: Mapped[list["AuthSession"]] = relationship(back_populates="user", cascade="all, delete-orphan")

    __table_args__ = (CheckConstraint("age IS NULL OR (age >= 0 AND age <= 130)", name="ck_users_age"),)


class Role(SerializableMixin, db.Model):
    __tablename__ = "roles"

    role_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    assignments: Mapped[list["UserRole"]] = relationship(back_populates="role")


class UserRole(SerializableMixin, db.Model):
    __tablename__ = "user_roles"

    user_role_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.role_id", ondelete="CASCADE"), nullable=False)
    hospital_id: Mapped[int | None] = mapped_column(ForeignKey("hospitals.hospital_id", ondelete="CASCADE"))
    assigned_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.user_id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    user: Mapped[User] = relationship(back_populates="role_assignments", foreign_keys=[user_id])
    role: Mapped[Role] = relationship(back_populates="assignments")

    __table_args__ = (
        UniqueConstraint("user_id", "role_id", "hospital_id", name="uq_user_role_hospital"),
        Index("ix_user_roles_user_hospital", "user_id", "hospital_id"),
    )


class Hospital(SerializableMixin, db.Model):
    __tablename__ = "hospitals"

    hospital_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hospital_name: Mapped[str] = mapped_column(String(160), nullable=False)
    location: Mapped[str | None] = mapped_column(String(255))
    total_doctors: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    emergency_available: Mapped[str] = mapped_column(String(16), default="Yes", nullable=False)
    avg_wait_time: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    busyness_level: Mapped[str] = mapped_column(String(32), default="Moderate", nullable=False)

    departments: Mapped[list["Department"]] = relationship(back_populates="hospital")


class Department(SerializableMixin, db.Model):
    __tablename__ = "departments"

    dept_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hospital_id: Mapped[int] = mapped_column(ForeignKey("hospitals.hospital_id", ondelete="CASCADE"), nullable=False)
    dept_name: Mapped[str] = mapped_column(String(120), nullable=False)
    avg_consult_time: Mapped[int] = mapped_column(Integer, default=10, nullable=False)

    hospital: Mapped[Hospital] = relationship(back_populates="departments")
    doctors: Mapped[list["Doctor"]] = relationship(back_populates="department")

    __table_args__ = (
        UniqueConstraint("hospital_id", "dept_name", name="uq_department_hospital_name"),
        CheckConstraint("avg_consult_time > 0", name="ck_department_consult_time"),
    )


class Doctor(SerializableMixin, db.Model):
    __tablename__ = "doctors"

    doctor_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    doctor_name: Mapped[str] = mapped_column(String(120), nullable=False)
    specialization: Mapped[str | None] = mapped_column(String(120))
    dept_id: Mapped[int] = mapped_column(ForeignKey("departments.dept_id", ondelete="CASCADE"), nullable=False)
    patients_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    availability: Mapped[str] = mapped_column(String(32), default="Available", nullable=False)

    department: Mapped[Department] = relationship(back_populates="doctors")


class StaffProfile(SerializableMixin, db.Model):
    __tablename__ = "staff_profiles"

    staff_profile_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="CASCADE"), unique=True, nullable=False)
    hospital_id: Mapped[int] = mapped_column(ForeignKey("hospitals.hospital_id", ondelete="CASCADE"), nullable=False)
    doctor_id: Mapped[int | None] = mapped_column(ForeignKey("doctors.doctor_id", ondelete="SET NULL"), unique=True)
    employee_code: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(24), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("hospital_id", "employee_code", name="uq_staff_hospital_employee"),
        CheckConstraint("status IN ('active','suspended','inactive')", name="ck_staff_status"),
    )


class PatientProfile(SerializableMixin, db.Model):
    __tablename__ = "patient_profiles"

    patient_profile_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[uuid.UUID] = mapped_column(Uuid, default=uuid.uuid4, unique=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="CASCADE"), unique=True, nullable=False)
    medical_record_number: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    blood_group: Mapped[str | None] = mapped_column(String(8))
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    emergency_contact: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    user: Mapped[User] = relationship()


class DoctorProfile(SerializableMixin, db.Model):
    __tablename__ = "doctor_profiles"

    doctor_profile_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[uuid.UUID] = mapped_column(Uuid, default=uuid.uuid4, unique=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="CASCADE"), unique=True, nullable=False)
    hospital_id: Mapped[int] = mapped_column(ForeignKey("hospitals.hospital_id", ondelete="CASCADE"), nullable=False)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctors.doctor_id", ondelete="RESTRICT"), unique=True, nullable=False)
    license_number: Mapped[str | None] = mapped_column(String(80), unique=True)
    status: Mapped[str] = mapped_column(String(24), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    user: Mapped[User] = relationship()
    doctor: Mapped[Doctor] = relationship()

    __table_args__ = (CheckConstraint("status IN ('active','suspended','inactive')", name="ck_doctor_profile_status"),)


class QueueSession(SerializableMixin, db.Model):
    __tablename__ = "queue_sessions"

    queue_session_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hospital_id: Mapped[int] = mapped_column(ForeignKey("hospitals.hospital_id", ondelete="CASCADE"), nullable=False)
    dept_id: Mapped[int] = mapped_column(ForeignKey("departments.dept_id", ondelete="CASCADE"), nullable=False)
    queue_date: Mapped[date] = mapped_column(Date, nullable=False)
    next_sequence: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="open", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("hospital_id", "dept_id", "queue_date", name="uq_queue_session_day"),
        CheckConstraint("next_sequence > 0", name="ck_queue_session_sequence"),
    )


class Token(SerializableMixin, db.Model):
    __tablename__ = "tokens"

    token_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False)
    patient_profile_id: Mapped[int | None] = mapped_column(ForeignKey("patient_profiles.patient_profile_id", ondelete="RESTRICT"))
    hospital_id: Mapped[int] = mapped_column(ForeignKey("hospitals.hospital_id", ondelete="RESTRICT"), nullable=False)
    dept_id: Mapped[int] = mapped_column(ForeignKey("departments.dept_id", ondelete="RESTRICT"), nullable=False)
    doctor_id: Mapped[int | None] = mapped_column(ForeignKey("doctors.doctor_id", ondelete="SET NULL"))
    queue_session_id: Mapped[int] = mapped_column(ForeignKey("queue_sessions.queue_session_id", ondelete="RESTRICT"), nullable=False)
    queue_date: Mapped[date] = mapped_column(Date, default=utc_today, nullable=False)
    token_number: Mapped[str] = mapped_column(String(24), nullable=False)
    tracking_code_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    tracking_code_last4: Mapped[str | None] = mapped_column(String(4))
    status: Mapped[str] = mapped_column(String(24), default="waiting", nullable=False)
    priority: Mapped[str] = mapped_column(String(24), default="normal", nullable=False)
    booked_patient_name: Mapped[str | None] = mapped_column(String(120))
    booked_patient_age: Mapped[int | None] = mapped_column(Integer)
    symptoms: Mapped[str | None] = mapped_column(Text)
    estimated_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    user: Mapped[User] = relationship(back_populates="tokens")

    __table_args__ = (
        UniqueConstraint("hospital_id", "dept_id", "queue_date", "token_number", name="uq_token_queue_number"),
        CheckConstraint("status IN ('waiting','serving','completed','missed','cancelled')", name="ck_token_status"),
        CheckConstraint("priority IN ('normal','elderly','emergency')", name="ck_token_priority"),
        Index("ix_tokens_hospital_status", "hospital_id", "status"),
        Index("ix_tokens_dept_status_created", "dept_id", "status", "created_at"),
        Index("ix_tokens_queue_priority", "queue_session_id", "status", "priority", "created_at"),
    )


class QueueLog(SerializableMixin, db.Model):
    __tablename__ = "queue_logs"

    log_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dept_id: Mapped[int] = mapped_column(ForeignKey("departments.dept_id", ondelete="CASCADE"), nullable=False)
    log_date: Mapped[date] = mapped_column(Date, nullable=False)
    total_patients: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    avg_wait_time: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    peak_hour: Mapped[str | None] = mapped_column(String(32))

    __table_args__ = (Index("ix_queue_logs_dept_date", "dept_id", "log_date"),)


class SymptomsHistory(SerializableMixin, db.Model):
    __tablename__ = "symptoms_history"

    history_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.user_id", ondelete="SET NULL"))
    symptoms: Mapped[str | None] = mapped_column(Text)
    severity_score: Mapped[int | None] = mapped_column(Integer)
    predicted_department: Mapped[str | None] = mapped_column(String(120))
    visit_date: Mapped[date] = mapped_column(Date, default=utc_today, nullable=False)


class EmergencyCase(SerializableMixin, db.Model):
    __tablename__ = "emergency_cases"

    case_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_id: Mapped[int] = mapped_column(ForeignKey("tokens.token_id", ondelete="CASCADE"), nullable=False)
    emergency_level: Mapped[str] = mapped_column(String(32), nullable=False)
    response_time: Mapped[int | None] = mapped_column(Integer)
    admitted: Mapped[str | None] = mapped_column(String(16))


class Appointment(SerializableMixin, db.Model):
    __tablename__ = "appointments"

    appointment_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    patient_profile_id: Mapped[int | None] = mapped_column(ForeignKey("patient_profiles.patient_profile_id", ondelete="RESTRICT"))
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False)
    appointment_date: Mapped[date] = mapped_column(Date, nullable=False)
    appointment_time: Mapped[time] = mapped_column(Time, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="Booked", nullable=False)


class Encounter(SerializableMixin, db.Model):
    __tablename__ = "encounters"

    encounter_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[uuid.UUID] = mapped_column(Uuid, default=uuid.uuid4, unique=True, nullable=False)
    patient_profile_id: Mapped[int] = mapped_column(ForeignKey("patient_profiles.patient_profile_id", ondelete="RESTRICT"), nullable=False)
    hospital_id: Mapped[int] = mapped_column(ForeignKey("hospitals.hospital_id", ondelete="RESTRICT"), nullable=False)
    dept_id: Mapped[int] = mapped_column(ForeignKey("departments.dept_id", ondelete="RESTRICT"), nullable=False)
    doctor_profile_id: Mapped[int | None] = mapped_column(ForeignKey("doctor_profiles.doctor_profile_id", ondelete="SET NULL"))
    appointment_id: Mapped[int | None] = mapped_column(ForeignKey("appointments.appointment_id", ondelete="SET NULL"), unique=True)
    token_id: Mapped[int | None] = mapped_column(ForeignKey("tokens.token_id", ondelete="SET NULL"), unique=True)
    encounter_type: Mapped[str] = mapped_column(String(40), default="outpatient", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="planned", nullable=False)
    chief_complaint: Mapped[str | None] = mapped_column(Text)
    clinical_notes: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('planned','in_progress','completed','cancelled')", name="ck_encounter_status"),
        CheckConstraint("encounter_type IN ('outpatient','emergency','inpatient','telemedicine')", name="ck_encounter_type"),
        Index("ix_encounters_patient_created", "patient_profile_id", "created_at"),
        Index("ix_encounters_doctor_status", "doctor_profile_id", "status"),
    )


class Diagnosis(SerializableMixin, db.Model):
    __tablename__ = "diagnoses"

    diagnosis_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[uuid.UUID] = mapped_column(Uuid, default=uuid.uuid4, unique=True, nullable=False)
    encounter_id: Mapped[int] = mapped_column(ForeignKey("encounters.encounter_id", ondelete="CASCADE"), nullable=False)
    code: Mapped[str | None] = mapped_column(String(32))
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    author_doctor_profile_id: Mapped[int] = mapped_column(ForeignKey("doctor_profiles.doctor_profile_id", ondelete="RESTRICT"), nullable=False)
    review_status: Mapped[str] = mapped_column(String(24), default="draft", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint("review_status IN ('draft','confirmed','rejected')", name="ck_diagnosis_review_status"),
        Index("ix_diagnoses_encounter_status", "encounter_id", "review_status"),
    )


class Allergy(SerializableMixin, db.Model):
    __tablename__ = "allergies"

    allergy_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[uuid.UUID] = mapped_column(Uuid, default=uuid.uuid4, unique=True, nullable=False)
    patient_profile_id: Mapped[int] = mapped_column(ForeignKey("patient_profiles.patient_profile_id", ondelete="CASCADE"), nullable=False)
    substance: Mapped[str] = mapped_column(String(160), nullable=False)
    severity: Mapped[str] = mapped_column(String(24), default="unknown", nullable=False)
    reaction: Mapped[str | None] = mapped_column(String(500))
    verification_status: Mapped[str] = mapped_column(String(24), default="unverified", nullable=False)
    source: Mapped[str] = mapped_column(String(80), default="patient_reported", nullable=False)
    recorded_by_doctor_profile_id: Mapped[int | None] = mapped_column(ForeignKey("doctor_profiles.doctor_profile_id", ondelete="SET NULL"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint("severity IN ('unknown','mild','moderate','severe')", name="ck_allergy_severity"),
        CheckConstraint("verification_status IN ('unverified','confirmed','rejected')", name="ck_allergy_verification"),
        Index("ix_allergies_patient_active", "patient_profile_id", "is_active"),
    )


class Prescription(SerializableMixin, db.Model):
    __tablename__ = "prescriptions"

    prescription_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[uuid.UUID] = mapped_column(Uuid, default=uuid.uuid4, unique=True, nullable=False)
    encounter_id: Mapped[int] = mapped_column(ForeignKey("encounters.encounter_id", ondelete="CASCADE"), nullable=False)
    patient_profile_id: Mapped[int] = mapped_column(ForeignKey("patient_profiles.patient_profile_id", ondelete="RESTRICT"), nullable=False)
    author_doctor_profile_id: Mapped[int] = mapped_column(ForeignKey("doctor_profiles.doctor_profile_id", ondelete="RESTRICT"), nullable=False)
    medicine: Mapped[str] = mapped_column(String(200), nullable=False)
    dosage: Mapped[str] = mapped_column(String(120), nullable=False)
    frequency: Mapped[str] = mapped_column(String(120), nullable=False)
    duration: Mapped[str] = mapped_column(String(120), nullable=False)
    instructions: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('active','completed','cancelled')", name="ck_prescription_status"),
        Index("ix_prescriptions_patient_status", "patient_profile_id", "status"),
    )


class Vaccination(SerializableMixin, db.Model):
    __tablename__ = "vaccinations"

    vaccination_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[uuid.UUID] = mapped_column(Uuid, default=uuid.uuid4, unique=True, nullable=False)
    patient_profile_id: Mapped[int] = mapped_column(ForeignKey("patient_profiles.patient_profile_id", ondelete="CASCADE"), nullable=False)
    vaccine_name: Mapped[str] = mapped_column(String(200), nullable=False)
    administered_on: Mapped[date] = mapped_column(Date, nullable=False)
    dose_number: Mapped[str | None] = mapped_column(String(40))
    lot_number: Mapped[str | None] = mapped_column(String(80))
    provider_name: Mapped[str | None] = mapped_column(String(160))
    source: Mapped[str] = mapped_column(String(80), default="provider_recorded", nullable=False)
    verification_status: Mapped[str] = mapped_column(String(24), default="confirmed", nullable=False)
    recorded_by_doctor_profile_id: Mapped[int | None] = mapped_column(ForeignKey("doctor_profiles.doctor_profile_id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint("verification_status IN ('unverified','confirmed','rejected')", name="ck_vaccination_verification"),
        Index("ix_vaccinations_patient_date", "patient_profile_id", "administered_on"),
    )


class ClinicalChange(SerializableMixin, db.Model):
    __tablename__ = "clinical_changes"

    clinical_change_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[uuid.UUID] = mapped_column(Uuid, default=uuid.uuid4, unique=True, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(60), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(80), nullable=False)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    context: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    before_snapshot: Mapped[dict | None] = mapped_column(JSON)
    after_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint("action IN ('created','updated','status_changed','corrected')", name="ck_clinical_change_action"),
        Index("ix_clinical_changes_entity_time", "entity_type", "entity_id", "created_at"),
        Index("ix_clinical_changes_actor_time", "actor_user_id", "created_at"),
    )


class Feedback(SerializableMixin, db.Model):
    __tablename__ = "feedback"

    feedback_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    feedback_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (CheckConstraint("rating >= 1 AND rating <= 5", name="ck_feedback_rating"),)


class IdempotencyRecord(SerializableMixin, db.Model):
    __tablename__ = "idempotency_records"

    idempotency_record_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    scope: Mapped[str] = mapped_column(String(80), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("scope", "key", name="uq_idempotency_scope_key"),
        Index("ix_idempotency_expires_at", "expires_at"),
    )


class AuditEvent(SerializableMixin, db.Model):
    __tablename__ = "audit_events"

    audit_event_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[uuid.UUID] = mapped_column(Uuid, default=uuid.uuid4, unique=True, nullable=False)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.user_id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(80), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(160))
    outcome: Mapped[str] = mapped_column(String(32), default="success", nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(64))
    remote_addr: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(255))
    details: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        Index("ix_audit_events_created_at", "created_at"),
        Index("ix_audit_events_resource", "resource_type", "resource_id"),
        Index("ix_audit_events_actor", "actor_user_id", "created_at"),
        CheckConstraint("outcome IN ('success','denied','failure')", name="ck_audit_event_outcome"),
    )


class AuthSession(SerializableMixin, db.Model):
    __tablename__ = "auth_sessions"

    auth_session_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[uuid.UUID] = mapped_column(Uuid, default=uuid.uuid4, unique=True, nullable=False)
    family_id: Mapped[uuid.UUID] = mapped_column(Uuid, default=uuid.uuid4, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    refresh_token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    replaced_by_session_id: Mapped[int | None] = mapped_column(ForeignKey("auth_sessions.auth_session_id", ondelete="SET NULL"))
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoke_reason: Mapped[str | None] = mapped_column(String(120))
    remote_addr: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(255))
    mfa_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    user: Mapped[User] = relationship(back_populates="auth_sessions", foreign_keys=[user_id])

    __table_args__ = (
        Index("ix_auth_sessions_user_expiry", "user_id", "expires_at"),
        Index("ix_auth_sessions_family", "family_id"),
    )


class PasswordResetToken(SerializableMixin, db.Model):
    __tablename__ = "password_reset_tokens"

    password_reset_token_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    requested_ip: Mapped[str | None] = mapped_column(String(64))

    __table_args__ = (Index("ix_password_reset_user_expiry", "user_id", "expires_at"),)


class AccountActivationToken(SerializableMixin, db.Model):
    __tablename__ = "account_activation_tokens"

    account_activation_token_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("ix_account_activation_user_expiry", "user_id", "expires_at"),)


class LoginAttempt(SerializableMixin, db.Model):
    __tablename__ = "login_attempts"

    login_attempt_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.user_id", ondelete="SET NULL"))
    identifier_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(80))
    remote_addr: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(255))
    session_public_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        Index("ix_login_attempt_identifier_time", "identifier_hash", "created_at"),
        Index("ix_login_attempt_ip_time", "remote_addr", "created_at"),
    )


# ---------------------------------------------------------------------------
# Task 5: Encrypted medical document pipeline
# ---------------------------------------------------------------------------

class MedicalDocument(SerializableMixin, db.Model):
    """Top-level document record owned by a patient.

    Actual file bytes are never stored here — only metadata and a reference to
    the encrypted object in the storage backend.  The SHA-256 digest is
    captured *before* encryption so integrity can be re-verified at any time.
    """

    __tablename__ = "medical_documents"

    document_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[uuid.UUID] = mapped_column(Uuid, default=uuid.uuid4, unique=True, nullable=False)
    patient_profile_id: Mapped[int] = mapped_column(
        ForeignKey("patient_profiles.patient_profile_id", ondelete="RESTRICT"), nullable=False
    )
    # Who uploaded — always a user (patient or authorized staff).
    uploaded_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False
    )
    # Optional encounter linkage.
    encounter_id: Mapped[int | None] = mapped_column(
        ForeignKey("encounters.encounter_id", ondelete="SET NULL")
    )

    # Human-visible metadata.
    document_type: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    document_date: Mapped[date | None] = mapped_column(Date)

    # Processing lifecycle state machine.
    # upload → processing → ready  (happy path)
    #                     → failed
    #                     → quarantined  (malware detected)
    # ready  → archived
    status: Mapped[str] = mapped_column(String(32), default="upload", nullable=False)

    # Verification: doctor who formally reviewed/verified the document.
    verified_by_doctor_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("doctor_profiles.doctor_profile_id", ondelete="SET NULL")
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verification_notes: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    versions: Mapped[list["DocumentVersion"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="DocumentVersion.version_number"
    )
    analysis_results: Mapped[list["DocumentAnalysisResult"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('upload','processing','ready','failed','quarantined','archived')",
            name="ck_medical_document_status",
        ),
        CheckConstraint(
            "document_type IN ("
            "'lab_report','imaging','prescription','discharge_summary',"
            "'referral','vaccination_certificate','insurance','other')",
            name="ck_medical_document_type",
        ),
        Index("ix_medical_documents_patient_status", "patient_profile_id", "status"),
        Index("ix_medical_documents_patient_created", "patient_profile_id", "created_at"),
    )


class DocumentVersion(SerializableMixin, db.Model):
    """Immutable per-version snapshot of an uploaded file.

    Each upload or replacement creates a new version row.  Versions are never
    deleted, providing a tamper-evident history.  The storage_key is an opaque
    reference understood only by the storage backend (local path fragment or
    S3 object key).  The SHA-256 hash is of the *plaintext* bytes so it can be
    independently verified after download + decryption.
    """

    __tablename__ = "document_versions"

    document_version_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[uuid.UUID] = mapped_column(Uuid, default=uuid.uuid4, unique=True, nullable=False)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("medical_documents.document_id", ondelete="RESTRICT"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)

    # File identity — captured from the original bytes before any transformation.
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False)
    sha256_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # hex digest

    # Storage — opaque key + which backend held the file.
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    storage_backend: Mapped[str] = mapped_column(String(32), nullable=False)

    # Envelope encryption metadata (key ID/label only — never the raw key).
    encryption_key_id: Mapped[str] = mapped_column(String(80), nullable=False)

    # Extracted text (plain-text, not source bytes).
    extracted_text: Mapped[str | None] = mapped_column(Text)
    extraction_method: Mapped[str | None] = mapped_column(String(40))  # 'pdf_text', 'ocr', None
    extraction_confidence: Mapped[float | None] = mapped_column()     # 0.0–1.0 for OCR
    extraction_warnings: Mapped[str | None] = mapped_column(Text)      # JSON-serialised list

    uploaded_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    document: Mapped["MedicalDocument"] = relationship(back_populates="versions")

    __table_args__ = (
        UniqueConstraint("document_id", "version_number", name="uq_document_version"),
        Index("ix_document_versions_document", "document_id", "version_number"),
        Index("ix_document_versions_hash", "sha256_hash"),
    )


class DocumentAnalysisResult(SerializableMixin, db.Model):
    """AI-generated analysis of a document version.

    Analysis is *decision support only* and requires explicit doctor review
    before it can be treated as clinically accepted.  The model_version and
    rule_version fields provide full reproducibility provenance.
    """

    __tablename__ = "document_analysis_results"

    analysis_result_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[uuid.UUID] = mapped_column(Uuid, default=uuid.uuid4, unique=True, nullable=False)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("medical_documents.document_id", ondelete="CASCADE"), nullable=False
    )
    document_version_id: Mapped[int] = mapped_column(
        ForeignKey("document_versions.document_version_id", ondelete="CASCADE"), nullable=False
    )

    # Provenance — what produced this result.
    analysis_type: Mapped[str] = mapped_column(String(80), nullable=False)  # e.g. 'lab_report_extraction'
    model_version: Mapped[str | None] = mapped_column(String(80))
    rule_version: Mapped[str | None] = mapped_column(String(80))

    # Outputs — stored as JSON to accommodate varied report types.
    extracted_biomarkers: Mapped[dict | None] = mapped_column(JSON)   # {name: {value, unit, ref_range, flag}}
    abnormal_flags: Mapped[list | None] = mapped_column(JSON)          # list of flagged biomarker names
    summary: Mapped[str | None] = mapped_column(Text)                  # plain-language assistive summary
    caveats: Mapped[list | None] = mapped_column(JSON)                  # list of caveats/warnings
    confidence_score: Mapped[float | None] = mapped_column()           # overall extraction confidence

    # Clinical workflow: pending → accepted | rejected | corrected
    review_status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False)
    reviewed_by_doctor_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("doctor_profiles.doctor_profile_id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewer_notes: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    document: Mapped["MedicalDocument"] = relationship(back_populates="analysis_results")

    __table_args__ = (
        CheckConstraint(
            "review_status IN ('pending','accepted','rejected','corrected')",
            name="ck_analysis_review_status",
        ),
        Index("ix_analysis_results_document", "document_id", "created_at"),
        Index("ix_analysis_results_review", "review_status", "document_id"),
    )


# ---------------------------------------------------------------------------
# Task 6: Disease-risk prediction
# ---------------------------------------------------------------------------

class RiskPrediction(SerializableMixin, db.Model):
    """Immutable snapshot of a disease-risk prediction.

    Input values, output scores, and model version are stored together so
    predictions are fully reproducible and auditable.  Every row is
    decision-support only; review_status tracks the doctor's acceptance.

    Design constraints (task 6.11):
    - input_snapshot is stored as JSON — no external FK into domain tables,
      so de-identified inputs cannot leak patient identity via this table.
    - output_snapshot stores the full RiskPredictionOutput dict.
    - model_version and rule_version provide complete provenance.
    - review_status mirrors DocumentAnalysisResult: pending → accepted |
      rejected | corrected.
    """

    __tablename__ = "risk_predictions"

    risk_prediction_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[uuid.UUID] = mapped_column(Uuid, default=uuid.uuid4, unique=True, nullable=False)

    # Owner linkage — patient who requested the prediction.
    patient_profile_id: Mapped[int] = mapped_column(
        ForeignKey("patient_profiles.patient_profile_id", ondelete="RESTRICT"), nullable=False
    )
    requested_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False
    )

    # Optional linkage to a document that provided the biomarker inputs.
    source_document_id: Mapped[int | None] = mapped_column(
        ForeignKey("medical_documents.document_id", ondelete="SET NULL")
    )

    # Model provenance.
    model_name: Mapped[str] = mapped_column(String(80), nullable=False)
    model_version: Mapped[str] = mapped_column(String(80), nullable=False)

    # Immutable snapshots — never overwritten.
    input_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)   # de-identified inputs
    output_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)  # full RiskPredictionOutput dict

    # Derived outputs stored separately for query convenience.
    risk_score: Mapped[float] = mapped_column(nullable=False)
    risk_band: Mapped[str] = mapped_column(String(24), nullable=False)

    # Clinical-review workflow.
    review_status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False)
    reviewed_by_doctor_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("doctor_profiles.doctor_profile_id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewer_notes: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "review_status IN ('pending','accepted','rejected','corrected')",
            name="ck_risk_prediction_review_status",
        ),
        CheckConstraint(
            "risk_band IN ('low','moderate','high','very_high')",
            name="ck_risk_prediction_band",
        ),
        Index("ix_risk_predictions_patient", "patient_profile_id", "created_at"),
        Index("ix_risk_predictions_model", "model_name", "model_version"),
        Index("ix_risk_predictions_review", "review_status", "patient_profile_id"),
    )


# ---------------------------------------------------------------------------
# Task 7: Consent and authorization domain
# ---------------------------------------------------------------------------

# Scopes define which record categories a consent grant covers (7.2).
# These are stored as a JSON list on ConsentGrant.scopes.
# Valid scope values:
CONSENT_SCOPES = frozenset({
    "summary",          # patient profile summary, demographics
    "encounters",       # encounter notes and visit history
    "diagnoses",        # diagnosis records
    "prescriptions",    # medication records
    "allergies",        # allergy records
    "vaccinations",     # vaccination records
    "reports",          # uploaded medical documents and analysis results
    "risk_predictions", # disease-risk prediction results
    "monitoring",       # vital-sign observations and alerts (task 10)
})

BREAK_GLASS_DURATION_HOURS = 4  # maximum break-glass session duration


class ConsentGrant(SerializableMixin, db.Model):
    """A patient's explicit consent grant to a doctor (or hospital) for
    access to specific record scopes for a bounded purpose and time window.

    Lifecycle (7.1):
      pending  → granted | denied          (patient acts on a request)
      granted  → revoked                   (patient revokes)
      granted  → expired                   (set automatically at check time)
      *        → break_glass               (emergency override by doctor)

    Break-glass rows are a separate grant with status='break_glass' and
    a short, mandatory expiry.  They are audited with enhanced detail (7.7).

    Scope enforcement (7.6) happens in consent_service.check_consent_scope()
    which is called from authorization.authorize_clinical_access().
    """

    __tablename__ = "consent_grants"

    consent_grant_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[uuid.UUID] = mapped_column(Uuid, default=uuid.uuid4, unique=True, nullable=False)

    # Parties
    patient_profile_id: Mapped[int] = mapped_column(
        ForeignKey("patient_profiles.patient_profile_id", ondelete="RESTRICT"), nullable=False
    )
    requesting_doctor_profile_id: Mapped[int] = mapped_column(
        ForeignKey("doctor_profiles.doctor_profile_id", ondelete="RESTRICT"), nullable=False
    )
    # Requesting hospital — may differ from the doctor's home hospital for
    # cross-hospital sharing scenarios (task 9).
    requesting_hospital_id: Mapped[int] = mapped_column(
        ForeignKey("hospitals.hospital_id", ondelete="RESTRICT"), nullable=False
    )

    # What is being requested / granted
    scopes: Mapped[list] = mapped_column(JSON, nullable=False)          # list[str] from CONSENT_SCOPES
    purpose: Mapped[str] = mapped_column(String(500), nullable=False)   # plain-text reason for access
    operation: Mapped[str] = mapped_column(String(80), nullable=False)  # e.g. "treatment", "second_opinion"

    # Lifecycle
    status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False)
    # When access is valid (patient sets these on grant)
    access_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    access_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Revocation / denial metadata
    denied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    denied_reason: Mapped[str | None] = mapped_column(String(500))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_reason: Mapped[str | None] = mapped_column(String(500))
    # Break-glass fields (7.7)
    is_break_glass: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    break_glass_reason: Mapped[str | None] = mapped_column(Text)  # mandatory for break-glass

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    status_history: Mapped[list["ConsentStatusHistory"]] = relationship(
        back_populates="consent_grant", cascade="all, delete-orphan",
        order_by="ConsentStatusHistory.created_at"
    )
    notifications: Mapped[list["ConsentNotification"]] = relationship(
        back_populates="consent_grant", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','granted','denied','revoked','expired','break_glass')",
            name="ck_consent_grant_status",
        ),
        CheckConstraint(
            "operation IN ('treatment','second_opinion','research_review','referral','emergency','other')",
            name="ck_consent_grant_operation",
        ),
        # A doctor can have only one active (pending or granted) request per patient.
        # Additional requests require the prior one to be resolved first.
        Index("ix_consent_grants_patient_status", "patient_profile_id", "status"),
        Index("ix_consent_grants_doctor_patient", "requesting_doctor_profile_id", "patient_profile_id"),
        Index("ix_consent_grants_expiry", "access_expires_at", "status"),
    )


class ConsentStatusHistory(SerializableMixin, db.Model):
    """Immutable append-only log of every status transition on a ConsentGrant.

    Every grant, denial, revocation, expiry, and break-glass event writes
    a row here so the full lifecycle is auditable (7.1, Milestone 7).
    """

    __tablename__ = "consent_status_history"

    consent_status_history_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    consent_grant_id: Mapped[int] = mapped_column(
        ForeignKey("consent_grants.consent_grant_id", ondelete="CASCADE"), nullable=False
    )
    from_status: Mapped[str] = mapped_column(String(24), nullable=False)
    to_status: Mapped[str] = mapped_column(String(24), nullable=False)
    actor_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False
    )
    reason: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    consent_grant: Mapped["ConsentGrant"] = relationship(back_populates="status_history")

    __table_args__ = (
        Index("ix_consent_status_history_grant", "consent_grant_id", "created_at"),
    )


class ConsentNotification(SerializableMixin, db.Model):
    """In-app notification event triggered by consent lifecycle changes (7.8).

    The patient receives notifications when a doctor requests access.
    The doctor receives notifications when the patient grants, denies,
    revokes, or when break-glass access is used.

    notification_type values:
      access_requested  — doctor submitted a new consent request
      access_granted    — patient granted the request
      access_denied     — patient denied the request
      access_revoked    — patient revoked a previously granted consent
      consent_expired   — a grant expired automatically
      break_glass_used  — doctor invoked emergency break-glass access
    """

    __tablename__ = "consent_notifications"

    consent_notification_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[uuid.UUID] = mapped_column(Uuid, default=uuid.uuid4, unique=True, nullable=False)
    consent_grant_id: Mapped[int] = mapped_column(
        ForeignKey("consent_grants.consent_grant_id", ondelete="CASCADE"), nullable=False
    )
    recipient_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    notification_type: Mapped[str] = mapped_column(String(60), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    consent_grant: Mapped["ConsentGrant"] = relationship(back_populates="notifications")

    __table_args__ = (
        CheckConstraint(
            "notification_type IN ("
            "'access_requested','access_granted','access_denied',"
            "'access_revoked','consent_expired','break_glass_used')",
            name="ck_consent_notification_type",
        ),
        Index("ix_consent_notifications_recipient_read", "recipient_user_id", "is_read", "created_at"),
        Index("ix_consent_notifications_grant", "consent_grant_id"),
    )


class BlockchainTransaction(SerializableMixin, db.Model):
    """Asynchronous blockchain outbox and transaction receipt metadata.

    `proof_payload` is restricted by the service layer to bytes32-compatible
    hashes. Direct identifiers, filenames, consent purposes, and medical
    content are never stored in this payload or submitted to the contract.
    """

    __tablename__ = "blockchain_transactions"

    blockchain_transaction_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[uuid.UUID] = mapped_column(Uuid, default=uuid.uuid4, unique=True, nullable=False)
    operation: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(60), nullable=False)
    entity_reference_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    proof_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    document_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("document_versions.document_version_id", ondelete="SET NULL")
    )
    consent_grant_id: Mapped[int | None] = mapped_column(
        ForeignKey("consent_grants.consent_grant_id", ondelete="SET NULL")
    )
    chain_id: Mapped[int | None] = mapped_column(Integer)
    contract_address: Mapped[str | None] = mapped_column(String(42))
    transaction_hash: Mapped[str | None] = mapped_column(String(66), unique=True)
    block_number: Mapped[int | None] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(24), default="pending", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "operation IN ('record_register','consent_grant','consent_revoke','audit_anchor')",
            name="ck_blockchain_transaction_operation",
        ),
        CheckConstraint(
            "state IN ('pending','submitted','confirmed','failed','retry')",
            name="ck_blockchain_transaction_state",
        ),
        CheckConstraint("attempts >= 0", name="ck_blockchain_transaction_attempts"),
        UniqueConstraint("operation", "entity_reference_hash", name="uq_blockchain_operation_entity"),
        Index("ix_blockchain_transactions_state_retry", "state", "next_retry_at"),
        Index("ix_blockchain_transactions_document", "document_version_id", "operation"),
        Index("ix_blockchain_transactions_consent", "consent_grant_id", "operation"),
    )


class BlockchainAuditAnchor(SerializableMixin, db.Model):
    __tablename__ = "blockchain_audit_anchors"

    blockchain_audit_anchor_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[uuid.UUID] = mapped_column(Uuid, default=uuid.uuid4, unique=True, nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_reference_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    merkle_root: Mapped[str] = mapped_column(String(64), nullable=False)
    event_count: Mapped[int] = mapped_column(Integer, nullable=False)
    blockchain_transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("blockchain_transactions.blockchain_transaction_id", ondelete="SET NULL"), unique=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint("period_end > period_start", name="ck_blockchain_audit_anchor_period"),
        CheckConstraint("event_count >= 0", name="ck_blockchain_audit_anchor_event_count"),
        Index("ix_blockchain_audit_anchors_period", "period_start", "period_end"),
    )


# ---------------------------------------------------------------------------
# Task 9: Secure cross-hospital sharing
# ---------------------------------------------------------------------------

class CrossHospitalShare(SerializableMixin, db.Model):
    """A patient-authorised cross-hospital data-sharing agreement.

    Architecture (9.1 / 9.2)
    ------------------------
    Cross-hospital sharing is modelled as a first-class entity separate from
    same-hospital ConsentGrant rows.  It captures all the same consent
    semantics (scopes, purpose, operation, expiry, status history) plus the
    two-hospital context (source vs requesting) needed for tenant checks (9.5).

    Lifecycle:
      pending   → granted  (patient approves)
                → denied   (patient rejects)
      granted   → revoked  (patient revokes — immediate)
                → expired  (lazy at access time — 9.5 enforcement)

    Sharing rules enforced at service layer (not routes):
    - Only the source hospital's patient data can be shared (9.5).
    - The requesting hospital must be different from the source (same-hospital
      access uses ConsentGrant, not CrossHospitalShare).
    - No raw storage paths or document URLs are returned in shared responses;
      shared document payloads contain only metadata (9.4).
    - Responses project only the approved scopes (9.3 minimum-necessary).
    - Every data access (success, denial, expiry, revocation, break-glass) is
      audited (9.6).
    """

    __tablename__ = "cross_hospital_shares"

    share_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, default=uuid.uuid4, unique=True, nullable=False
    )

    # Patient who owns the data being shared.
    patient_profile_id: Mapped[int] = mapped_column(
        ForeignKey("patient_profiles.patient_profile_id", ondelete="RESTRICT"),
        nullable=False,
    )
    # Hospital where the patient's data lives.
    source_hospital_id: Mapped[int] = mapped_column(
        ForeignKey("hospitals.hospital_id", ondelete="RESTRICT"),
        nullable=False,
    )
    # Hospital requesting access (must differ from source_hospital_id).
    requesting_hospital_id: Mapped[int] = mapped_column(
        ForeignKey("hospitals.hospital_id", ondelete="RESTRICT"),
        nullable=False,
    )
    # Doctor at the requesting hospital who submitted the share request.
    requesting_doctor_profile_id: Mapped[int] = mapped_column(
        ForeignKey("doctor_profiles.doctor_profile_id", ondelete="RESTRICT"),
        nullable=False,
    )

    # Consent semantics — reused from Task 7 (9.2).
    scopes: Mapped[list] = mapped_column(JSON, nullable=False)
    purpose: Mapped[str] = mapped_column(String(500), nullable=False)
    operation: Mapped[str] = mapped_column(String(80), nullable=False)
    requested_duration_days: Mapped[int] = mapped_column(Integer, default=30, nullable=False)

    # Lifecycle.
    status: Mapped[str] = mapped_column(
        String(24), default="pending", nullable=False
    )
    access_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    access_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Resolution metadata.
    denied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    denied_reason: Mapped[str | None] = mapped_column(String(500))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_reason: Mapped[str | None] = mapped_column(String(500))
    is_break_glass: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    break_glass_reason: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','granted','denied','revoked','expired','break_glass')",
            name="ck_cross_hospital_share_status",
        ),
        CheckConstraint(
            "operation IN ('treatment','second_opinion','research_review','referral','emergency','other')",
            name="ck_cross_hospital_share_operation",
        ),
        # Requesting hospital must differ from source hospital.
        CheckConstraint(
            "source_hospital_id != requesting_hospital_id",
            name="ck_cross_hospital_share_different_hospitals",
        ),
        Index(
            "ix_cross_hospital_shares_patient_status",
            "patient_profile_id",
            "status",
        ),
        Index(
            "ix_cross_hospital_shares_requesting",
            "requesting_hospital_id",
            "requesting_doctor_profile_id",
        ),
        Index(
            "ix_cross_hospital_shares_expiry",
            "access_expires_at",
            "status",
        ),
    )


class CrossHospitalShareHistory(SerializableMixin, db.Model):
    """Immutable append-only cross-hospital share lifecycle."""

    __tablename__ = "cross_hospital_share_history"

    share_history_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    share_id: Mapped[int] = mapped_column(
        ForeignKey("cross_hospital_shares.share_id", ondelete="CASCADE"), nullable=False
    )
    from_status: Mapped[str | None] = mapped_column(String(24))
    to_status: Mapped[str] = mapped_column(String(24), nullable=False)
    actor_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False
    )
    reason: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        Index("ix_cross_hospital_share_history_share", "share_id", "created_at"),
    )


# ---------------------------------------------------------------------------
# Task 10: Patient monitoring and realtime alerts
# ---------------------------------------------------------------------------

OBSERVATION_TYPES = frozenset({
    "heart_rate", "blood_pressure", "blood_oxygen", "temperature", "blood_glucose", "respiratory_rate",
})


class ObservationDefinition(SerializableMixin, db.Model):
    __tablename__ = "observation_definitions"

    observation_definition_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    unit: Mapped[str] = mapped_column(String(24), nullable=False)
    secondary_unit: Mapped[str | None] = mapped_column(String(24))
    value_min: Mapped[float] = mapped_column(Float, nullable=False)
    value_max: Mapped[float] = mapped_column(Float, nullable=False)
    secondary_value_min: Mapped[float | None] = mapped_column(Float)
    secondary_value_max: Mapped[float | None] = mapped_column(Float)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint("value_max > value_min", name="ck_observation_definition_range"),
    )


class PatientObservation(SerializableMixin, db.Model):
    __tablename__ = "patient_observations"

    observation_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[uuid.UUID] = mapped_column(Uuid, default=uuid.uuid4, unique=True, nullable=False)
    patient_profile_id: Mapped[int] = mapped_column(
        ForeignKey("patient_profiles.patient_profile_id", ondelete="CASCADE"), nullable=False
    )
    observation_type: Mapped[str] = mapped_column(String(40), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    secondary_value: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(24), nullable=False)
    source: Mapped[str] = mapped_column(String(24), nullable=False)
    source_reference: Mapped[str | None] = mapped_column(String(160))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "observation_type IN ('heart_rate','blood_pressure','blood_oxygen','temperature','blood_glucose','respiratory_rate')",
            name="ck_patient_observation_type",
        ),
        CheckConstraint("source IN ('manual','device','simulator')", name="ck_patient_observation_source"),
        Index("ix_patient_observations_patient_recorded", "patient_profile_id", "recorded_at"),
        Index("ix_patient_observations_type_recorded", "observation_type", "recorded_at"),
    )


class MonitoringRule(SerializableMixin, db.Model):
    __tablename__ = "monitoring_rules"

    monitoring_rule_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[uuid.UUID] = mapped_column(Uuid, default=uuid.uuid4, unique=True, nullable=False)
    hospital_id: Mapped[int | None] = mapped_column(
        ForeignKey("hospitals.hospital_id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    observation_type: Mapped[str] = mapped_column(String(40), nullable=False)
    minimum_value: Mapped[float | None] = mapped_column(Float)
    maximum_value: Mapped[float | None] = mapped_column(Float)
    secondary_minimum_value: Mapped[float | None] = mapped_column(Float)
    secondary_maximum_value: Mapped[float | None] = mapped_column(Float)
    trend_window_count: Mapped[int | None] = mapped_column(Integer)
    trend_delta: Mapped[float | None] = mapped_column(Float)
    severity: Mapped[str] = mapped_column(String(16), default="warning", nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.user_id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "observation_type IN ('heart_rate','blood_pressure','blood_oxygen','temperature','blood_glucose','respiratory_rate')",
            name="ck_monitoring_rule_type",
        ),
        CheckConstraint("severity IN ('info','warning','critical')", name="ck_monitoring_rule_severity"),
        Index("ix_monitoring_rules_hospital_type", "hospital_id", "observation_type", "is_enabled"),
    )


class MonitoringAlert(SerializableMixin, db.Model):
    __tablename__ = "monitoring_alerts"

    monitoring_alert_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[uuid.UUID] = mapped_column(Uuid, default=uuid.uuid4, unique=True, nullable=False)
    patient_profile_id: Mapped[int] = mapped_column(
        ForeignKey("patient_profiles.patient_profile_id", ondelete="CASCADE"), nullable=False
    )
    observation_id: Mapped[int] = mapped_column(
        ForeignKey("patient_observations.observation_id", ondelete="CASCADE"), nullable=False
    )
    monitoring_rule_id: Mapped[int] = mapped_column(
        ForeignKey("monitoring_rules.monitoring_rule_id", ondelete="RESTRICT"), nullable=False
    )
    hospital_id: Mapped[int | None] = mapped_column(
        ForeignKey("hospitals.hospital_id", ondelete="SET NULL")
    )
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False)
    message: Mapped[str] = mapped_column(String(500), nullable=False)
    assigned_doctor_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("doctor_profiles.doctor_profile_id", ondelete="SET NULL")
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.user_id", ondelete="SET NULL")
    )
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_notes: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.user_id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint("severity IN ('info','warning','critical')", name="ck_monitoring_alert_severity"),
        CheckConstraint(
            "status IN ('open','acknowledged','escalated','resolved')",
            name="ck_monitoring_alert_status",
        ),
        Index("ix_monitoring_alerts_hospital_status", "hospital_id", "status", "created_at"),
        Index("ix_monitoring_alerts_patient_created", "patient_profile_id", "created_at"),
    )


# ---------------------------------------------------------------------------
# Task 12: Cybersecurity event collection and threat detection
# ---------------------------------------------------------------------------

class SecurityEvent(SerializableMixin, db.Model):
    __tablename__ = "security_events"

    security_event_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[uuid.UUID] = mapped_column(Uuid, default=uuid.uuid4, unique=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), default="info", nullable=False)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.user_id", ondelete="SET NULL"))
    subject_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.user_id", ondelete="SET NULL"))
    auth_session_id: Mapped[int | None] = mapped_column(ForeignKey("auth_sessions.auth_session_id", ondelete="SET NULL"))
    resource_type: Mapped[str | None] = mapped_column(String(80))
    resource_id: Mapped[str | None] = mapped_column(String(160))
    request_id: Mapped[str | None] = mapped_column(String(64))
    ip_hash: Mapped[str | None] = mapped_column(String(64))
    device_hash: Mapped[str | None] = mapped_column(String(64))
    safe_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    feature_vector: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    anomaly_score: Mapped[float | None] = mapped_column(Float)
    anomaly_model: Mapped[str | None] = mapped_column(String(80))
    anomaly_advisory: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    training_label: Mapped[str | None] = mapped_column(String(24))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint("severity IN ('info','low','medium','high','critical')", name="ck_security_event_severity"),
        CheckConstraint("outcome IN ('success','denied','failure')", name="ck_security_event_outcome"),
        Index("ix_security_events_type_created", "event_type", "created_at"),
        Index("ix_security_events_actor_created", "actor_user_id", "created_at"),
        Index("ix_security_events_ip_created", "ip_hash", "created_at"),
        Index("ix_security_events_category_severity", "category", "severity", "created_at"),
    )


class SecurityAlert(SerializableMixin, db.Model):
    __tablename__ = "security_alerts"

    security_alert_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[uuid.UUID] = mapped_column(Uuid, default=uuid.uuid4, unique=True, nullable=False)
    rule_code: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(String(700), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    anomaly_score: Mapped[float | None] = mapped_column(Float)
    anomaly_advisory: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    subject_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.user_id", ondelete="SET NULL"))
    subject_ip_hash: Mapped[str | None] = mapped_column(String(64))
    assigned_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.user_id", ondelete="SET NULL"))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint("severity IN ('low','medium','high','critical')", name="ck_security_alert_severity"),
        CheckConstraint("status IN ('open','acknowledged','investigating','resolved','dismissed')", name="ck_security_alert_status"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_security_alert_confidence"),
        Index("ix_security_alerts_status_severity", "status", "severity", "created_at"),
        Index("ix_security_alerts_rule_subject", "rule_code", "subject_user_id", "created_at"),
    )


class SecurityBlockAction(SerializableMixin, db.Model):
    __tablename__ = "security_block_actions"

    security_block_action_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[uuid.UUID] = mapped_column(Uuid, default=uuid.uuid4, unique=True, nullable=False)
    target_type: Mapped[str] = mapped_column(String(16), nullable=False)
    target_hash: Mapped[str | None] = mapped_column(String(64))
    target_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.user_id", ondelete="CASCADE"))
    target_session_id: Mapped[int | None] = mapped_column(ForeignKey("auth_sessions.auth_session_id", ondelete="CASCADE"))
    rule_code: Mapped[str] = mapped_column(String(80), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    automated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.user_id", ondelete="SET NULL"))
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    released_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.user_id", ondelete="SET NULL"))
    release_reason: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint("target_type IN ('account','session','ip')", name="ck_security_block_target"),
        Index("ix_security_blocks_active_expiry", "is_active", "expires_at"),
        Index("ix_security_blocks_user_active", "target_user_id", "is_active"),
        Index("ix_security_blocks_hash_active", "target_hash", "is_active"),
    )


class SecurityAlertResolution(SerializableMixin, db.Model):
    __tablename__ = "security_alert_resolutions"

    security_alert_resolution_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    security_alert_id: Mapped[int] = mapped_column(ForeignKey("security_alerts.security_alert_id", ondelete="CASCADE"), nullable=False)
    action: Mapped[str] = mapped_column(String(24), nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False)
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint("action IN ('acknowledged','investigating','resolved','dismissed','reopened')", name="ck_security_resolution_action"),
        Index("ix_security_resolutions_alert_created", "security_alert_id", "created_at"),
    )


class SecurityAllowlistEntry(SerializableMixin, db.Model):
    __tablename__ = "security_allowlist_entries"

    security_allowlist_entry_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    target_type: Mapped[str] = mapped_column(String(16), nullable=False)
    target_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(String(300), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.user_id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint("target_type IN ('account','ip','device')", name="ck_security_allowlist_target"),
        UniqueConstraint("target_type", "target_hash", name="uq_security_allowlist_target"),
    )


# ---------------------------------------------------------------------------
# Task 11: Telemedicine
# ---------------------------------------------------------------------------

class TelemedicineSession(SerializableMixin, db.Model):
    """Telemedicine session record tied to an appointment and encounter.

    Design rules (11.2 – 11.9):
    - A session is created when a doctor confirms a telemedicine appointment.
    - room_reference is an opaque identifier understood by the configured
      provider (Jitsi room name).  It is NEVER exposed to unauthenticated
      callers — short-lived JWT room tokens are issued instead (11.6).
    - audio/video recording is OFF by default; the field documents intent
      only and does NOT enable recording infrastructure (11.8).
    - Every status transition writes an AuditEvent row (11.9).
    - consultation_notes, diagnoses, and prescriptions are attached via
      the linked Encounter row (11.7).

    Lifecycle:
      scheduled  → confirmed   (doctor confirms)
                 → cancelled   (doctor or patient cancels before start)
      confirmed  → patient_waiting  (patient joins waiting room)
                 → doctor_waiting   (doctor joins waiting room)
                 → in_progress      (both join — first join sets respective state)
                 → cancelled
      in_progress → completed  (doctor completes and records outcome)
    """

    __tablename__ = "telemedicine_sessions"

    session_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, default=uuid.uuid4, unique=True, nullable=False
    )

    # Required linkages
    appointment_id: Mapped[int] = mapped_column(
        ForeignKey("appointments.appointment_id", ondelete="RESTRICT"),
        unique=True,
        nullable=False,
    )
    encounter_id: Mapped[int | None] = mapped_column(
        ForeignKey("encounters.encounter_id", ondelete="SET NULL"),
        unique=True,
    )
    patient_profile_id: Mapped[int] = mapped_column(
        ForeignKey("patient_profiles.patient_profile_id", ondelete="RESTRICT"),
        nullable=False,
    )
    doctor_profile_id: Mapped[int] = mapped_column(
        ForeignKey("doctor_profiles.doctor_profile_id", ondelete="RESTRICT"),
        nullable=False,
    )

    # Provider and room (11.3)
    provider: Mapped[str] = mapped_column(
        String(40), default="jitsi", nullable=False
    )  # "jitsi" | "webrtc_custom"
    # Opaque room identifier — never returned without a signed room token (11.6)
    room_reference: Mapped[str] = mapped_column(String(255), nullable=False)

    # Schedule
    scheduled_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    scheduled_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Actual join/leave times (11.2)
    patient_joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    patient_left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    doctor_joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    doctor_left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Lifecycle status (11.5)
    status: Mapped[str] = mapped_column(
        String(32), default="scheduled", nullable=False
    )

    # Cancellation / reschedule metadata
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.user_id", ondelete="SET NULL")
    )
    cancel_reason: Mapped[str | None] = mapped_column(String(500))

    # Completion
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consultation_summary: Mapped[str | None] = mapped_column(Text)

    # 11.8 — audio/video recording is OFF by default.
    # This field documents the configured intent; it does NOT enable
    # recording infrastructure.  Default is False and must remain False
    # unless explicitly set by an authorised admin.
    recording_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ("
            "'scheduled','confirmed','patient_waiting','doctor_waiting',"
            "'in_progress','completed','cancelled')",
            name="ck_telemedicine_session_status",
        ),
        CheckConstraint(
            "provider IN ('jitsi','webrtc_custom')",
            name="ck_telemedicine_session_provider",
        ),
        Index("ix_telemedicine_sessions_patient", "patient_profile_id", "status"),
        Index("ix_telemedicine_sessions_doctor", "doctor_profile_id", "status"),
        Index("ix_telemedicine_sessions_scheduled", "scheduled_start", "status"),
    )
