"""Telemedicine HTTP endpoints.

Patient routes (11.10):
  GET  /api/v1/patients/me/telemedicine
       List all telemedicine sessions (filterable by status).
  GET  /api/v1/patients/me/telemedicine/<id>
       Session detail and current waiting-room status.
  POST /api/v1/patients/me/telemedicine/<id>/join
       Patient enters the waiting room; returns a short-lived room token (11.6).
  POST /api/v1/patients/me/telemedicine/<id>/leave
       Record patient leaving the room.
  POST /api/v1/patients/me/telemedicine/<id>/cancel
       Patient cancels a scheduled or confirmed session.

Doctor routes (11.11):
  GET  /api/v1/doctors/me/telemedicine
       List sessions assigned to this doctor (filterable by status).
  GET  /api/v1/doctors/me/telemedicine/<id>
       Session detail.
  POST /api/v1/doctors/me/appointments/<appt_id>/telemedicine
       Schedule a new telemedicine session for an appointment.
  POST /api/v1/doctors/me/telemedicine/<id>/confirm
       Confirm a scheduled session.
  POST /api/v1/doctors/me/telemedicine/<id>/reschedule
       Reschedule a scheduled or confirmed session.
  POST /api/v1/doctors/me/telemedicine/<id>/join
       Doctor enters the waiting room; returns a short-lived room token (11.6).
  POST /api/v1/doctors/me/telemedicine/<id>/leave
       Record doctor leaving the room.
  POST /api/v1/doctors/me/telemedicine/<id>/cancel
       Doctor cancels a session.
  POST /api/v1/doctors/me/telemedicine/<id>/complete
       Complete the session, link encounter, and record summary (11.7).
"""

from __future__ import annotations

from datetime import timezone
from uuid import UUID

from flask import Flask, current_app, g, jsonify

