"""Reusable authentication, role, tenant, ownership, and consent-ready guards."""

from __future__ import annotations

from datetime import datetime, timezone
from functools import wraps
import uuid

from flask import current_app, g, request
from sqlalchemy import select

from auth_service import (
    ROLE_DOCTOR,
    ROLE_HOSPITAL_ADMIN,
    ROLE_PATIENT,
    ROLE_SECURITY_ADMIN,
    STAFF_ROLES,
    as_utc,
    decode_access_token,
    identity_context,
)
from errors import ApiProblem
from extensions import db
from models import AuthSession, User
from observability import is_v1_request


def _bearer_token() -> str:
    header = request.headers.get("Authorization", "")
    scheme, _, value = header.partition(" ")
    if scheme.lower() != "bearer" or not value:
        raise ApiProblem("authentication_required", "Authentication is required", 401)
    return value


def authenticate_request() -> User:
    payload = decode_access_token(_bearer_token(), current_app.config)
    try:
        user_public_id = uuid.UUID(payload["sub"])
        session_public_id = uuid.UUID(payload["sid"])
    except (ValueError, TypeError, KeyError) as error:
        raise ApiProblem("invalid_token", "Access token is invalid", 401) from error
    user = db.session.scalar(select(User).where(User.public_id == user_public_id))
    auth_session = db.session.scalar(select(AuthSession).where(AuthSession.public_id == session_public_id))
    if user is None or auth_session is None or auth_session.user_id != user.user_id:
        raise ApiProblem("invalid_session", "Authentication session is invalid", 401)
    from security_service import enforce_controls
    enforce_controls(
        db.session, user_id=user.user_id, auth_session_id=auth_session.auth_session_id,
        remote_addr=request.remote_addr, secret=current_app.config["SECRET_KEY"],
        allowlisted_ips=set(current_app.config.get("SECURITY_IP_ALLOWLIST", [])),
    )
    if auth_session.revoked_at is not None or as_utc(auth_session.expires_at) <= datetime.now(timezone.utc):
        raise ApiProblem("session_expired", "Authentication session is no longer active", 401)
    if not user.is_active:
        raise ApiProblem("account_inactive", "Account is inactive", 403)

    roles, tenants = identity_context(db.session, user)
    if current_app.config.get("MFA_REQUIRED_FOR_STAFF") and roles.intersection(STAFF_ROLES) and not auth_session.mfa_verified:
        raise ApiProblem("mfa_required", "Multi-factor verification is required", 403)
    g.current_user = user
    g.current_roles = roles
    g.current_tenants = tenants
    g.auth_session = auth_session
    g.access_claims = payload
    return user


def require_auth(*required_roles: str):
    def decorator(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            authenticate_request()
            if required_roles and not g.current_roles.intersection(required_roles):
                raise ApiProblem("forbidden", "Your role cannot perform this operation", 403)
            return function(*args, **kwargs)

        return wrapped

    return decorator


def require_v1_auth(*required_roles: str):
    def decorator(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            if is_v1_request():
                authenticate_request()
                if required_roles and not g.current_roles.intersection(required_roles):
                    raise ApiProblem("forbidden", "Your role cannot perform this operation", 403)
            return function(*args, **kwargs)

        return wrapped

    return decorator


def enforce_tenant(hospital_id: int) -> None:
    if ROLE_SECURITY_ADMIN in g.current_roles:
        return
    allowed = set()
    for role_name in (ROLE_DOCTOR, ROLE_HOSPITAL_ADMIN):
        allowed.update(g.current_tenants.get(role_name, set()))
    if hospital_id not in allowed:
        raise ApiProblem("tenant_forbidden", "The requested hospital is outside your tenant scope", 403)


def enforce_owner(owner_user_id: int) -> None:
    if g.current_user.user_id != owner_user_id:
        raise ApiProblem("ownership_required", "You do not own this resource", 403)


def authorize_clinical_access(
    *,
    owner_user_id: int,
    hospital_id: int | None = None,
    consent_check=None,
) -> None:
    if ROLE_PATIENT in g.current_roles and g.current_user.user_id == owner_user_id:
        return
    if ROLE_SECURITY_ADMIN in g.current_roles:
        raise ApiProblem("clinical_access_forbidden", "Security administrators cannot access clinical content", 403)
    if ROLE_DOCTOR in g.current_roles:
        if hospital_id is not None:
            enforce_tenant(hospital_id)
        # 7.6 — live consent check at the service layer.
        # Falls back to the caller-supplied consent_check for backwards
        # compatibility; new callers pass required_scope directly via
        # the module-level require_consent_scope() helper below.
        if consent_check and consent_check(g.current_user.user_id, owner_user_id):
            return
        raise ApiProblem("consent_required", "Valid patient consent is required", 403)
    raise ApiProblem("clinical_access_forbidden", "Clinical access is not permitted", 403)


def require_consent_scope(required_scope: str, owner_user_id: int) -> None:
    """Enforce that the current doctor has active, unexpired, in-scope consent.

    This is the Task 7.6 enforcement point — called directly from service
    functions that access specific record categories.  It checks the live
    consent table via consent_service.check_consent_scope() which also
    lazily expires any grants that have passed their access_expires_at.

    Raises ApiProblem('consent_required', 403) if consent is absent,
    expired, revoked, or does not cover required_scope.

    Only meaningful when the caller is a doctor; patients always have
    access to their own records via enforce_owner().
    """
    if ROLE_DOCTOR not in g.current_roles:
        return  # non-doctors are handled by their own guards

    from consent_service import check_consent_scope

    has_consent = check_consent_scope(
        db.session,
        doctor_user_id=g.current_user.user_id,
        patient_user_id=owner_user_id,
        required_scope=required_scope,
        actor_user_id=g.current_user.user_id,
    )
    if not has_consent:
        write_access_denied_audit(
            owner_user_id=owner_user_id,
            required_scope=required_scope,
        )
        raise ApiProblem(
            "consent_required",
            f"Valid patient consent covering scope '{required_scope}' is required. "
            "Submit a consent request to the patient first.",
            403,
        )


def write_access_denied_audit(owner_user_id: int, required_scope: str) -> None:
    """Write a denied audit event for a consent scope failure."""
    from audit import write_audit_event
    try:
        write_audit_event(
            db.session,
            action="consent.scope_access_denied",
            resource_type="patient_profile",
            resource_id=str(owner_user_id),
            actor_user_id=g.current_user.user_id if hasattr(g, "current_user") else None,
            outcome="denied",
            details={"required_scope": required_scope},
        )
    except Exception:  # noqa: BLE001 — audit must not crash the app
        pass
