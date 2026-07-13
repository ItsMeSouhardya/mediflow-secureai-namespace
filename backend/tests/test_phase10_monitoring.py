from __future__ import annotations

from datetime import datetime, timedelta, timezone

from auth_service import ROLE_DOCTOR, onboard_staff
from extensions import db
from models import AuditEvent, ConsentGrant, DoctorProfile, MonitoringAlert, PatientObservation, PatientProfile, User


def _bearer(response):
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.get_json()['data']['access_token']}"}


def _authorized_doctor(client, app):
    email = "monitoring.doctor@example.test"; password = "MonitoringDoctor!42"
    with app.app_context():
        assigner = db.session.scalar(db.select(User).where(User.email == "patient@mediflow.test"))
        onboard_staff(
            db.session, name="Monitoring Doctor", email=email, phone=None, password=password,
            role_name=ROLE_DOCTOR, hospital_id=1, doctor_id=1, employee_code="MON-DOC-1",
            assigned_by_user_id=assigner.user_id,
        )
        doctor = db.session.scalar(db.select(DoctorProfile).join(User).where(User.email == email))
        patient = db.session.scalar(db.select(PatientProfile).join(User).where(User.email == "patient@mediflow.test"))
        now = datetime.now(timezone.utc)
        db.session.add(ConsentGrant(
            patient_profile_id=patient.patient_profile_id,
            requesting_doctor_profile_id=doctor.doctor_profile_id,
            requesting_hospital_id=1, scopes=["monitoring"], purpose="Continuous vital monitoring",
            operation="treatment", status="granted", access_start=now,
            access_expires_at=now + timedelta(days=7),
        ))
        patient_id = str(patient.public_id)
        db.session.commit()
    login = client.post("/api/v1/auth/login", json={"identifier": email, "password": password})
    return _bearer(login), patient_id


def test_manual_observation_alert_realtime_and_triage_lifecycle(client, app, auth_headers):
    doctor_headers, patient_id = _authorized_doctor(client, app)
    invalid = client.post(
        "/api/v1/patients/me/monitoring/observations", headers=auth_headers,
        json={"observation_type": "blood_pressure", "value": 70, "secondary_value": 90},
    )
    assert invalid.status_code == 422

    recorded = client.post(
        "/api/v1/patients/me/monitoring/observations", headers=auth_headers,
        json={"observation_type": "blood_oxygen", "value": 88, "source_reference": "home-oximeter"},
    )
    assert recorded.status_code == 201
    body = recorded.get_json()["data"]
    assert body["observation"]["unit"] == "%"
    assert body["observation"]["source"] == "manual"
    assert body["alerts"][0]["severity"] == "critical"

    doctor_alerts = client.get("/api/v1/doctors/me/monitoring/alerts", headers=doctor_headers)
    assert doctor_alerts.status_code == 200
    alert = doctor_alerts.get_json()["data"][0]
    assert alert["patient"]["id"] == patient_id
    assert alert["status"] == "open"

    stream = client.get("/api/v1/doctors/me/monitoring/stream?once=true", headers=doctor_headers)
    assert stream.status_code == 200
    assert stream.mimetype == "text/event-stream"
    assert b"snapshot" in stream.data

    acknowledged = client.patch(
        f"/api/v1/doctors/me/monitoring/alerts/{alert['id']}", headers=doctor_headers,
        json={"action": "acknowledge"},
    )
    assert acknowledged.status_code == 200
    assert acknowledged.get_json()["data"]["status"] == "acknowledged"
    escalated = client.patch(
        f"/api/v1/doctors/me/monitoring/alerts/{alert['id']}", headers=doctor_headers,
        json={"action": "escalate", "notes": "Escalating persistent hypoxemia"},
    )
    assert escalated.status_code == 200
    assert escalated.get_json()["data"]["status"] == "escalated"
    resolved = client.patch(
        f"/api/v1/doctors/me/monitoring/alerts/{alert['id']}", headers=doctor_headers,
        json={"action": "resolve", "notes": "Patient contacted and oxygen normalized."},
    )
    assert resolved.status_code == 200
    assert resolved.get_json()["data"]["status"] == "resolved"

    history = client.get(
        f"/api/v1/doctors/me/monitoring/patients/{patient_id}/observations",
        headers=doctor_headers,
    )
    assert history.status_code == 200
    assert history.get_json()["data"][0]["value"] == 88

    with app.app_context():
        persisted = db.session.query(PatientObservation).count()
        assert persisted == 1
        assert db.session.query(MonitoringAlert).one().resolution_notes.startswith("Patient contacted")
        actions = {item.action for item in db.session.scalars(
            db.select(AuditEvent).where(AuditEvent.action.like("monitoring.%"))
        )}
        assert {"monitoring.alert_created", "monitoring.alert_acknowledged", "monitoring.alert_escalated", "monitoring.alert_resolved"} <= actions


def test_simulator_is_deterministic_and_creates_abnormal_alerts(client, app, auth_headers):
    _authorized_doctor(client, app)
    payload = {"observation_types": ["heart_rate"], "count": 4, "seed": 77, "abnormal_every": 4}
    first = client.post("/api/v1/patients/me/monitoring/simulate", headers=auth_headers, json=payload)
    second = client.post("/api/v1/patients/me/monitoring/simulate", headers=auth_headers, json=payload)
    assert first.status_code == second.status_code == 201
    first_values = [item["value"] for item in first.get_json()["data"]["observations"]]
    second_values = [item["value"] for item in second.get_json()["data"]["observations"]]
    assert first_values == second_values
    assert first_values[-1] == 145.0
    assert first.get_json()["data"]["alerts_created"] >= 1


def test_patient_clears_only_selected_parameter_history(client, app, auth_headers):
    readings = [
        {"observation_type": "heart_rate", "value": 72},
        {"observation_type": "heart_rate", "value": 145},
        {"observation_type": "blood_oxygen", "value": 98},
    ]
    for reading in readings:
        response = client.post(
            "/api/v1/patients/me/monitoring/observations",
            headers=auth_headers,
            json=reading,
        )
        assert response.status_code == 201

    cleared = client.post(
        "/api/v1/patients/me/monitoring/observations/heart_rate/clear",
        headers=auth_headers,
    )
    assert cleared.status_code == 200
    assert cleared.get_json()["data"] == {
        "type": "heart_rate",
        "deleted_count": 2,
    }

    remaining = client.get(
        "/api/v1/patients/me/monitoring/observations", headers=auth_headers
    ).get_json()["data"]
    assert [(item["type"], item["value"]) for item in remaining] == [
        ("blood_oxygen", 98.0)
    ]
    assert client.get(
        "/api/v1/patients/me/monitoring/alerts", headers=auth_headers
    ).get_json()["data"] == []

    with app.app_context():
        assert db.session.scalar(
            db.select(AuditEvent).where(
                AuditEvent.action == "monitoring.observations_cleared"
            )
        ) is not None

    unsupported = client.delete(
        "/api/v1/patients/me/monitoring/observations/not_a_signal",
        headers=auth_headers,
    )
    assert unsupported.status_code == 400
