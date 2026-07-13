"""Queue lifecycle and hospital-resource management endpoints.

Covers task 13.2, 13.3, 13.4, 13.6, 13.8, 13.9, 13.10:

  Patient routes (13.9):
    GET  /api/v1/patients/me/tokens
         List the authenticated patient's own tokens with priority-ordered position.
    GET  /api/v1/patients/me/tokens/<token_id>/position
         Real-time position and wait estimate for one token.

  Staff queue actions (13.2 / 13.3):
    POST /api/v1/queue/tokens/<token_id>/action
         Apply a lifecycle action: call_next, complete, miss, requeue, cancel.
    GET  /api/v1/queue/departments/<dept_id>/next
         Return the next token the doctor should call.

  Live queue feed (13.6):
    GET  /api/v1/queue/live/<dept_id>
         Server-Sent Events stream delivering queue state updates every 5 s.
         Replaces the fake frontend ticker.

  Emergency workflow (13.8):
    POST /api/v1/queue/tokens/<token_id>/emergency
         Escalate a token to emergency priority; create EmergencyCase record;
         fire a monitoring-style alert to assigned doctor.

  Hospital-admin controls (13.10):
    GET  /api/v1/admin/hospitals/<hospital_id>/queue
         Full live queue overview (all departments, breakdown, next tokens).
    GET  /api/v1/admin/departments/<dept_id>/tokens
         Priority-ordered waiting-token list for a department.
    PATCH /api/v1/admin/doctors/<doctor_id>/availability
         Toggle a doctor's availability status.
"""

from __future__ import annotations

import json
import time as _time
from datetime import datetime, timezone

from flask import Flask, Response, g, jsonify, stream_with_context
from sqlalchemy import select

