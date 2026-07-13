"""Privacy-safe security telemetry, explainable rules, controls, and advisory anomaly scoring."""

from __future__ import annotations

import hashlib
import math
import random
from datetime import datetime, timedelta, timezone
from uuid import UUID

from flask import current_app, g, has_app_context, has_request_context, request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from errors import ApiProblem
from models import (
    AuthSession,
    BlockchainTransaction,
    SecurityAlert,
    SecurityAlertResolution,
    SecurityAllowlistEntry,
    SecurityBlockAction,
    SecurityEvent,
    User,
)


SAFE_METADATA_KEYS = {
    "status", "role", "hospital_id", "department_id", "type", "source",
    "severity", "state", "code", "is_active", "revoked_sessions",
    "alerts_created", "blockchain_state", "tamper_status", "reason_code",
}
RECORD_ACCESS_PREFIXES = ("clinical.", "document.", "sharing.record", "monitoring.history")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def fingerprint(value: str | None, secret: str) -> str | None:
    if not value:
        return None
    return hashlib.sha256(f"{secret}:{value}".encode()).hexdigest()


def safe_metadata(values: dict | None) -> dict:
    return {
        key: value for key, value in (values or {}).items()
        if key in SAFE_METADATA_KEYS and isinstance(value, (str, int, float, bool, type(None)))
    }


def _category(event_type: str) -> str:
    if event_type.startswith("identity.") or event_type.startswith("auth."):
        return "authentication"
    if event_type.startswith(("access.", "consent.", "sharing.", "clinical.", "document.access", "monitoring.history")):
        return "access"
    if "integrity" in event_type or "verification" in event_type:
        return "integrity"
    if event_type.startswith("blockchain."):
        return "blockchain"
    if "upload" in event_type:
        return "upload"
    if event_type.startswith("rate_limit"):
        return "rate_limit"
    if event_type.startswith(("admin.", "security.", "identity.staff", "identity.status")):
        return "administration"
    return "application"


def _severity(event_type: str, outcome: str) -> str:
    if "break_glass" in event_type or ("integrity" in event_type and outcome == "failure"):
        return "high"
    if outcome == "failure":
        return "medium"
    if outcome == "denied":
        return "low"
    return "info"


def _features(session: Session, *, event_type: str, outcome: str, actor_user_id: int | None, ip_hash: str | None, device_hash: str | None) -> tuple[dict, float]:
    now = _utcnow(); cutoff = now - timedelta(minutes=5)
    identity_conditions = []
    if actor_user_id is not None:
        identity_conditions.append(SecurityEvent.actor_user_id == actor_user_id)
    if ip_hash is not None:
        identity_conditions.append(SecurityEvent.ip_hash == ip_hash)
    burst = int(session.scalar(select(func.count(SecurityEvent.security_event_id)).where(
        SecurityEvent.created_at >= cutoff,
        or_(*identity_conditions) if identity_conditions else SecurityEvent.security_event_id < 0,
    )) or 0)
    known_ip = bool(actor_user_id and ip_hash and session.scalar(select(SecurityEvent.security_event_id).where(
        SecurityEvent.actor_user_id == actor_user_id, SecurityEvent.ip_hash == ip_hash
    ).limit(1)))
    known_device = bool(actor_user_id and device_hash and session.scalar(select(SecurityEvent.security_event_id).where(
        SecurityEvent.actor_user_id == actor_user_id, SecurityEvent.device_hash == device_hash
    ).limit(1)))
    hour = now.hour + now.minute / 60
    features = {
        "hour_sin": round(math.sin(2 * math.pi * hour / 24), 6),
        "hour_cos": round(math.cos(2 * math.pi * hour / 24), 6),
        "failure": int(outcome == "failure"), "denied": int(outcome == "denied"),
        "new_ip": int(bool(actor_user_id and ip_hash and not known_ip)),
        "new_device": int(bool(actor_user_id and device_hash and not known_device)),
        "event_volume_5m": burst,
        "record_access": int(event_type.startswith(RECORD_ACCESS_PREFIXES)),
    }
    # Experimental distance score: advisory only. Rule decisions never consume it.
    score = min(1.0, 0.28 * features["failure"] + 0.18 * features["denied"] +
                0.16 * features["new_ip"] + 0.16 * features["new_device"] +
                min(burst / 50, 0.22))
    return features, round(score, 4)


