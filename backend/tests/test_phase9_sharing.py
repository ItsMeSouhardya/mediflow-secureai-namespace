from __future__ import annotations

from uuid import UUID

from auth_service import ROLE_DOCTOR, onboard_staff
from extensions import db
from models import (
    AuditEvent,
    CrossHospitalShare,
    CrossHospitalShareHistory,
    Department,
    Doctor,
    PatientProfile,
    User,
)


def _bearer(response):
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.get_json()['data']['access_token']}"}


def _doctor_at_hospital(client, app, hospital_id: int):
    email = f"sharing.doctor.h{hospital_id}@example.test"
    password = "SharingDoctor!42"
    with app.app_context():
        provider = db.session.scalar(
            db.select(Doctor)
            .join(Department, Department.dept_id == Doctor.dept_id)
            .where(Department.hospital_id == hospital_id)
            .order_by(Doctor.doctor_id)
        )
        assigner = db.session.scalar(db.select(User).where(User.email == "patient@mediflow.test"))
        onboard_staff(
            db.session, name="Referral Doctor", email=email, phone=None,
            password=password, role_name=ROLE_DOCTOR, hospital_id=hospital_id,
            doctor_id=provider.doctor_id, employee_code=f"SHARE-H{hospital_id}",
            assigned_by_user_id=assigner.user_id,
        )
        patient_id = str(db.session.scalar(db.select(PatientProfile)).public_id)
        db.session.commit()
    login = client.post("/api/v1/auth/login", json={"identifier": email, "password": password})
    return _bearer(login), patient_id


def test_cross_hospital_share_lifecycle_projection_and_break_glass(client, app, auth_headers):
    doctor_headers, patient_id = _doctor_at_hospital(client, app, 2)
    requested = client.post(
        "/api/v1/doctors/me/shares/requests",
        headers=doctor_headers,
        json={
            "patient_id": patient_id,
            "source_hospital_id": 1,
            "scopes": ["summary"],
            "purpose": "Referral review at another hospital",
            "operation": "referral",
            "requested_duration_days": 7,
        },
    )
    assert requested.status_code == 201
    share_id = requested.get_json()["data"]["id"]

    pending_access = client.get(
        f"/api/v1/doctors/me/shares/{share_id}/records", headers=doctor_headers
    )
    assert pending_access.status_code == 403

    inbox = client.get("/api/v1/patients/me/shares", headers=auth_headers)
    assert inbox.status_code == 200
    assert inbox.get_json()["data"][0]["requested_duration_days"] == 7
    granted = client.post(
        f"/api/v1/patients/me/shares/{share_id}/grant",
        headers=auth_headers,
        json={"scopes": ["summary"], "access_expires_days": 7},
    )
    assert granted.status_code == 200

    access = client.get(
        f"/api/v1/doctors/me/shares/{share_id}/records", headers=doctor_headers
    )
    assert access.status_code == 200
    projection = access.get_json()["data"]
    assert set(projection) == {"approved_scopes", "patient"}
    serialized = str(projection).lower()
    for forbidden in ("medical_record_number", "storage_key", "download_url", "patient_profile_id"):
        assert forbidden not in serialized

    revoked = client.post(
        f"/api/v1/patients/me/shares/{share_id}/revoke",
        headers=auth_headers,
        json={"reason": "Referral completed"},
    )
    assert revoked.status_code == 200
    assert client.get(
        f"/api/v1/doctors/me/shares/{share_id}/records", headers=doctor_headers
    ).status_code == 403

    emergency = client.post(
        "/api/v1/doctors/me/shares/break-glass",
        headers=doctor_headers,
        json={
            "patient_id": patient_id,
            "source_hospital_id": 1,
            "scopes": ["summary"],
            "reason": "Unconscious patient requires urgent medication reconciliation",
        },
    )
    assert emergency.status_code == 201
    emergency_data = emergency.get_json()["data"]
    assert emergency_data["status"] == "break_glass"
    assert client.get(
        f"/api/v1/doctors/me/shares/{emergency_data['id']}/records", headers=doctor_headers
    ).status_code == 200

    with app.app_context():
        share = db.session.scalar(db.select(CrossHospitalShare).where(CrossHospitalShare.public_id == UUID(share_id)))
        history = db.session.scalars(
            db.select(CrossHospitalShareHistory)
            .where(CrossHospitalShareHistory.share_id == share.share_id)
            .order_by(CrossHospitalShareHistory.share_history_id)
        ).all()
        assert [item.to_status for item in history] == ["pending", "granted", "revoked"]
        actions = {item.action for item in db.session.scalars(
            db.select(AuditEvent).where(AuditEvent.resource_id == share_id)
        )}
        assert {"sharing.access_denied_not_granted", "sharing.record_accessed", "sharing.share_revoked"} <= actions
