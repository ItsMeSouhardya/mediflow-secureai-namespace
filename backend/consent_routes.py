"""Consent and authorization domain endpoints.

Patient routes (7.9):
  GET  /api/v1/patients/me/consent/inbox
       Pending access requests awaiting the patient's decision.
  GET  /api/v1/patients/me/consent/active
       Currently active (granted + break_glass) consents.
  GET  /api/v1/patients/me/consent/history
       Full consent lifecycle history.
  POST /api/v1/patients/me/consent/<id>/grant
       Grant a pending request (optionally narrowing scopes and expiry).
  POST /api/v1/patients/me/consent/<id>/deny
       Deny a pending request.
  POST /api/v1/patients/me/consent/<id>/revoke
       Revoke a previously granted consent (immediate effect).
  GET  /api/v1/patients/me/notifications
       Consent notification inbox.
  POST /api/v1/patients/me/notifications/mark-read
       Mark notifications as read.

Doctor routes (7.10):
  POST /api/v1/doctors/me/consent/request
       Submit a new access request for a patient's records.
  GET  /api/v1/doctors/me/consent/requests
       List all consent requests made by this doctor.
  GET  /api/v1/doctors/me/consent/status/<patient_id>
       Current consent state with a specific patient.
  POST /api/v1/doctors/me/consent/break-glass
       Emergency break-glass access (mandatory reason, 4-hour cap).
  GET  /api/v1/doctors/me/notifications
       Consent notification inbox.
  POST /api/v1/doctors/me/notifications/mark-read
       Mark notifications as read.
"""

from __future__ import annotations

from uuid import UUID

from flask import Flask, g, jsonify
from sqlalchemy import select

from audit import write_audit_event
from blockchain_service import (
    enqueue_consent_grant,
    enqueue_consent_revocation,
    transaction_payload,
)
from auth_service import ROLE_DOCTOR, ROLE_PATIENT
from authorization import require_auth
from consent_service import (
    deny_access,
    get_consent_status,
    get_grant_for_doctor,
    get_grant_for_patient,
    grant_access,
    list_doctor_requests,
    list_notifications,
    list_patient_active,
    list_patient_history,
    list_patient_pending,
    mark_notifications_read,
    request_access,
    request_break_glass_access,
    revoke_access,
)
from ehr_service import (
    doctor_profile_for_user,
    ensure_patient_profile,
    patient_profile_by_public_id,
)
from extensions import db, limiter
from rate_limits import SENSITIVE_WRITE_RATE_LIMIT
from schemas import (
    BreakGlassRequest,
    ConsentDenyRequest,
    ConsentGrantRequest,
    ConsentRequestCreate,
    ConsentRevokeRequest,
    MarkNotificationReadRequest,
    validate_json,
)


# ---------------------------------------------------------------------------
# Internal helpers
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


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------

