"""Durable, privacy-conscious audit-event writer."""

from __future__ import annotations

from flask import g, has_request_context, request
from sqlalchemy.orm import Session

from models import AuditEvent


SENSITIVE_DETAIL_KEYS = {"password", "token", "symptoms", "document", "content", "secret"}


def _safe_details(details: dict | None) -> dict:
    return {
        key: value
        for key, value in (details or {}).items()
        if key.lower() not in SENSITIVE_DETAIL_KEYS
    }


def write_audit_event(
    session: Session,
    *,
    action: str,
    resource_type: str,
    resource_id: str | int | None = None,
    actor_user_id: int | None = None,
    outcome: str = "success",
    details: dict | None = None,
) -> AuditEvent:
    event = AuditEvent(
        actor_user_id=actor_user_id,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id is not None else None,
        outcome=outcome,
        request_id=getattr(g, "request_id", None) if has_request_context() else None,
        remote_addr=request.remote_addr if has_request_context() else None,
        user_agent=(request.user_agent.string[:255] if request.user_agent else None) if has_request_context() else None,
        details=_safe_details(details),
    )
    session.add(event)
    # Security telemetry is a sanitized projection of audit data. It never
    # copies arbitrary clinical details into the security domain.
    from security_service import collect_from_audit
    collect_from_audit(session, event)
    return event
