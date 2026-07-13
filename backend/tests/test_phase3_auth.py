from __future__ import annotations

from auth_service import ROLE_DOCTOR, ROLE_HOSPITAL_ADMIN, ROLE_SECURITY_ADMIN, onboard_staff, verify_password
from extensions import db
from models import AuthSession, Token, User


def bearer(response) -> dict[str, str]:
    return {"Authorization": f"Bearer {response.get_json()['data']['access_token']}"}


def test_patient_registration_session_and_protected_profile(client):
    anonymous = client.get("/api/v1/auth/me")
    assert anonymous.status_code == 401

    registered = client.post(
        "/api/v1/auth/register",
        json={
            "name": "New Patient",
            "email": "new.patient@example.test",
            "phone": "9000000999",
            "password": "StrongPatient!42",
            "age": 31,
            "gender": "Other",
        },
    )
    assert registered.status_code == 201
    assert registered.get_json()["data"]["user"]["roles"] == ["patient"]
    assert "HttpOnly" in registered.headers["Set-Cookie"]
    activation_token = registered.get_json()["data"]["testing_activation_token"]
    activated = client.post("/api/v1/auth/activation/confirm", json={"token": activation_token})
    assert activated.status_code == 200
    assert client.post("/api/v1/auth/activation/confirm", json={"token": activation_token}).status_code == 400

    profile = client.get("/api/v1/auth/me", headers=bearer(registered))
    assert profile.status_code == 200
    assert profile.get_json()["data"]["email"] == "new.patient@example.test"
    assert profile.get_json()["data"]["email_verified"] is True
    assert profile.get_json()["data"]["created_at"]


def test_patient_can_update_profile_and_delete_account(client, app):
    login = client.post(
        "/api/v1/auth/login",
        json={"identifier": "patient@mediflow.test", "password": "PatientDemo!123"},
    )
    headers = bearer(login)
    updated = client.patch(
        "/api/v1/auth/me",
        headers=headers,
        json={"name": "Updated Demo Patient", "email": "updated.patient@example.test", "age": 29},
    )
    assert updated.status_code == 200
    assert updated.get_json()["data"]["name"] == "Updated Demo Patient"
    assert updated.get_json()["data"]["email"] == "updated.patient@example.test"
    assert updated.get_json()["data"]["email_verified"] is False

    rejected = client.post(
        "/api/v1/auth/me/delete",
        headers=headers,
        json={"password": "wrong-password", "confirmation": "DELETE"},
    )
    assert rejected.status_code == 401

    deleted = client.post(
        "/api/v1/auth/me/delete",
        headers=headers,
        json={"password": "PatientDemo!123", "confirmation": "DELETE"},
    )
    assert deleted.status_code == 200
    assert deleted.get_json()["data"]["deleted"] is True
    with app.app_context():
        user = db.session.scalar(db.select(User).where(User.name == "Deleted account"))
        assert user is not None
        assert user.is_active is False
        assert user.email.endswith("@invalid.mediflow")
        assert user.password_hash is None


def test_refresh_rotates_server_side_session_and_logout_revokes(client, app):
    login = client.post(
        "/api/v1/auth/login",
        json={"identifier": "patient@mediflow.test", "password": "PatientDemo!123"},
    )
    assert login.status_code == 200
    refreshed = client.post("/api/v1/auth/refresh")
    assert refreshed.status_code == 200
    assert refreshed.get_json()["data"]["access_token"] != login.get_json()["data"]["access_token"]

    with app.app_context():
        sessions = db.session.query(AuthSession).order_by(AuthSession.auth_session_id).all()
        assert len(sessions) == 2
        assert sessions[0].revoke_reason == "rotated"
        assert sessions[0].replaced_by_session_id == sessions[1].auth_session_id

    logout = client.post("/api/v1/auth/logout", headers=bearer(refreshed))
    assert logout.status_code == 200
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_password_reset_is_single_use_and_revokes_sessions(client):
    client.post(
        "/api/v1/auth/login",
        json={"identifier": "patient@mediflow.test", "password": "PatientDemo!123"},
    )
    requested = client.post(
        "/api/v1/auth/password-reset/request",
        json={"identifier": "patient@mediflow.test"},
    )
    token = requested.get_json()["data"]["testing_reset_token"]
    confirmed = client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": token, "new_password": "Replacement!Password42"},
    )
    assert confirmed.status_code == 200
    assert client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": token, "new_password": "Another!Password42"},
    ).status_code == 400
    assert client.post(
        "/api/v1/auth/login",
        json={"identifier": "patient@mediflow.test", "password": "Replacement!Password42"},
    ).status_code == 200


