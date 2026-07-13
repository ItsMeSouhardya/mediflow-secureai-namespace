"""Versioned patient and doctor EHR endpoints."""

from __future__ import annotations

from uuid import UUID

from flask import Flask, g, jsonify, request

from audit import write_audit_event
from auth_service import ROLE_DOCTOR, ROLE_PATIENT
from authorization import require_auth
from ehr_service import (
    create_allergy,
    create_diagnosis,
    create_encounter,
    create_prescription,
    create_vaccination,
    doctor_patient_list,
    doctor_profile_for_user,
    ensure_patient_profile,
    patient_ehr_summary,
    patient_profile_by_public_id,
    require_assigned_encounter,
    require_doctor_patient_access,
    update_diagnosis_status,
    update_encounter,
    update_prescription_status,
)
from extensions import db, limiter
from rate_limits import SENSITIVE_WRITE_RATE_LIMIT
from schemas import (
    AllergyCreateRequest,
    DiagnosisCreateRequest,
    DiagnosisStatusRequest,
    EncounterCreateRequest,
    EncounterUpdateRequest,
    PrescriptionCreateRequest,
    PrescriptionStatusRequest,
    VaccinationCreateRequest,
    validate_json,
)


def _context() -> dict:
    return {"request_id": g.request_id, "path": request.path}


def _audit(action: str, resource_type: str, resource_id, details: dict | None = None) -> None:
    write_audit_event(
        db.session,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        actor_user_id=g.current_user.user_id,
        details=details or {},
    )


