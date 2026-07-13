from __future__ import annotations

from sqlalchemy.pool import StaticPool

from app import create_app
from extensions import db
from models import AuditEvent, IdempotencyRecord
from seed import seed_demo_data


def test_v1_envelope_request_id_and_security_headers(client):
    request_id = "trace-phase2-0001"
    response = client.get("/api/v1/hospitals", headers={"X-Request-ID": request_id})
    body = response.get_json()

    assert response.status_code == 200
    assert body["status"] == "success"
    assert isinstance(body["data"], list)
    assert body["meta"]["request_id"] == request_id
    assert response.headers["X-Request-ID"] == request_id
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Cache-Control"] == "no-store"


def test_legacy_collection_contract_is_preserved(client):
    response = client.get("/api/hospitals")
    assert response.status_code == 200
    assert isinstance(response.get_json(), list)


def test_invalid_query_uses_safe_standard_error(client, auth_headers):
    response = client.get(
        "/api/v1/ai-report?dept_id=invalid&symptoms=fever&age=999&unexpected=value",
        headers=auth_headers,
    )
    body = response.get_json()
    assert response.status_code == 422
    assert body["status"] == "error"
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["message"] == "Query parameters are invalid"
    assert body["error"]["details"]
    assert "999" not in str(body["error"]["details"])


def test_pagination_sorting_and_date_range_validation(client, auth_headers):
    response = client.get("/api/v1/appointments?page=1&per_page=1&sort_order=asc", headers=auth_headers)
    body = response.get_json()
    assert response.status_code == 200
    assert len(body["data"]) == 1
    assert body["meta"]["pagination"] == {
        "page": 1,
        "per_page": 1,
        "total": 1,
        "total_pages": 1,
    }

    too_large = client.get("/api/v1/appointments?per_page=101", headers=auth_headers)
    invalid_dates = client.get("/api/v1/appointments?date_from=2026-07-12&date_to=2026-07-01", headers=auth_headers)
    assert too_large.status_code == 422
    assert invalid_dates.status_code == 422


def test_booking_idempotency_and_durable_audit(client, app, auth_headers):
    payload = {
        "dept_id": 1,
        "patient_name": "Idempotent Patient",
        "age": 36,
        "phone": "9000090001",
        "gender": "Other",
        "symptoms": "general checkup",
    }
    headers = {**auth_headers, "Idempotency-Key": "booking-phase2-0001"}
    first = client.post("/api/v1/tokens/book", json=payload, headers=headers)
    replay = client.post("/api/v1/tokens/book", json=payload, headers=headers)

    assert first.status_code == 201
    assert replay.status_code == 201
    assert replay.headers["Idempotent-Replayed"] == "true"
    assert first.get_json()["data"]["token_id"] == replay.get_json()["data"]["token_id"]

    conflict = client.post(
        "/api/v1/tokens/book",
        json={**payload, "phone": "9000090002"},
        headers=headers,
    )
    assert conflict.status_code == 409
    assert conflict.get_json()["error"]["code"] == "idempotency_conflict"

    with app.app_context():
        assert db.session.query(IdempotencyRecord).count() == 1
        booking_events = db.session.query(AuditEvent).filter_by(action="token.booked").all()
        assert len(booking_events) == 1
        assert booking_events[0].request_id


def test_v1_requires_idempotency_key_for_booking(client, auth_headers):
    response = client.post(
        "/api/v1/tokens/book",
        json={"dept_id": 1, "patient_name": "No Key", "age": 30, "symptoms": "checkup"},
        headers=auth_headers,
    )
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "idempotency_key_required"


def test_cors_rejects_unlisted_origins(client):
    allowed = client.get("/api/v1/health", headers={"Origin": "http://localhost:5173"})
    denied = client.get("/api/v1/health", headers={"Origin": "https://untrusted.example"})
    assert allowed.headers["Access-Control-Allow-Origin"] == "http://localhost:5173"
    assert "Access-Control-Allow-Origin" not in denied.headers


def test_rate_limit_returns_standard_v1_error():
    application = create_app(
        "testing",
        {
            "SQLALCHEMY_DATABASE_URI": "sqlite+pysqlite:///:memory:",
            "SQLALCHEMY_ENGINE_OPTIONS": {
                "poolclass": StaticPool,
                "connect_args": {"check_same_thread": False},
            },
            "RATELIMIT_ENABLED": True,
            "RATELIMIT_STORAGE_URI": "memory://",
            "CORS_ORIGINS": ["http://localhost:5173"],
        },
    )
    with application.app_context():
        db.create_all()
        seed_demo_data(db.session)
        db.session.commit()
        client = application.test_client()
        responses = [
            client.get("/api/v1/analyze?symptoms=fever&dept_id=1")
            for _ in range(31)
        ]
        assert responses[-1].status_code == 429
        assert responses[-1].get_json()["error"]["code"] == "rate_limit_exceeded"
        db.session.remove()
        db.drop_all()
