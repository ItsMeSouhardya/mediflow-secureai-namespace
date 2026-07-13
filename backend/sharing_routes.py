"""Task 9 cross-hospital sharing API."""

from __future__ import annotations

from uuid import UUID

from flask import Flask, g, jsonify, request

from auth_service import ROLE_DOCTOR, ROLE_HOSPITAL_ADMIN, ROLE_PATIENT
from authorization import require_auth
from ehr_service import doctor_profile_for_user, ensure_patient_profile, patient_profile_by_public_id
from errors import ApiProblem
from extensions import db, limiter
from rate_limits import SENSITIVE_WRITE_RATE_LIMIT
from schemas import (
    CrossHospitalBreakGlassRequest,
    CrossHospitalShareRequest,
    ShareDenyRequest,
    ShareGrantRequest,
    ShareRevokeRequest,
    validate_json,
)
from sharing_service import (
    access_shared_record,
    deny_share,
    get_share,
    grant_share,
    list_hospital_incoming_shares,
    list_incoming_shares,
    list_patient_shares,
    request_break_glass_share,
    request_share,
    revoke_share,
    share_payload,
)


def _success(data, status: int = 200):
    return jsonify({"status": "success", "data": data}), status


def register_sharing_routes(app: Flask) -> None:
    @app.get("/api/v1/patients/me/shares")
    @require_auth(ROLE_PATIENT)
    def patient_shares():
        patient = ensure_patient_profile(db.session, g.current_user)
        return _success(list_patient_shares(db.session, patient, status_filter=request.args.get("status")))

    @app.post("/api/v1/patients/me/shares/<uuid:share_id>/grant")
    @require_auth(ROLE_PATIENT)
    @limiter.limit(SENSITIVE_WRITE_RATE_LIMIT)
    def patient_grant_share(share_id: UUID):
        body = validate_json(ShareGrantRequest)
        patient = ensure_patient_profile(db.session, g.current_user)
        share = grant_share(
            db.session, get_share(db.session, share_id), patient=patient,
            scopes=body.scopes, access_expires_days=body.access_expires_days,
            actor_user_id=g.current_user.user_id,
        )
        db.session.commit()
        return _success(share_payload(db.session, share))

    @app.post("/api/v1/patients/me/shares/<uuid:share_id>/deny")
    @require_auth(ROLE_PATIENT)
    @limiter.limit(SENSITIVE_WRITE_RATE_LIMIT)
    def patient_deny_share(share_id: UUID):
        body = validate_json(ShareDenyRequest)
        patient = ensure_patient_profile(db.session, g.current_user)
        share = deny_share(
            db.session, get_share(db.session, share_id), patient=patient,
            reason=body.reason, actor_user_id=g.current_user.user_id,
        )
        db.session.commit()
        return _success(share_payload(db.session, share))

    @app.post("/api/v1/patients/me/shares/<uuid:share_id>/revoke")
    @require_auth(ROLE_PATIENT)
    @limiter.limit(SENSITIVE_WRITE_RATE_LIMIT)
    def patient_revoke_share(share_id: UUID):
        body = validate_json(ShareRevokeRequest)
        patient = ensure_patient_profile(db.session, g.current_user)
        share = revoke_share(
            db.session, get_share(db.session, share_id), patient=patient,
            reason=body.reason, actor_user_id=g.current_user.user_id,
        )
        db.session.commit()
        return _success(share_payload(db.session, share))

    @app.post("/api/v1/doctors/me/shares/requests")
    @require_auth(ROLE_DOCTOR)
    @limiter.limit(SENSITIVE_WRITE_RATE_LIMIT)
    def doctor_request_share():
        body = validate_json(CrossHospitalShareRequest)
        doctor = doctor_profile_for_user(db.session, g.current_user.user_id)
        patient = patient_profile_by_public_id(db.session, body.patient_id)
        share = request_share(
            db.session, doctor=doctor, patient=patient,
            source_hospital_id=body.source_hospital_id, scopes=body.scopes,
            purpose=body.purpose, operation=body.operation,
            requested_duration_days=body.requested_duration_days,
            actor_user_id=g.current_user.user_id,
        )
        db.session.commit()
        return _success(share_payload(db.session, share), 201)

    @app.post("/api/v1/doctors/me/shares/break-glass")
    @require_auth(ROLE_DOCTOR)
    @limiter.limit(SENSITIVE_WRITE_RATE_LIMIT)
    def doctor_break_glass_share():
        body = validate_json(CrossHospitalBreakGlassRequest)
        doctor = doctor_profile_for_user(db.session, g.current_user.user_id)
        patient = patient_profile_by_public_id(db.session, body.patient_id)
        share = request_break_glass_share(
            db.session, doctor=doctor, patient=patient,
            source_hospital_id=body.source_hospital_id, scopes=body.scopes,
            reason=body.reason, actor_user_id=g.current_user.user_id,
        )
        db.session.commit()
        return _success({**share_payload(db.session, share), "warning": "Emergency access is audited and expires in four hours."}, 201)

    @app.get("/api/v1/doctors/me/shares/incoming")
    @require_auth(ROLE_DOCTOR)
    def doctor_incoming_shares():
        doctor = doctor_profile_for_user(db.session, g.current_user.user_id)
        return _success(list_incoming_shares(db.session, doctor, status_filter=request.args.get("status")))

    @app.get("/api/v1/doctors/me/shares/<uuid:share_id>/records")
    @require_auth(ROLE_DOCTOR)
    def doctor_access_shared_records(share_id: UUID):
        doctor = doctor_profile_for_user(db.session, g.current_user.user_id)
        try:
            data = access_shared_record(
                db.session, get_share(db.session, share_id), doctor=doctor,
                actor_user_id=g.current_user.user_id,
            )
        except ApiProblem:
            # Access denials and lazy expiry are security events and must survive
            # the rejected HTTP request.
            db.session.commit()
            raise
        db.session.commit()
        return _success(data)

    @app.get("/api/v1/hospitals/me/shares/incoming")
    @require_auth(ROLE_HOSPITAL_ADMIN)
    def hospital_incoming_shares():
        hospital_ids = sorted(g.current_tenants.get(ROLE_HOSPITAL_ADMIN, set()))
        return _success(list_hospital_incoming_shares(
            db.session, hospital_ids, status_filter=request.args.get("status")
        ))