def register_ehr_routes(app: Flask) -> None:
    @app.get("/api/v1/patients/me/ehr")
    @require_auth(ROLE_PATIENT)
    def patient_ehr():
        profile = ensure_patient_profile(db.session, g.current_user)
        _audit("ehr.patient_summary_viewed", "patient_profile", profile.public_id)
        db.session.commit()
        return jsonify(patient_ehr_summary(db.session, profile))

    @app.get("/api/v1/doctors/me/patients")
    @require_auth(ROLE_DOCTOR)
    def doctor_patients():
        doctor = doctor_profile_for_user(db.session, g.current_user.user_id)
        return jsonify(doctor_patient_list(db.session, doctor))

    @app.get("/api/v1/doctors/me/patients/<uuid:patient_id>")
    @require_auth(ROLE_DOCTOR)
    def doctor_patient_detail(patient_id: UUID):
        doctor = doctor_profile_for_user(db.session, g.current_user.user_id)
        patient = patient_profile_by_public_id(db.session, patient_id)
        require_doctor_patient_access(db.session, doctor, patient)
        _audit(
            "ehr.doctor_patient_viewed",
            "patient_profile",
            patient.public_id,
            {"doctor_profile_id": str(doctor.public_id), "hospital_id": doctor.hospital_id},
        )
        db.session.commit()
        return jsonify(patient_ehr_summary(db.session, patient))

    @app.post("/api/v1/doctors/me/encounters")
    @require_auth(ROLE_DOCTOR)
    @limiter.limit(SENSITIVE_WRITE_RATE_LIMIT)
    def doctor_create_encounter():
        body = validate_json(EncounterCreateRequest)
        doctor = doctor_profile_for_user(db.session, g.current_user.user_id)
        patient = patient_profile_by_public_id(db.session, body.patient_id)
        encounter = create_encounter(
            db.session,
            doctor=doctor,
            patient=patient,
            data=body.model_dump(),
            actor_user_id=g.current_user.user_id,
            context=_context(),
        )
        _audit("clinical.encounter_created", "encounter", encounter.public_id, {"reason": body.reason})
        db.session.commit()
        return jsonify({"id": str(encounter.public_id), "status": encounter.status}), 201

    @app.patch("/api/v1/doctors/me/encounters/<uuid:encounter_id>")
    @require_auth(ROLE_DOCTOR)
    @limiter.limit(SENSITIVE_WRITE_RATE_LIMIT)
    def doctor_update_encounter(encounter_id: UUID):
        body = validate_json(EncounterUpdateRequest)
        doctor = doctor_profile_for_user(db.session, g.current_user.user_id)
        encounter = require_assigned_encounter(db.session, doctor, encounter_id)
        update_encounter(
            db.session,
            encounter=encounter,
            data=body.model_dump(),
            actor_user_id=g.current_user.user_id,
            context=_context(),
        )
        _audit("clinical.encounter_updated", "encounter", encounter.public_id, {"reason": body.reason})
        db.session.commit()
        return jsonify({"id": str(encounter.public_id), "status": encounter.status})

    @app.post("/api/v1/doctors/me/encounters/<uuid:encounter_id>/diagnoses")
    @require_auth(ROLE_DOCTOR)
    @limiter.limit(SENSITIVE_WRITE_RATE_LIMIT)
    def doctor_create_diagnosis(encounter_id: UUID):
        body = validate_json(DiagnosisCreateRequest)
        doctor = doctor_profile_for_user(db.session, g.current_user.user_id)
        encounter = require_assigned_encounter(db.session, doctor, encounter_id)
        diagnosis = create_diagnosis(
            db.session, encounter=encounter, doctor=doctor, data=body.model_dump(),
            actor_user_id=g.current_user.user_id, context=_context(),
        )
        _audit("clinical.diagnosis_created", "diagnosis", diagnosis.public_id, {"reason": body.reason})
        db.session.commit()
        return jsonify({"id": str(diagnosis.public_id), "review_status": diagnosis.review_status}), 201

    @app.patch("/api/v1/doctors/me/diagnoses/<uuid:diagnosis_id>")
    @require_auth(ROLE_DOCTOR)
    @limiter.limit(SENSITIVE_WRITE_RATE_LIMIT)
    def doctor_update_diagnosis(diagnosis_id: UUID):
        body = validate_json(DiagnosisStatusRequest)
        doctor = doctor_profile_for_user(db.session, g.current_user.user_id)
        diagnosis = update_diagnosis_status(
            db.session, diagnosis_public_id=diagnosis_id, doctor=doctor, data=body.model_dump(),
            actor_user_id=g.current_user.user_id, context=_context(),
        )
        _audit("clinical.diagnosis_status_changed", "diagnosis", diagnosis.public_id, {"reason": body.reason})
        db.session.commit()
        return jsonify({"id": str(diagnosis.public_id), "review_status": diagnosis.review_status})

    @app.post("/api/v1/doctors/me/encounters/<uuid:encounter_id>/prescriptions")
    @require_auth(ROLE_DOCTOR)
    @limiter.limit(SENSITIVE_WRITE_RATE_LIMIT)
    def doctor_create_prescription(encounter_id: UUID):
        body = validate_json(PrescriptionCreateRequest)
        doctor = doctor_profile_for_user(db.session, g.current_user.user_id)
        encounter = require_assigned_encounter(db.session, doctor, encounter_id)
        prescription = create_prescription(
            db.session, encounter=encounter, doctor=doctor, data=body.model_dump(),
            actor_user_id=g.current_user.user_id, context=_context(),
        )
        _audit("clinical.prescription_created", "prescription", prescription.public_id, {"reason": body.reason})
        db.session.commit()
        return jsonify({"id": str(prescription.public_id), "status": prescription.status}), 201

    @app.patch("/api/v1/doctors/me/prescriptions/<uuid:prescription_id>")
    @require_auth(ROLE_DOCTOR)
    @limiter.limit(SENSITIVE_WRITE_RATE_LIMIT)
    def doctor_update_prescription(prescription_id: UUID):
        body = validate_json(PrescriptionStatusRequest)
        doctor = doctor_profile_for_user(db.session, g.current_user.user_id)
        prescription = update_prescription_status(
            db.session, prescription_public_id=prescription_id, doctor=doctor, data=body.model_dump(),
            actor_user_id=g.current_user.user_id, context=_context(),
        )
        _audit("clinical.prescription_status_changed", "prescription", prescription.public_id, {"reason": body.reason})
        db.session.commit()
        return jsonify({"id": str(prescription.public_id), "status": prescription.status})

    @app.post("/api/v1/doctors/me/patients/<uuid:patient_id>/allergies")
    @require_auth(ROLE_DOCTOR)
    @limiter.limit(SENSITIVE_WRITE_RATE_LIMIT)
    def doctor_create_allergy(patient_id: UUID):
        body = validate_json(AllergyCreateRequest)
        doctor = doctor_profile_for_user(db.session, g.current_user.user_id)
        patient = patient_profile_by_public_id(db.session, patient_id)
        allergy = create_allergy(
            db.session, patient=patient, doctor=doctor, data=body.model_dump(),
            actor_user_id=g.current_user.user_id, context=_context(),
        )
        _audit("clinical.allergy_created", "allergy", allergy.public_id, {"reason": body.reason})
        db.session.commit()
        return jsonify({"id": str(allergy.public_id), "verification_status": allergy.verification_status}), 201

    @app.post("/api/v1/doctors/me/patients/<uuid:patient_id>/vaccinations")
    @require_auth(ROLE_DOCTOR)
    @limiter.limit(SENSITIVE_WRITE_RATE_LIMIT)
    def doctor_create_vaccination(patient_id: UUID):
        body = validate_json(VaccinationCreateRequest)
        doctor = doctor_profile_for_user(db.session, g.current_user.user_id)
        patient = patient_profile_by_public_id(db.session, patient_id)
        vaccination = create_vaccination(
            db.session, patient=patient, doctor=doctor, data=body.model_dump(),
            actor_user_id=g.current_user.user_id, context=_context(),
        )
        _audit("clinical.vaccination_created", "vaccination", vaccination.public_id, {"reason": body.reason})
        db.session.commit()
        return jsonify({"id": str(vaccination.public_id), "verification_status": vaccination.verification_status}), 201
