"""Opaque public tracking credentials for queue tokens."""

from __future__ import annotations

import hashlib
import secrets


def hash_tracking_code(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def generate_tracking_code() -> tuple[str, str, str]:
    raw = secrets.token_urlsafe(24)
    return raw, hash_tracking_code(raw), raw[-4:]
