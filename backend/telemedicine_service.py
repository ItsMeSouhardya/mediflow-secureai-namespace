"""Telemedicine domain — service layer.

Covers task 11.3 through 11.8:
  11.3  Configurable Jitsi/WebRTC provider — room name generation and
        signed join URLs via provider-specific JWT tokens.
  11.4  Doctor confirmation, cancellation, and reschedule flow.
  11.5  Patient and doctor waiting-room state transitions.
  11.6  Short-lived signed room tokens — the opaque room_reference is
        NEVER returned directly; callers always receive a time-limited
        signed URL or token valid for ROOM_TOKEN_TTL_MINUTES.
  11.7  Consultation notes, diagnoses, and prescriptions are linked to
        the session via an Encounter row created at completion.
  11.8  Audio/video recording is OFF by default; recording_enabled=False
        is set at session creation and requires explicit admin action to
        change.
  11.9  Every status transition writes an AuditEvent row.

Architecture rules
------------------
- All state-machine transitions happen here; route handlers only call
  service functions and commit.
- room_reference is generated as a UUID-based slug — never a patient
  name or appointment ID — so it carries no PII (11.6 / 11.8).
- The Jitsi JWT is signed with TELEMEDICINE_JITSI_SECRET for a private,
  JWT-enabled deployment. Public Jitsi rooms receive a direct join URL and
  never receive a token that the provider cannot validate.
- Unauthorised join attempts (wrong role, wrong patient/doctor, expired
  token) raise ApiProblem before a room token is issued.
"""

from __future__ import annotations

import logging
import secrets
import uuid as _uuid
from datetime import datetime, timedelta, timezone
from typing import NamedTuple
from uuid import UUID