from audit import write_audit_event
from auth_service import ROLE_DOCTOR, ROLE_PATIENT
from authorization import require_auth
from ehr_service import (
    doctor_profile_for_user,
    ensure_patient_profile,
)
from errors import ApiProblem
from extensions import db, limiter
from models import Appointment
from rate_limits import SENSITIVE_WRITE_RATE_LIMIT
from schemas import (
    ConsultationCancelRequest,
    ConsultationCompleteRequest,
    TelemedicineRescheduleRequest,
    TelemedicineScheduleRequest,
    validate_json,
)
from telemedicine_service import (
    RoomToken,
    cancel_session,
    complete_session,
    confirm_session,
    doctor_join,
    doctor_leave,
    get_session_for_doctor,
    get_session_for_patient,
    issue_room_token,
    list_doctor_sessions,
    list_patient_sessions,
    patient_join,
    patient_leave,
    reschedule_session,
    schedule_session,
    _session_payload,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _success(data, status: int = 200):
    return jsonify({"status": "success", "data": data}), status


def _audit(action: str, resource_type: str, resource_id, details: dict | None = None) -> None:
    write_audit_event(
        db.session,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        actor_user_id=g.current_user.user_id,
        details=details or {},
    )


def _room_token_payload(rt: RoomToken) -> dict:
    return {
        "token": rt.token,
        "room_reference": rt.room_reference,
        "join_url": rt.join_url,
        "expires_at": rt.expires_at,
    }


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register_telemedicine_routes(app: Flask) -> None:

    # ======================================================================
    # Patient routes (11.10)
    # ======================================================================

    @app.get("/api/v1/patients/me/telemedicine")
    @require_auth(ROLE_PATIENT)
    def patient_list_sessions():
        """List telemedicine sessions for the authenticated patient."""
        from flask import request as _req
        status_filter = _req.args.get("status")
        patient = ensure_patient_profile(db.session, g.current_user)
        sessions = list_patient_sessions(db.session, patient, status_filter=status_filter)
        _audit("telemedicine.patient_list_viewed", "patient_profile", patient.public_id)
        db.session.commit()
        return _success(sessions)

    @app.get("/api/v1/patients/me/telemedicine/<uuid:session_id>")
    @require_auth(ROLE_PATIENT)
    def patient_get_session(session_id: UUID):
        """Session detail and current waiting-room status."""
        patient = ensure_patient_profile(db.session, g.current_user)
        tele = get_session_for_patient(db.session, session_id, patient)
        _audit("telemedicine.session_viewed", "telemedicine_session", tele.public_id)
        db.session.commit()
        return _success(_session_payload(tele))

    @app.post("/api/v1/patients/me/telemedicine/<uuid:session_id>/join")
    @require_auth(ROLE_PATIENT)
    @limiter.limit(SENSITIVE_WRITE_RATE_LIMIT)
    def patient_join_session(session_id: UUID):
        """Patient enters the waiting room. Returns a short-lived room token (11.6)."""
        patient = ensure_patient_profile(db.session, g.current_user)
        tele = get_session_for_patient(db.session, session_id, patient)
        patient_join(db.session, tele, patient=patient, actor_user_id=g.current_user.user_id)
        token = issue_room_token(
            tele, user=g.current_user, role="patient", config=current_app.config
        )
        db.session.commit()
        return _success({
            "session": _session_payload(tele),
            "room_access": _room_token_payload(token),
        })

    @app.post("/api/v1/patients/me/telemedicine/<uuid:session_id>/leave")
    @require_auth(ROLE_PATIENT)
    @limiter.limit(SENSITIVE_WRITE_RATE_LIMIT)
    def patient_leave_session(session_id: UUID):
        """Record patient leaving the room."""
        patient = ensure_patient_profile(db.session, g.current_user)
        tele = get_session_for_patient(db.session, session_id, patient)
        patient_leave(db.session, tele, patient=patient, actor_user_id=g.current_user.user_id)
        db.session.commit()
        return _success({"id": str(tele.public_id), "status": tele.status})

    @app.post("/api/v1/patients/me/telemedicine/<uuid:session_id>/cancel")
    @require_auth(ROLE_PATIENT)
    @limiter.limit(SENSITIVE_WRITE_RATE_LIMIT)
    def patient_cancel_session(session_id: UUID):
        """Patient cancels a scheduled or confirmed session."""
        body = validate_json(ConsultationCancelRequest)
        patient = ensure_patient_profile(db.session, g.current_user)
        tele = get_session_for_patient(db.session, session_id, patient)
        cancel_session(
            db.session,
            tele,
            actor_user_id=g.current_user.user_id,
            reason=body.reason,
            cancelled_by_user_id=g.current_user.user_id,
        )
        db.session.commit()
        return _success({"id": str(tele.public_id), "status": tele.status})

    # ======================================================================
    # Doctor routes (11.11)
    # ======================================================================

    @app.get("/api/v1/doctors/me/telemedicine")
    @require_auth(ROLE_DOCTOR)
    def doctor_list_sessions():
        """List telemedicine sessions for the authenticated doctor."""
        from flask import request as _req
        status_filter = _req.args.get("status")
        doctor = doctor_profile_for_user(db.session, g.current_user.user_id)
        sessions = list_doctor_sessions(db.session, doctor, status_filter=status_filter)
        db.session.commit()
        return _success(sessions)

    @app.get("/api/v1/doctors/me/telemedicine/<uuid:session_id>")
    @require_auth(ROLE_DOCTOR)
    def doctor_get_session(session_id: UUID):
        """Session detail."""
        doctor = doctor_profile_for_user(db.session, g.current_user.user_id)
        tele = get_session_for_doctor(db.session, session_id, doctor)
        _audit("telemedicine.doctor_session_viewed", "telemedicine_session", tele.public_id)
        db.session.commit()
        return _success(_session_payload(tele))

    @app.post("/api/v1/doctors/me/appointments/<int:appointment_id>/telemedicine")
    @require_auth(ROLE_DOCTOR)
    @limiter.limit(SENSITIVE_WRITE_RATE_LIMIT)
    def doctor_schedule_session(appointment_id: int):
        """Schedule a new telemedicine session for an appointment (11.4)."""
        body = validate_json(TelemedicineScheduleRequest)
        doctor = doctor_profile_for_user(db.session, g.current_user.user_id)

        appointment = db.session.get(Appointment, appointment_id)
        if appointment is None:
            raise ApiProblem("appointment_not_found", "Appointment not found", 404)

        # Ensure scheduled_start is timezone-aware.
        start = body.scheduled_start
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        end = body.scheduled_end
        if end is not None and end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)

        tele = schedule_session(
            db.session,
            appointment=appointment,
            doctor=doctor,
            scheduled_start=start,
            scheduled_end=end,
            actor_user_id=g.current_user.user_id,
        )
        db.session.commit()
        return _success({"id": str(tele.public_id), "status": tele.status}, 201)

    @app.post("/api/v1/doctors/me/telemedicine/<uuid:session_id>/confirm")
    @require_auth(ROLE_DOCTOR)
    @limiter.limit(SENSITIVE_WRITE_RATE_LIMIT)
    def doctor_confirm_session(session_id: UUID):
        """Doctor confirms a scheduled session."""
        doctor = doctor_profile_for_user(db.session, g.current_user.user_id)
        tele = get_session_for_doctor(db.session, session_id, doctor)
        confirm_session(db.session, tele, doctor=doctor, actor_user_id=g.current_user.user_id)
        db.session.commit()
        return _success({"id": str(tele.public_id), "status": tele.status})

    @app.post("/api/v1/doctors/me/telemedicine/<uuid:session_id>/reschedule")
    @require_auth(ROLE_DOCTOR)
    @limiter.limit(SENSITIVE_WRITE_RATE_LIMIT)
    def doctor_reschedule_session(session_id: UUID):
        """Reschedule a scheduled or confirmed session (11.4). Invalidates old room URL."""
        body = validate_json(TelemedicineRescheduleRequest)
        doctor = doctor_profile_for_user(db.session, g.current_user.user_id)
        tele = get_session_for_doctor(db.session, session_id, doctor)

        start = body.scheduled_start
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        end = body.scheduled_end
        if end is not None and end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)

        reschedule_session(
            db.session,
            tele,
            doctor=doctor,
            new_start=start,
            new_end=end,
            actor_user_id=g.current_user.user_id,
        )
        db.session.commit()
        return _success({
            "id": str(tele.public_id),
            "status": tele.status,
            "scheduled_start": tele.scheduled_start.isoformat(),
        })

    @app.post("/api/v1/doctors/me/telemedicine/<uuid:session_id>/join")
    @require_auth(ROLE_DOCTOR)
    @limiter.limit(SENSITIVE_WRITE_RATE_LIMIT)
    def doctor_join_session(session_id: UUID):
        """Doctor enters the waiting room. Returns a short-lived room token (11.6)."""
        doctor = doctor_profile_for_user(db.session, g.current_user.user_id)
        tele = get_session_for_doctor(db.session, session_id, doctor)
        doctor_join(db.session, tele, doctor=doctor, actor_user_id=g.current_user.user_id)
        token = issue_room_token(
            tele, user=g.current_user, role="doctor", config=current_app.config
        )
        db.session.commit()
        return _success({
            "session": _session_payload(tele),
            "room_access": _room_token_payload(token),
        })

    @app.post("/api/v1/doctors/me/telemedicine/<uuid:session_id>/leave")
    @require_auth(ROLE_DOCTOR)
    @limiter.limit(SENSITIVE_WRITE_RATE_LIMIT)
    def doctor_leave_session(session_id: UUID):
        """Record doctor leaving the room."""
        doctor = doctor_profile_for_user(db.session, g.current_user.user_id)
        tele = get_session_for_doctor(db.session, session_id, doctor)
        doctor_leave(db.session, tele, doctor=doctor, actor_user_id=g.current_user.user_id)
        db.session.commit()
        return _success({"id": str(tele.public_id), "status": tele.status})

    @app.post("/api/v1/doctors/me/telemedicine/<uuid:session_id>/cancel")
    @require_auth(ROLE_DOCTOR)
    @limiter.limit(SENSITIVE_WRITE_RATE_LIMIT)
    def doctor_cancel_session(session_id: UUID):
        """Doctor cancels a session (11.4)."""
        body = validate_json(ConsultationCancelRequest)
        doctor = doctor_profile_for_user(db.session, g.current_user.user_id)
        tele = get_session_for_doctor(db.session, session_id, doctor)
        cancel_session(
            db.session,
            tele,
            actor_user_id=g.current_user.user_id,
            reason=body.reason,
            cancelled_by_user_id=g.current_user.user_id,
        )
        db.session.commit()
        return _success({"id": str(tele.public_id), "status": tele.status})

    @app.post("/api/v1/doctors/me/telemedicine/<uuid:session_id>/complete")
    @require_auth(ROLE_DOCTOR)
    @limiter.limit(SENSITIVE_WRITE_RATE_LIMIT)
    def doctor_complete_session(session_id: UUID):
        """Complete the consultation and link outcome to an encounter (11.7)."""
        body = validate_json(ConsultationCompleteRequest)
        doctor = doctor_profile_for_user(db.session, g.current_user.user_id)
        tele = get_session_for_doctor(db.session, session_id, doctor)
        complete_session(
            db.session,
            tele,
            doctor=doctor,
            consultation_summary=body.consultation_summary,
            encounter_id=body.encounter_id,
            actor_user_id=g.current_user.user_id,
        )
        db.session.commit()
        return _success({
            "id": str(tele.public_id),
            "status": tele.status,
            "encounter_id": tele.encounter_id,
            "completed_at": tele.completed_at.isoformat() if tele.completed_at else None,
        })
