from __future__ import annotations

import ai_engine


def test_health_and_readiness(client):
    health = client.get("/api/health")
    readiness = client.get("/api/ready")
    assert health.status_code == 200
    assert health.get_json()["status"] == "ok"
    assert readiness.status_code == 200
    assert readiness.get_json()["database"] == "connected"


def test_hospital_and_dashboard_baseline(client):
    hospitals = client.get("/api/hospitals")
    dashboard = client.get("/api/dashboard/stats?hospital_id=1")
    assert hospitals.status_code == 200
    assert len(hospitals.get_json()) == 3
    assert dashboard.status_code == 200
    body = dashboard.get_json()
    assert set(body) == {"total_waiting", "total_served", "active_doctors", "departments"}
    assert len(body["departments"]) == 6


def test_emergency_analysis_compatibility(client):
    response = client.get("/api/analyze?symptoms=chest%20pain&dept_id=1")
    assert response.status_code == 200
    assert response.get_json()["recommended_department"] == "Cardiology"


def test_ai_report_contract(client):
    response = client.get("/api/ai-report?dept_id=1&token=A001&symptoms=fever&age=45")
    assert response.status_code == 200
    body = response.get_json()
    assert body["status"] == "success"
    assert {
        "wait_time",
        "advice",
        "doctor",
        "department",
        "position",
        "priority_score",
        "queue_length",
    }.issubset(body["data"])
    total_time = body["data"]["total_time"]
    expected = "You can visit now to hospital" if total_time < 30 else f"Delay your visit by {total_time - 30} mins"
    assert body["data"]["advice"] == expected


def test_ai_report_recommends_an_immediate_visit_for_a_short_journey(client, monkeypatch):
    monkeypatch.setattr(ai_engine, "hospital_journey", lambda repo, dept_id, wait_time: (["Short journey"], 25))
    response = client.get("/api/ai-report?dept_id=1&token=A001&symptoms=checkup&age=30")
    assert response.status_code == 200
    report = response.get_json()["data"]
    assert report["total_time"] < 30
    assert report["advice"] == "You can visit now to hospital"


def test_booking_allocates_unique_transactional_numbers(client):
    payload = {
        "dept_id": 1,
        "patient_name": "Migration Test Patient",
        "age": 40,
        "phone": "9000012345",
        "gender": "Other",
        "symptoms": "general checkup",
    }
    first = client.post("/api/tokens/book", json=payload)
    second = client.post("/api/tokens/book", json={**payload, "phone": "9000012346"})
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.get_json()["token_code"] == "A005"
    assert second.get_json()["token_code"] == "A006"
    assert first.get_json()["token_code"] != second.get_json()["token_code"]

    tracked = client.get(f"/api/tokens/{first.get_json()['token_id']}")
    assert tracked.status_code == 200
    assert tracked.get_json()["patient_name"] == "Migration Test Patient"
