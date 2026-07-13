"""Security-admin investigation, detection response, controls, health, and exports."""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from uuid import UUID

from flask import Flask, Response, current_app, g, jsonify, request
from sqlalchemy import func, select

from audit import write_audit_event
from auth_service import ROLE_SECURITY_ADMIN
from authorization import require_auth
from errors import ApiProblem
from extensions import db, limiter
from models import (
    AuthSession,
    SecurityAlert,
    SecurityAlertResolution,
    SecurityAllowlistEntry,
    SecurityBlockAction,
    SecurityEvent,
    User,
)
from rate_limits import SENSITIVE_WRITE_RATE_LIMIT
from schemas import (
    SecurityAlertActionRequest,
    SecurityAllowlistRequest,
    SecurityBlockReleaseRequest,
    SecurityBlockRequest,
    validate_json,
)
from security_service import (
    alert_payload,
    block_payload,
    create_block,
    event_payload,
    fingerprint,
    release_expired_blocks,
    storage_health,
    synthetic_dataset,
    transition_alert,
)


def _success(data, status: int = 200):
    return jsonify({"status": "success", "data": data}), status


def _event_query():
    query = select(SecurityEvent)
    for field, column in (
        ("category", SecurityEvent.category), ("severity", SecurityEvent.severity),
        ("outcome", SecurityEvent.outcome), ("event_type", SecurityEvent.event_type),
    ):
        value = request.args.get(field)
        if value:
            query = query.where(column == value)
    return query


def _get_alert(public_id: UUID) -> SecurityAlert:
    item = db.session.scalar(select(SecurityAlert).where(SecurityAlert.public_id == public_id))
    if item is None:
        raise ApiProblem("security_alert_not_found", "Security alert not found", 404)
    return item