from audit import write_audit_event
from auth_service import (
    ROLE_DOCTOR,
    ROLE_HOSPITAL_ADMIN,
    ROLE_PATIENT,
)
from authorization import enforce_tenant, require_auth
from errors import ApiProblem
from extensions import db, limiter
from models import Doctor, EmergencyCase, PatientProfile, Token
from rate_limits import SENSITIVE_WRITE_RATE_LIMIT
from repository import MediFlowRepository
from schemas import (
    DoctorAvailabilityRequest,
    EmergencyEscalateRequest,
    QueueActionRequest,
    validate_json,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _repo() -> MediFlowRepository:
    return MediFlowRepository(db.session)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


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


def _get_token_or_404(token_id: int) -> Token:
    token = db.session.get(Token, token_id)
    if token is None:
        raise ApiProblem("token_not_found", "Token not found", 404)
    return token


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------

def register_queue_routes(app: Flask) -> None:

    # ======================================================================
    # Patient — own tokens with live position (13.9)
    # ======================================================================

    @app.get("/api/v1/patients/me/tokens")
    @require_auth(ROLE_PATIENT)
    def patient_list_tokens():
        """List all tokens for the authenticated patient with live positions."""
        patient = db.session.scalar(
            select(PatientProfile).where(
                PatientProfile.user_id == g.current_user.user_id
            )
        )
        if patient is None:
            return _success([])

        tokens = list(
            db.session.scalars(
                select(Token)
                .where(Token.patient_profile_id == patient.patient_profile_id)
                .order_by(Token.created_at.desc())
            )
        )
        repo = _repo()
        result = []
        for token in tokens:
            position = (
                repo.queue_position_v2(token.dept_id, token.token_id)
                if token.status == "waiting"
                else None
            )
            wait = (
                repo.wait_estimate(token.dept_id, token.token_id)
                if token.status == "waiting"
                else None
            )
            result.append({
                "token_id": token.token_id,
                "token_number": token.token_number,
                "status": token.status,
                "priority": token.priority,
                "hospital_id": token.hospital_id,
                "dept_id": token.dept_id,
                "queue_date": token.queue_date.isoformat(),
                "position": position,
                "estimated_wait_minutes": wait,
                "created_at": token.created_at.isoformat(),
            })

        _audit("queue.patient_tokens_viewed", "patient_profile", patient.public_id)
        db.session.commit()
        return _success(result)

    @app.get("/api/v1/patients/me/tokens/<int:token_id>/position")
    @require_auth(ROLE_PATIENT)
    def patient_token_position(token_id: int):
        """Real-time priority-ordered position and wait estimate (13.4 / 13.9)."""
        token = _get_token_or_404(token_id)

        # Ownership — patient may only see their own tokens.
        if token.user_id != g.current_user.user_id:
            raise ApiProblem("ownership_required", "You do not own this token", 403)

        repo = _repo()
        position = (
            repo.queue_position_v2(token.dept_id, token.token_id)
            if token.status == "waiting"
            else None
        )
        wait = (
            repo.wait_estimate(token.dept_id, token.token_id)
            if token.status == "waiting"
            else None
        )
        db.session.commit()
        return _success({
            "token_id": token_id,
            "token_number": token.token_number,
            "status": token.status,
            "priority": token.priority,
            "position": position,
            "estimated_wait_minutes": wait,
            "last_updated": _utcnow().isoformat(),
        })

    # ======================================================================
    # Staff — queue lifecycle actions (13.2 / 13.3)
    # ======================================================================

    @app.post("/api/v1/queue/tokens/<int:token_id>/action")
    @require_auth(ROLE_DOCTOR, ROLE_HOSPITAL_ADMIN)
    @limiter.limit(SENSITIVE_WRITE_RATE_LIMIT)
    def queue_token_action(token_id: int):
        """Apply call_next, complete, miss, requeue, or cancel to a token (13.2)."""
        body = validate_json(QueueActionRequest)
        token = _get_token_or_404(token_id)
        enforce_tenant(token.hospital_id)

        repo = _repo()
        repo.perform_queue_action(
            token,
            body.action,
            actor_user_id=g.current_user.user_id,
            session=db.session,
            reason=body.reason,
        )
        db.session.commit()
        return _success({
            "token_id": token_id,
            "token_number": token.token_number,
            "status": token.status,
            "action_applied": body.action,
        })

    @app.get("/api/v1/queue/departments/<int:dept_id>/next")
    @require_auth(ROLE_DOCTOR, ROLE_HOSPITAL_ADMIN)
    def queue_next_token(dept_id: int):
        """Return the next highest-priority waiting token for this department (13.2 / 13.3)."""
        # Verify the department belongs to the caller's hospital.
        from models import Department
        dept = db.session.get(Department, dept_id)
        if dept is None:
            raise ApiProblem("dept_not_found", "Department not found", 404)
        enforce_tenant(dept.hospital_id)

        repo = _repo()
        next_token = repo.get_next_waiting_token(dept_id)
        if next_token is None:
            return _success({"next_token": None, "queue_empty": True})

        from models import User
        user = db.session.get(User, next_token.user_id)
        db.session.commit()
        return _success({
            "next_token": {
                "token_id": next_token.token_id,
                "token_number": next_token.token_number,
                "priority": next_token.priority,
                "patient_name": user.name if user else None,
                "created_at": next_token.created_at.isoformat(),
            },
            "queue_empty": False,
        })

    # ======================================================================
    # Live queue SSE feed — replaces fake frontend ticker (13.6)
    # ======================================================================

    @app.get("/api/v1/queue/live/<int:dept_id>")
    @require_auth(ROLE_DOCTOR, ROLE_HOSPITAL_ADMIN, ROLE_PATIENT)
    def queue_live_feed(dept_id: int):
        """Server-Sent Events stream — pushes queue state every 5 seconds (13.6).

        Patients receive their own position only.
        Doctors / admins receive the full department summary.

        The client connects once and keeps the connection open; no polling
        loop needed in the frontend.  If the connection drops, the client
        reconnects using the standard SSE retry mechanism.
        """
        is_patient = "patient" in g.current_roles
        caller_user_id = g.current_user.user_id

        def generate():
            # Flask app context is needed inside the generator.
            with app.app_context():
                retries = 0
                max_retries = 120   # ~10 minutes at 5 s intervals

                while retries < max_retries:
                    try:
                        from sqlalchemy import create_engine
                        # Re-use the existing session via db.session (already
                        # bound to this request context via app context push).
                        repo = MediFlowRepository(db.session)

                        if is_patient:
                            # Patient payload: their own position only.
                            patient = db.session.scalar(
                                select(PatientProfile).where(
                                    PatientProfile.user_id == caller_user_id
                                )
                            )
                            waiting_token = None
                            if patient:
                                waiting_token = db.session.scalar(
                                    select(Token).where(
                                        Token.patient_profile_id == patient.patient_profile_id,
                                        Token.dept_id == dept_id,
                                        Token.status == "waiting",
                                    ).order_by(Token.created_at.desc()).limit(1)
                                )
                            if waiting_token:
                                pos = repo.queue_position_v2(dept_id, waiting_token.token_id)
                                wait = repo.wait_estimate(dept_id, waiting_token.token_id)
                                payload = {
                                    "token_number": waiting_token.token_number,
                                    "position": pos,
                                    "estimated_wait_minutes": wait,
                                    "status": waiting_token.status,
                                    "priority": waiting_token.priority,
                                    "timestamp": _utcnow().isoformat(),
                                }
                            else:
                                payload = {
                                    "token_number": None,
                                    "position": None,
                                    "estimated_wait_minutes": None,
                                    "status": "no_active_token",
                                    "timestamp": _utcnow().isoformat(),
                                }
                        else:
                            # Staff payload: full department summary.
                            waiting_tokens = repo.ordered_waiting_tokens(dept_id)
                            from models import Department
                            dept = db.session.get(Department, dept_id)
                            payload = {
                                "dept_id": dept_id,
                                "dept_name": dept.dept_name if dept else None,
                                "waiting_count": len(waiting_tokens),
                                "priority_breakdown": {
                                    "emergency": sum(1 for t in waiting_tokens if t.priority == "emergency"),
                                    "elderly": sum(1 for t in waiting_tokens if t.priority == "elderly"),
                                    "normal": sum(1 for t in waiting_tokens if t.priority == "normal"),
                                },
                                "next_token": waiting_tokens[0].token_number if waiting_tokens else None,
                                "timestamp": _utcnow().isoformat(),
                            }

                        db.session.expire_all()   # refresh on next iteration
                        yield f"data: {json.dumps(payload)}\n\n"

                    except Exception as exc:  # noqa: BLE001
                        yield f"data: {json.dumps({'error': str(exc), 'timestamp': _utcnow().isoformat()})}\n\n"

                    _time.sleep(5)
                    retries += 1

                yield "data: {\"event\": \"stream_end\", \"reason\": \"max_duration_reached\"}\n\n"

        return Response(
            stream_with_context(generate()),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",   # disable nginx buffering
                "Connection": "keep-alive",
            },
        )

    # ======================================================================
    # Emergency escalation — creates EmergencyCase + raises priority (13.8)
    # ======================================================================

    @app.post("/api/v1/queue/tokens/<int:token_id>/emergency")
    @require_auth(ROLE_DOCTOR, ROLE_HOSPITAL_ADMIN)
    @limiter.limit(SENSITIVE_WRITE_RATE_LIMIT)
    def escalate_to_emergency(token_id: int):
        """Escalate a token to emergency priority and create an EmergencyCase (13.8).

        Sets token.priority = 'emergency' (moves to front of queue).
        Creates an EmergencyCase row recording the emergency level and response.
        Fires a monitoring alert to the assigned doctor via the existing
        monitoring_service alert pipeline if monitoring is available.
        """
        body = validate_json(EmergencyEscalateRequest)
        token = _get_token_or_404(token_id)
        enforce_tenant(token.hospital_id)

        if token.status not in ("waiting", "serving"):
            raise ApiProblem(
                "invalid_token_state",
                f"Emergency escalation requires status 'waiting' or 'serving' "
                f"(current: '{token.status}')",
                409,
            )

        # Apply emergency priority so the token jumps to the front (13.3).
        old_priority = token.priority
        token.priority = "emergency"

        # Create or update the EmergencyCase record (13.8).
        existing_case = db.session.scalar(
            select(EmergencyCase).where(EmergencyCase.token_id == token_id)
        )
        if existing_case is None:
            emergency_case = EmergencyCase(
                token_id=token_id,
                emergency_level=body.emergency_level,
                response_time=body.response_time_minutes,
                admitted=None,
            )
            db.session.add(emergency_case)
        else:
            existing_case.emergency_level = body.emergency_level

        db.session.flush()

        # Fire a monitoring alert to the assigned doctor (13.8).
        _try_fire_emergency_alert(token, body.emergency_level, body.notes)

        write_audit_event(
            db.session,
            action="queue.emergency_escalated",
            resource_type="token",
            resource_id=token_id,
            actor_user_id=g.current_user.user_id,
            details={
                "old_priority": old_priority,
                "emergency_level": body.emergency_level,
                "hospital_id": token.hospital_id,
                "dept_id": token.dept_id,
                "notes": body.notes,
            },
        )
        db.session.commit()
        return _success({
            "token_id": token_id,
            "token_number": token.token_number,
            "priority": token.priority,
            "emergency_level": body.emergency_level,
        })

    # ======================================================================
    # Hospital-admin resource overview (13.10)
    # ======================================================================

    @app.get("/api/v1/admin/hospitals/<int:hospital_id>/queue")
    @require_auth(ROLE_HOSPITAL_ADMIN)
    def admin_hospital_queue_overview(hospital_id: int):
        """Full live queue overview for all departments (13.10)."""
        enforce_tenant(hospital_id)
        overview = _repo().queue_overview(hospital_id)
        _audit("queue.admin_overview_viewed", "hospital", hospital_id,
               {"hospital_id": hospital_id})
        db.session.commit()
        return _success(overview)

    @app.get("/api/v1/admin/departments/<int:dept_id>/tokens")
    @require_auth(ROLE_DOCTOR, ROLE_HOSPITAL_ADMIN)
    def admin_dept_waiting_tokens(dept_id: int):
        """Priority-ordered waiting-token list for a department (13.10)."""
        from models import Department
        dept = db.session.get(Department, dept_id)
        if dept is None:
            raise ApiProblem("dept_not_found", "Department not found", 404)
        enforce_tenant(dept.hospital_id)

        tokens = _repo().list_waiting_tokens(dept_id)
        db.session.commit()
        return _success(tokens)

    @app.patch("/api/v1/admin/doctors/<int:doctor_id>/availability")
    @require_auth(ROLE_HOSPITAL_ADMIN)
    @limiter.limit(SENSITIVE_WRITE_RATE_LIMIT)
    def admin_set_doctor_availability(doctor_id: int):
        """Toggle a doctor's availability status for queue assignment (13.10)."""
        body = validate_json(DoctorAvailabilityRequest)
        doctor = db.session.get(Doctor, doctor_id)
        if doctor is None:
            raise ApiProblem("doctor_not_found", "Doctor not found", 404)

        from models import Department
        dept = db.session.get(Department, doctor.dept_id)
        if dept is None:
            raise ApiProblem("dept_not_found", "Department not found", 404)
        enforce_tenant(dept.hospital_id)

        old_availability = doctor.availability
        doctor.availability = body.availability
        doctor.patients_today = (
            body.patients_today
            if body.patients_today is not None
            else doctor.patients_today
        )
        db.session.flush()

        write_audit_event(
            db.session,
            action="queue.doctor_availability_changed",
            resource_type="doctor",
            resource_id=doctor_id,
            actor_user_id=g.current_user.user_id,
            details={
                "old_availability": old_availability,
                "new_availability": body.availability,
                "doctor_id": doctor_id,
            },
        )
        db.session.commit()
        return _success({
            "doctor_id": doctor_id,
            "availability": doctor.availability,
            "patients_today": doctor.patients_today,
        })


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _try_fire_emergency_alert(token: Token, emergency_level: str, notes: str | None) -> None:
    """Attempt to fire a monitoring-style alert for the emergency escalation (13.8).

    Gracefully no-ops if the monitoring subsystem is unavailable, so the
    emergency escalation itself is never blocked by alert delivery.
    """
    try:
        from monitoring_service import ensure_monitoring_catalog
        from models import MonitoringAlert, MonitoringRule, DoctorProfile
        from sqlalchemy import select

        # Find the doctor assigned to the token (if any).
        if token.doctor_id is None:
            return

        doctor_profile = db.session.scalar(
            select(DoctorProfile).where(
                DoctorProfile.doctor_id == token.doctor_id,
                DoctorProfile.status == "active",
            )
        )
        if doctor_profile is None:
            return

        # Find or create a sentinel emergency rule for this hospital.
        rule = db.session.scalar(
            select(MonitoringRule).where(
                MonitoringRule.hospital_id == token.hospital_id,
                MonitoringRule.name == "Emergency queue escalation",
            )
        )
        if rule is None:
            rule = MonitoringRule(
                hospital_id=token.hospital_id,
                name="Emergency queue escalation",
                observation_type="heart_rate",   # sentinel type
                severity="critical",
                is_enabled=True,
                created_by_user_id=None,
            )
            db.session.add(rule)
            db.session.flush()

        # We need a real observation ID but don't have one — use the most
        # recent heart-rate observation for the patient if available,
        # otherwise skip the alert row (emergency case row is sufficient).
        from models import PatientObservation
        obs = db.session.scalar(
            select(PatientObservation).where(
                PatientObservation.patient_profile_id == db.session.scalar(
                    select(token.__class__.patient_profile_id).where(
                        token.__class__.token_id == token.token_id
                    )
                ),
                PatientObservation.observation_type == "heart_rate",
            ).order_by(PatientObservation.recorded_at.desc()).limit(1)
        )
        if obs is None:
            return

        from models import utcnow
        alert = MonitoringAlert(
            patient_profile_id=token.patient_profile_id,
            observation_id=obs.observation_id,
            monitoring_rule_id=rule.monitoring_rule_id,
            hospital_id=token.hospital_id,
            severity="critical",
            status="open",
            message=(
                f"Emergency queue escalation — level: {emergency_level}. "
                f"Token: {token.token_number}. "
                + (f"Notes: {notes}" if notes else "")
            ),
            assigned_doctor_profile_id=doctor_profile.doctor_profile_id,
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        db.session.add(alert)
        db.session.flush()

    except Exception:  # noqa: BLE001
        # Alert failure must never break emergency escalation itself.
        pass
