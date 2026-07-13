from __future__ import annotations

from auth_service import ROLE_SECURITY_ADMIN, onboard_staff
from extensions import db
from models import SecurityAlert, SecurityBlockAction, SecurityEvent, User
from security_service import collect_security_event


def _bearer(response):
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.get_json()['data']['access_token']}"}


def _security_admin(client, app):
    email = "security.ops@example.test"; password = "SecurityOperations!42"
    with app.app_context():
        assigner = db.session.scalar(db.select(User).where(User.email == "patient@mediflow.test"))
        onboard_staff(
            db.session, name="Security Operator", email=email, phone=None, password=password,
            role_name=ROLE_SECURITY_ADMIN, hospital_id=None, doctor_id=None,
            employee_code=None, assigned_by_user_id=assigner.user_id,
        )
        db.session.commit()
    return _bearer(client.post("/api/v1/auth/login", json={"identifier": email, "password": password}))


def test_failed_logins_and_denied_clinical_access_are_visible_and_explainable(client, app):
    admin_headers = _security_admin(client, app)
    for _ in range(5):
        response = client.post(
            "/api/v1/auth/login",
            json={"identifier": "patient@mediflow.test", "password": "incorrect-password"},
        )
        assert response.status_code == 401

    denied = client.get("/api/v1/patients/me/ehr", headers=admin_headers)
    assert denied.status_code == 403

    events = client.get("/api/v1/security/events", headers=admin_headers).get_json()["data"]
    failed = [item for item in events if item["event_type"] == "identity.login_failure"]
    assert len(failed) == 5
    assert any(item["event_type"] == "access.denied" for item in events)
    serialized = str(events).lower()
    for forbidden in ("incorrect-password", "symptoms", "clinical_notes", "document content", "ramesh"):
        assert forbidden not in serialized

    alerts = client.get("/api/v1/security/alerts", headers=admin_headers).get_json()["data"]
    brute = next(item for item in alerts if item["rule_code"] == "brute_force_15m")
    assert brute["evidence"]["event_count"] >= 5
    assert brute["confidence"] == 0.98
    acknowledged = client.patch(
        f"/api/v1/security/alerts/{brute['id']}", headers=admin_headers,
        json={"action": "acknowledged", "notes": "Validated repeated failures against account."},
    )
    assert acknowledged.status_code == 200
    resolved = client.patch(
        f"/api/v1/security/alerts/{brute['id']}", headers=admin_headers,
        json={"action": "resolved", "notes": "Account owner contacted and credentials rotated."},
    )
    assert resolved.get_json()["data"]["status"] == "resolved"
    detail = client.get(f"/api/v1/security/alerts/{brute['id']}", headers=admin_headers).get_json()["data"]
    assert [item["action"] for item in detail["history"]] == ["acknowledged", "resolved"]

    dataset = client.get(
        "/api/v1/security/anomaly-dataset?source=synthetic&count=20&seed=7",
        headers=admin_headers,
    ).get_json()["data"]
    assert dataset["model_status"] == "experimental_advisory_only"
    assert len(dataset["rows"]) == 20
    assert {row["label"] for row in dataset["rows"]} == {"normal", "anomalous"}


def test_manual_account_control_blocks_and_release_restores_access(client, app):
    patient_login = client.post(
        "/api/v1/auth/login",
        json={"identifier": "patient@mediflow.test", "password": "PatientDemo!123"},
    )
    patient_headers = _bearer(patient_login)
    patient_public_id = client.get("/api/v1/auth/me", headers=patient_headers).get_json()["data"]["id"]
    admin_headers = _security_admin(client, app)

    blocked = client.post(
        "/api/v1/security/blocks", headers=admin_headers,
        json={
            "target_type": "account", "target": patient_public_id,
            "reason": "Temporary investigation control for suspicious activity", "duration_minutes": 30,
        },
    )
    assert blocked.status_code == 201
    block = blocked.get_json()["data"]
    restricted = client.get("/api/v1/auth/me", headers=patient_headers)
    assert restricted.status_code == 423
    assert restricted.get_json()["error"]["code"] == "security_control_active"

    released = client.post(
        f"/api/v1/security/blocks/{block['id']}/release", headers=admin_headers,
        json={"reason": "Investigation completed; account activity is legitimate"},
    )
    assert released.status_code == 200
    assert client.get("/api/v1/auth/me", headers=patient_headers).status_code == 200
    exported = client.get("/api/v1/security/export", headers=admin_headers)
    assert exported.status_code == 200
    assert exported.mimetype == "text/csv"
    assert b"event_type" in exported.data


def test_integrity_and_rate_limit_rules_are_deterministic_and_anomaly_is_advisory(app):
    with app.app_context():
        user = db.session.scalar(db.select(User).where(User.email == "patient@mediflow.test"))
        collect_security_event(
            db.session, event_type="document.integrity_verification", outcome="failure",
            actor_user_id=user.user_id, resource_type="medical_document", resource_id="opaque-doc",
            remote_addr="198.51.100.10", user_agent="test-device",
        )
        event = collect_security_event(
            db.session, event_type="rate_limit.violation", outcome="denied",
            actor_user_id=user.user_id, resource_type="api_route", resource_id="/api/v1/example",
            remote_addr="198.51.100.10", user_agent="test-device",
        )
        db.session.commit()
        rules = {item.rule_code for item in db.session.query(SecurityAlert).all()}
        assert {"integrity_failure", "request_burst"} <= rules
        block = db.session.query(SecurityBlockAction).filter_by(rule_code="request_burst").one()
        assert block.automated is True
        assert event.anomaly_advisory is True
        assert all(item.rule_code != "advisory_anomaly_score" or item.anomaly_advisory for item in db.session.query(SecurityAlert))
        assert db.session.query(SecurityEvent).filter_by(resource_id="opaque-doc").one().safe_metadata == {}