def collect_security_event(
    session: Session, *, event_type: str, outcome: str,
    actor_user_id: int | None = None, subject_user_id: int | None = None,
    auth_session_id: int | None = None, resource_type: str | None = None,
    resource_id: str | None = None, remote_addr: str | None = None,
    user_agent: str | None = None, metadata: dict | None = None,
    secret: str | None = None, run_detection: bool = True,
) -> SecurityEvent:
    secret = secret or (current_app.config["SECRET_KEY"] if has_app_context() else "local-security-event-key")
    ip_hash = fingerprint(remote_addr, secret)
    device_hash = fingerprint(user_agent, secret)
    features, anomaly_score = _features(
        session, event_type=event_type, outcome=outcome,
        actor_user_id=actor_user_id, ip_hash=ip_hash, device_hash=device_hash,
    )
    item = SecurityEvent(
        event_type=event_type, category=_category(event_type),
        severity=_severity(event_type, outcome), outcome=outcome,
        actor_user_id=actor_user_id, subject_user_id=subject_user_id,
        auth_session_id=auth_session_id, resource_type=resource_type,
        resource_id=resource_id, request_id=getattr(g, "request_id", None) if has_request_context() else None,
        ip_hash=ip_hash, device_hash=device_hash, safe_metadata=safe_metadata(metadata),
        feature_vector=features, anomaly_score=anomaly_score,
        anomaly_model="experimental_distance_v1", anomaly_advisory=True,
    )
    session.add(item); session.flush()
    if run_detection:
        run_rule_detections(session, item)
        if anomaly_score >= 0.82:
            _create_alert(
                session, rule_code="advisory_anomaly_score", title="Advisory anomalous security event",
                description="Experimental feature-distance score exceeded the review threshold.",
                severity="medium", confidence=anomaly_score,
                evidence={"event_id": str(item.public_id), "model": item.anomaly_model},
                subject_user_id=actor_user_id, subject_ip_hash=ip_hash,
                anomaly_score=anomaly_score, anomaly_advisory=True,
            )
    return item


def collect_from_audit(session: Session, audit_event) -> SecurityEvent:
    remote_addr = audit_event.remote_addr or (request.remote_addr if has_request_context() else None)
    user_agent = audit_event.user_agent or (request.user_agent.string if has_request_context() and request.user_agent else None)
    outcome = audit_event.outcome
    metadata = dict(audit_event.details or {})
    if metadata.get("tamper_status") == "modified" or metadata.get("blockchain_state") == "failed":
        outcome = "failure"
    return collect_security_event(
        session, event_type=audit_event.action, outcome=outcome,
        actor_user_id=audit_event.actor_user_id, subject_user_id=audit_event.actor_user_id,
        resource_type=audit_event.resource_type, resource_id=audit_event.resource_id,
        remote_addr=remote_addr, user_agent=user_agent, metadata=metadata,
    )


def collect_login_attempt(
    session: Session, *, user: User | None, success: bool, reason: str,
    remote_addr: str | None, user_agent: str | None, auth_session_id: int | None,
    secret: str,
) -> SecurityEvent:
    return collect_security_event(
        session, event_type="identity.login_success" if success else "identity.login_failure",
        outcome="success" if success else "failure", actor_user_id=user.user_id if user else None,
        subject_user_id=user.user_id if user else None, auth_session_id=auth_session_id,
        resource_type="auth_session", remote_addr=remote_addr, user_agent=user_agent,
        metadata={"reason_code": reason}, secret=secret,
    )