def register_consent_routes(app: Flask) -> None:

    # ======================================================================
    # Patient — consent inbox and management (7.9)
    # ======================================================================

    @app.get("/api/v1/patients/me/consent/inbox")
    @require_auth(ROLE_PATIENT)
    def patient_consent_inbox():
        """Pending consent requests awaiting patient's decision."""
        patient = ensure_patient_profile(db.session, g.current_user)
        _audit("consent.inbox_viewed", "patient_profile", patient.public_id)
        db.session.commit()
        return _success(list_patient_pending(db.session, patient))

    @app.get("/api/v1/patients/me/consent/active")
    @require_auth(ROLE_PATIENT)
    def patient_consent_active():
        """Active (granted + break_glass) consent grants."""
        patient = ensure_patient_profile(db.session, g.current_user)
        _audit("consent.active_viewed", "patient_profile", patient.public_id)
        db.session.commit()
        return _success(list_patient_active(db.session, patient))

    @app.get("/api/v1/patients/me/consent/history")
    @require_auth(ROLE_PATIENT)
    def patient_consent_history():
        """Full consent lifecycle history for this patient."""
        patient = ensure_patient_profile(db.session, g.current_user)
        _audit("consent.history_viewed", "patient_profile", patient.public_id)
        db.session.commit()
        return _success(list_patient_history(db.session, patient))

    @app.post("/api/v1/patients/me/consent/<uuid:grant_id>/grant")
    @require_auth(ROLE_PATIENT)
    @limiter.limit(SENSITIVE_WRITE_RATE_LIMIT)
    def patient_grant_consent(grant_id: UUID):
        """Grant a pending access request."""
        body = validate_json(ConsentGrantRequest)
        patient = ensure_patient_profile(db.session, g.current_user)
        grant = get_grant_for_patient(db.session, grant_id, patient)

        grant_access(
            db.session,
            grant,
            patient=patient,
            scopes=body.scopes,
            access_expires_days=body.access_expires_days,
            actor_user_id=g.current_user.user_id,
        )
        proof_transaction = enqueue_consent_grant(db.session, grant, app.config)
        db.session.commit()
        return _success({
            "id": str(grant.public_id),
            "status": grant.status,
            "scopes": grant.scopes,
            "access_expires_at": grant.access_expires_at.isoformat(),
            "blockchain_proof": transaction_payload(proof_transaction),
        })

    @app.post("/api/v1/patients/me/consent/<uuid:grant_id>/deny")
    @require_auth(ROLE_PATIENT)
    @limiter.limit(SENSITIVE_WRITE_RATE_LIMIT)
    def patient_deny_consent(grant_id: UUID):
        """Deny a pending access request."""
        body = validate_json(ConsentDenyRequest)
        patient = ensure_patient_profile(db.session, g.current_user)
        grant = get_grant_for_patient(db.session, grant_id, patient)

        deny_access(
            db.session,
            grant,
            patient=patient,
            reason=body.reason,
            actor_user_id=g.current_user.user_id,
        )
        db.session.commit()
        return _success({"id": str(grant.public_id), "status": grant.status})

    @app.post("/api/v1/patients/me/consent/<uuid:grant_id>/revoke")
    @require_auth(ROLE_PATIENT)
    @limiter.limit(SENSITIVE_WRITE_RATE_LIMIT)
    def patient_revoke_consent(grant_id: UUID):
        """Revoke a previously granted consent (immediate effect)."""
        body = validate_json(ConsentRevokeRequest)
        patient = ensure_patient_profile(db.session, g.current_user)
        grant = get_grant_for_patient(db.session, grant_id, patient)

        revoke_access(
            db.session,
            grant,
            patient=patient,
            reason=body.reason,
            actor_user_id=g.current_user.user_id,
        )
        proof_transaction = enqueue_consent_revocation(db.session, grant, app.config)
        db.session.commit()
        return _success({
            "id": str(grant.public_id),
            "status": grant.status,
            "blockchain_proof": transaction_payload(proof_transaction),
        })

    # ======================================================================
    # Patient — notifications (7.8 / 7.9)
    # ======================================================================

    @app.get("/api/v1/patients/me/notifications")
    @require_auth(ROLE_PATIENT)
    def patient_notifications():
        """Consent notification inbox."""
        from flask import request as _req
        unread_only = _req.args.get("unread_only", "false").lower() == "true"
        notifs = list_notifications(db.session, g.current_user.user_id, unread_only=unread_only)
        db.session.commit()
        return _success(notifs)

    @app.post("/api/v1/patients/me/notifications/mark-read")
    @require_auth(ROLE_PATIENT)
    @limiter.limit(SENSITIVE_WRITE_RATE_LIMIT)
    def patient_mark_notifications_read():
        """Mark one or more notifications as read."""
        body = validate_json(MarkNotificationReadRequest)
        count = mark_notifications_read(
            db.session, body.notification_ids, g.current_user.user_id
        )
        db.session.commit()
        return _success({"marked_read": count})

    # ======================================================================
    # Doctor — consent requests and status (7.10)
    # ======================================================================

    @app.post("/api/v1/doctors/me/consent/request")
    @require_auth(ROLE_DOCTOR)
    @limiter.limit(SENSITIVE_WRITE_RATE_LIMIT)
    def doctor_request_consent():
        """Submit a new access request for a patient's records."""
        body = validate_json(ConsentRequestCreate)
        doctor = doctor_profile_for_user(db.session, g.current_user.user_id)
        patient = patient_profile_by_public_id(db.session, body.patient_id)

        grant = request_access(
            db.session,
            doctor=doctor,
            patient=patient,
            scopes=body.scopes,
            purpose=body.purpose,
            operation=body.operation,
            requested_duration_days=body.requested_duration_days,
            actor_user_id=g.current_user.user_id,
        )
        db.session.commit()
        return _success({"id": str(grant.public_id), "status": grant.status}, 201)

    @app.get("/api/v1/doctors/me/consent/requests")
    @require_auth(ROLE_DOCTOR)
    def doctor_list_consent_requests():
        """List all consent requests made by this doctor."""
        doctor = doctor_profile_for_user(db.session, g.current_user.user_id)
        db.session.commit()
        return _success(list_doctor_requests(db.session, doctor))

    @app.get("/api/v1/doctors/me/consent/status/<uuid:patient_id>")
    @require_auth(ROLE_DOCTOR)
    def doctor_consent_status(patient_id: UUID):
        """Current consent state with a specific patient."""
        doctor = doctor_profile_for_user(db.session, g.current_user.user_id)
        patient = patient_profile_by_public_id(db.session, patient_id)
        status = get_consent_status(db.session, doctor, patient)
        _audit(
            "consent.status_checked",
            "patient_profile",
            patient.public_id,
            {"doctor_profile_id": str(doctor.public_id)},
        )
        db.session.commit()
        return _success(status)

    @app.post("/api/v1/doctors/me/consent/break-glass")
    @require_auth(ROLE_DOCTOR)
    @limiter.limit(SENSITIVE_WRITE_RATE_LIMIT)
    def doctor_break_glass():
        """Emergency break-glass access — mandatory reason, 4-hour cap (7.7)."""
        body = validate_json(BreakGlassRequest)
        doctor = doctor_profile_for_user(db.session, g.current_user.user_id)
        patient = patient_profile_by_public_id(db.session, body.patient_id)

        grant = request_break_glass_access(
            db.session,
            doctor=doctor,
            patient=patient,
            scopes=body.scopes,
            reason=body.reason,
            actor_user_id=g.current_user.user_id,
        )
        proof_transaction = enqueue_consent_grant(db.session, grant, app.config)
        db.session.commit()
        return _success(
            {
                "id": str(grant.public_id),
                "status": grant.status,
                "scopes": grant.scopes,
                "access_expires_at": grant.access_expires_at.isoformat(),
                "warning": (
                    "Break-glass access is logged with enhanced detail. "
                    "The patient has been notified immediately. "
                    "Access expires in 4 hours."
                ),
                "blockchain_proof": transaction_payload(proof_transaction),
            },
            201,
        )

    # ======================================================================
    # Doctor — notifications (7.8 / 7.10)
    # ======================================================================

    @app.get("/api/v1/doctors/me/notifications")
    @require_auth(ROLE_DOCTOR)
    def doctor_notifications():
        """Consent notification inbox for doctor."""
        from flask import request as _req
        unread_only = _req.args.get("unread_only", "false").lower() == "true"
        notifs = list_notifications(db.session, g.current_user.user_id, unread_only=unread_only)
        db.session.commit()
        return _success(notifs)

    @app.post("/api/v1/doctors/me/notifications/mark-read")
    @require_auth(ROLE_DOCTOR)
    @limiter.limit(SENSITIVE_WRITE_RATE_LIMIT)
    def doctor_mark_notifications_read():
        """Mark one or more consent notifications as read."""
        body = validate_json(MarkNotificationReadRequest)
        count = mark_notifications_read(
            db.session, body.notification_ids, g.current_user.user_id
        )
        db.session.commit()
        return _success({"marked_read": count})
