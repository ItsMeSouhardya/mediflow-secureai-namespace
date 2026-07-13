"""Online PostgreSQL acceptance checks for Tasks 1 and 2.

This script refuses to run against a database whose name does not end in
``_test``. It applies Alembic migrations, installs deterministic demo data when
needed, exercises concurrent queue allocation with independent transactions,
and validates the API security foundation against that real PostgreSQL target.
"""

from __future__ import annotations

import sys
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app import create_app  # noqa: E402
from config import get_config  # noqa: E402
from extensions import db  # noqa: E402
from flask_migrate import upgrade  # noqa: E402
from models import Department, Hospital, PatientProfile, Token, User  # noqa: E402
from repository import MediFlowRepository  # noqa: E402
from seed import seed_demo_data  # noqa: E402


CONCURRENT_BOOKINGS = 20


def _target_url() -> str:
    configured = get_config("testing").SQLALCHEMY_DATABASE_URI
    url = make_url(configured)
    if url.get_backend_name() != "postgresql":
        raise SystemExit("TEST_DATABASE_URL must use PostgreSQL for this verifier")
    if not (url.database or "").endswith("_test"):
        raise SystemExit("Refusing to modify a database whose name does not end in '_test'")
    return configured


def _migrate_and_seed(database_url: str):
    application = create_app(
        "testing",
        {
            "SQLALCHEMY_DATABASE_URI": database_url,
            "SQLALCHEMY_ENGINE_OPTIONS": {"pool_pre_ping": True},
            "RATELIMIT_ENABLED": True,
            "RATELIMIT_STORAGE_URI": "memory://",
            "CORS_ORIGINS": ["http://localhost:5173"],
        },
    )
    with application.app_context():
        upgrade(directory=str(BACKEND_DIR / "migrations"))
        if db.session.scalar(select(func.count(Hospital.hospital_id))) == 0:
            seed_demo_data(db.session)
            db.session.commit()
    return application


def _concurrent_booking_check(database_url: str) -> dict:
    engine = create_engine(
        database_url,
        pool_pre_ping=True,
        pool_size=CONCURRENT_BOOKINGS,
        max_overflow=CONCURRENT_BOOKINGS,
    )
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with Session(engine) as session:
        patient_user_id = session.scalar(
            select(User.user_id).where(User.email == "patient@mediflow.test")
        )
        department_id = session.scalar(select(Department.dept_id).order_by(Department.dept_id))
        if patient_user_id is None or department_id is None:
            raise RuntimeError("Deterministic patient or department is missing from the test database")

    run_id = uuid.uuid4().hex[:12]

    def book(index: int) -> tuple[int, str, int]:
        session = factory()
        try:
            token = MediFlowRepository(session).book_token(
                dept_id=department_id,
                patient_name="PostgreSQL concurrency verifier",
                age=35,
                phone=None,
                gender="Other",
                symptoms="test-only concurrency verification",
                priority="normal",
                doctor_id=None,
                user_id=patient_user_id,
                tracking_code_hash=f"{run_id}{index:02d}".ljust(64, "0"),
                tracking_code_last4=f"{index:04d}"[-4:],
            )
            session.commit()
            return token.queue_session_id, token.token_number, token.token_id
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    results = []
    with ThreadPoolExecutor(max_workers=CONCURRENT_BOOKINGS) as executor:
        futures = [executor.submit(book, index) for index in range(CONCURRENT_BOOKINGS)]
        for future in as_completed(futures):
            results.append(future.result())

    queue_sessions = {item[0] for item in results}
    token_numbers = [item[1] for item in results]
    if len(queue_sessions) != 1:
        raise AssertionError(f"Concurrent bookings crossed queue sessions: {queue_sessions}")
    if len(token_numbers) != len(set(token_numbers)):
        raise AssertionError(f"Duplicate PostgreSQL token numbers detected: {token_numbers}")

    with Session(engine) as session:
        persisted = int(session.scalar(select(func.count(Token.token_id)).where(
            Token.token_id.in_([item[2] for item in results])
        )) or 0)
    engine.dispose()
    if persisted != CONCURRENT_BOOKINGS:
        raise AssertionError(f"Expected {CONCURRENT_BOOKINGS} committed tokens, found {persisted}")
    return {
        "workers": CONCURRENT_BOOKINGS,
        "committed": persisted,
        "unique_token_numbers": len(set(token_numbers)),
        "queue_session_id": next(iter(queue_sessions)),
    }


def _api_foundation_check(application) -> dict:
    client = application.test_client()
    request_id = f"postgres-task12-{uuid.uuid4().hex[:12]}"
    traced = client.get("/api/v1/hospitals", headers={"X-Request-ID": request_id})
    assert traced.status_code == 200, (traced.status_code, traced.get_json(silent=True))
    assert traced.headers["X-Request-ID"] == request_id
    assert traced.get_json()["meta"]["request_id"] == request_id
    assert traced.headers["X-Content-Type-Options"] == "nosniff"
    assert traced.headers["X-Frame-Options"] == "DENY"

    allowed = client.get("/api/v1/health", headers={"Origin": "http://localhost:5173"})
    denied = client.get("/api/v1/health", headers={"Origin": "https://untrusted.example"})
    assert allowed.headers.get("Access-Control-Allow-Origin") == "http://localhost:5173"
    assert "Access-Control-Allow-Origin" not in denied.headers

    login = client.post(
        "/api/v1/auth/login",
        json={"identifier": "patient@mediflow.test", "password": "PatientDemo!123"},
    )
    assert login.status_code == 200
    authorization = {"Authorization": f"Bearer {login.get_json()['data']['access_token']}"}
    invalid = client.get(
        "/api/v1/ai-report?dept_id=invalid&symptoms=fever&age=999&unexpected=value",
        headers=authorization,
    )
    assert invalid.status_code == 422
    invalid_body = invalid.get_json()
    assert invalid_body["error"]["code"] == "validation_error"
    assert "999" not in str(invalid_body["error"]["details"])

    idempotency_key = f"postgres-idempotency-{uuid.uuid4().hex}"
    booking_headers = {**authorization, "Idempotency-Key": idempotency_key}
    payload = {
        "dept_id": 1,
        "patient_name": "Ignored authenticated name",
        "age": 35,
        "gender": "Other",
        "symptoms": "test-only idempotency verification",
    }
    first = client.post("/api/v1/tokens/book", json=payload, headers=booking_headers)
    replay = client.post("/api/v1/tokens/book", json=payload, headers=booking_headers)
    assert first.status_code == replay.status_code == 201
    assert replay.headers.get("Idempotent-Replayed") == "true"
    assert first.get_json()["data"]["token_id"] == replay.get_json()["data"]["token_id"]

    responses = [
        client.get("/api/v1/analyze?symptoms=fever&dept_id=1")
        for _ in range(31)
    ]
    assert responses[-1].status_code == 429
    assert responses[-1].get_json()["error"]["code"] == "rate_limit_exceeded"
    return {
        "request_id": "passed",
        "safe_validation": "passed",
        "cors_allowlist": "passed",
        "idempotency_replay": "passed",
        "rate_limit": "passed",
    }


def main() -> None:
    database_url = _target_url()
    application = _migrate_and_seed(database_url)
    concurrency = _concurrent_booking_check(database_url)
    api = _api_foundation_check(application)
    print("PostgreSQL Task 1 concurrency:", concurrency)
    print("PostgreSQL Task 2 API foundation:", api)
    print("Tasks 1 and 2 online PostgreSQL verification passed.")


if __name__ == "__main__":
    main()