def _create_alert(
    session: Session, *, rule_code: str, title: str, description: str,
    severity: str, confidence: float, evidence: dict,
    subject_user_id: int | None, subject_ip_hash: str | None,
    anomaly_score: float | None = None, anomaly_advisory: bool = False,
) -> SecurityAlert:
    cutoff = _utcnow() - timedelta(minutes=15)
    existing = session.scalar(select(SecurityAlert).where(
        SecurityAlert.rule_code == rule_code,
        SecurityAlert.status.in_(("open", "acknowledged", "investigating")),
        SecurityAlert.subject_user_id == subject_user_id,
        SecurityAlert.subject_ip_hash == subject_ip_hash,
        SecurityAlert.created_at >= cutoff,
    ).order_by(SecurityAlert.created_at.desc()))
    if existing:
        existing.evidence = {**existing.evidence, **safe_metadata(evidence), "last_seen_at": _utcnow().isoformat()}
        existing.updated_at = _utcnow()
        return existing
    alert = SecurityAlert(
        rule_code=rule_code, title=title, description=description,
        severity=severity, evidence=safe_metadata(evidence), confidence=confidence,
        subject_user_id=subject_user_id, subject_ip_hash=subject_ip_hash,
        anomaly_score=anomaly_score, anomaly_advisory=anomaly_advisory,
    )
    # Evidence has a separate safe allowlist suitable for opaque IDs/counts.
    alert.evidence = {
        key: value for key, value in evidence.items()
        if key in {"event_id", "event_count", "window_minutes", "model", "last_seen_at"}
    }
    session.add(alert); session.flush()
    return alert


def _is_allowlisted_hash(session: Session, target_type: str, target_hash: str | None) -> bool:
    if not target_hash:
        return False
    now = _utcnow()
    entry = session.scalar(select(SecurityAllowlistEntry).where(
        SecurityAllowlistEntry.target_type == target_type,
        SecurityAllowlistEntry.target_hash == target_hash,
        SecurityAllowlistEntry.is_active.is_(True),
        or_(SecurityAllowlistEntry.expires_at.is_(None), SecurityAllowlistEntry.expires_at > now),
    ))
    return entry is not None


def create_block(
    session: Session, *, target_type: str, reason: str, rule_code: str,
    duration_minutes: int, target_user_id: int | None = None,
    target_session_id: int | None = None, target_hash: str | None = None,
    automated: bool = False, actor_user_id: int | None = None,
) -> SecurityBlockAction | None:
    allow_type = "account" if target_type == "account" else target_type
    allow_hash = str(target_user_id) if target_type == "account" and target_user_id else target_hash
    if _is_allowlisted_hash(session, allow_type, allow_hash):
        return None
    now = _utcnow()
    target_conditions = []
    if target_user_id is not None:
        target_conditions.append(SecurityBlockAction.target_user_id == target_user_id)
    if target_session_id is not None:
        target_conditions.append(SecurityBlockAction.target_session_id == target_session_id)
    if target_hash is not None:
        target_conditions.append(SecurityBlockAction.target_hash == target_hash)
    existing = session.scalar(select(SecurityBlockAction).where(
        SecurityBlockAction.target_type == target_type,
        SecurityBlockAction.is_active.is_(True), SecurityBlockAction.expires_at > now,
        or_(*target_conditions) if target_conditions else SecurityBlockAction.security_block_action_id < 0,
    ))
    if existing:
        return existing
    item = SecurityBlockAction(
        target_type=target_type, target_hash=target_hash,
        target_user_id=target_user_id, target_session_id=target_session_id,
        rule_code=rule_code, reason=reason, starts_at=now,
        expires_at=now + timedelta(minutes=duration_minutes), automated=automated,
        created_by_user_id=actor_user_id,
    )
    session.add(item); session.flush()
    return item


