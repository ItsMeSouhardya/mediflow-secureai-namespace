"""Versioned authentication, identity, staff, and session endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import click
from flask import Flask, current_app, g, jsonify, make_response, request
from sqlalchemy import func, select

from audit import write_audit_event
from auth_service import (
    ROLE_DOCTOR,
    ROLE_HOSPITAL_ADMIN,
    ROLE_PATIENT,
    ROLE_SECURITY_ADMIN,
    as_utc,
    activate_account,
    authenticate,
    create_password_reset,
    create_account_activation,
    ensure_default_roles,
    hash_password,
    identity_context,
    normalize_email,
    normalize_phone,
    onboard_staff,
    register_patient,
    request_account_activation,
    reset_password,
    revoke_all_sessions,
    revoke_session,
    rotate_refresh_token,
    serialize_user,
    verify_password,
)
from authorization import enforce_tenant, require_auth
from errors import ApiProblem
from extensions import db, limiter
from models import AuthSession, StaffProfile, User
from rate_limits import AUTHENTICATION_RATE_LIMIT, SENSITIVE_WRITE_RATE_LIMIT
from schemas import (
    AccountActivationConfirmRequest,
    AccountDeleteRequest,
    LoginRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    PatientRegisterRequest,
    ProfileUpdateRequest,
    StaffOnboardRequest,
    UserStatusRequest,
    validate_json,
)


def _request_context() -> tuple[str | None, str | None]:
    return request.remote_addr, request.user_agent.string if request.user_agent else None


def _auth_payload(issued) -> dict:
    return {
        "access_token": issued.access_token,
        "token_type": "Bearer",
        "expires_in": issued.expires_in,
        "user": serialize_user(db.session, issued.user),
    }


def _set_refresh_cookie(response, refresh_token: str) -> None:
    response.set_cookie(
        current_app.config["REFRESH_COOKIE_NAME"],
        refresh_token,
        max_age=int(current_app.config["REFRESH_TOKEN_DAYS"]) * 86400,
        httponly=True,
        secure=bool(current_app.config["SESSION_COOKIE_SECURE"]),
        samesite="Strict",
        path="/api/v1/auth",
    )


def _clear_refresh_cookie(response) -> None:
    response.delete_cookie(
        current_app.config["REFRESH_COOKIE_NAME"],
        secure=bool(current_app.config["SESSION_COOKIE_SECURE"]),
        httponly=True,
        samesite="Strict",
        path="/api/v1/auth",
    )


def register_auth_routes(app: Flask) -> None:
    @app.post("/api/v1/auth/register")
    @limiter.limit(AUTHENTICATION_RATE_LIMIT)
    def register():
        body = validate_json(PatientRegisterRequest)
        user = register_patient(
            db.session,
            name=body.name,
            email=body.email,
            phone=body.phone,
            password=body.password,
            age=body.age,
            gender=body.gender,
        )
        write_audit_event(
            db.session,
            action="identity.registered",
            resource_type="user",
            resource_id=user.public_id,
            actor_user_id=user.user_id,
        )
        db.session.commit()
        activation_token = create_account_activation(db.session, user=user, config=current_app.config)
        remote_addr, user_agent = _request_context()
        issued = authenticate(
            db.session,
            identifier=body.email,
            password=body.password,
            config=current_app.config,
            remote_addr=remote_addr,
            user_agent=user_agent,
        )
        payload = _auth_payload(issued)
        if current_app.testing and activation_token:
            payload["testing_activation_token"] = activation_token
        response = make_response(jsonify(payload), 201)
        _set_refresh_cookie(response, issued.refresh_token)
        return response

    @app.post("/api/v1/auth/login")
    @limiter.limit(AUTHENTICATION_RATE_LIMIT)
    def login():
        body = validate_json(LoginRequest)
        remote_addr, user_agent = _request_context()
        issued = authenticate(
            db.session,
            identifier=body.identifier,
            password=body.password,
            config=current_app.config,
            remote_addr=remote_addr,
            user_agent=user_agent,
        )
        write_audit_event(
            db.session,
            action="identity.login",
            resource_type="auth_session",
            resource_id=issued.session.public_id,
            actor_user_id=issued.user.user_id,
        )
        db.session.commit()
        response = make_response(jsonify(_auth_payload(issued)))
        _set_refresh_cookie(response, issued.refresh_token)
        return response

    @app.post("/api/v1/auth/refresh")
    @limiter.limit(AUTHENTICATION_RATE_LIMIT)
    def refresh():
        raw_refresh = request.cookies.get(current_app.config["REFRESH_COOKIE_NAME"])
        if not raw_refresh:
            raise ApiProblem("refresh_required", "Refresh session is required", 401)
        remote_addr, user_agent = _request_context()
        issued = rotate_refresh_token(
            db.session,
            refresh_token=raw_refresh,
            config=current_app.config,
            remote_addr=remote_addr,
            user_agent=user_agent,
        )
        write_audit_event(
            db.session,
            action="identity.session_rotated",
            resource_type="auth_session",
            resource_id=issued.session.public_id,
            actor_user_id=issued.user.user_id,
        )
        db.session.commit()
        response = make_response(jsonify(_auth_payload(issued)))
        _set_refresh_cookie(response, issued.refresh_token)
        return response

    @app.post("/api/v1/auth/logout")
    @require_auth()
    def logout():
        revoke_session(db.session, g.auth_session)
        write_audit_event(
            db.session,
            action="identity.logout",
            resource_type="auth_session",
            resource_id=g.auth_session.public_id,
            actor_user_id=g.current_user.user_id,
        )
        db.session.commit()
        response = make_response(jsonify({"logged_out": True}))
        _clear_refresh_cookie(response)
        return response

    @app.post("/api/v1/auth/logout-all")
    @require_auth()
    def logout_all():
        revoked = revoke_all_sessions(db.session, g.current_user.user_id)
        write_audit_event(
            db.session,
            action="identity.logout_all",
            resource_type="user",
            resource_id=g.current_user.public_id,
            actor_user_id=g.current_user.user_id,
            details={"revoked_sessions": revoked},
        )
        db.session.commit()
        response = make_response(jsonify({"logged_out": True, "revoked_sessions": revoked}))
        _clear_refresh_cookie(response)
        return response

    @app.get("/api/v1/auth/me")
    @require_auth()
    def me():
        return jsonify(serialize_user(db.session, g.current_user))

    @app.patch("/api/v1/auth/me")
    @require_auth()
    @limiter.limit(SENSITIVE_WRITE_RATE_LIMIT)
    def update_me():
        body = validate_json(ProfileUpdateRequest)
        updates = body.model_dump(exclude_unset=True)
        if "email" in updates:
            normalized_email = normalize_email(updates["email"])
            duplicate = db.session.scalar(
                select(User).where(
                    func.lower(User.email) == normalized_email,
                    User.user_id != g.current_user.user_id,
                )
            )
            if duplicate:
                raise ApiProblem("identity_exists", "This email is already registered", 409)
            updates["email"] = normalized_email
            g.current_user.email_verified_at = None
        if "phone" in updates:
            normalized = normalize_phone(updates["phone"])
            duplicate = db.session.scalar(
                select(User).where(User.phone == normalized, User.user_id != g.current_user.user_id)
            )
            if duplicate:
                raise ApiProblem("identity_exists", "This phone is already registered", 409)
            updates["phone"] = normalized
            g.current_user.phone_verified_at = None
        for field, value in updates.items():
            setattr(g.current_user, field, value)
        write_audit_event(
            db.session,
            action="identity.profile_updated",
            resource_type="user",
            resource_id=g.current_user.public_id,
            actor_user_id=g.current_user.user_id,
            details={"fields": sorted(updates)},
        )
        db.session.commit()
        return jsonify(serialize_user(db.session, g.current_user))

    @app.post("/api/v1/auth/me/delete")
    @require_auth()
    @limiter.limit(SENSITIVE_WRITE_RATE_LIMIT)
    def delete_me():
        body = validate_json(AccountDeleteRequest)
        user = g.current_user
        if not verify_password(user.password_hash, body.password):
            raise ApiProblem("invalid_credentials", "Current password is incorrect", 401)

        now = datetime.now(timezone.utc)
        public_id = str(user.public_id)
        write_audit_event(
            db.session,
            action="identity.account_deleted",
            resource_type="user",
            resource_id=public_id,
            actor_user_id=user.user_id,
            details={"deletion_type": "deactivated_and_anonymized"},
        )
        revoked = revoke_all_sessions(db.session, user.user_id, reason="account_deleted")
        user.name = "Deleted account"
        user.email = f"deleted+{public_id}@invalid.mediflow"
        user.phone = None
        user.age = None
        user.gender = None
        user.password_hash = None
        user.is_active = False
        user.deactivated_at = now
        user.email_verified_at = None
        user.phone_verified_at = None
        user.mfa_enabled = False
        user.mfa_secret_encrypted = None
        user.mfa_enforced_at = None
        db.session.commit()

        response = make_response(jsonify({"deleted": True, "revoked_sessions": revoked}))
        _clear_refresh_cookie(response)
        return response

    @app.get("/api/v1/auth/sessions")
    @require_auth()
    def sessions():
        now = datetime.now(timezone.utc)
        items = []
        for auth_session in db.session.scalars(
            select(AuthSession)
            .where(AuthSession.user_id == g.current_user.user_id)
            .order_by(AuthSession.issued_at.desc())
        ):
            items.append(
                {
                    "id": str(auth_session.public_id),
                    "issued_at": auth_session.issued_at.isoformat(),
                    "expires_at": auth_session.expires_at.isoformat(),
                    "active": auth_session.revoked_at is None and as_utc(auth_session.expires_at) > now,
                    "current": auth_session.auth_session_id == g.auth_session.auth_session_id,
                    "remote_addr": auth_session.remote_addr,
                    "user_agent": auth_session.user_agent,
                    "mfa_verified": auth_session.mfa_verified,
                }
            )
        return jsonify(items)

    @app.delete("/api/v1/auth/sessions/<session_public_id>")
    @require_auth()
    def revoke_specific_session(session_public_id: str):
        try:
            session_uuid = uuid.UUID(session_public_id)
        except ValueError as error:
            raise ApiProblem("validation_error", "Session identifier is invalid", 422) from error
        target = db.session.scalar(
            select(AuthSession).where(
                AuthSession.public_id == session_uuid,
                AuthSession.user_id == g.current_user.user_id,
            )
        )
        if target is None:
            raise ApiProblem("session_not_found", "Session not found", 404)
        revoke_session(db.session, target, "user_revoked")
        write_audit_event(
            db.session, action="identity.session_revoked", resource_type="auth_session",
            resource_id=target.public_id, actor_user_id=g.current_user.user_id,
        )
        db.session.commit()
        return jsonify({"revoked": True})

    @app.post("/api/v1/auth/password-reset/request")
    @limiter.limit(AUTHENTICATION_RATE_LIMIT)
    def request_password_reset():
        body = validate_json(PasswordResetRequest)
        raw_token = create_password_reset(
            db.session,
            identifier=body.identifier,
            config=current_app.config,
            remote_addr=request.remote_addr,
        )
        from security_service import collect_security_event
        collect_security_event(
            db.session, event_type="identity.password_reset_requested", outcome="success",
            resource_type="user", remote_addr=request.remote_addr,
            user_agent=request.user_agent.string if request.user_agent else None,
        )
        db.session.commit()
        payload = {"accepted": True, "message": "If the account exists, reset instructions will be sent"}
        if current_app.testing and raw_token:
            payload["testing_reset_token"] = raw_token
        return jsonify(payload), 202

    @app.post("/api/v1/auth/password-reset/confirm")
    @limiter.limit(AUTHENTICATION_RATE_LIMIT)
    def confirm_password_reset():
        body = validate_json(PasswordResetConfirmRequest)
        user = reset_password(db.session, token=body.token, new_password=body.new_password)
        write_audit_event(
            db.session,
            action="identity.password_reset",
            resource_type="user",
            resource_id=user.public_id,
            actor_user_id=user.user_id,
        )
        db.session.commit()
        response = make_response(jsonify({"password_reset": True}))
        _clear_refresh_cookie(response)
        return response

    @app.post("/api/v1/auth/activation/request")
    @limiter.limit(AUTHENTICATION_RATE_LIMIT)
    def request_activation():
        body = validate_json(PasswordResetRequest)
        raw_token = request_account_activation(db.session, identifier=body.identifier, config=current_app.config)
        payload = {"accepted": True, "message": "If activation is required, instructions will be sent"}
        if current_app.testing and raw_token:
            payload["testing_activation_token"] = raw_token
        return jsonify(payload), 202

    @app.post("/api/v1/auth/activation/confirm")
    @limiter.limit(AUTHENTICATION_RATE_LIMIT)
    def confirm_activation():
        body = validate_json(AccountActivationConfirmRequest)
        user = activate_account(db.session, token=body.token)
        write_audit_event(
            db.session,
            action="identity.email_verified",
            resource_type="user",
            resource_id=user.public_id,
            actor_user_id=user.user_id,
        )
        db.session.commit()
        return jsonify({"activated": True})

    @app.post("/api/v1/admin/staff")
    @require_auth(ROLE_HOSPITAL_ADMIN, ROLE_SECURITY_ADMIN)
    @limiter.limit(SENSITIVE_WRITE_RATE_LIMIT)
    def create_staff():
        body = validate_json(StaffOnboardRequest)
        if ROLE_HOSPITAL_ADMIN in g.current_roles:
            if body.role != ROLE_DOCTOR:
                raise ApiProblem("forbidden", "Hospital administrators may onboard doctors only", 403)
            enforce_tenant(body.hospital_id)
        elif body.role == ROLE_SECURITY_ADMIN and ROLE_SECURITY_ADMIN not in g.current_roles:
            raise ApiProblem("forbidden", "Only security administrators may create this role", 403)

        user = onboard_staff(
            db.session,
            name=body.name,
            email=body.email,
            phone=body.phone,
            password=body.password,
            role_name=body.role,
            hospital_id=body.hospital_id,
            doctor_id=body.doctor_id,
            employee_code=body.employee_code,
            assigned_by_user_id=g.current_user.user_id,
        )
        write_audit_event(
            db.session,
            action="identity.staff_onboarded",
            resource_type="user",
            resource_id=user.public_id,
            actor_user_id=g.current_user.user_id,
            details={"role": body.role, "hospital_id": body.hospital_id},
        )
        db.session.commit()
        return jsonify({"user": serialize_user(db.session, user)}), 201

    @app.patch("/api/v1/admin/users/<user_public_id>/status")
    @require_auth(ROLE_HOSPITAL_ADMIN, ROLE_SECURITY_ADMIN)
    @limiter.limit(SENSITIVE_WRITE_RATE_LIMIT)
    def update_user_status(user_public_id: str):
        body = validate_json(UserStatusRequest)
        try:
            public_id = uuid.UUID(user_public_id)
        except ValueError as error:
            raise ApiProblem("validation_error", "User identifier is invalid", 422) from error
        target = db.session.scalar(select(User).where(User.public_id == public_id))
        if target is None:
            raise ApiProblem("user_not_found", "User not found", 404)
        target_roles, target_tenants = identity_context(db.session, target)
        if ROLE_HOSPITAL_ADMIN in g.current_roles and ROLE_SECURITY_ADMIN not in g.current_roles:
            if ROLE_SECURITY_ADMIN in target_roles:
                raise ApiProblem("forbidden", "Hospital administrators cannot modify security administrators", 403)
            allowed_hospitals = g.current_tenants.get(ROLE_HOSPITAL_ADMIN, set())
            target_hospitals = set().union(*target_tenants.values()) if target_tenants else set()
            if not allowed_hospitals.intersection(target_hospitals):
                raise ApiProblem("tenant_forbidden", "User is outside your hospital tenant", 403)
        if target.user_id == g.current_user.user_id and not body.is_active:
            raise ApiProblem("self_deactivation_forbidden", "You cannot deactivate your own account", 409)

        target.is_active = body.is_active
        target.deactivated_at = None if body.is_active else datetime.now(timezone.utc)
        revoked = revoke_all_sessions(db.session, target.user_id, "account_deactivated") if not body.is_active else 0
        write_audit_event(
            db.session,
            action="identity.status_changed",
            resource_type="user",
            resource_id=target.public_id,
            actor_user_id=g.current_user.user_id,
            details={"is_active": body.is_active, "reason": body.reason, "revoked_sessions": revoked},
        )
        db.session.commit()
        return jsonify({"user": serialize_user(db.session, target)})


def register_auth_commands(app: Flask) -> None:
    @app.cli.command("seed-roles")
    def seed_roles_command():
        ensure_default_roles(db.session)
        db.session.commit()
        click.echo("Default roles are available.")

    @app.cli.command("bootstrap-security-admin")
    @click.option("--name", required=True)
    @click.option("--email", required=True)
    @click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True)
    def bootstrap_security_admin_command(name: str, email: str, password: str):
        existing = db.session.scalar(select(User).where(func.lower(User.email) == email.lower()))
        if existing:
            raise click.ClickException("A user already exists for this email")
        user = User(name=name, email=email.lower(), password_hash=hash_password(password), is_active=True)
        db.session.add(user)
        db.session.flush()
        from auth_service import assign_role

        assign_role(db.session, user=user, role_name=ROLE_SECURITY_ADMIN)
        db.session.commit()
        click.echo(f"Security administrator created: {user.public_id}")
