"""Patient-visible audit history scoped strictly to patient-owned resources."""

from __future__ import annotations

from flask import Flask, g, jsonify, request
from sqlalchemy import or_, select

from auth_service import ROLE_PATIENT
from authorization import require_auth
from ehr_service import ensure_patient_profile
from extensions import db
from models import (
    AuditEvent,
    ConsentGrant,
    CrossHospitalShare,
    MedicalDocument,
    MonitoringAlert,
    PatientObservation,
    TelemedicineSession,
    Token,
)


def register_patient_audit_routes(app: Flask) -> None:
    @app.get("/api/v1/patients/me/audit-events")
    @require_auth(ROLE_PATIENT)
    def patient_audit_events():
        patient = ensure_patient_profile(db.session, g.current_user)
        limit = min(max(int(request.args.get("limit", 100)), 1), 250)

        resource_ids: dict[str, set[str]] = {
            "patient_profile": {str(patient.public_id)},
            "medical_document": {
                str(value) for value in db.session.scalars(
                    select(MedicalDocument.public_id).where(
                        MedicalDocument.patient_profile_id == patient.patient_profile_id
                    )
                )
            },
            "consent_grant": {
                str(value) for value in db.session.scalars(
                    select(ConsentGrant.public_id).where(
                        ConsentGrant.patient_profile_id == patient.patient_profile_id
                    )
                )
            },
            "cross_hospital_share": {
                str(value) for value in db.session.scalars(
                    select(CrossHospitalShare.public_id).where(
                        CrossHospitalShare.patient_profile_id == patient.patient_profile_id
                    )
                )
            },
            "patient_observation": {
                str(value) for value in db.session.scalars(
                    select(PatientObservation.public_id).where(
                        PatientObservation.patient_profile_id == patient.patient_profile_id
                    )
                )
            },
            "monitoring_alert": {
                str(value) for value in db.session.scalars(
                    select(MonitoringAlert.public_id).where(
                        MonitoringAlert.patient_profile_id == patient.patient_profile_id
                    )
                )
            },
            "telemedicine_session": {
                str(value) for value in db.session.scalars(
                    select(TelemedicineSession.public_id).where(
                        TelemedicineSession.patient_profile_id == patient.patient_profile_id
                    )
                )
            },
            "token": {
                str(value) for value in db.session.scalars(
                    select(Token.token_id).where(Token.patient_profile_id == patient.patient_profile_id)
                )
            },
        }
        conditions = [AuditEvent.actor_user_id == g.current_user.user_id]
        for resource_type, ids in resource_ids.items():
            if ids:
                conditions.append(
                    (AuditEvent.resource_type == resource_type) & AuditEvent.resource_id.in_(ids)
                )
        rows = db.session.scalars(
            select(AuditEvent)
            .where(or_(*conditions))
            .order_by(AuditEvent.created_at.desc())
            .limit(limit)
        )
        return jsonify({"status": "success", "data": [{
            "id": str(item.public_id),
            "action": item.action,
            "resource_type": item.resource_type,
            "resource_id": item.resource_id,
            "outcome": item.outcome,
            "actor": "you" if item.actor_user_id == g.current_user.user_id else "authorized care team",
            "request_id": item.request_id,
            "details": item.details,
            "created_at": item.created_at.isoformat(),
        } for item in rows]})