def run_rule_detections(session: Session, event: SecurityEvent) -> list[SecurityAlert]:
    alerts = []
    now = _utcnow()
    if event.event_type == "identity.login_failure":
        match_conditions = []
        if event.ip_hash is not None:
            match_conditions.append(SecurityEvent.ip_hash == event.ip_hash)
        if event.subject_user_id is not None:
            match_conditions.append(SecurityEvent.subject_user_id == event.subject_user_id)
        count = int(session.scalar(select(func.count(SecurityEvent.security_event_id)).where(
            SecurityEvent.event_type == "identity.login_failure",
            SecurityEvent.created_at >= now - timedelta(minutes=15),
            or_(*match_conditions) if match_conditions else SecurityEvent.security_event_id == event.security_event_id,
        )) or 0)
        if count >= 5:
            alerts.append(_create_alert(
                session, rule_code="brute_force_15m", title="Repeated authentication failures",
                description="Five or more failed logins occurred within fifteen minutes.",
                severity="high", confidence=0.98,
                evidence={"event_count": count, "window_minutes": 15, "event_id": str(event.public_id)},
                subject_user_id=event.subject_user_id, subject_ip_hash=event.ip_hash,
            ))
            if event.subject_user_id:
                create_block(session, target_type="account", target_user_id=event.subject_user_id,
                             reason="Automated brute-force protection", rule_code="brute_force_15m",
                             duration_minutes=15, automated=True)
    if event.outcome == "denied":
        denial_conditions = []
        if event.ip_hash is not None:
            denial_conditions.append(SecurityEvent.ip_hash == event.ip_hash)
        if event.actor_user_id is not None:
            denial_conditions.append(SecurityEvent.actor_user_id == event.actor_user_id)
        count = int(session.scalar(select(func.count(SecurityEvent.security_event_id)).where(
            SecurityEvent.outcome == "denied", SecurityEvent.created_at >= now - timedelta(minutes=10),
            or_(*denial_conditions) if denial_conditions else SecurityEvent.security_event_id == event.security_event_id,
        )) or 0)
        if count >= 5:
            alerts.append(_create_alert(
                session, rule_code="repeated_denials_10m", title="Repeated authorization denials",
                description="Repeated denied operations may indicate permission probing.", severity="high",
                confidence=0.9, evidence={"event_count": count, "window_minutes": 10, "event_id": str(event.public_id)},
                subject_user_id=event.actor_user_id, subject_ip_hash=event.ip_hash,
            ))
    if event.event_type.startswith(RECORD_ACCESS_PREFIXES) and event.outcome == "success":
        count = int(session.scalar(select(func.count(SecurityEvent.security_event_id)).where(
            SecurityEvent.actor_user_id == event.actor_user_id,
            SecurityEvent.created_at >= now - timedelta(minutes=5),
            SecurityEvent.event_type.like("%view%") | SecurityEvent.event_type.like("%access%"),
        )) or 0)
        if count >= 20:
            alerts.append(_create_alert(
                session, rule_code="record_volume_5m", title="Abnormal record access volume",
                description="A user accessed an unusually high number of records in five minutes.",
                severity="high", confidence=0.92,
                evidence={"event_count": count, "window_minutes": 5, "event_id": str(event.public_id)},
                subject_user_id=event.actor_user_id, subject_ip_hash=event.ip_hash,
            ))
    if event.category == "integrity" and event.outcome == "failure":
        alerts.append(_create_alert(
            session, rule_code="integrity_failure", title="Integrity verification failure",
            description="A cryptographic or document-integrity verification failed.", severity="critical",
            confidence=0.99, evidence={"event_id": str(event.public_id)},
            subject_user_id=event.actor_user_id, subject_ip_hash=event.ip_hash,
        ))
    if event.category == "blockchain" and event.outcome == "failure":
        alerts.append(_create_alert(
            session, rule_code="blockchain_failure", title="Blockchain proof operation failed",
            description="An asynchronous proof operation entered a failed state.", severity="high",
            confidence=0.97, evidence={"event_id": str(event.public_id)},
            subject_user_id=event.actor_user_id, subject_ip_hash=event.ip_hash,
        ))
    if event.event_type == "rate_limit.violation":
        alerts.append(_create_alert(
            session, rule_code="request_burst", title="Request burst blocked by rate limiting",
            description="The API rate limiter rejected a request burst.", severity="medium",
            confidence=0.95, evidence={"event_id": str(event.public_id), "window_minutes": 1},
            subject_user_id=event.actor_user_id, subject_ip_hash=event.ip_hash,
        ))
        create_block(session, target_type="ip", target_hash=event.ip_hash,
                     reason="Temporary request-burst control", rule_code="request_burst",
                     duration_minutes=5, automated=True)
    if event.event_type == "identity.login_success" and event.actor_user_id:
        previous = session.scalar(select(SecurityEvent).where(
            SecurityEvent.event_type == "identity.login_success",
            SecurityEvent.actor_user_id == event.actor_user_id,
            SecurityEvent.security_event_id != event.security_event_id,
            SecurityEvent.created_at >= now - timedelta(hours=1),
        ).order_by(SecurityEvent.created_at.desc()))
        if previous and previous.ip_hash != event.ip_hash and previous.device_hash != event.device_hash:
            alerts.append(_create_alert(
                session, rule_code="device_ip_change", title="Suspicious device and network change",
                description="A successful session used both a new device fingerprint and network fingerprint.",
                severity="medium", confidence=0.78, evidence={"event_id": str(event.public_id), "window_minutes": 60},
                subject_user_id=event.actor_user_id, subject_ip_hash=event.ip_hash,
            ))
    return alerts