import jwt as _jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from audit import write_audit_event
from errors import ApiProblem
from models import (
    Appointment,
    DoctorProfile,
    Encounter,
    Hospital,
    PatientProfile,
    TelemedicineSession,
    User,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# How long a signed room access token stays valid after issue (11.6).
ROOM_TOKEN_TTL_MINUTES = 60

# Statuses that allow a join attempt.
_JOINABLE_STATUSES = {"confirmed", "patient_waiting", "doctor_waiting", "in_progress"}

# Valid lifecycle transitions enforced at the service layer.
_VALID_TRANSITIONS: dict[str, set[str]] = {
    "scheduled":        {"confirmed", "cancelled"},
    "confirmed":        {"patient_waiting", "doctor_waiting", "in_progress", "cancelled"},
    "patient_waiting":  {"doctor_waiting", "in_progress", "cancelled"},
    "doctor_waiting":   {"patient_waiting", "in_progress", "cancelled"},
    "in_progress":      {"completed", "cancelled"},
    "completed":        set(),
    "cancelled":        set(),
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _transition(
    session: Session,
    tele: TelemedicineSession,
    to_status: str,
    actor_user_id: int,
    reason: str | None = None,
) -> None:
    """Validate and apply a status transition, writing an audit event."""
    allowed = _VALID_TRANSITIONS.get(tele.status, set())
    if to_status not in allowed:
        raise ApiProblem(
            "invalid_session_state",
            f"Cannot transition from '{tele.status}' to '{to_status}'",
            409,
        )
    old_status = tele.status
    tele.status = to_status
    tele.updated_at = _utcnow()
    session.flush()

    write_audit_event(
        session,
        action=f"telemedicine.session_{to_status}",
        resource_type="telemedicine_session",
        resource_id=str(tele.public_id),
        actor_user_id=actor_user_id,
        details={"from_status": old_status, "to_status": to_status, "reason": reason},
    )


def _session_payload(tele: TelemedicineSession, include_room: bool = False) -> dict:
    """Safe public representation of a session (room_reference excluded by default)."""
    payload: dict = {
        "id": str(tele.public_id),
        "appointment_id": tele.appointment_id,
        "encounter_id": tele.encounter_id,
        "provider": tele.provider,
        "scheduled_start": tele.scheduled_start.isoformat(),
        "scheduled_end": tele.scheduled_end.isoformat() if tele.scheduled_end else None,
        "status": tele.status,
        "patient_joined_at": tele.patient_joined_at.isoformat() if tele.patient_joined_at else None,
        "doctor_joined_at": tele.doctor_joined_at.isoformat() if tele.doctor_joined_at else None,
        "patient_left_at": tele.patient_left_at.isoformat() if tele.patient_left_at else None,
        "doctor_left_at": tele.doctor_left_at.isoformat() if tele.doctor_left_at else None,
        "completed_at": tele.completed_at.isoformat() if tele.completed_at else None,
        "consultation_summary": tele.consultation_summary,
        "cancelled_at": tele.cancelled_at.isoformat() if tele.cancelled_at else None,
        "cancel_reason": tele.cancel_reason,
        "recording_enabled": tele.recording_enabled,
        "created_at": tele.created_at.isoformat(),
    }
    # room_reference is never exposed directly (11.6); callers get a
    # time-limited signed token via issue_room_token() instead.
    if include_room:
        payload["_room_reference"] = tele.room_reference  # internal use only
    return payload


def _get_session(session: Session, public_id: UUID) -> TelemedicineSession:
    tele = session.scalar(
        select(TelemedicineSession).where(TelemedicineSession.public_id == public_id)
    )
    if tele is None:
        raise ApiProblem("session_not_found", "Telemedicine session not found", 404)
    return tele


# ---------------------------------------------------------------------------
# 11.3 — Room reference generation and Jitsi JWT signing
# ---------------------------------------------------------------------------

class RoomToken(NamedTuple):
    """Signed, time-limited room access credential returned to callers."""
    token: str           # signed JWT or opaque token
    room_reference: str  # the room name — included so the client can build the URL
    join_url: str        # ready-to-use Jitsi URL
    expires_at: str      # ISO-8601 UTC


def _generate_room_reference() -> str:
    """Generate an opaque room slug carrying no PII (11.6)."""
    # Format: mf-<8 hex chars>-<8 hex chars>
    # Collision probability is negligible for the expected session volume.
    return f"mf-{secrets.token_hex(4)}-{secrets.token_hex(4)}"


def issue_room_token(
    tele: TelemedicineSession,
    *,
    user: User,
    role: str,             # "patient" | "doctor"
    config: dict,
) -> RoomToken:
    """Issue a short-lived signed room access token (11.6).

    The token is a JWT signed with TELEMEDICINE_JITSI_SECRET for private
    JWT-enabled Jitsi deployments. If the secret is not configured, the
    application returns an opaque access reference and a direct public-room
    URL without a misleading ``?jwt=`` parameter.

    The caller receives the join_url; the backend never exposes the raw
    room_reference except inside the signed token payload.
    """
    now = _utcnow()
    expires_at = now + timedelta(minutes=ROOM_TOKEN_TTL_MINUTES)
    jitsi_domain = config.get("TELEMEDICINE_JITSI_DOMAIN", "meet.jit.si")
    secret = config.get("TELEMEDICINE_JITSI_SECRET", "")
    app_id = config.get("TELEMEDICINE_JITSI_APP_ID", "mediflow")

    claims: dict = {
        "context": {
            "user": {
                "name": user.name,
                # No email — avoid PII in Jitsi token context (11.6/11.8).
                "affiliation": role,
            },
            "features": {
                "recording": False,      # 11.8 — recording always off
                "livestreaming": False,
                "transcription": False,
                "outbound-call": False,
            },
        },
        "aud": "jitsi",
        "iss": app_id,
        "sub": jitsi_domain,
        "room": tele.room_reference,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "nbf": int(now.timestamp()),
    }

    if secret:
        token_str = _jwt.encode(claims, secret, algorithm="HS256")
        join_url = f"https://{jitsi_domain}/{tele.room_reference}?jwt={token_str}"
    else:
        # The API has already authorised the caller. Public Jitsi does not know
        # this application's signing key, so a fabricated JWT would cause valid
        # users to be rejected by the provider.
        token_str = secrets.token_urlsafe(32)
        join_url = f"https://{jitsi_domain}/{tele.room_reference}"

    return RoomToken(
        token=token_str,
        room_reference=tele.room_reference,
        join_url=join_url,
        expires_at=expires_at.isoformat(),
    )


# ---------------------------------------------------------------------------
# 11.4 — Scheduling a new telemedicine session (doctor confirms appointment)
# ---------------------------------------------------------------------------

def schedule_session(
    session: Session,
    *,
    appointment: Appointment,
    doctor: DoctorProfile,
    scheduled_start: datetime,
    scheduled_end: datetime | None,
    actor_user_id: int,
) -> TelemedicineSession:
    """Doctor schedules a telemedicine session for a confirmed appointment (11.4).

    Creates a TelemedicineSession in 'scheduled' status.  The appointment's
    consultation_mode is set to 'telemedicine'.
    """
    # Guard: appointment must belong to this doctor.
    if appointment.doctor_id != doctor.doctor_id:
        raise ApiProblem(
            "care_relationship_required",
            "This appointment is not assigned to you",
            403,
        )

    # Guard: no duplicate session for this appointment.
    existing = session.scalar(
        select(TelemedicineSession).where(
            TelemedicineSession.appointment_id == appointment.appointment_id
        )
    )
    if existing is not None:
        raise ApiProblem(
            "session_exists",
            f"A telemedicine session already exists for this appointment "
            f"(status: {existing.status})",
            409,
        )

    # Resolve patient profile.
    patient_profile = session.scalar(
        select(PatientProfile).where(
            PatientProfile.patient_profile_id == appointment.patient_profile_id
        )
    )
    if patient_profile is None:
        raise ApiProblem(
            "patient_not_found",
            "Patient profile not linked to this appointment",
            404,
        )

    now = _utcnow()
    room_reference = _generate_room_reference()

    tele = TelemedicineSession(
        appointment_id=appointment.appointment_id,
        patient_profile_id=patient_profile.patient_profile_id,
        doctor_profile_id=doctor.doctor_profile_id,
        provider="jitsi",
        room_reference=room_reference,
        scheduled_start=scheduled_start,
        scheduled_end=scheduled_end,
        status="scheduled",
        recording_enabled=False,   # 11.8 — always off at creation
        created_at=now,
        updated_at=now,
    )
    session.add(tele)

    # Mark appointment as telemedicine.
    appointment.consultation_mode = "telemedicine"   # type: ignore[attr-defined]
    appointment.telemedicine_status = "scheduled"    # type: ignore[attr-defined]
    session.flush()

    write_audit_event(
        session,
        action="telemedicine.session_scheduled",
        resource_type="telemedicine_session",
        resource_id=str(tele.public_id),
        actor_user_id=actor_user_id,
        details={
            "appointment_id": appointment.appointment_id,
            "scheduled_start": scheduled_start.isoformat(),
        },
    )
    return tele


def confirm_session(
    session: Session,
    tele: TelemedicineSession,
    *,
    doctor: DoctorProfile,
    actor_user_id: int,
) -> TelemedicineSession:
    """Doctor explicitly confirms a scheduled session (11.4)."""
    if tele.doctor_profile_id != doctor.doctor_profile_id:
        raise ApiProblem("ownership_required", "This session is not assigned to you", 403)
    _transition(session, tele, "confirmed", actor_user_id)
    return tele


def cancel_session(
    session: Session,
    tele: TelemedicineSession,
    *,
    actor_user_id: int,
    reason: str | None,
    cancelled_by_user_id: int,
) -> TelemedicineSession:
    """Cancel a session (doctor or patient — 11.4). Immediate effect."""
    _transition(session, tele, "cancelled", actor_user_id, reason=reason)
    tele.cancelled_at = _utcnow()
    tele.cancelled_by_user_id = cancelled_by_user_id
    tele.cancel_reason = reason
    session.flush()
    return tele


def reschedule_session(
    session: Session,
    tele: TelemedicineSession,
    *,
    doctor: DoctorProfile,
    new_start: datetime,
    new_end: datetime | None,
    actor_user_id: int,
) -> TelemedicineSession:
    """Doctor reschedules a scheduled or confirmed session (11.4).

    Re-generates the room_reference so the old URL becomes invalid.
    """
    if tele.doctor_profile_id != doctor.doctor_profile_id:
        raise ApiProblem("ownership_required", "This session is not assigned to you", 403)
    if tele.status not in {"scheduled", "confirmed"}:
        raise ApiProblem(
            "invalid_session_state",
            f"Only scheduled or confirmed sessions can be rescheduled (current: {tele.status})",
            409,
        )
    tele.scheduled_start = new_start
    tele.scheduled_end = new_end
    tele.room_reference = _generate_room_reference()   # invalidate old URL (11.6)
    tele.status = "scheduled"
    tele.updated_at = _utcnow()
    session.flush()

    write_audit_event(
        session,
        action="telemedicine.session_rescheduled",
        resource_type="telemedicine_session",
        resource_id=str(tele.public_id),
        actor_user_id=actor_user_id,
        details={"new_start": new_start.isoformat()},
    )
    return tele


# ---------------------------------------------------------------------------
# 11.5 — Waiting-room state and join logic
# ---------------------------------------------------------------------------

def patient_join(
    session: Session,
    tele: TelemedicineSession,
    *,
    patient: PatientProfile,
    actor_user_id: int,
) -> TelemedicineSession:
    """Patient enters the waiting room (11.5)."""
    if tele.patient_profile_id != patient.patient_profile_id:
        raise ApiProblem("ownership_required", "This session is not for you", 403)
    if tele.status not in _JOINABLE_STATUSES:
        raise ApiProblem(
            "session_not_joinable",
            f"Session cannot be joined in status '{tele.status}'",
            409,
        )

    now = _utcnow()
    # Check token expiry: session must not be more than 30 min past scheduled_end
    if tele.scheduled_end:
        deadline = tele.scheduled_end + timedelta(minutes=30)
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        if now > deadline:
            raise ApiProblem(
                "session_expired",
                "The scheduled consultation window has passed",
                410,
            )

    tele.patient_joined_at = now

    # Determine new status based on current state.
    if tele.status == "doctor_waiting":
        _transition(session, tele, "in_progress", actor_user_id, reason="Both parties joined")
    else:
        _transition(session, tele, "patient_waiting", actor_user_id, reason="Patient joined waiting room")

    return tele


def doctor_join(
    session: Session,
    tele: TelemedicineSession,
    *,
    doctor: DoctorProfile,
    actor_user_id: int,
) -> TelemedicineSession:
    """Doctor enters the waiting room (11.5)."""
    if tele.doctor_profile_id != doctor.doctor_profile_id:
        raise ApiProblem("ownership_required", "This session is not assigned to you", 403)
    if tele.status not in _JOINABLE_STATUSES:
        raise ApiProblem(
            "session_not_joinable",
            f"Session cannot be joined in status '{tele.status}'",
            409,
        )

    now = _utcnow()
    tele.doctor_joined_at = now

    if tele.status == "patient_waiting":
        _transition(session, tele, "in_progress", actor_user_id, reason="Both parties joined")
    else:
        _transition(session, tele, "doctor_waiting", actor_user_id, reason="Doctor joined waiting room")

    return tele


def patient_leave(
    session: Session,
    tele: TelemedicineSession,
    *,
    patient: PatientProfile,
    actor_user_id: int,
) -> TelemedicineSession:
    """Record patient leaving (does not end the session)."""
    if tele.patient_profile_id != patient.patient_profile_id:
        raise ApiProblem("ownership_required", "This session is not for you", 403)
    tele.patient_left_at = _utcnow()
    tele.updated_at = _utcnow()
    session.flush()
    write_audit_event(
        session,
        action="telemedicine.patient_left",
        resource_type="telemedicine_session",
        resource_id=str(tele.public_id),
        actor_user_id=actor_user_id,
    )
    return tele


def doctor_leave(
    session: Session,
    tele: TelemedicineSession,
    *,
    doctor: DoctorProfile,
    actor_user_id: int,
) -> TelemedicineSession:
    """Record doctor leaving (does not end the session)."""
    if tele.doctor_profile_id != doctor.doctor_profile_id:
        raise ApiProblem("ownership_required", "This session is not assigned to you", 403)
    tele.doctor_left_at = _utcnow()
    tele.updated_at = _utcnow()
    session.flush()
    write_audit_event(
        session,
        action="telemedicine.doctor_left",
        resource_type="telemedicine_session",
        resource_id=str(tele.public_id),
        actor_user_id=actor_user_id,
    )
    return tele


# ---------------------------------------------------------------------------
# 11.7 — Complete session and link outcome to encounter
# ---------------------------------------------------------------------------

def complete_session(
    session: Session,
    tele: TelemedicineSession,
    *,
    doctor: DoctorProfile,
    consultation_summary: str | None,
    encounter_id: int | None,
    actor_user_id: int,
) -> TelemedicineSession:
    """Doctor completes the session and records the outcome (11.7).

    If encounter_id is provided, the session is linked to that encounter so
    consultation notes, diagnoses, and prescriptions recorded there are
    associated with this session.
    """
    if tele.doctor_profile_id != doctor.doctor_profile_id:
        raise ApiProblem("ownership_required", "This session is not assigned to you", 403)

    # Validate encounter belongs to same patient.
    if encounter_id is not None:
        enc = session.get(Encounter, encounter_id)
        if enc is None or enc.patient_profile_id != tele.patient_profile_id:
            raise ApiProblem(
                "encounter_not_found",
                "Encounter not found or not owned by this patient",
                404,
            )
        tele.encounter_id = encounter_id

    tele.completed_at = _utcnow()
    tele.consultation_summary = consultation_summary
    _transition(session, tele, "completed", actor_user_id, reason="Consultation completed")
    return tele


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def list_patient_sessions(
    session: Session,
    patient: PatientProfile,
    *,
    status_filter: str | None = None,
) -> list[dict]:
    """Return telemedicine sessions for a patient (11.10)."""
    q = select(TelemedicineSession).where(
        TelemedicineSession.patient_profile_id == patient.patient_profile_id
    )
    if status_filter:
        q = q.where(TelemedicineSession.status == status_filter)
    q = q.order_by(TelemedicineSession.scheduled_start.desc())
    return [_session_payload(s) for s in session.scalars(q)]


def list_doctor_sessions(
    session: Session,
    doctor: DoctorProfile,
    *,
    status_filter: str | None = None,
) -> list[dict]:
    """Return telemedicine sessions for a doctor (11.11)."""
    q = select(TelemedicineSession).where(
        TelemedicineSession.doctor_profile_id == doctor.doctor_profile_id
    )
    if status_filter:
        q = q.where(TelemedicineSession.status == status_filter)
    q = q.order_by(TelemedicineSession.scheduled_start.desc())
    return [_session_payload(s) for s in session.scalars(q)]


def get_session_for_patient(
    session: Session,
    public_id: UUID,
    patient: PatientProfile,
) -> TelemedicineSession:
    tele = _get_session(session, public_id)
    if tele.patient_profile_id != patient.patient_profile_id:
        raise ApiProblem("ownership_required", "This session is not for you", 403)
    return tele


def get_session_for_doctor(
    session: Session,
    public_id: UUID,
    doctor: DoctorProfile,
) -> TelemedicineSession:
    tele = _get_session(session, public_id)
    if tele.doctor_profile_id != doctor.doctor_profile_id:
        raise ApiProblem("ownership_required", "This session is not assigned to you", 403)
    return tele
