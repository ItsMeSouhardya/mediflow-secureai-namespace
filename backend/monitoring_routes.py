"""Task 10 monitoring, alert triage, rule configuration, and SSE endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from flask import Flask, Response, g, jsonify, request, stream_with_context

from audit import write_audit_event
from auth_service import ROLE_DOCTOR, ROLE_HOSPITAL_ADMIN, ROLE_PATIENT
from authorization import enforce_tenant, require_auth
from consent_service import check_consent_scope
from ehr_service import doctor_profile_for_user, ensure_patient_profile, patient_profile_by_public_id
from errors import ApiProblem
from extensions import db, limiter
from models import MonitoringAlert, MonitoringRule, ObservationDefinition, PatientProfile, User
from monitoring_realtime import broker, doctor_channel, patient_channel
from monitoring_service import (
    alert_payload,
    clear_patient_observations,
    definition_payload,
    ensure_monitoring_catalog,
    get_alert_for_doctor,
    list_doctor_alerts,
    list_observations,
    observation_payload,
    publish_alert,
    publish_observation,
    record_observation,
    rule_payload,
    simulate_observations,
    transition_alert,
)
from rate_limits import SENSITIVE_WRITE_RATE_LIMIT
from schemas import (
    ManualObservationRequest,
    MonitoringAlertActionRequest,
    MonitoringRuleRequest,
    ObservationSimulationRequest,
    validate_json,
)


def _success(data, status: int = 200):
    return jsonify({"status": "success", "data": data}), status


def _sse(channel: str, snapshot: dict):
    def generate():
        import json
        yield f"event: snapshot\ndata: {json.dumps(snapshot, default=str)}\n\n"
        if request.args.get("once", "false").lower() == "true":
            return
        for encoded in broker.stream(channel):
            if encoded is None:
                yield ": heartbeat\n\n"
            else:
                yield f"data: {encoded}\n\n"
    return Response(
        stream_with_context(generate()), mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def register_monitoring_routes(app: Flask) -> None:
    broker.configure(app.config.get("REDIS_URL"))

    @app.get("/api/v1/monitoring/definitions")
    @require_auth(ROLE_PATIENT, ROLE_DOCTOR, ROLE_HOSPITAL_ADMIN)
    def monitoring_definitions():
        ensure_monitoring_catalog(db.session)
        rows = db.session.scalars(db.select(ObservationDefinition).where(ObservationDefinition.is_active.is_(True)).order_by(ObservationDefinition.code))
        db.session.commit()
        return _success([definition_payload(item) for item in rows])

    @app.get("/api/v1/patients/me/monitoring/observations")
    @require_auth(ROLE_PATIENT)
    def patient_observations():
        patient = ensure_patient_profile(db.session, g.current_user)
        return _success(list_observations(
            db.session, patient, observation_type=request.args.get("type"),
            limit=min(int(request.args.get("limit", 200)), 500),
        ))

    @app.post("/api/v1/patients/me/monitoring/observations")
    @require_auth(ROLE_PATIENT)
    @limiter.limit(SENSITIVE_WRITE_RATE_LIMIT)
    def patient_record_observation():
        body = validate_json(ManualObservationRequest)
        patient = ensure_patient_profile(db.session, g.current_user)
        item, alerts = record_observation(
            db.session, patient=patient, observation_type=body.observation_type,
            value=body.value, secondary_value=body.secondary_value, source="manual",
            source_reference=body.source_reference,
            recorded_at=body.recorded_at or datetime.now(timezone.utc),
            actor_user_id=g.current_user.user_id,
        )
        db.session.commit()
        publish_observation(item, alerts, db.session)
        return _success({"observation": observation_payload(item), "alerts": [alert_payload(db.session, alert) for alert in alerts]}, 201)

    @app.post("/api/v1/patients/me/monitoring/observations/<observation_type>/clear")
    @app.delete("/api/v1/patients/me/monitoring/observations/<observation_type>")
    @require_auth(ROLE_PATIENT)
    @limiter.limit(SENSITIVE_WRITE_RATE_LIMIT)
    def patient_clear_observations(observation_type: str):
        patient = ensure_patient_profile(db.session, g.current_user)
        deleted_count = clear_patient_observations(
            db.session,
            patient=patient,
            observation_type=observation_type,
            actor_user_id=g.current_user.user_id,
        )
        db.session.commit()
        broker.publish(patient_channel(patient.patient_profile_id), {
            "event": "observations_cleared",
            "data": {"type": observation_type, "deleted_count": deleted_count},
        })
        return _success({"type": observation_type, "deleted_count": deleted_count})

    @app.post("/api/v1/patients/me/monitoring/simulate")
    @require_auth(ROLE_PATIENT)
    @limiter.limit(SENSITIVE_WRITE_RATE_LIMIT)
    def patient_simulate_observations():
        body = validate_json(ObservationSimulationRequest)
        patient = ensure_patient_profile(db.session, g.current_user)
        results = simulate_observations(
            db.session, patient=patient, observation_types=body.observation_types,
            count=body.count, seed=body.seed, abnormal_every=body.abnormal_every,
            actor_user_id=g.current_user.user_id,
        )
        db.session.commit()
        for item, alerts in results:
            publish_observation(item, alerts, db.session)
        return _success({
            "observations": [observation_payload(item) for item, _ in results],
            "alerts_created": sum(len(alerts) for _, alerts in results),
            "seed": body.seed,
        }, 201)

    @app.get("/api/v1/patients/me/monitoring/alerts")
    @require_auth(ROLE_PATIENT)
    def patient_monitoring_alerts():
        patient = ensure_patient_profile(db.session, g.current_user)
        rows = db.session.scalars(db.select(MonitoringAlert).where(
            MonitoringAlert.patient_profile_id == patient.patient_profile_id
        ).order_by(MonitoringAlert.created_at.desc()).limit(250))
        return _success([alert_payload(db.session, item) for item in rows])

    @app.get("/api/v1/patients/me/monitoring/stream")
    @require_auth(ROLE_PATIENT)
    def patient_monitoring_stream():
        patient = ensure_patient_profile(db.session, g.current_user)
        snapshot = {"event": "snapshot", "data": {
            "observations": list_observations(db.session, patient, limit=25),
        }}
        return _sse(patient_channel(patient.patient_profile_id), snapshot)

    @app.get("/api/v1/doctors/me/monitoring/alerts")
    @require_auth(ROLE_DOCTOR)
    def doctor_monitoring_alerts():
        doctor = doctor_profile_for_user(db.session, g.current_user.user_id)
        data = list_doctor_alerts(db.session, doctor, g.current_user.user_id, request.args.get("status"))
        db.session.commit()
        return _success(data)

    @app.patch("/api/v1/doctors/me/monitoring/alerts/<uuid:alert_id>")
    @require_auth(ROLE_DOCTOR)
    @limiter.limit(SENSITIVE_WRITE_RATE_LIMIT)
    def doctor_transition_monitoring_alert(alert_id: UUID):
        body = validate_json(MonitoringAlertActionRequest)
        doctor = doctor_profile_for_user(db.session, g.current_user.user_id)
        alert = get_alert_for_doctor(db.session, alert_id, doctor, g.current_user.user_id)
        transition_alert(
            db.session, alert, action=body.action, doctor=doctor,
            notes=body.notes, actor_user_id=g.current_user.user_id,
        )
        db.session.commit()
        publish_alert(alert, db.session)
        return _success(alert_payload(db.session, alert))

    @app.get("/api/v1/doctors/me/monitoring/patients/<uuid:patient_id>/observations")
    @require_auth(ROLE_DOCTOR)
    def doctor_patient_observations(patient_id: UUID):
        doctor = doctor_profile_for_user(db.session, g.current_user.user_id)
        patient = patient_profile_by_public_id(db.session, patient_id)
        patient_user = db.session.get(User, patient.user_id)
        if not check_consent_scope(
            db.session, doctor_user_id=doctor.user_id, patient_user_id=patient_user.user_id,
            required_scope="monitoring", actor_user_id=g.current_user.user_id,
        ):
            db.session.commit()
            raise ApiProblem("monitoring_access_forbidden", "Active monitoring consent is required", 403)
        data = list_observations(db.session, patient, observation_type=request.args.get("type"), limit=500)
        write_audit_event(
            db.session, action="monitoring.history_viewed", resource_type="patient_profile",
            resource_id=str(patient.public_id), actor_user_id=g.current_user.user_id,
            details={"observation_type": request.args.get("type")},
        )
        db.session.commit()
        return _success(data)

    @app.get("/api/v1/doctors/me/monitoring/stream")
    @require_auth(ROLE_DOCTOR)
    def doctor_monitoring_stream():
        doctor = doctor_profile_for_user(db.session, g.current_user.user_id)
        snapshot = {"event": "snapshot", "data": {
            "alerts": list_doctor_alerts(db.session, doctor, g.current_user.user_id),
        }}
        db.session.commit()
        return _sse(doctor_channel(doctor.doctor_profile_id), snapshot)

    @app.get("/api/v1/hospitals/<int:hospital_id>/monitoring/rules")
    @require_auth(ROLE_HOSPITAL_ADMIN)
    def hospital_monitoring_rules(hospital_id: int):
        enforce_tenant(hospital_id)
        ensure_monitoring_catalog(db.session)
        rows = db.session.scalars(db.select(MonitoringRule).where(
            (MonitoringRule.hospital_id == hospital_id) | MonitoringRule.hospital_id.is_(None)
        ).order_by(MonitoringRule.observation_type, MonitoringRule.name))
        db.session.commit()
        return _success([rule_payload(item) for item in rows])

    @app.post("/api/v1/hospitals/<int:hospital_id>/monitoring/rules")
    @require_auth(ROLE_HOSPITAL_ADMIN)
    @limiter.limit(SENSITIVE_WRITE_RATE_LIMIT)
    def hospital_create_monitoring_rule(hospital_id: int):
        enforce_tenant(hospital_id)
        body = validate_json(MonitoringRuleRequest)
        rule = MonitoringRule(hospital_id=hospital_id, created_by_user_id=g.current_user.user_id, **body.model_dump())
        db.session.add(rule); db.session.flush()
        write_audit_event(
            db.session, action="monitoring.rule_created", resource_type="monitoring_rule",
            resource_id=str(rule.public_id), actor_user_id=g.current_user.user_id,
            details={"hospital_id": hospital_id, "type": rule.observation_type},
        )
        db.session.commit()
        return _success(rule_payload(rule), 201)
