"""Electronic health record queries and mutation rules."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import exists, or_, select
from sqlalchemy.orm import Session

from errors import ApiProblem
from models import (
    Allergy,
    Appointment,
    ClinicalChange,
    Department,
    Diagnosis,
    Doctor,
    DoctorProfile,
    Encounter,
    Hospital,
    PatientProfile,
    Prescription,
    Token,
    User,
    Vaccination,
)


def ensure_patient_profile(session: Session, user: User) -> PatientProfile:
    profile = session.scalar(select(PatientProfile).where(PatientProfile.user_id == user.user_id))
    if profile:
        return profile
    profile = PatientProfile(
        user_id=user.user_id,
        medical_record_number=f"MRN-{user.public_id.hex[:12].upper()}",
    )
    session.add(profile)
    session.flush()
    return profile


def patient_profile_by_public_id(session: Session, public_id: UUID) -> PatientProfile:
    profile = session.scalar(select(PatientProfile).where(PatientProfile.public_id == public_id))
    if profile is None:
        raise ApiProblem("patient_not_found", "Patient profile not found", 404)
    return profile


def doctor_profile_for_user(session: Session, user_id: int) -> DoctorProfile:
    profile = session.scalar(
        select(DoctorProfile).where(DoctorProfile.user_id == user_id, DoctorProfile.status == "active")
    )
    if profile is None:
        raise ApiProblem("doctor_profile_required", "An active doctor profile is required", 403)
    return profile


def has_doctor_care_relationship(session: Session, doctor: DoctorProfile, patient: PatientProfile) -> bool:
    appointment = session.scalar(
        select(exists().where(
            Appointment.patient_profile_id == patient.patient_profile_id,
            Appointment.doctor_id == doctor.doctor_id,
        ))
    )
    token = session.scalar(
        select(exists().where(
            Token.patient_profile_id == patient.patient_profile_id,
            Token.doctor_id == doctor.doctor_id,
        ))
    )
    encounter = session.scalar(
        select(exists().where(
            Encounter.patient_profile_id == patient.patient_profile_id,
            Encounter.doctor_profile_id == doctor.doctor_profile_id,
        ))
    )
    return bool(appointment or token or encounter)


def require_doctor_patient_access(session: Session, doctor: DoctorProfile, patient: PatientProfile) -> None:
    if not has_doctor_care_relationship(session, doctor, patient):
        raise ApiProblem("care_relationship_required", "No valid doctor-patient care relationship exists", 403)


def _public_user(user: User) -> dict:
    return {
        "id": str(user.public_id),
        "name": user.name,
        "age": user.age,
        "gender": user.gender,
    }


def _encounter_payload(session: Session, encounter: Encounter, include_notes: bool = True) -> dict:
    hospital = session.get(Hospital, encounter.hospital_id)
    department = session.get(Department, encounter.dept_id)
    doctor_profile = session.get(DoctorProfile, encounter.doctor_profile_id) if encounter.doctor_profile_id else None
    doctor = session.get(Doctor, doctor_profile.doctor_id) if doctor_profile else None
    payload = {
        "id": str(encounter.public_id),
        "hospital": hospital.hospital_name if hospital else None,
        "department": department.dept_name if department else None,
        "doctor": doctor.doctor_name if doctor else None,
        "type": encounter.encounter_type,
        "status": encounter.status,
        "chief_complaint": encounter.chief_complaint,
        "started_at": encounter.started_at.isoformat() if encounter.started_at else None,
        "ended_at": encounter.ended_at.isoformat() if encounter.ended_at else None,
        "created_at": encounter.created_at.isoformat(),
    }
    if include_notes:
        payload["clinical_notes"] = encounter.clinical_notes
    payload["diagnoses"] = [
        {
            "id": str(item.public_id),
            "code": item.code,
            "description": item.description,
            "review_status": item.review_status,
            "created_at": item.created_at.isoformat(),
        }
        for item in session.scalars(
            select(Diagnosis).where(Diagnosis.encounter_id == encounter.encounter_id).order_by(Diagnosis.created_at.desc())
        )
    ]
    return payload


def patient_ehr_summary(session: Session, profile: PatientProfile) -> dict:
    user = session.get(User, profile.user_id)
    encounters = list(
        session.scalars(
            select(Encounter)
            .where(Encounter.patient_profile_id == profile.patient_profile_id)
            .order_by(Encounter.created_at.desc())
        )
    )
    prescriptions = list(
        session.scalars(
            select(Prescription)
            .where(Prescription.patient_profile_id == profile.patient_profile_id)
            .order_by(Prescription.created_at.desc())
        )
    )
    allergies = list(
        session.scalars(
            select(Allergy)
            .where(Allergy.patient_profile_id == profile.patient_profile_id, Allergy.is_active.is_(True))
            .order_by(Allergy.created_at.desc())
        )
    )
    vaccinations = list(
        session.scalars(
            select(Vaccination)
            .where(Vaccination.patient_profile_id == profile.patient_profile_id)
            .order_by(Vaccination.administered_on.desc())
        )
    )
    appointments = list(
        session.scalars(
            select(Appointment)
            .where(Appointment.patient_profile_id == profile.patient_profile_id)
            .order_by(Appointment.appointment_date.desc(), Appointment.appointment_time.desc())
        )
    )
    return {
        "patient": {
            **_public_user(user),
            "patient_profile_id": str(profile.public_id),
            "medical_record_number": profile.medical_record_number,
            "blood_group": profile.blood_group,
            "date_of_birth": profile.date_of_birth.isoformat() if profile.date_of_birth else None,
            "emergency_contact": profile.emergency_contact,
        },
        "encounters": [_encounter_payload(session, item) for item in encounters],
        "allergies": [
            {
                "id": str(item.public_id), "substance": item.substance, "severity": item.severity,
                "reaction": item.reaction, "verification_status": item.verification_status, "source": item.source,
            }
            for item in allergies
        ],
        "prescriptions": [
            {
                "id": str(item.public_id), "medicine": item.medicine, "dosage": item.dosage,
                "frequency": item.frequency, "duration": item.duration, "instructions": item.instructions,
                "status": item.status, "created_at": item.created_at.isoformat(),
            }
            for item in prescriptions
        ],
        "vaccinations": [
            {
                "id": str(item.public_id), "vaccine_name": item.vaccine_name,
                "administered_on": item.administered_on.isoformat(), "dose_number": item.dose_number,
                "provider_name": item.provider_name, "verification_status": item.verification_status,
            }
            for item in vaccinations
        ],
        "appointments": [
            {
                "id": item.appointment_id, "doctor_id": item.doctor_id,
                "date": item.appointment_date.isoformat(), "time": item.appointment_time.isoformat(),
                "status": item.status,
            }
            for item in appointments
        ],
        "meta": {
            "encounter_count": len(encounters),
            "active_prescription_count": sum(item.status == "active" for item in prescriptions),
            "active_allergy_count": len(allergies),
        },
    }


def doctor_patient_list(session: Session, doctor: DoctorProfile) -> list[dict]:
    profiles = list(
        session.scalars(
            select(PatientProfile)
            .where(
                or_(
                    exists().where(
                        Appointment.patient_profile_id == PatientProfile.patient_profile_id,
                        Appointment.doctor_id == doctor.doctor_id,
                    ),
                    exists().where(
                        Token.patient_profile_id == PatientProfile.patient_profile_id,
                        Token.doctor_id == doctor.doctor_id,
                    ),
                    exists().where(
                        Encounter.patient_profile_id == PatientProfile.patient_profile_id,
                        Encounter.doctor_profile_id == doctor.doctor_profile_id,
                    ),
                )
            )
            .order_by(PatientProfile.patient_profile_id)
        )
    )
    return [
        {
            **_public_user(session.get(User, profile.user_id)),
            "patient_profile_id": str(profile.public_id),
            "medical_record_number": profile.medical_record_number,
        }
        for profile in profiles
    ]


def record_clinical_change(
    session: Session,
    *,
    entity,
    action: str,
    actor_user_id: int,
    reason: str,
    context: dict | None = None,
    before_snapshot: dict | None = None,
) -> ClinicalChange:
    change = ClinicalChange(
        entity_type=entity.__tablename__,
        entity_id=str(entity.public_id),
        action=action,
        actor_user_id=actor_user_id,
        reason=reason,
        context=context or {},
        before_snapshot=before_snapshot,
        after_snapshot=entity.to_dict(),
    )
    session.add(change)
    session.flush()
    return change


def create_encounter(session: Session, *, doctor: DoctorProfile, patient: PatientProfile, data: dict, actor_user_id: int, context: dict) -> Encounter:
    appointment = session.get(Appointment, data.get("appointment_id")) if data.get("appointment_id") else None
    token = session.get(Token, data.get("token_id")) if data.get("token_id") else None
    if data.get("appointment_id") and appointment is None:
        raise ApiProblem("appointment_not_found", "Appointment not found", 404)
    if data.get("token_id") and token is None:
        raise ApiProblem("token_not_found", "Token not found", 404)
    if appointment and (appointment.patient_profile_id != patient.patient_profile_id or appointment.doctor_id != doctor.doctor_id):
        raise ApiProblem("care_relationship_required", "Appointment is not assigned to this doctor and patient", 403)
    if token and (token.patient_profile_id != patient.patient_profile_id or token.doctor_id != doctor.doctor_id):
        raise ApiProblem("care_relationship_required", "Queue token is not assigned to this doctor and patient", 403)
    if appointment and session.scalar(select(Encounter).where(Encounter.appointment_id == appointment.appointment_id)):
        raise ApiProblem("encounter_exists", "An encounter already exists for this appointment", 409)
    if token and session.scalar(select(Encounter).where(Encounter.token_id == token.token_id)):
        raise ApiProblem("encounter_exists", "An encounter already exists for this queue token", 409)

    if token:
        hospital_id, dept_id = token.hospital_id, token.dept_id
    else:
        provider = session.get(Doctor, appointment.doctor_id)
        department = session.get(Department, provider.dept_id)
        hospital_id, dept_id = department.hospital_id, department.dept_id
    if hospital_id != doctor.hospital_id:
        raise ApiProblem("tenant_forbidden", "Encounter is outside the doctor's hospital", 403)

    now = datetime.now(timezone.utc)
    encounter = Encounter(
        patient_profile_id=patient.patient_profile_id,
        hospital_id=hospital_id,
        dept_id=dept_id,
        doctor_profile_id=doctor.doctor_profile_id,
        appointment_id=appointment.appointment_id if appointment else None,
        token_id=token.token_id if token else None,
        encounter_type=data["encounter_type"],
        status="in_progress",
        chief_complaint=data.get("chief_complaint"),
        started_at=now,
    )
    session.add(encounter)
    session.flush()
    record_clinical_change(session, entity=encounter, action="created", actor_user_id=actor_user_id, reason=data["reason"], context=context)
    return encounter


def require_assigned_encounter(session: Session, doctor: DoctorProfile, encounter_public_id: UUID) -> Encounter:
    encounter = session.scalar(select(Encounter).where(Encounter.public_id == encounter_public_id))
    if encounter is None:
        raise ApiProblem("encounter_not_found", "Encounter not found", 404)
    if encounter.doctor_profile_id != doctor.doctor_profile_id or encounter.hospital_id != doctor.hospital_id:
        raise ApiProblem("care_relationship_required", "Encounter is not assigned to this doctor", 403)
    return encounter


def update_encounter(session: Session, *, encounter: Encounter, data: dict, actor_user_id: int, context: dict) -> Encounter:
    before = encounter.to_dict()
    if data.get("clinical_notes") is not None:
        encounter.clinical_notes = data["clinical_notes"]
    if data.get("status") is not None:
        encounter.status = data["status"]
        if data["status"] == "in_progress" and encounter.started_at is None:
            encounter.started_at = datetime.now(timezone.utc)
        if data["status"] == "completed":
            encounter.ended_at = datetime.now(timezone.utc)
    session.flush()
    action = "status_changed" if data.get("status") else "updated"
    record_clinical_change(session, entity=encounter, action=action, actor_user_id=actor_user_id, reason=data["reason"], context=context, before_snapshot=before)
    return encounter


def create_diagnosis(session: Session, *, encounter: Encounter, doctor: DoctorProfile, data: dict, actor_user_id: int, context: dict) -> Diagnosis:
    diagnosis = Diagnosis(
        encounter_id=encounter.encounter_id,
        code=data.get("code"),
        description=data["description"],
        author_doctor_profile_id=doctor.doctor_profile_id,
        review_status=data["review_status"],
    )
    session.add(diagnosis)
    session.flush()
    record_clinical_change(session, entity=diagnosis, action="created", actor_user_id=actor_user_id, reason=data["reason"], context=context)
    return diagnosis


def update_diagnosis_status(session: Session, *, diagnosis_public_id: UUID, doctor: DoctorProfile, data: dict, actor_user_id: int, context: dict) -> Diagnosis:
    diagnosis = session.scalar(select(Diagnosis).where(Diagnosis.public_id == diagnosis_public_id))
    if diagnosis is None:
        raise ApiProblem("diagnosis_not_found", "Diagnosis not found", 404)
    encounter = session.get(Encounter, diagnosis.encounter_id)
    if encounter.doctor_profile_id != doctor.doctor_profile_id:
        raise ApiProblem("care_relationship_required", "Diagnosis is outside this doctor's care relationship", 403)
    before = diagnosis.to_dict()
    diagnosis.review_status = data["review_status"]
    session.flush()
    record_clinical_change(session, entity=diagnosis, action="status_changed", actor_user_id=actor_user_id, reason=data["reason"], context=context, before_snapshot=before)
    return diagnosis


def create_prescription(session: Session, *, encounter: Encounter, doctor: DoctorProfile, data: dict, actor_user_id: int, context: dict) -> Prescription:
    prescription = Prescription(
        encounter_id=encounter.encounter_id,
        patient_profile_id=encounter.patient_profile_id,
        author_doctor_profile_id=doctor.doctor_profile_id,
        medicine=data["medicine"], dosage=data["dosage"], frequency=data["frequency"],
        duration=data["duration"], instructions=data.get("instructions"), status="active",
    )
    session.add(prescription)
    session.flush()
    record_clinical_change(session, entity=prescription, action="created", actor_user_id=actor_user_id, reason=data["reason"], context=context)
    return prescription


def update_prescription_status(session: Session, *, prescription_public_id: UUID, doctor: DoctorProfile, data: dict, actor_user_id: int, context: dict) -> Prescription:
    prescription = session.scalar(select(Prescription).where(Prescription.public_id == prescription_public_id))
    if prescription is None:
        raise ApiProblem("prescription_not_found", "Prescription not found", 404)
    encounter = session.get(Encounter, prescription.encounter_id)
    if encounter.doctor_profile_id != doctor.doctor_profile_id:
        raise ApiProblem("care_relationship_required", "Prescription is outside this doctor's care relationship", 403)
    before = prescription.to_dict()
    prescription.status = data["status"]
    session.flush()
    record_clinical_change(session, entity=prescription, action="status_changed", actor_user_id=actor_user_id, reason=data["reason"], context=context, before_snapshot=before)
    return prescription


def create_allergy(session: Session, *, patient: PatientProfile, doctor: DoctorProfile, data: dict, actor_user_id: int, context: dict) -> Allergy:
    require_doctor_patient_access(session, doctor, patient)
    allergy = Allergy(
        patient_profile_id=patient.patient_profile_id, substance=data["substance"], severity=data["severity"],
        reaction=data.get("reaction"), verification_status=data["verification_status"], source=data["source"],
        recorded_by_doctor_profile_id=doctor.doctor_profile_id,
    )
    session.add(allergy)
    session.flush()
    record_clinical_change(session, entity=allergy, action="created", actor_user_id=actor_user_id, reason=data["reason"], context=context)
    return allergy


def create_vaccination(session: Session, *, patient: PatientProfile, doctor: DoctorProfile, data: dict, actor_user_id: int, context: dict) -> Vaccination:
    require_doctor_patient_access(session, doctor, patient)
    vaccination = Vaccination(
        patient_profile_id=patient.patient_profile_id, vaccine_name=data["vaccine_name"],
        administered_on=data["administered_on"], dose_number=data.get("dose_number"), lot_number=data.get("lot_number"),
        provider_name=data.get("provider_name"), source=data["source"], verification_status=data["verification_status"],
        recorded_by_doctor_profile_id=doctor.doctor_profile_id,
    )
    session.add(vaccination)
    session.flush()
    record_clinical_change(session, entity=vaccination, action="created", actor_user_id=actor_user_id, reason=data["reason"], context=context)
    return vaccination