def enforce_controls(session: Session, *, user_id: int | None = None, auth_session_id: int | None = None, remote_addr: str | None = None, secret: str, allowlisted_ips: set[str] | None = None) -> None:
    if remote_addr and remote_addr in (allowlisted_ips or set()):
        remote_addr = None
    now = _utcnow(); ip_hash = fingerprint(remote_addr, secret)
    query = select(SecurityBlockAction).where(
        SecurityBlockAction.is_active.is_(True), SecurityBlockAction.starts_at <= now,
        SecurityBlockAction.expires_at > now,
    )
    conditions = []
    if user_id: conditions.append(SecurityBlockAction.target_user_id == user_id)
    if auth_session_id: conditions.append(SecurityBlockAction.target_session_id == auth_session_id)
    if ip_hash and not _is_allowlisted_hash(session, "ip", ip_hash): conditions.append(SecurityBlockAction.target_hash == ip_hash)
    if conditions and session.scalar(query.where(or_(*conditions)).limit(1)):
        raise ApiProblem("security_control_active", "Access is temporarily restricted by a security control", 423)


def release_expired_blocks(session: Session) -> int:
    now = _utcnow(); count = 0
    for item in session.scalars(select(SecurityBlockAction).where(
        SecurityBlockAction.is_active.is_(True), SecurityBlockAction.expires_at <= now
    )):
        item.is_active = False; item.released_at = now; item.release_reason = "expired"; count += 1
    return count


def event_payload(item: SecurityEvent) -> dict:
    return {
        "id": str(item.public_id), "event_type": item.event_type,
        "category": item.category, "severity": item.severity, "outcome": item.outcome,
        "actor_user_id": item.actor_user_id, "subject_user_id": item.subject_user_id,
        "resource_type": item.resource_type, "resource_id": item.resource_id,
        "request_id": item.request_id, "ip_fingerprint": item.ip_hash[:12] if item.ip_hash else None,
        "device_fingerprint": item.device_hash[:12] if item.device_hash else None,
        "metadata": item.safe_metadata, "features": item.feature_vector,
        "anomaly": {"score": item.anomaly_score, "model": item.anomaly_model, "advisory_only": True},
        "created_at": item.created_at.isoformat(),
    }