def register_security_routes(app: Flask) -> None:
    @app.get("/api/v1/security/dashboard")
    @require_auth(ROLE_SECURITY_ADMIN)
    def security_dashboard():
        release_expired_blocks(db.session)
        since = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        event_counts = {
            category: int(db.session.scalar(select(func.count(SecurityEvent.security_event_id)).where(
                SecurityEvent.category == category, SecurityEvent.created_at >= since
            )) or 0)
            for category in ("authentication", "access", "integrity", "upload", "blockchain", "rate_limit", "administration")
        }
        data = {
            "today": event_counts,
            "failed_logins": int(db.session.scalar(select(func.count(SecurityEvent.security_event_id)).where(
                SecurityEvent.event_type == "identity.login_failure", SecurityEvent.created_at >= since
            )) or 0),
            "open_alerts": int(db.session.scalar(select(func.count(SecurityAlert.security_alert_id)).where(
                SecurityAlert.status.in_(("open", "acknowledged", "investigating"))
            )) or 0),
            "critical_alerts": int(db.session.scalar(select(func.count(SecurityAlert.security_alert_id)).where(
                SecurityAlert.status != "resolved", SecurityAlert.severity == "critical"
            )) or 0),
            "active_blocks": int(db.session.scalar(select(func.count(SecurityBlockAction.security_block_action_id)).where(
                SecurityBlockAction.is_active.is_(True), SecurityBlockAction.expires_at > datetime.now(timezone.utc)
            )) or 0),
            "health": storage_health(current_app.config, db.session),
        }
        db.session.commit()
        return _success(data)

    @app.get("/api/v1/security/events")
    @require_auth(ROLE_SECURITY_ADMIN)
    def security_events():
        limit = min(max(int(request.args.get("limit", 100)), 1), 500)
        rows = db.session.scalars(_event_query().order_by(SecurityEvent.created_at.desc()).limit(limit))
        return _success([event_payload(item) for item in rows])

    @app.get("/api/v1/security/events/<uuid:event_id>")
    @require_auth(ROLE_SECURITY_ADMIN)
    def security_event_detail(event_id: UUID):
        item = db.session.scalar(select(SecurityEvent).where(SecurityEvent.public_id == event_id))
        if item is None:
            raise ApiProblem("security_event_not_found", "Security event not found", 404)
        return _success(event_payload(item))

    @app.get("/api/v1/security/alerts")
    @require_auth(ROLE_SECURITY_ADMIN)
    def security_alerts():
        query = select(SecurityAlert)
        if request.args.get("status"):
            query = query.where(SecurityAlert.status == request.args["status"])
        if request.args.get("severity"):
            query = query.where(SecurityAlert.severity == request.args["severity"])
        rows = db.session.scalars(query.order_by(SecurityAlert.created_at.desc()).limit(500))
        return _success([alert_payload(item) for item in rows])

    @app.get("/api/v1/security/alerts/<uuid:alert_id>")
    @require_auth(ROLE_SECURITY_ADMIN)
    def security_alert_detail(alert_id: UUID):
        alert = _get_alert(alert_id)
        resolutions = db.session.scalars(select(SecurityAlertResolution).where(
            SecurityAlertResolution.security_alert_id == alert.security_alert_id
        ).order_by(SecurityAlertResolution.created_at))
        return _success({**alert_payload(alert), "history": [{
            "action": item.action, "notes": item.notes,
            "actor_user_id": item.actor_user_id, "created_at": item.created_at.isoformat(),
        } for item in resolutions]})

    @app.patch("/api/v1/security/alerts/<uuid:alert_id>")
    @require_auth(ROLE_SECURITY_ADMIN)
    @limiter.limit(SENSITIVE_WRITE_RATE_LIMIT)
    def security_alert_action(alert_id: UUID):
        body = validate_json(SecurityAlertActionRequest)
        alert = transition_alert(
            db.session, _get_alert(alert_id), action=body.action,
            notes=body.notes, actor_user_id=g.current_user.user_id,
        )
        write_audit_event(
            db.session, action="security.alert_status_changed", resource_type="security_alert",
            resource_id=str(alert.public_id), actor_user_id=g.current_user.user_id,
            details={"status": alert.status},
        )
        db.session.commit()
        return _success(alert_payload(alert))

    @app.get("/api/v1/security/blocks")
    @require_auth(ROLE_SECURITY_ADMIN)
    def security_blocks():
        release_expired_blocks(db.session)
        rows = db.session.scalars(select(SecurityBlockAction).order_by(SecurityBlockAction.created_at.desc()).limit(500))
        db.session.commit()
        return _success([block_payload(item) for item in rows])

    @app.post("/api/v1/security/blocks")
    @require_auth(ROLE_SECURITY_ADMIN)
    @limiter.limit(SENSITIVE_WRITE_RATE_LIMIT)
    def security_create_block():
        body = validate_json(SecurityBlockRequest)
        values = {"target_user_id": None, "target_session_id": None, "target_hash": None}
        try:
            if body.target_type == "account":
                target = db.session.scalar(select(User).where(User.public_id == UUID(body.target)))
                if target is None: raise ValueError
                values["target_user_id"] = target.user_id
            elif body.target_type == "session":
                target = db.session.scalar(select(AuthSession).where(AuthSession.public_id == UUID(body.target)))
                if target is None: raise ValueError
                values["target_session_id"] = target.auth_session_id
            else:
                values["target_hash"] = fingerprint(body.target, current_app.config["SECRET_KEY"])
        except (ValueError, TypeError) as error:
            raise ApiProblem("security_target_not_found", "Security control target was not found", 404) from error
        block = create_block(
            db.session, target_type=body.target_type, reason=body.reason,
            rule_code="manual_security_control", duration_minutes=body.duration_minutes,
            actor_user_id=g.current_user.user_id, **values,
        )
        if block is None:
            raise ApiProblem("security_target_allowlisted", "The target is protected by an active allowlist entry", 409)
        write_audit_event(
            db.session, action="security.block_created", resource_type="security_block",
            resource_id=str(block.public_id), actor_user_id=g.current_user.user_id,
            details={"type": block.target_type},
        )
        db.session.commit()
        return _success(block_payload(block), 201)

    @app.post("/api/v1/security/blocks/<uuid:block_id>/release")
    @require_auth(ROLE_SECURITY_ADMIN)
    @limiter.limit(SENSITIVE_WRITE_RATE_LIMIT)
    def security_release_block(block_id: UUID):
        body = validate_json(SecurityBlockReleaseRequest)
        block = db.session.scalar(select(SecurityBlockAction).where(SecurityBlockAction.public_id == block_id))
        if block is None: raise ApiProblem("security_block_not_found", "Security block not found", 404)
        block.is_active = False; block.released_at = datetime.now(timezone.utc)
        block.released_by_user_id = g.current_user.user_id; block.release_reason = body.reason
        write_audit_event(
            db.session, action="security.block_released", resource_type="security_block",
            resource_id=str(block.public_id), actor_user_id=g.current_user.user_id,
        )
        db.session.commit()
        return _success(block_payload(block))

    @app.get("/api/v1/security/allowlist")
    @require_auth(ROLE_SECURITY_ADMIN)
    def security_allowlist():
        rows = db.session.scalars(select(SecurityAllowlistEntry).order_by(SecurityAllowlistEntry.created_at.desc()))
        return _success([{
            "id": item.security_allowlist_entry_id, "target_type": item.target_type,
            "target_fingerprint": item.target_hash[:12], "description": item.description,
            "expires_at": item.expires_at.isoformat() if item.expires_at else None,
            "is_active": item.is_active,
        } for item in rows])

    @app.post("/api/v1/security/allowlist")
    @require_auth(ROLE_SECURITY_ADMIN)
    @limiter.limit(SENSITIVE_WRITE_RATE_LIMIT)
    def security_create_allowlist():
        body = validate_json(SecurityAllowlistRequest)
        if body.target_type == "account":
            try: user = db.session.scalar(select(User).where(User.public_id == UUID(body.target)))
            except ValueError as error: raise ApiProblem("security_target_not_found", "Account not found", 404) from error
            if user is None: raise ApiProblem("security_target_not_found", "Account not found", 404)
            target_hash = str(user.user_id)
        else:
            target_hash = fingerprint(body.target, current_app.config["SECRET_KEY"])
        item = SecurityAllowlistEntry(
            target_type=body.target_type, target_hash=target_hash,
            description=body.description, expires_at=body.expires_at,
            created_by_user_id=g.current_user.user_id,
        )
        db.session.add(item)
        write_audit_event(
            db.session, action="security.allowlist_created", resource_type="security_allowlist",
            actor_user_id=g.current_user.user_id, details={"type": body.target_type},
        )
        db.session.commit()
        return _success({"target_type": item.target_type, "target_fingerprint": item.target_hash[:12]}, 201)

    @app.get("/api/v1/security/export")
    @require_auth(ROLE_SECURITY_ADMIN)
    @limiter.limit(SENSITIVE_WRITE_RATE_LIMIT)
    def security_export():
        rows = list(db.session.scalars(_event_query().order_by(SecurityEvent.created_at.desc()).limit(5000)))
        output = io.StringIO(); writer = csv.DictWriter(output, fieldnames=[
            "id", "event_type", "category", "severity", "outcome", "resource_type",
            "request_id", "ip_fingerprint", "anomaly_score", "advisory_only", "created_at",
        ])
        writer.writeheader()
        for item in rows:
            payload = event_payload(item)
            writer.writerow({
                "id": payload["id"], "event_type": payload["event_type"], "category": payload["category"],
                "severity": payload["severity"], "outcome": payload["outcome"],
                "resource_type": payload["resource_type"], "request_id": payload["request_id"],
                "ip_fingerprint": payload["ip_fingerprint"], "anomaly_score": payload["anomaly"]["score"],
                "advisory_only": True, "created_at": payload["created_at"],
            })
        write_audit_event(
            db.session, action="security.events_exported", resource_type="security_event",
            actor_user_id=g.current_user.user_id, details={"type": "csv"},
        )
        db.session.commit()
        return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=security-events.csv"})

    @app.get("/api/v1/security/anomaly-dataset")
    @require_auth(ROLE_SECURITY_ADMIN)
    def security_anomaly_dataset():
        source = request.args.get("source", "events")
        if source == "synthetic":
            rows = synthetic_dataset(min(int(request.args.get("count", 500)), 5000), int(request.args.get("seed", 42)))
        else:
            events = db.session.scalars(select(SecurityEvent).order_by(SecurityEvent.created_at.desc()).limit(5000))
            rows = [{**item.feature_vector, "label": item.training_label or "unlabeled", "source": "sanitized_event"} for item in events]
        return _success({"model_status": "experimental_advisory_only", "rows": rows})
