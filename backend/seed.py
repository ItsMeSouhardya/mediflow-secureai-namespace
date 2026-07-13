"""Deterministic demo data for fresh development databases."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from auth_service import ROLE_PATIENT, assign_role, ensure_default_roles, hash_password
from models import (
    Appointment,
    Department,
    Doctor,
    Feedback,
    Hospital,
    PatientProfile,
    QueueLog,
    QueueSession,
    SymptomsHistory,
    Token,
    User,
)


def seed_demo_data(session: Session) -> None:
    if session.scalar(select(func.count(Hospital.hospital_id))):
        return

    hospitals = [
        Hospital(hospital_name="City Hospital", location="Kolkata", total_doctors=40, emergency_available="Yes", avg_wait_time=45, busyness_level="High"),
        Hospital(hospital_name="District Hospital", location="Howrah", total_doctors=30, emergency_available="Yes", avg_wait_time=30, busyness_level="Moderate"),
        Hospital(hospital_name="Apollo Lifeline", location="Salt Lake", total_doctors=35, emergency_available="Yes", avg_wait_time=20, busyness_level="Low"),
    ]
    session.add_all(hospitals)
    session.flush()

    department_specs = [
        ("General Medicine", 10),
        ("Orthopedic", 15),
        ("Dental", 15),
        ("Cardiology", 20),
        ("Pediatrics", 10),
        ("ENT", 12),
    ]
    departments: list[Department] = []
    for hospital in hospitals:
        for name, duration in department_specs:
            departments.append(
                Department(
                    hospital_id=hospital.hospital_id,
                    dept_name=name,
                    avg_consult_time=duration,
                )
            )
    session.add_all(departments)
    session.flush()

    doctor_names = ["Dr. Sharma", "Dr. Roy", "Dr. Das", "Dr. Gupta", "Dr. Sen", "Dr. Bose"]
    doctors: list[Doctor] = []
    for index, department in enumerate(departments):
        for offset in range(2):
            doctors.append(
                Doctor(
                    doctor_name=doctor_names[(index + offset) % len(doctor_names)],
                    specialization=department.dept_name,
                    dept_id=department.dept_id,
                    patients_today=5 + ((index * 2 + offset) % 12),
                    availability="Available" if offset == 0 else "Busy",
                )
            )
    session.add_all(doctors)
    session.flush()

    users = [
        User(
            name="Ramesh",
            email="patient@mediflow.test",
            password_hash=hash_password("PatientDemo!123"),
            email_verified_at=datetime.now(timezone.utc),
            phone="9876543210",
            age=45,
            gender="Male",
        ),
        User(name="Sita", phone="9123456780", age=60, gender="Female"),
        User(name="Rahul", phone="9988776655", age=25, gender="Male"),
        User(name="Priya", phone="8877665544", age=32, gender="Female"),
        User(name="Amit", phone="9000000001", age=34, gender="Male"),
        User(name="Ananya", phone="9000000004", age=22, gender="Female"),
        User(name="Karan", phone="9000000005", age=39, gender="Male"),
        User(name="Neha", phone="9000000006", age=48, gender="Female"),
    ]
    session.add_all(users)
    session.flush()
    patient_profiles = [
        PatientProfile(
            user_id=user.user_id,
            medical_record_number=f"MRN-{user.public_id.hex[:12].upper()}",
        )
        for user in users
    ]
    session.add_all(patient_profiles)
    session.flush()
    ensure_default_roles(session)
    for user in users:
        assign_role(session, user=user, role_name=ROLE_PATIENT)

    now = datetime.now(timezone.utc)
    today = now.date()
    status_pattern = ["waiting", "waiting", "completed", "missed"]
    priority_pattern = ["normal", "elderly", "normal", "emergency"]
    for dept_index, department in enumerate(departments):
        queue_session = QueueSession(
            hospital_id=department.hospital_id,
            dept_id=department.dept_id,
            queue_date=today,
            next_sequence=5,
            status="open",
        )
        session.add(queue_session)
        session.flush()
        dept_doctors = [doctor for doctor in doctors if doctor.dept_id == department.dept_id]
        for sequence in range(1, 5):
            session.add(
                Token(
                    user_id=users[(dept_index + sequence) % len(users)].user_id,
                    patient_profile_id=patient_profiles[(dept_index + sequence) % len(users)].patient_profile_id,
                    hospital_id=department.hospital_id,
                    dept_id=department.dept_id,
                    doctor_id=dept_doctors[0].doctor_id,
                    queue_session_id=queue_session.queue_session_id,
                    queue_date=today,
                    token_number=f"A{sequence:03d}",
                    status=status_pattern[sequence - 1],
                    priority=priority_pattern[sequence - 1],
                    symptoms="Regular checkup",
                    created_at=now + timedelta(seconds=sequence),
                )
            )
        for days_ago in range(3):
            session.add(
                QueueLog(
                    dept_id=department.dept_id,
                    log_date=today - timedelta(days=days_ago),
                    total_patients=60 + dept_index * 3 + days_ago,
                    avg_wait_time=25 + (dept_index % 6) * 5,
                    peak_hour=["11AM-1PM", "10AM-12PM", "12PM-2PM"][days_ago],
                )
            )

    session.add_all(
        [
            SymptomsHistory(user_id=users[0].user_id, symptoms="fever and cough", severity_score=2, predicted_department="General Medicine", visit_date=today),
            SymptomsHistory(user_id=users[1].user_id, symptoms="chest pain", severity_score=5, predicted_department="Cardiology", visit_date=today),
            Appointment(user_id=users[0].user_id, patient_profile_id=patient_profiles[0].patient_profile_id, doctor_id=doctors[0].doctor_id, appointment_date=today + timedelta(days=1), appointment_time=time(10, 0), status="Booked"),
            Feedback(user_id=users[0].user_id, rating=5, feedback_text="Very smooth process"),
        ]
    )
