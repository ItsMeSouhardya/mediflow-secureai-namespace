"""Authentication, password, session rotation, and identity services."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from errors import ApiProblem
from models import (
    AccountActivationToken,
    AuthSession,
    Doctor,
    DoctorProfile,
    Hospital,
    LoginAttempt,
    PasswordResetToken,
    PatientProfile,
    Role,
    StaffProfile,
    User,
    UserRole,
)


ROLE_PATIENT = "patient"
ROLE_DOCTOR = "doctor"
ROLE_HOSPITAL_ADMIN = "hospital_admin"
ROLE_SECURITY_ADMIN = "security_admin"
STAFF_ROLES = {ROLE_DOCTOR, ROLE_HOSPITAL_ADMIN, ROLE_SECURITY_ADMIN}
ROLE_DESCRIPTIONS = {
    ROLE_PATIENT: "Patient with access to owned healthcare resources",
    ROLE_DOCTOR: "Clinical staff with consent-scoped patient access",
    ROLE_HOSPITAL_ADMIN: "Hospital-scoped operational administrator",
    ROLE_SECURITY_ADMIN: "Global security metadata administrator without clinical-data access",
}

PASSWORD_HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)


@dataclass
class IssuedSession:
    user: User
    session: AuthSession
    access_token: str
    refresh_token: str
    expires_in: int


def as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def normalize_email(value: str | None) -> str | None:
    return value.strip().lower() if value else None


def normalize_phone(value: str | None) -> str | None:
    if not value:
        return None
    prefix = "+" if value.strip().startswith("+") else ""
    digits = "".join(character for character in value if character.isdigit())
    return f"{prefix}{digits}" if digits else None


def hash_password(password: str) -> str:
    return PASSWORD_HASHER.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    if not password_hash:
        return False
    try:
        return PASSWORD_HASHER.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def secret_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def identifier_hash(identifier: str, secret_key: str) -> str:
    return hmac.new(secret_key.encode("utf-8"), identifier.lower().encode("utf-8"), hashlib.sha256).hexdigest()


def ensure_default_roles(session: Session) -> dict[str, Role]:
    existing = {role.name: role for role in session.scalars(select(Role))}
    for name, description in ROLE_DESCRIPTIONS.items():
        if name not in existing:
            role = Role(name=name, description=description)
            session.add(role)
            session.flush()
            existing[name] = role
    return existing


def assign_role(
    session: Session,
    *,
    user: User,
    role_name: str,
    hospital_id: int | None = None,
    assigned_by_user_id: int | None = None,
) -> UserRole:
    roles = ensure_default_roles(session)
    if role_name not in roles:
        raise ApiProblem("invalid_role", "Requested role is not supported", 422)
    existing = session.scalar(
        select(UserRole).where(
            UserRole.user_id == user.user_id,
            UserRole.role_id == roles[role_name].role_id,
            UserRole.hospital_id == hospital_id,
        )
    )
    if existing:
        return existing
    assignment = UserRole(
        user_id=user.user_id,
        role_id=roles[role_name].role_id,
        hospital_id=hospital_id,
        assigned_by_user_id=assigned_by_user_id,
    )
    session.add(assignment)
    session.flush()
    return assignment


def identity_context(session: Session, user: User) -> tuple[set[str], dict[str, set[int]]]:
    assignments = session.execute(
        select(Role.name, UserRole.hospital_id)
        .join(UserRole, UserRole.role_id == Role.role_id)
        .where(UserRole.user_id == user.user_id)
    )
    roles: set[str] = set()
    tenants: dict[str, set[int]] = {}
    for role_name, hospital_id in assignments:
        roles.add(role_name)
        if hospital_id is not None:
            tenants.setdefault(role_name, set()).add(hospital_id)
    return roles, tenants


def serialize_user(session: Session, user: User) -> dict:
    roles, tenants = identity_context(session, user)
    staff = session.scalar(select(StaffProfile).where(StaffProfile.user_id == user.user_id))
    return {
        "id": str(user.public_id),
        "name": user.name,
        "email": user.email,
        "phone": user.phone,
        "age": user.age,
        "gender": user.gender,
        "is_active": user.is_active,
        "email_verified": user.email_verified_at is not None,
        "phone_verified": user.phone_verified_at is not None,
        "mfa_enabled": user.mfa_enabled,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "roles": sorted(roles),
        "tenants": {name: sorted(values) for name, values in tenants.items()},
        "staff": (
            {
                "hospital_id": staff.hospital_id,
                "doctor_id": staff.doctor_id,
                "employee_code": staff.employee_code,
                "status": staff.status,
            }
            if staff
            else None
        ),
    }


def _find_user(session: Session, identifier: str) -> User | None:
    email = normalize_email(identifier)
    phone = normalize_phone(identifier)
    conditions = [func.lower(User.email) == email]
    if phone:
        conditions.append(User.phone == phone)
    return session.scalar(select(User).where(or_(*conditions)))


def register_patient(session: Session, *, name: str, email: str, phone: str | None, password: str, age: int | None, gender: str | None) -> User:
    normalized_email = normalize_email(email)
    normalized_phone = normalize_phone(phone)
    if session.scalar(select(User).where(func.lower(User.email) == normalized_email)):
        raise ApiProblem("identity_exists", "An account already exists for this email", 409)
    if normalized_phone and session.scalar(select(User).where(User.phone == normalized_phone)):
        raise ApiProblem("identity_exists", "An account already exists for this phone", 409)
    user = User(
        name=name,
        email=normalized_email,
        phone=normalized_phone,
        password_hash=hash_password(password),
        age=age,
        gender=gender,
        is_active=True,
    )
    session.add(user)
    session.flush()
    session.add(
        PatientProfile(
            user_id=user.user_id,
            medical_record_number=f"MRN-{user.public_id.hex[:12].upper()}",
        )
    )
    session.flush()
    assign_role(session, user=user, role_name=ROLE_PATIENT)
    return user


def onboard_staff(
    session: Session,
    *,
    name: str,
    email: str,
    phone: str | None,
    password: str,
    role_name: str,
    hospital_id: int | None,
    doctor_id: int | None,
    employee_code: str | None,
    assigned_by_user_id: int,
) -> User:
    if role_name not in STAFF_ROLES:
        raise ApiProblem("invalid_role", "Staff role is invalid", 422)
    if role_name != ROLE_SECURITY_ADMIN and hospital_id is None:
        raise ApiProblem("hospital_required", "A hospital is required for this staff role", 422)
    if role_name == ROLE_DOCTOR and doctor_id is None:
        raise ApiProblem("doctor_required", "A doctor directory profile is required", 422)
    if hospital_id is not None and session.get(Hospital, hospital_id) is None:
        raise ApiProblem("hospital_not_found", "Hospital not found", 404)
    if doctor_id is not None:
        doctor = session.get(Doctor, doctor_id)
        if doctor is None:
            raise ApiProblem("doctor_not_found", "Doctor not found", 404)
        if hospital_id is None or doctor.department.hospital_id != hospital_id:
            raise ApiProblem("tenant_mismatch", "Doctor does not belong to the selected hospital", 403)

    user = register_patient(
        session,
        name=name,
        email=email,
        phone=phone,
        password=password,
        age=None,
        gender=None,
    )
    patient_role = session.scalar(select(Role).where(Role.name == ROLE_PATIENT))
    patient_assignment = session.scalar(
        select(UserRole).where(UserRole.user_id == user.user_id, UserRole.role_id == patient_role.role_id)
    )
    if patient_assignment:
        session.delete(patient_assignment)
    patient_profile = session.scalar(select(PatientProfile).where(PatientProfile.user_id == user.user_id))
    if patient_profile:
        session.delete(patient_profile)
    session.flush()
    assign_role(
        session,
        user=user,
        role_name=role_name,
        hospital_id=hospital_id,
        assigned_by_user_id=assigned_by_user_id,
    )
    if role_name != ROLE_SECURITY_ADMIN:
        session.add(
            StaffProfile(
                user_id=user.user_id,
                hospital_id=hospital_id,
                doctor_id=doctor_id,
                employee_code=employee_code,
            )
        )
    if role_name == ROLE_DOCTOR:
        session.add(
            DoctorProfile(
                user_id=user.user_id,
                hospital_id=hospital_id,
                doctor_id=doctor_id,
                status="active",
            )
        )
    session.flush()
    return user


def _record_login_attempt(session: Session, *, user: User | None, identifier: str, success: bool, reason: str, secret_key: str, remote_addr: str | None, user_agent: str | None, session_public_id: uuid.UUID | None = None) -> None:
    identifier_digest = identifier_hash(identifier, secret_key)
    session.add(
        LoginAttempt(
            user_id=user.user_id if user else None,
            identifier_hash=identifier_digest,
            success=success,
            reason=reason,
            remote_addr=remote_addr,
            user_agent=(user_agent or "")[:255] or None,
            session_public_id=session_public_id,
        )
    )
    if not success:
        from audit import write_audit_event

        write_audit_event(
            session,
            action="identity.login_failed",
            resource_type="user" if user else "identity",
            resource_id=user.public_id if user else identifier_digest,
            actor_user_id=user.user_id if user else None,
            outcome="failure",
            details={"reason": reason},
        )
    from security_service import collect_login_attempt
    collect_login_attempt(
        session, user=user, success=success, reason=reason,
        remote_addr=remote_addr, user_agent=user_agent,
        auth_session_id=None, secret=secret_key,
    )


def _access_token(session: Session, user: User, auth_session: AuthSession, config: dict) -> tuple[str, int]:
    roles, tenants = identity_context(session, user)
    now = datetime.now(timezone.utc)
    expires_in = int(config["ACCESS_TOKEN_MINUTES"]) * 60
    payload = {
        "iss": "mediflow-secure",
        "sub": str(user.public_id),
        "sid": str(auth_session.public_id),
        "type": "access",
        "roles": sorted(roles),
        "tenants": {key: sorted(value) for key, value in tenants.items()},
        "mfa": auth_session.mfa_verified,
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, config["JWT_SECRET_KEY"], algorithm="HS256"), expires_in


def _new_session(session: Session, user: User, config: dict, *, family_id: uuid.UUID | None = None, remote_addr: str | None = None, user_agent: str | None = None, mfa_verified: bool = False) -> tuple[AuthSession, str]:
    refresh_token = secrets.token_urlsafe(48)
    auth_session = AuthSession(
        user_id=user.user_id,
        family_id=family_id or uuid.uuid4(),
        refresh_token_hash=secret_hash(refresh_token),
        expires_at=datetime.now(timezone.utc) + timedelta(days=int(config["REFRESH_TOKEN_DAYS"])),
        remote_addr=remote_addr,
        user_agent=(user_agent or "")[:255] or None,
        mfa_verified=mfa_verified,
    )
    session.add(auth_session)
    session.flush()
    return auth_session, refresh_token


def authenticate(session: Session, *, identifier: str, password: str, config: dict, remote_addr: str | None, user_agent: str | None) -> IssuedSession:
    now = datetime.now(timezone.utc)
    user = _find_user(session, identifier)
    generic_error = ApiProblem("invalid_credentials", "Invalid login credentials", 401)
    if user is None:
        _record_login_attempt(session, user=None, identifier=identifier, success=False, reason="unknown_identity", secret_key=config["SECRET_KEY"], remote_addr=remote_addr, user_agent=user_agent)
        session.commit()
        raise generic_error
    if user.locked_until and as_utc(user.locked_until) > now:
        _record_login_attempt(session, user=user, identifier=identifier, success=False, reason="account_locked", secret_key=config["SECRET_KEY"], remote_addr=remote_addr, user_agent=user_agent)
        session.commit()
        raise ApiProblem("account_locked", "Account is temporarily locked", 423)
    if not user.is_active:
        _record_login_attempt(session, user=user, identifier=identifier, success=False, reason="inactive", secret_key=config["SECRET_KEY"], remote_addr=remote_addr, user_agent=user_agent)
        session.commit()
        raise ApiProblem("account_inactive", "Account is inactive", 403)
    from security_service import enforce_controls
    enforce_controls(
        session, user_id=user.user_id, remote_addr=remote_addr,
        secret=config["SECRET_KEY"], allowlisted_ips=set(config.get("SECURITY_IP_ALLOWLIST", [])),
    )
    if not verify_password(user.password_hash, password):
        identifier_digest = identifier_hash(identifier, config["SECRET_KEY"])
        cutoff = now - timedelta(minutes=15)
        failures = int(
            session.scalar(
                select(func.count(LoginAttempt.login_attempt_id)).where(
                    LoginAttempt.identifier_hash == identifier_digest,
                    LoginAttempt.success.is_(False),
                    LoginAttempt.created_at >= cutoff,
                )
            )
            or 0
        )
        if failures + 1 >= 5:
            user.locked_until = now + timedelta(minutes=15)
        _record_login_attempt(session, user=user, identifier=identifier, success=False, reason="invalid_password", secret_key=config["SECRET_KEY"], remote_addr=remote_addr, user_agent=user_agent)
        session.commit()
        raise generic_error

    if PASSWORD_HASHER.check_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    auth_session, refresh_token = _new_session(session, user, config, remote_addr=remote_addr, user_agent=user_agent)
    user.last_login_at = now
    user.locked_until = None
    _record_login_attempt(session, user=user, identifier=identifier, success=True, reason="authenticated", secret_key=config["SECRET_KEY"], remote_addr=remote_addr, user_agent=user_agent, session_public_id=auth_session.public_id)
    access_token, expires_in = _access_token(session, user, auth_session, config)
    session.commit()
    return IssuedSession(user, auth_session, access_token, refresh_token, expires_in)


def decode_access_token(token: str, config: dict) -> dict:
    try:
        payload = jwt.decode(
            token,
            config["JWT_SECRET_KEY"],
            algorithms=["HS256"],
            issuer="mediflow-secure",
            options={"require": ["exp", "iat", "sub", "sid", "type"]},
        )
    except jwt.ExpiredSignatureError as error:
        raise ApiProblem("token_expired", "Access token has expired", 401) from error
    except jwt.InvalidTokenError as error:
        raise ApiProblem("invalid_token", "Access token is invalid", 401) from error
    if payload.get("type") != "access":
        raise ApiProblem("invalid_token", "Token type is invalid", 401)
    return payload


def rotate_refresh_token(session: Session, *, refresh_token: str, config: dict, remote_addr: str | None, user_agent: str | None) -> IssuedSession:
    now = datetime.now(timezone.utc)
    current = session.scalar(select(AuthSession).where(AuthSession.refresh_token_hash == secret_hash(refresh_token)))
    if current is None:
        raise ApiProblem("invalid_refresh_token", "Refresh session is invalid", 401)
    if current.revoked_at is not None:
        for related in session.scalars(select(AuthSession).where(AuthSession.family_id == current.family_id)):
            if related.revoked_at is None:
                related.revoked_at = now
                related.revoke_reason = "refresh_token_reuse"
        session.commit()
        raise ApiProblem("refresh_token_reuse", "Refresh token reuse was detected", 401)
    if as_utc(current.expires_at) <= now:
        current.revoked_at = now
        current.revoke_reason = "expired"
        session.commit()
        raise ApiProblem("refresh_token_expired", "Refresh session has expired", 401)
    user = session.get(User, current.user_id)
    if user is None or not user.is_active:
        raise ApiProblem("account_inactive", "Account is inactive", 403)

    replacement, raw_refresh = _new_session(
        session,
        user,
        config,
        family_id=current.family_id,
        remote_addr=remote_addr,
        user_agent=user_agent,
        mfa_verified=current.mfa_verified,
    )
    current.revoked_at = now
    current.revoke_reason = "rotated"
    current.replaced_by_session_id = replacement.auth_session_id
    access_token, expires_in = _access_token(session, user, replacement, config)
    session.commit()
    return IssuedSession(user, replacement, access_token, raw_refresh, expires_in)


def revoke_session(session: Session, auth_session: AuthSession, reason: str = "logout") -> None:
    if auth_session.revoked_at is None:
        auth_session.revoked_at = datetime.now(timezone.utc)
        auth_session.revoke_reason = reason


def revoke_all_sessions(session: Session, user_id: int, reason: str = "logout_all") -> int:
    count = 0
    now = datetime.now(timezone.utc)
    for auth_session in session.scalars(select(AuthSession).where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))):
        auth_session.revoked_at = now
        auth_session.revoke_reason = reason
        count += 1
    return count


def create_password_reset(session: Session, *, identifier: str, config: dict, remote_addr: str | None) -> str | None:
    user = _find_user(session, identifier)
    if user is None or not user.is_active:
        return None
    now = datetime.now(timezone.utc)
    for existing in session.scalars(select(PasswordResetToken).where(PasswordResetToken.user_id == user.user_id, PasswordResetToken.used_at.is_(None))):
        existing.used_at = now
    raw_token = secrets.token_urlsafe(40)
    session.add(
        PasswordResetToken(
            user_id=user.user_id,
            token_hash=secret_hash(raw_token),
            expires_at=now + timedelta(minutes=int(config["PASSWORD_RESET_MINUTES"])),
            requested_ip=remote_addr,
        )
    )
    session.commit()
    return raw_token


def reset_password(session: Session, *, token: str, new_password: str) -> User:
    now = datetime.now(timezone.utc)
    reset = session.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == secret_hash(token)))
    if reset is None or reset.used_at is not None or as_utc(reset.expires_at) <= now:
        raise ApiProblem("invalid_reset_token", "Password reset token is invalid or expired", 400)
    user = session.get(User, reset.user_id)
    if user is None or not user.is_active:
        raise ApiProblem("account_inactive", "Account is inactive", 403)
    user.password_hash = hash_password(new_password)
    user.locked_until = None
    reset.used_at = now
    revoke_all_sessions(session, user.user_id, "password_reset")
    session.commit()
    return user


def create_account_activation(session: Session, *, user: User, config: dict) -> str | None:
    if user.email_verified_at is not None or not user.is_active:
        return None
    now = datetime.now(timezone.utc)
    for existing in session.scalars(
        select(AccountActivationToken).where(
            AccountActivationToken.user_id == user.user_id,
            AccountActivationToken.used_at.is_(None),
        )
    ):
        existing.used_at = now
    raw_token = secrets.token_urlsafe(40)
    session.add(
        AccountActivationToken(
            user_id=user.user_id,
            token_hash=secret_hash(raw_token),
            expires_at=now + timedelta(minutes=int(config["ACCOUNT_ACTIVATION_MINUTES"])),
        )
    )
    session.commit()
    return raw_token


def request_account_activation(session: Session, *, identifier: str, config: dict) -> str | None:
    user = _find_user(session, identifier)
    if user is None:
        return None
    return create_account_activation(session, user=user, config=config)


def activate_account(session: Session, *, token: str) -> User:
    now = datetime.now(timezone.utc)
    activation = session.scalar(
        select(AccountActivationToken).where(AccountActivationToken.token_hash == secret_hash(token))
    )
    if activation is None or activation.used_at is not None or as_utc(activation.expires_at) <= now:
        raise ApiProblem("invalid_activation_token", "Activation token is invalid or expired", 400)
    user = session.get(User, activation.user_id)
    if user is None or not user.is_active:
        raise ApiProblem("account_inactive", "Account is inactive", 403)
    user.email_verified_at = now
    activation.used_at = now
    session.commit()
    return user
