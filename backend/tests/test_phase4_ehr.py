from __future__ import annotations

from auth_service import ROLE_DOCTOR, onboard_staff
from extensions import db
from models import AuditEvent, ClinicalChange, PatientProfile, User


def bearer(response) -> dict[str, str]:
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.get_json()['data']['access_token']}"}


def create_doctor_login(client, app, *, email: str, doctor_id: int, employee_code: str):
    password = "ClinicalDoctor!42"
    with app.app_context():
        assigner = db.session.scalar(db.select(User).where(User.email == "patient@mediflow.test"))
        onboard_staff(
            db.session,
            name=f"Doctor {doctor_id}",
            email=email,
            phone=None,
            password=password,
            role_name=ROLE_DOCTOR,
            hospital_id=1,
            doctor_id=doctor_id,
            employee_code=employee_code,
            assigned_by_user_id=assigner.user_id,
        )
        db.session.commit()
    return client.post("/api/v1/auth/login", json={"identifier": email, "password": password})


def test_patient_has_owned_longitudinal_ehr_summary(client, auth_headers):
    anonymous = client.get("/api/v1/patients/me/ehr")
    assert anonymous.status_code == 401

    response = client.get("/api/v1/patients/me/ehr", headers=auth_headers)
    assert response.status_code == 200
    ehr = response.get_json()["data"]
    assert ehr["patient"]["name"] == "Ramesh"
    assert ehr["patient"]["medical_record_number"].startswith("MRN-")
    assert len(ehr["appointments"]) == 1
    assert {"encounters", "allergies", "prescriptions", "vaccinations", "appointments", "meta"} <= ehr.keys()
    assert "user_id" not in str(ehr)


def test_doctor_patient_list_requires_real_care_relationship(client, app):
    assigned = create_doctor_login(client, app, email="assigned.doctor@example.test", doctor_id=1, employee_code="EHR-D1")
    assigned_headers = bearer(assigned)
    patient_list = client.get("/api/v1/doctors/me/patients", headers=assigned_headers)
    assert patient_list.status_code == 200
    patients = patient_list.get_json()["data"]
    ramesh = next(item for item in patients if item["name"] == "Ramesh")
    assert client.get(f"/api/v1/doctors/me/patients/{ramesh['patient_profile_id']}", headers=assigned_headers).status_code == 200

    unassigned = create_doctor_login(client, app, email="unassigned.doctor@example.test", doctor_id=2, employee_code="EHR-D2")
    unassigned_headers = bearer(unassigned)
    denied = client.get(f"/api/v1/doctors/me/patients/{ramesh['patient_profile_id']}", headers=unassigned_headers)
    assert denied.status_code == 403
    assert denied.get_json()["error"]["code"] == "care_relationship_required"


def test_doctor_can_build_audited_longitudinal_record(client, app, auth_headers):
    doctor_login = create_doctor_login(client, app, email="workflow.doctor@example.test", doctor_id=1, employee_code="EHR-WORKFLOW")
    headers = bearer(doctor_login)
    patients = client.get("/api/v1/doctors/me/patients", headers=headers).get_json()["data"]
    patient = next(item for item in patients if item["name"] == "Ramesh")
    detail = client.get(f"/api/v1/doctors/me/patients/{patient['patient_profile_id']}", headers=headers).get_json()["data"]
    appointment_id = detail["appointments"][0]["id"]

    encounter = client.post(
        "/api/v1/doctors/me/encounters",
        headers=headers,
        json={
            "patient_id": patient["patient_profile_id"],
            "appointment_id": appointment_id,
            "encounter_type": "outpatient",
            "chief_complaint": "Persistent cough",
            "reason": "Scheduled consultation started",
        },
    )
    assert encounter.status_code == 201
    encounter_id = encounter.get_json()["data"]["id"]

    note = client.patch(
        f"/api/v1/doctors/me/encounters/{encounter_id}",
        headers=headers,
        json={"clinical_notes": "Chest clear; hydration and observation advised.", "reason": "Consultation findings recorded"},
    )
    assert note.status_code == 200
    diagnosis = client.post(
        f"/api/v1/doctors/me/encounters/{encounter_id}/diagnoses",
        headers=headers,
        json={"code": "R05", "description": "Acute cough", "review_status": "confirmed", "reason": "Clinical assessment completed"},
    )
    assert diagnosis.status_code == 201
    prescription = client.post(
        f"/api/v1/doctors/me/encounters/{encounter_id}/prescriptions",
        headers=headers,
        json={"medicine": "Paracetamol", "dosage": "500 mg", "frequency": "Twice daily", "duration": "3 days", "instructions": "After food", "reason": "Symptomatic treatment"},
    )
    assert prescription.status_code == 201
    allergy = client.post(
        f"/api/v1/doctors/me/patients/{patient['patient_profile_id']}/allergies",
        headers=headers,
        json={"substance": "Penicillin", "severity": "severe", "reaction": "Hives", "verification_status": "confirmed", "source": "clinician_recorded", "reason": "Patient history verified"},
    )
    assert allergy.status_code == 201
    vaccination = client.post(
        f"/api/v1/doctors/me/patients/{patient['patient_profile_id']}/vaccinations",
        headers=headers,
        json={"vaccine_name": "Influenza", "administered_on": "2026-06-01", "dose_number": "1", "verification_status": "confirmed", "reason": "Vaccination card reviewed"},
    )
    assert vaccination.status_code == 201

    patient_ehr = client.get("/api/v1/patients/me/ehr", headers=auth_headers).get_json()["data"]
    assert patient_ehr["encounters"][0]["clinical_notes"].startswith("Chest clear")
    assert patient_ehr["encounters"][0]["diagnoses"][0]["description"] == "Acute cough"
    assert patient_ehr["prescriptions"][0]["medicine"] == "Paracetamol"
    assert patient_ehr["allergies"][0]["substance"] == "Penicillin"
    assert patient_ehr["vaccinations"][0]["vaccine_name"] == "Influenza"

    with app.app_context():
        changes = db.session.query(ClinicalChange).order_by(ClinicalChange.clinical_change_id).all()
        assert len(changes) == 6
        assert all(change.actor_user_id and change.reason and change.created_at for change in changes)
        assert all(change.after_snapshot for change in changes)
        assert changes[1].before_snapshot is not None
        clinical_audits = db.session.query(AuditEvent).filter(AuditEvent.action.like("clinical.%")).all()
        assert len(clinical_audits) == 6


def test_patient_profile_is_one_to_one_with_authenticated_user(app):
    with app.app_context():
        patient = db.session.scalar(db.select(User).where(User.email == "patient@mediflow.test"))
        profiles = db.session.query(PatientProfile).filter_by(user_id=patient.user_id).all()
        assert len(profiles) == 1
