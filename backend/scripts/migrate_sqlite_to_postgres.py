"""One-time, non-destructive migration from legacy SQLite to a migrated target DB.

The target must be empty and must already have the Alembic schema applied. By
default the script only accepts PostgreSQL. `--allow-non-postgres` exists solely
for isolated migration tests.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import uuid
from collections import defaultdict
from datetime import date, datetime, time, timezone
from pathlib import Path

from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.orm import Session

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from auth_service import ROLE_PATIENT, assign_role, ensure_default_roles  # noqa: E402
from models import (  # noqa: E402
    AccountActivationToken,
    Appointment,
    AuditEvent,
    AuthSession,
    Allergy,
    BlockchainAuditAnchor,
    BlockchainTransaction,
    ClinicalChange,
    CrossHospitalShare,
    CrossHospitalShareHistory,
    Department,
    Diagnosis,
    Doctor,
    DoctorProfile,
    EmergencyCase,
    Encounter,
    Feedback,
    Hospital,
    IdempotencyRecord,
    LoginAttempt,
    MonitoringAlert,
    MonitoringRule,
    ObservationDefinition,
    PatientObservation,
    PasswordResetToken,
    PatientProfile,
    Prescription,
    QueueLog,
    QueueSession,
    SecurityAlert,
    SecurityAlertResolution,
    SecurityAllowlistEntry,
    SecurityBlockAction,
    SecurityEvent,
    Role,
    StaffProfile,
    SymptomsHistory,
    Token,
    User,
    UserRole,
    Vaccination,
)


MODEL_TABLES = [
    User,
    Hospital,
    Department,
    Doctor,
    QueueSession,
    Token,
    QueueLog,
    SymptomsHistory,
    EmergencyCase,
    Appointment,
    Feedback,
    IdempotencyRecord,
    AuditEvent,
    Role,
    UserRole,
    StaffProfile,
    PatientProfile,
    DoctorProfile,
    Encounter,
    Diagnosis,
    Allergy,
    Prescription,
    Vaccination,
    ClinicalChange,
    BlockchainTransaction,
    BlockchainAuditAnchor,
    CrossHospitalShare,
    CrossHospitalShareHistory,
    AuthSession,
    PasswordResetToken,
    AccountActivationToken,
    LoginAttempt,
    ObservationDefinition,
    PatientObservation,
    MonitoringRule,
    MonitoringAlert,
    SecurityEvent,
    SecurityAlert,
    SecurityBlockAction,
    SecurityAlertResolution,
    SecurityAllowlistEntry,
]


def rows(connection: sqlite3.Connection, table: str) -> list[dict]:
    return [dict(row) for row in connection.execute(f'SELECT * FROM "{table}"')]


def parse_datetime(value) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc)


def parse_date(value) -> date | None:
    if not value:
        return None
    return date.fromisoformat(str(value)[:10])


def parse_time(value) -> time | None:
    if not value:
        return None
    return time.fromisoformat(str(value))


def token_numeric(token_number: str) -> int:
    digits = "".join(character for character in token_number if character.isdigit())
    return int(digits) if digits else 0


def assert_empty(session: Session) -> None:
    # Canonical roles are installed by the Task 3 schema migration; all domain data must still be empty.
    populated = [
        model.__tablename__
        for model in MODEL_TABLES
        if model is not Role and session.scalar(select(func.count()).select_from(model))
    ]
    if populated:
        raise RuntimeError(f"Target database must be empty; populated tables: {', '.join(populated)}")


def migrate(source: Path, target_url: str, allow_non_postgres: bool = False) -> dict[str, int]:
    source_connection = sqlite3.connect(source)
    source_connection.row_factory = sqlite3.Row
    engine = create_engine(target_url, pool_pre_ping=True)
    if engine.dialect.name != "postgresql" and not allow_non_postgres:
        raise RuntimeError("Target must be PostgreSQL. Use --allow-non-postgres only for isolated tests.")

    required_tables = {model.__tablename__ for model in MODEL_TABLES}
    missing = required_tables - set(inspect(engine).get_table_names())
    if missing:
        raise RuntimeError(f"Target schema is not migrated; missing tables: {', '.join(sorted(missing))}")

    try:
        with Session(engine) as session:
            assert_empty(session)

            for row in rows(source_connection, "users"):
                session.add(
                    User(
                        user_id=row["user_id"],
                        public_id=uuid.uuid4(),
                        name=row["name"],
                        email=None,
                        phone=row.get("phone"),
                        password_hash=None,
                        age=row.get("age"),
                        gender=row.get("gender"),
                        created_at=parse_datetime(row.get("created_at")) or datetime.now(timezone.utc),
                    )
                )
            session.flush()
            ensure_default_roles(session)
            for user in session.scalars(select(User)):
                assign_role(session, user=user, role_name=ROLE_PATIENT)
                session.add(
                    PatientProfile(
                        user_id=user.user_id,
                        medical_record_number=f"MRN-{user.public_id.hex[:12].upper()}",
                    )
                )
            session.flush()
            patient_profile_ids = {
                profile.user_id: profile.patient_profile_id for profile in session.scalars(select(PatientProfile))
            }

            for row in rows(source_connection, "hospitals"):
                session.add(Hospital(**row))
            session.flush()

            for row in rows(source_connection, "departments"):
                session.add(Department(**row))
            session.flush()

            for row in rows(source_connection, "doctors"):
                session.add(Doctor(**row))
            session.flush()

            legacy_tokens = rows(source_connection, "tokens")
            grouped: dict[tuple[int, int, date], list[dict]] = defaultdict(list)
            for row in legacy_tokens:
                created = parse_datetime(row.get("created_at")) or datetime.now(timezone.utc)
                grouped[(row["hospital_id"], row["dept_id"], created.date())].append(row)

            queue_sessions: dict[tuple[int, int, date], QueueSession] = {}
            for key, token_rows in grouped.items():
                hospital_id, dept_id, queue_date = key
                queue_session = QueueSession(
                    hospital_id=hospital_id,
                    dept_id=dept_id,
                    queue_date=queue_date,
                    next_sequence=max(token_numeric(row["token_number"]) for row in token_rows) + 1,
                    status="open",
                )
                session.add(queue_session)
                session.flush()
                queue_sessions[key] = queue_session

            seen_tokens: set[tuple[int, int, date, str]] = set()
            for row in legacy_tokens:
                created = parse_datetime(row.get("created_at")) or datetime.now(timezone.utc)
                key = (row["hospital_id"], row["dept_id"], created.date(), row["token_number"])
                if key in seen_tokens:
                    raise RuntimeError(f"Duplicate legacy token prevents safe migration: {key}")
                seen_tokens.add(key)
                session.add(
                    Token(
                        token_id=row["token_id"],
                        user_id=row["user_id"],
                        patient_profile_id=patient_profile_ids[row["user_id"]],
                        hospital_id=row["hospital_id"],
                        dept_id=row["dept_id"],
                        doctor_id=row.get("doctor_id"),
                        queue_session_id=queue_sessions[key[:3]].queue_session_id,
                        queue_date=created.date(),
                        token_number=row["token_number"],
                        status=row.get("status") or "waiting",
                        priority=row.get("priority") or "normal",
                        symptoms=row.get("symptoms"),
                        estimated_time=parse_datetime(row.get("estimated_time")),
                        created_at=created,
                    )
                )
            session.flush()

            for row in rows(source_connection, "queue_logs"):
                session.add(
                    QueueLog(
                        log_id=row["log_id"],
                        dept_id=row["dept_id"],
                        log_date=parse_date(row.get("log_date")) or date.today(),
                        total_patients=row.get("total_patients") or 0,
                        avg_wait_time=row.get("avg_wait_time") or 0,
                        peak_hour=row.get("peak_hour"),
                    )
                )

            for row in rows(source_connection, "symptoms_history"):
                session.add(
                    SymptomsHistory(
                        history_id=row["history_id"],
                        user_id=row.get("user_id"),
                        symptoms=row.get("symptoms"),
                        severity_score=row.get("severity_score"),
                        predicted_department=row.get("predicted_department"),
                        visit_date=parse_date(row.get("visit_date")) or date.today(),
                    )
                )

            for row in rows(source_connection, "emergency_cases"):
                session.add(EmergencyCase(**row))

            for row in rows(source_connection, "appointments"):
                session.add(
                    Appointment(
                        appointment_id=row["appointment_id"],
                        user_id=row["user_id"],
                        patient_profile_id=patient_profile_ids[row["user_id"]],
                        doctor_id=row["doctor_id"],
                        appointment_date=parse_date(row.get("appointment_date")) or date.today(),
                        appointment_time=parse_time(row.get("appointment_time")) or time(9, 0),
                        status=row.get("status") or "Booked",
                    )
                )

            for row in rows(source_connection, "feedback"):
                created = parse_datetime(row.get("created_at"))
                if created is None:
                    created_date = parse_date(row.get("created_at")) or date.today()
                    created = datetime.combine(created_date, time.min, tzinfo=timezone.utc)
                session.add(
                    Feedback(
                        feedback_id=row["feedback_id"],
                        user_id=row["user_id"],
                        rating=row["rating"],
                        feedback_text=row.get("feedback_text"),
                        created_at=created,
                    )
                )

            session.commit()

            if engine.dialect.name == "postgresql":
                sequence_keys = {
                    "users": "user_id",
                    "hospitals": "hospital_id",
                    "departments": "dept_id",
                    "doctors": "doctor_id",
                    "queue_sessions": "queue_session_id",
                    "tokens": "token_id",
                    "queue_logs": "log_id",
                    "symptoms_history": "history_id",
                    "emergency_cases": "case_id",
                    "appointments": "appointment_id",
                    "feedback": "feedback_id",
                }
                for table_name, key_name in sequence_keys.items():
                    session.execute(
                        text(
                            f"SELECT setval(pg_get_serial_sequence('{table_name}', '{key_name}'), "
                            f"COALESCE((SELECT MAX({key_name}) FROM {table_name}), 1), true)"
                        )
                    )
                session.commit()

            return {
                model.__tablename__: int(session.scalar(select(func.count()).select_from(model)) or 0)
                for model in MODEL_TABLES
            }
    finally:
        source_connection.close()
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--target", required=True, help="SQLAlchemy PostgreSQL URL")
    parser.add_argument("--allow-non-postgres", action="store_true", help="Tests only")
    args = parser.parse_args()
    counts = migrate(args.source, args.target, args.allow_non_postgres)
    print("Migration completed with counts:")
    for table, count in counts.items():
        print(f"  {table}: {count}")


if __name__ == "__main__":
    main()
