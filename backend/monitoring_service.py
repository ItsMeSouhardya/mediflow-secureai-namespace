"""Task 10 durable observations, deterministic simulation, rules, and alert lifecycle."""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from audit import write_audit_event
from consent_service import check_consent_scope
from errors import ApiProblem
from models import (
    ConsentGrant,
    DoctorProfile,
    MonitoringAlert,
    MonitoringRule,
    ObservationDefinition,
    PatientObservation,
    PatientProfile,
    User,
)
from monitoring_realtime import broker, doctor_channel, patient_channel


DEFINITIONS = {
    "heart_rate": ("Heart rate", "bpm", None, 20.0, 250.0, None, None),
    "blood_pressure": ("Blood pressure", "mmHg", "mmHg", 40.0, 260.0, 20.0, 180.0),
    "blood_oxygen": ("Blood oxygen", "%", None, 50.0, 100.0, None, None),
    "temperature": ("Temperature", "°C", None, 30.0, 45.0, None, None),
    "blood_glucose": ("Blood glucose", "mg/dL", None, 20.0, 600.0, None, None),
    "respiratory_rate": ("Respiratory rate", "breaths/min", None, 4.0, 60.0, None, None),
}

DEFAULT_RULES = (
    ("Heart rate outside safe range", "heart_rate", 50.0, 120.0, None, None, None, None, "warning"),
    ("Critical blood pressure", "blood_pressure", 90.0, 180.0, 60.0, 120.0, None, None, "critical"),
    ("Low blood oxygen", "blood_oxygen", 92.0, None, None, None, None, None, "critical"),
    ("Temperature outside safe range", "temperature", 35.0, 39.0, None, None, None, None, "warning"),
    ("Blood glucose outside safe range", "blood_glucose", 60.0, 250.0, None, None, None, None, "critical"),
    ("Respiratory rate outside safe range", "respiratory_rate", 10.0, 24.0, None, None, None, None, "warning"),
    ("Rapid heart-rate change", "heart_rate", None, None, None, None, 3, 30.0, "warning"),
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def ensure_monitoring_catalog(session: Session) -> None:
    existing = set(session.scalars(select(ObservationDefinition.code)))
    for code, values in DEFINITIONS.items():
        if code not in existing:
            name, unit, secondary_unit, minimum, maximum, second_min, second_max = values
            session.add(ObservationDefinition(
                code=code, display_name=name, unit=unit, secondary_unit=secondary_unit,
                value_min=minimum, value_max=maximum,
                secondary_value_min=second_min, secondary_value_max=second_max,
            ))
    existing_rules = set(session.scalars(select(MonitoringRule.name)))
    for name, kind, minimum, maximum, second_min, second_max, window, delta, severity in DEFAULT_RULES:
        if name not in existing_rules:
            session.add(MonitoringRule(
                name=name, observation_type=kind, minimum_value=minimum,
                maximum_value=maximum, secondary_minimum_value=second_min,
                secondary_maximum_value=second_max, trend_window_count=window,
                trend_delta=delta, severity=severity,
            ))
    session.flush()


def definition_payload(item: ObservationDefinition) -> dict:
    return {
        "code": item.code, "display_name": item.display_name, "unit": item.unit,
        "secondary_unit": item.secondary_unit, "value_min": item.value_min,
        "value_max": item.value_max, "secondary_value_min": item.secondary_value_min,
        "secondary_value_max": item.secondary_value_max,
    }


def observation_payload(item: PatientObservation) -> dict:
    return {
        "id": str(item.public_id), "type": item.observation_type,
        "value": item.value, "secondary_value": item.secondary_value,
        "unit": item.unit, "source": item.source,
        "source_reference": item.source_reference,
        "recorded_at": item.recorded_at.isoformat(),
    }


def alert_payload(session: Session, item: MonitoringAlert) -> dict:
    patient = session.get(PatientProfile, item.patient_profile_id)
    user = session.get(User, patient.user_id) if patient else None
    observation = session.get(PatientObservation, item.observation_id)
    rule = session.get(MonitoringRule, item.monitoring_rule_id)
    assignee = session.get(DoctorProfile, item.assigned_doctor_profile_id) if item.assigned_doctor_profile_id else None
    return {
        "id": str(item.public_id), "patient": {
            "id": str(patient.public_id) if patient else None,
            "name": user.name if user else None,
        },
        "observation": observation_payload(observation) if observation else None,
        "rule": rule.name if rule else None, "severity": item.severity,
        "status": item.status, "message": item.message,
        "hospital_id": item.hospital_id,
        "assigned_doctor_id": str(assignee.public_id) if assignee else None,
        "acknowledged_at": item.acknowledged_at.isoformat() if item.acknowledged_at else None,
        "escalated_at": item.escalated_at.isoformat() if item.escalated_at else None,
        "resolution_notes": item.resolution_notes,
        "resolved_at": item.resolved_at.isoformat() if item.resolved_at else None,
        "created_at": item.created_at.isoformat(),
    }


def _target_hospitals(session: Session, patient: PatientProfile) -> list[int | None]:
    now = _utcnow()
    hospitals = set()
    grants = session.scalars(select(ConsentGrant).where(
        ConsentGrant.patient_profile_id == patient.patient_profile_id,
        ConsentGrant.status.in_(("granted", "break_glass")),
    ))
    for grant in grants:
        if "monitoring" not in grant.scopes:
            continue
        if grant.access_start and _aware(grant.access_start) > now:
            continue
        if grant.access_expires_at and _aware(grant.access_expires_at) <= now:
            continue
        hospitals.add(grant.requesting_hospital_id)
    return sorted(hospitals) if hospitals else [None]


def _authorized_doctor_ids(session: Session, patient_profile_id: int) -> set[int]:
    now = _utcnow()
    result = set()
    grants = session.scalars(select(ConsentGrant).where(
        ConsentGrant.patient_profile_id == patient_profile_id,
        ConsentGrant.status.in_(("granted", "break_glass")),
    ))
    for grant in grants:
        if "monitoring" not in grant.scopes:
            continue
        if grant.access_start and _aware(grant.access_start) > now:
            continue
        if grant.access_expires_at and _aware(grant.access_expires_at) <= now:
            continue
        result.add(grant.requesting_doctor_profile_id)
    return result


def _rule_triggered(session: Session, rule: MonitoringRule, observation: PatientObservation) -> tuple[bool, str]:
    failures = []
    if rule.minimum_value is not None and observation.value < rule.minimum_value:
        failures.append(f"value below {rule.minimum_value:g}")
    if rule.maximum_value is not None and observation.value > rule.maximum_value:
        failures.append(f"value above {rule.maximum_value:g}")
    if observation.secondary_value is not None:
        if rule.secondary_minimum_value is not None and observation.secondary_value < rule.secondary_minimum_value:
            failures.append(f"secondary value below {rule.secondary_minimum_value:g}")
        if rule.secondary_maximum_value is not None and observation.secondary_value > rule.secondary_maximum_value:
            failures.append(f"secondary value above {rule.secondary_maximum_value:g}")
    if rule.trend_window_count and rule.trend_delta is not None:
        recent = list(session.scalars(
            select(PatientObservation).where(
                PatientObservation.patient_profile_id == observation.patient_profile_id,
                PatientObservation.observation_type == observation.observation_type,
            ).order_by(PatientObservation.recorded_at.desc()).limit(rule.trend_window_count)
        ))
        if len(recent) >= rule.trend_window_count and abs(recent[0].value - recent[-1].value) >= rule.trend_delta:
            failures.append(f"change exceeded {rule.trend_delta:g} across {rule.trend_window_count} readings")
    return bool(failures), "; ".join(failures)


def _create_alerts(session: Session, observation: PatientObservation, patient: PatientProfile, actor_user_id: int) -> list[MonitoringAlert]:
    alerts = []
    for hospital_id in _target_hospitals(session, patient):
        rules = session.scalars(select(MonitoringRule).where(
            MonitoringRule.observation_type == observation.observation_type,
            MonitoringRule.is_enabled.is_(True),
            or_(MonitoringRule.hospital_id.is_(None), MonitoringRule.hospital_id == hospital_id),
        ))
        for rule in rules:
            triggered, reason = _rule_triggered(session, rule, observation)
            if not triggered:
                continue
            alert = MonitoringAlert(
                patient_profile_id=patient.patient_profile_id,
                observation_id=observation.observation_id,
                monitoring_rule_id=rule.monitoring_rule_id,
                hospital_id=hospital_id, severity=rule.severity,
                message=f"{rule.name}: {reason}", status="open",
            )
            session.add(alert)
            session.flush()
            write_audit_event(
                session, action="monitoring.alert_created", resource_type="monitoring_alert",
                resource_id=str(alert.public_id), actor_user_id=actor_user_id,
                details={"severity": alert.severity, "hospital_id": hospital_id, "rule_id": str(rule.public_id)},
            )
            alerts.append(alert)
    return alerts


def record_observation(
    session: Session, *, patient: PatientProfile, observation_type: str,
    value: float, secondary_value: float | None, source: str,
    source_reference: str | None, recorded_at: datetime,
    actor_user_id: int,
) -> tuple[PatientObservation, list[MonitoringAlert]]:
    ensure_monitoring_catalog(session)
    definition = session.scalar(select(ObservationDefinition).where(
        ObservationDefinition.code == observation_type,
        ObservationDefinition.is_active.is_(True),
    ))
    if definition is None:
        raise ApiProblem("observation_type_invalid", "Unsupported observation type", 400)
    if not definition.value_min <= value <= definition.value_max:
        raise ApiProblem("observation_value_invalid", "Observation value is outside the physiological validation range", 422)
    if observation_type == "blood_pressure":
        if secondary_value is None or not definition.secondary_value_min <= secondary_value <= definition.secondary_value_max:
            raise ApiProblem("observation_value_invalid", "Valid diastolic blood pressure is required", 422)
        if value <= secondary_value:
            raise ApiProblem("observation_value_invalid", "Systolic pressure must exceed diastolic pressure", 422)
    elif secondary_value is not None:
        raise ApiProblem("observation_value_invalid", "This observation type has no secondary value", 422)
    timestamp = _aware(recorded_at)
    if timestamp > _utcnow() + timedelta(minutes=5) or timestamp < _utcnow() - timedelta(days=365):
        raise ApiProblem("recorded_at_invalid", "Recorded time is outside the accepted range", 422)
    item = PatientObservation(
        patient_profile_id=patient.patient_profile_id, observation_type=observation_type,
        value=value, secondary_value=secondary_value, unit=definition.unit,
        source=source, source_reference=source_reference, recorded_at=timestamp,
        recorded_by_user_id=actor_user_id,
    )
    session.add(item)
    session.flush()
    alerts = _create_alerts(session, item, patient, actor_user_id)
    write_audit_event(
        session, action="monitoring.observation_recorded", resource_type="patient_observation",
        resource_id=str(item.public_id), actor_user_id=actor_user_id,
        details={"type": observation_type, "source": source, "alerts_created": len(alerts)},
    )
    return item, alerts


def publish_observation(item: PatientObservation, alerts: list[MonitoringAlert], session: Session) -> None:
    broker.publish(patient_channel(item.patient_profile_id), {"event": "observation", "data": observation_payload(item)})
    for alert in alerts:
        event = {"event": "alert", "data": alert_payload(session, alert)}
        broker.publish(patient_channel(item.patient_profile_id), event)
        for doctor_profile_id in _authorized_doctor_ids(session, item.patient_profile_id):
            broker.publish(doctor_channel(doctor_profile_id), event)


def simulate_observations(
    session: Session, *, patient: PatientProfile, observation_types: list[str],
    count: int, seed: int, abnormal_every: int | None, actor_user_id: int,
) -> list[tuple[PatientObservation, list[MonitoringAlert]]]:
    rng = random.Random(seed)
    baselines = {
        "heart_rate": (78.0, 4.0, None), "blood_pressure": (120.0, 5.0, 78.0),
        "blood_oxygen": (97.0, 1.0, None), "temperature": (36.8, 0.25, None),
        "blood_glucose": (105.0, 12.0, None), "respiratory_rate": (16.0, 2.0, None),
    }
    results = []
    start = _utcnow() - timedelta(minutes=max(count - 1, 0))
    for index in range(count):
        kind = observation_types[index % len(observation_types)]
        base, spread, secondary = baselines[kind]
        value = round(base + rng.uniform(-spread, spread), 1)
        second = round(secondary + rng.uniform(-4, 4), 1) if secondary is not None else None
        if abnormal_every and (index + 1) % abnormal_every == 0:
            abnormal = {"heart_rate": 145.0, "blood_pressure": 195.0, "blood_oxygen": 88.0, "temperature": 40.0, "blood_glucose": 310.0, "respiratory_rate": 34.0}
            value = abnormal[kind]
            second = 125.0 if kind == "blood_pressure" else second
        results.append(record_observation(
            session, patient=patient, observation_type=kind, value=value,
            secondary_value=second, source="simulator", source_reference=f"sim:{seed}:{index}",
            recorded_at=start + timedelta(minutes=index), actor_user_id=actor_user_id,
        ))
    return results


def list_observations(session: Session, patient: PatientProfile, *, observation_type: str | None = None, limit: int = 200) -> list[dict]:
    query = select(PatientObservation).where(PatientObservation.patient_profile_id == patient.patient_profile_id)
    if observation_type:
        query = query.where(PatientObservation.observation_type == observation_type)
    rows = session.scalars(query.order_by(PatientObservation.recorded_at.desc()).limit(limit))
    return [observation_payload(item) for item in rows]


def clear_patient_observations(
    session: Session,
    *,
    patient: PatientProfile,
    observation_type: str,
    actor_user_id: int,
) -> int:
    """Delete one parameter history and alerts derived from those readings."""
    if observation_type not in DEFINITIONS:
        raise ApiProblem("observation_type_invalid", "Unsupported observation type", 400)

    observation_ids = list(session.scalars(
        select(PatientObservation.observation_id).where(
            PatientObservation.patient_profile_id == patient.patient_profile_id,
            PatientObservation.observation_type == observation_type,
        )
    ))
    if observation_ids:
        # Explicit alert deletion keeps SQLite demonstrations consistent even
        # when database-level foreign-key cascade actions are disabled.
        session.execute(
            delete(MonitoringAlert).where(
                MonitoringAlert.patient_profile_id == patient.patient_profile_id,
                MonitoringAlert.observation_id.in_(observation_ids),
            )
        )
        session.execute(
            delete(PatientObservation).where(
                PatientObservation.patient_profile_id == patient.patient_profile_id,
                PatientObservation.observation_id.in_(observation_ids),
            )
        )

    write_audit_event(
        session,
        action="monitoring.observations_cleared",
        resource_type="patient_profile",
        resource_id=str(patient.public_id),
        actor_user_id=actor_user_id,
        details={"type": observation_type, "deleted_count": len(observation_ids)},
    )
    session.flush()
    return len(observation_ids)


def _doctor_authorized(session: Session, doctor: DoctorProfile, patient: PatientProfile, actor_user_id: int) -> bool:
    user = session.get(User, patient.user_id)
    return bool(user and check_consent_scope(
        session, doctor_user_id=doctor.user_id, patient_user_id=user.user_id,
        required_scope="monitoring", actor_user_id=actor_user_id,
    ))


def list_doctor_alerts(session: Session, doctor: DoctorProfile, actor_user_id: int, status: str | None = None) -> list[dict]:
    query = select(MonitoringAlert).where(or_(
        MonitoringAlert.hospital_id == doctor.hospital_id,
        MonitoringAlert.assigned_doctor_profile_id == doctor.doctor_profile_id,
    ))
    if status:
        query = query.where(MonitoringAlert.status == status)
    rows = session.scalars(query.order_by(MonitoringAlert.created_at.desc()).limit(250))
    allowed = {}
    result = []
    for alert in rows:
        patient = session.get(PatientProfile, alert.patient_profile_id)
        if patient.patient_profile_id not in allowed:
            allowed[patient.patient_profile_id] = _doctor_authorized(session, doctor, patient, actor_user_id)
        if allowed[patient.patient_profile_id]:
            result.append(alert_payload(session, alert))
    return result


def get_alert_for_doctor(session: Session, public_id: UUID, doctor: DoctorProfile, actor_user_id: int) -> MonitoringAlert:
    alert = session.scalar(select(MonitoringAlert).where(MonitoringAlert.public_id == public_id))
    if alert is None:
        raise ApiProblem("monitoring_alert_not_found", "Monitoring alert not found", 404)
    patient = session.get(PatientProfile, alert.patient_profile_id)
    if alert.hospital_id not in (None, doctor.hospital_id) or not _doctor_authorized(session, doctor, patient, actor_user_id):
        raise ApiProblem("monitoring_access_forbidden", "Active monitoring consent is required", 403)
    return alert


def transition_alert(session: Session, alert: MonitoringAlert, *, action: str, doctor: DoctorProfile, notes: str | None, actor_user_id: int) -> MonitoringAlert:
    now = _utcnow()
    if alert.status == "resolved":
        raise ApiProblem("invalid_alert_state", "Resolved alerts cannot be changed", 409)
    if action == "acknowledge":
        alert.status = "acknowledged"; alert.acknowledged_at = now; alert.acknowledged_by_user_id = actor_user_id
        alert.assigned_doctor_profile_id = doctor.doctor_profile_id
    elif action == "escalate":
        alert.status = "escalated"; alert.escalated_at = now; alert.assigned_doctor_profile_id = doctor.doctor_profile_id
    elif action == "resolve":
        if not notes or len(notes.strip()) < 10:
            raise ApiProblem("resolution_notes_required", "Resolution notes of at least 10 characters are required", 400)
        alert.status = "resolved"; alert.resolved_at = now; alert.resolved_by_user_id = actor_user_id
        alert.resolution_notes = notes.strip(); alert.assigned_doctor_profile_id = doctor.doctor_profile_id
    else:
        raise ApiProblem("alert_action_invalid", "Unsupported alert action", 400)
    alert.updated_at = now
    session.flush()
    write_audit_event(
        session, action=f"monitoring.alert_{action}d" if action != "resolve" else "monitoring.alert_resolved",
        resource_type="monitoring_alert", resource_id=str(alert.public_id),
        actor_user_id=actor_user_id, details={"status": alert.status, "notes": notes},
    )
    return alert


def publish_alert(alert: MonitoringAlert, session: Session) -> None:
    event = {"event": "alert_updated", "data": alert_payload(session, alert)}
    broker.publish(patient_channel(alert.patient_profile_id), event)
    for doctor_profile_id in _authorized_doctor_ids(session, alert.patient_profile_id):
        broker.publish(doctor_channel(doctor_profile_id), event)


def rule_payload(item: MonitoringRule) -> dict:
    return {
        "id": str(item.public_id), "hospital_id": item.hospital_id, "name": item.name,
        "observation_type": item.observation_type, "minimum_value": item.minimum_value,
        "maximum_value": item.maximum_value, "secondary_minimum_value": item.secondary_minimum_value,
        "secondary_maximum_value": item.secondary_maximum_value,
        "trend_window_count": item.trend_window_count, "trend_delta": item.trend_delta,
        "severity": item.severity, "is_enabled": item.is_enabled,
    }
