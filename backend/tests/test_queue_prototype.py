"""Regression coverage for the patient-facing prototype queue simulation."""

from extensions import db
from models import QueueSession, Token


def test_booking_queue_and_report_share_one_patient_facing_snapshot(client, app, auth_headers):
    with app.app_context():
        # Exercise the fresh daily-session path that previously always returned A001.
        db.session.query(Token).filter(Token.dept_id == 1).delete(synchronize_session=False)
        db.session.query(QueueSession).filter(QueueSession.dept_id == 1).delete(synchronize_session=False)
        db.session.commit()

    booked = client.post(
        "/api/v1/tokens/book",
        headers={**auth_headers, "Idempotency-Key": "prototype-queue-regression-0001"},
        json={
            "dept_id": 1,
            "patient_name": "Booked Patient Name",
            "age": 47,
            "symptoms": "routine follow-up",
        },
    )
    assert booked.status_code == 201
    booking_envelope = booked.get_json()
    booking = booking_envelope.get("data", booking_envelope)
    token_number = booking["token_number"]
    assert token_number.startswith("A")
    assert 20 <= int(token_number[1:]) <= 160

    tracked = client.get(f"/api/v1/public/tokens/{booking['tracking_code']}")
    assert tracked.status_code == 200
    queue_envelope = tracked.get_json()
    queue = queue_envelope.get("data", queue_envelope)
    assert queue["display_token"] == token_number
    assert queue["position"] >= 2

    report_response = client.get(
        f"/api/v1/patients/me/tokens/{booking['token_id']}/ai-report",
        headers=auth_headers,
    )
    assert report_response.status_code == 200
    report = report_response.get_json()["data"]
    assert report["token_number"] == token_number
    assert report["patient_name"] == "Booked Patient Name"
    assert report["age"] == 47
    assert report["position"] == queue["position"]
    assert report["wait_time"] == queue["wait_time"]
    assert queue["wait_time"] == queue["position"] * report["consult_time"]
    assert report["booked_department"] == "General Medicine"
