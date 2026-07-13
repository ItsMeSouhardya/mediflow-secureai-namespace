"""Regression coverage for the public prototype hospital dashboard."""


def test_public_dashboard_stats_are_available_without_staff_authentication(client):
    response = client.get("/api/dashboard/stats?hospital_id=1")
    assert response.status_code == 200
    data = response.get_json()
    assert set(data) >= {"total_waiting", "total_served", "active_doctors", "departments"}
    assert data["departments"]
    assert all(set(row) >= {"name", "waiting", "completed", "est_wait", "crowd_color", "queue_capacity", "load_percentage"} for row in data["departments"])
    assert all(0 <= row["load_percentage"] <= 100 for row in data["departments"])
    assert any(row["waiting"] and row["load_percentage"] < 100 for row in data["departments"])
