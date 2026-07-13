"""Reusable idempotency support for sensitive create operations."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from errors import ApiProblem
from models import IdempotencyRecord


KEY_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")


def request_hash(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_key(value: str | None, *, required: bool) -> str | None:
    if not value:
        if required:
            raise ApiProblem("idempotency_key_required", "Idempotency-Key header is required", 400)
        return None
    if not KEY_PATTERN.fullmatch(value):
        raise ApiProblem("invalid_idempotency_key", "Idempotency-Key format is invalid", 400)
    return value


def find_replay(session: Session, *, scope: str, key: str, payload_hash: str) -> IdempotencyRecord | None:
    record = session.scalar(
        select(IdempotencyRecord).where(IdempotencyRecord.scope == scope, IdempotencyRecord.key == key)
    )
    if record is None:
        return None
    expires_at = record.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= datetime.now(timezone.utc):
        session.delete(record)
        session.flush()
        return None
    if record.request_hash != payload_hash:
        raise ApiProblem(
            "idempotency_conflict",
            "This Idempotency-Key was already used with a different request",
            409,
        )
    return record


def store_result(
    session: Session,
    *,
    scope: str,
    key: str,
    payload_hash: str,
    response_json: dict,
    status_code: int,
    ttl_hours: int = 24,
) -> IdempotencyRecord:
    record = IdempotencyRecord(
        scope=scope,
        key=key,
        request_hash=payload_hash,
        response_json=response_json,
        status_code=status_code,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=ttl_hours),
    )
    session.add(record)
    return record