def alert_payload(item: SecurityAlert) -> dict:
    return {
        "id": str(item.public_id), "rule_code": item.rule_code, "title": item.title,
        "description": item.description, "severity": item.severity, "status": item.status,
        "evidence": item.evidence, "confidence": item.confidence,
        "anomaly_score": item.anomaly_score, "anomaly_advisory": item.anomaly_advisory,
        "subject_user_id": item.subject_user_id,
        "subject_ip_fingerprint": item.subject_ip_hash[:12] if item.subject_ip_hash else None,
        "assigned_user_id": item.assigned_user_id,
        "acknowledged_at": item.acknowledged_at.isoformat() if item.acknowledged_at else None,
        "resolved_at": item.resolved_at.isoformat() if item.resolved_at else None,
        "created_at": item.created_at.isoformat(), "updated_at": item.updated_at.isoformat(),
    }


def block_payload(item: SecurityBlockAction) -> dict:
    return {
        "id": str(item.public_id), "target_type": item.target_type,
        "target_user_id": item.target_user_id,
        "target_fingerprint": item.target_hash[:12] if item.target_hash else None,
        "rule_code": item.rule_code, "reason": item.reason,
        "starts_at": item.starts_at.isoformat(), "expires_at": item.expires_at.isoformat(),
        "is_active": item.is_active, "automated": item.automated,
        "released_at": item.released_at.isoformat() if item.released_at else None,
        "release_reason": item.release_reason,
    }


def transition_alert(session: Session, alert: SecurityAlert, *, action: str, notes: str, actor_user_id: int) -> SecurityAlert:
    now = _utcnow()
    if action == "acknowledged":
        alert.status = "acknowledged"; alert.acknowledged_at = now; alert.assigned_user_id = actor_user_id
    elif action == "investigating":
        alert.status = "investigating"; alert.assigned_user_id = actor_user_id
    elif action in ("resolved", "dismissed"):
        alert.status = action; alert.resolved_at = now; alert.assigned_user_id = actor_user_id
    elif action == "reopened":
        alert.status = "open"; alert.resolved_at = None
    else:
        raise ApiProblem("security_alert_action_invalid", "Unsupported security alert action", 400)
    alert.updated_at = now
    session.add(SecurityAlertResolution(
        security_alert_id=alert.security_alert_id, action=action,
        notes=notes, actor_user_id=actor_user_id,
    ))
    session.flush(); return alert


def synthetic_dataset(count: int = 500, seed: int = 42) -> list[dict]:
    rng = random.Random(seed); rows = []
    for index in range(count):
        malicious = index % 10 == 0
        rows.append({
            "hour_sin": round(rng.uniform(-1, 1), 6), "hour_cos": round(rng.uniform(-1, 1), 6),
            "failure": int(malicious or rng.random() < 0.05),
            "denied": int(malicious or rng.random() < 0.08),
            "new_ip": int(malicious or rng.random() < 0.12),
            "new_device": int(malicious or rng.random() < 0.1),
            "event_volume_5m": rng.randint(25, 80) if malicious else rng.randint(0, 12),
            "record_access": int(rng.random() < 0.3),
            "label": "anomalous" if malicious else "normal", "source": "synthetic", "seed": seed,
        })
    return rows


def storage_health(config: dict, session: Session) -> dict:
    blockchain = {
        state: int(session.scalar(select(func.count(BlockchainTransaction.blockchain_transaction_id)).where(
            BlockchainTransaction.state == state
        )) or 0) for state in ("pending", "submitted", "confirmed", "failed")
    }
    return {
        "blockchain": {"enabled": bool(config.get("BLOCKCHAIN_ENABLED")), "transactions": blockchain},
        "encryption": {"persistent_key_configured": bool(config.get("DOCUMENT_ENCRYPTION_KEY"))},
        "storage": {
            "backend": config.get("DOCUMENT_STORAGE_BACKEND", "local"),
            "configured": bool(config.get("DOCUMENT_STORAGE_PATH") or config.get("DOCUMENT_S3_BUCKET")),
        },
        "anomaly_model": {"name": "experimental_distance_v1", "advisory_only": True, "automated_blocking": False},
    }
