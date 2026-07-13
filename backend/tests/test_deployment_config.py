from types import SimpleNamespace
from uuid import uuid4

import jwt


def test_render_database_url_selects_psycopg3(monkeypatch):
    from config import _database_url

    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@render.internal/db")

    assert _database_url("production") == (
        "postgresql+psycopg://user:pass@render.internal/db"
    )


def test_explicit_sqlalchemy_driver_is_preserved(monkeypatch):
    from config import _database_url

    expected = "postgresql+psycopg://user:pass@localhost/db"
    monkeypatch.setenv("DATABASE_URL", expected)

    assert _database_url("production") == expected


def test_public_jitsi_url_does_not_include_unverifiable_jwt():
    from telemedicine_service import issue_room_token

    tele = SimpleNamespace(public_id=uuid4(), room_reference="mf-public-room")
    user = SimpleNamespace(name="Prototype Patient")

    room = issue_room_token(
        tele,
        user=user,
        role="patient",
        config={
            "TELEMEDICINE_JITSI_DOMAIN": "meet.jit.si",
            "TELEMEDICINE_JITSI_SECRET": "",
        },
    )

    assert room.join_url == "https://meet.jit.si/mf-public-room"
    assert "jwt=" not in room.join_url
    assert room.token


def test_private_jitsi_url_contains_signed_provider_jwt():
    from telemedicine_service import issue_room_token

    tele = SimpleNamespace(public_id=uuid4(), room_reference="mf-private-room")
    user = SimpleNamespace(name="Prototype Doctor")
    jitsi_secret = "test-jitsi-secret-at-least-32-bytes"

    room = issue_room_token(
        tele,
        user=user,
        role="doctor",
        config={
            "TELEMEDICINE_JITSI_DOMAIN": "video.example.test",
            "TELEMEDICINE_JITSI_SECRET": jitsi_secret,
            "TELEMEDICINE_JITSI_APP_ID": "mediflow-test",
        },
    )

    claims = jwt.decode(
        room.token,
        jitsi_secret,
        algorithms=["HS256"],
        audience="jitsi",
    )
    assert room.join_url.endswith(f"?jwt={room.token}")
    assert claims["iss"] == "mediflow-test"
    assert claims["room"] == "mf-private-room"