def test_repeated_failed_login_temporarily_locks_account(client):
    for _ in range(5):
        response = client.post(
            "/api/v1/auth/login",
            json={"identifier": "patient@mediflow.test", "password": "incorrect-password"},
        )
        assert response.status_code == 401
    locked = client.post(
        "/api/v1/auth/login",
        json={"identifier": "patient@mediflow.test", "password": "PatientDemo!123"},
    )
    assert locked.status_code == 423
    assert locked.get_json()["error"]["code"] == "account_locked"


def test_booking_is_owned_and_public_tracking_response_contains_no_phi(client, auth_headers, app):
    booked = client.post(
        "/api/v1/tokens/book",
        headers={**auth_headers, "Idempotency-Key": "phase3-public-tracking-1"},
        json={
            "dept_id": 1,
            "patient_name": "Spoofed Name",
            "age": 99,
            "phone": "7777777777",
            "gender": "Other",
            "symptoms": "private symptom",
        },
    )
    assert booked.status_code == 201
    data = booked.get_json()["data"]
    with app.app_context():
        token = db.session.get(Token, data["token_id"])
        owner = db.session.scalar(db.select(User).where(User.email == "patient@mediflow.test"))
        assert token.user_id == owner.user_id

    public = client.get(f"/api/v1/public/tokens/{data['tracking_code']}")
    assert public.status_code == 200
    public_data = public.get_json()["data"]
    assert {"display_token", "status", "priority", "position", "wait_time", "hospital_name", "department_name"} <= public_data.keys()
    serialized = str(public_data).lower()
    for forbidden in ("ramesh", "spoofed", "private symptom", "user_id", "token_id", "phone", "age"):
        assert forbidden not in serialized


def test_hospital_admin_cannot_cross_tenant(client, app):
    with app.app_context():
        assigner = db.session.scalar(db.select(User).where(User.email == "patient@mediflow.test"))
        onboard_staff(
            db.session,
            name="Hospital One Admin",
            email="admin.one@example.test",
            phone=None,
            password="HospitalAdmin!42",
            role_name=ROLE_HOSPITAL_ADMIN,
            hospital_id=1,
            doctor_id=None,
            employee_code="H1-ADMIN",
            assigned_by_user_id=assigner.user_id,
        )
        db.session.commit()

    login = client.post(
        "/api/v1/auth/login",
        json={"identifier": "admin.one@example.test", "password": "HospitalAdmin!42"},
    )
    headers = bearer(login)
    assert client.get("/api/v1/dashboard/stats?hospital_id=1", headers=headers).status_code == 200
    denied = client.get("/api/v1/dashboard/stats?hospital_id=2", headers=headers)
    assert denied.status_code == 403
    assert denied.get_json()["error"]["code"] == "tenant_forbidden"


def test_patient_doctor_and_security_admin_clinical_isolation(client, auth_headers, app):
    booked = client.post(
        "/api/v1/tokens/book",
        headers={**auth_headers, "Idempotency-Key": "phase3-isolation-token"},
        json={"dept_id": 1, "patient_name": "Owner", "age": 45, "symptoms": "private"},
    )
    token_id = booked.get_json()["data"]["token_id"]

    other_patient = client.post(
        "/api/v1/auth/register",
        json={"name": "Other Patient", "email": "other@example.test", "password": "OtherPatient!42"},
    )
    assert client.get(f"/api/v1/tokens/{token_id}", headers=bearer(other_patient)).status_code == 403

    with app.app_context():
        assigner = db.session.scalar(db.select(User).where(User.email == "patient@mediflow.test"))
        onboard_staff(
            db.session, name="Doctor One", email="doctor.one@example.test", phone=None,
            password="DoctorAccess!42", role_name=ROLE_DOCTOR, hospital_id=1, doctor_id=1,
            employee_code="H1-DOC", assigned_by_user_id=assigner.user_id,
        )
        onboard_staff(
            db.session, name="Security Admin", email="security@example.test", phone=None,
            password="SecurityAdmin!42", role_name=ROLE_SECURITY_ADMIN, hospital_id=None, doctor_id=None,
            employee_code=None, assigned_by_user_id=assigner.user_id,
        )
        doctor_user = db.session.scalar(db.select(User).where(User.email == "doctor.one@example.test"))
        assert verify_password(doctor_user.password_hash, "DoctorAccess!42")
        db.session.commit()

    doctor = client.post("/api/v1/auth/login", json={"identifier": "doctor.one@example.test", "password": "DoctorAccess!42"})
    doctor_read = client.get(f"/api/v1/tokens/{token_id}", headers=bearer(doctor))
    assert doctor_read.status_code == 403
    assert doctor_read.get_json()["error"]["code"] == "consent_required"

    security = client.post("/api/v1/auth/login", json={"identifier": "security@example.test", "password": "SecurityAdmin!42"})
    security_headers = bearer(security)
    assert client.get("/api/v1/dashboard/stats?hospital_id=2", headers=security_headers).status_code == 200
    assert client.get(f"/api/v1/tokens/{token_id}", headers=security_headers).status_code == 403
