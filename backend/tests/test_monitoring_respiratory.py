"""Regression coverage for respiratory-rate monitoring."""


def test_patient_can_record_respiratory_rate_and_trigger_warning(client, auth_headers):
    response = client.post(
        "/api/v1/patients/me/monitoring/observations",
        headers=auth_headers,
        json={
            "observation_type": "respiratory_rate",
            "value": 32,
            "source_reference": "prototype:respiratory_rate",
        },
    )
    assert response.status_code == 201
    data = response.get_json()["data"]
    assert data["observation"]["type"] == "respiratory_rate"
    assert data["observation"]["unit"] == "breaths/min"
    assert data["alerts"]
    assert data["alerts"][0]["severity"] == "warning"

    history = client.get(
        "/api/v1/patients/me/monitoring/observations?type=respiratory_rate",
        headers=auth_headers,
    )
    assert history.status_code == 200
    assert [(item["type"], item["value"]) for item in history.get_json()["data"]] == [
        ("respiratory_rate", 32.0)
    ]

    cleared = client.post(
        "/api/v1/patients/me/monitoring/observations/respiratory_rate/clear",
        headers=auth_headers,
    )
    assert cleared.status_code == 200
    assert cleared.get_json()["data"]["deleted_count"] == 1
    assert client.get(
        "/api/v1/patients/me/monitoring/observations?type=respiratory_rate",
        headers=auth_headers,
    ).get_json()["data"] == []
