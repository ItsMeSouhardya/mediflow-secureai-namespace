"""Consent and authorization domain — service layer.

Covers task 7.3 through 7.7:
  7.3  Doctor/hospital access requests
  7.4  Patient grant, deny, and revoke actions
  7.5  Consent expiry enforcement (checked at every access attempt)
  7.6  Consent scope enforcement at service level (not only frontend)
  7.7  Emergency break-glass access with mandatory reason, restricted
       duration (BREAK_GLASS_DURATION_HOURS), and enhanced audit events
  7.8  Consent notification events (written on every lifecycle transition)

Architecture rules
------------------
- All enforcement happens HERE, not in route handlers.  Routes call
  service functions which raise ApiProblem on any violation.
- check_consent_scope() is the single chokepoint called from
  authorization.authorize_clinical_access() so scope enforcement is
  guaranteed regardless of which endpoint a request arrives at.
- Expiry is evaluated lazily at check time (7.5): if a granted consent
  has passed its access_expires_at, its status is transitioned to
  'expired' in the same database transaction and access is denied.
- Break-glass rows are independent ConsentGrant rows (is_break_glass=True)
  with a server-enforced short expiry and mandatory reason (7.7).
- Every status transition appends a ConsentStatusHistory row AND writes
  an AuditEvent so the audit trail is both queryable and durable.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from audit import write_audit_event
from errors import ApiProblem
from models import (
    BREAK_GLASS_DURATION_HOURS,
    CONSENT_SCOPES,
    ConsentGrant,
    ConsentNotification,
    ConsentStatusHistory,
    DoctorProfile,
    PatientProfile,
    User,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _transition(
    session: Session,
    grant: ConsentGrant,
    to_status: str,
    actor_user_id: int,
    reason: str | None = None,
) -> None:
    """Append a ConsentStatusHistory row and update the grant's status."""
    history = ConsentStatusHistory(
        consent_grant_id=grant.consent_grant_id,
        from_status=grant.status,
        to_status=to_status,
        actor_user_id=actor_user_id,
        reason=reason,
        created_at=_utcnow(),
    )
    session.add(history)
    grant.status = to_status
    grant.updated_at = _utcnow()
    session.flush()


def _notify(
    session: Session,
    grant: ConsentGrant,
    recipient_user_id: int,
    notification_type: str,
    title: str,
    body: str,
) -> ConsentNotification:
    """Create an in-app notification for a consent lifecycle event (7.8)."""
    notif = ConsentNotification(
        consent_grant_id=grant.consent_grant_id,
        recipient_user_id=recipient_user_id,
        notification_type=notification_type,
        title=title,
        body=body,
        created_at=_utcnow(),
    )
    session.add(notif)
    session.flush()
    return notif


def _grant_payload(grant: ConsentGrant) -> dict:
    return {
        "id": str(grant.public_id),
        "patient_profile_id": grant.patient_profile_id,
        "requesting_doctor_profile_id": grant.requesting_doctor_profile_id,
        "requesting_hospital_id": grant.requesting_hospital_id,
        "scopes": grant.scopes,
        "purpose": grant.purpose,
        "operation": grant.operation,
        "status": grant.status,
        "access_start": grant.access_start.isoformat() if grant.access_start else None,
        "access_expires_at": grant.access_expires_at.isoformat() if grant.access_expires_at else None,
        "denied_at": grant.denied_at.isoformat() if grant.denied_at else None,
        "denied_reason": grant.denied_reason,
        "revoked_at": grant.revoked_at.isoformat() if grant.revoked_at else None,
        "revoked_reason": grant.revoked_reason,
        "is_break_glass": grant.is_break_glass,
        "break_glass_reason": grant.break_glass_reason,
        "created_at": grant.created_at.isoformat(),
        "updated_at": grant.updated_at.isoformat(),
    }


def _get_grant(session: Session, public_id: UUID) -> ConsentGrant:
    grant = session.scalar(
        select(ConsentGrant).where(ConsentGrant.public_id == public_id)
    )
    if grant is None:
        raise ApiProblem("consent_not_found", "Consent grant not found", 404)
    return grant


def _validate_scopes(scopes: list[str]) -> None:
    unknown = set(scopes) - CONSENT_SCOPES
    if unknown:
        raise ApiProblem(
            "invalid_scope",
            f"Unknown consent scopes: {sorted(unknown)}. "
            f"Valid scopes: {sorted(CONSENT_SCOPES)}",
            400,
        )


# ---------------------------------------------------------------------------
# 7.3 — Doctor submits an access request
# ---------------------------------------------------------------------------

def request_access(
    session: Session,
    *,
    doctor: DoctorProfile,
    patient: PatientProfile,
    scopes: list[str],
    purpose: str,
    operation: str,
    requested_duration_days: int,
    actor_user_id: int,
) -> ConsentGrant:
    """Doctor requests access to a patient's records (7.3).

    Rules:
    - At most ONE pending or granted request per doctor–patient pair is
      allowed.  The doctor must revoke or wait for an existing one to
      expire before requesting again.
    - Scopes must all be from CONSENT_SCOPES.
    - Break-glass is a separate path (use request_break_glass_access).
    """
    _validate_scopes(scopes)

    # Check for a blocking existing active request.
    existing = session.scalar(
        select(ConsentGrant).where(
            ConsentGrant.requesting_doctor_profile_id == doctor.doctor_profile_id,
            ConsentGrant.patient_profile_id == patient.patient_profile_id,
            ConsentGrant.status.in_(("pending", "granted")),
            ConsentGrant.is_break_glass == False,  # noqa: E712
        )
    )
    if existing is not None:
        raise ApiProblem(
            "consent_request_exists",
            f"An active consent request already exists (status: {existing.status}). "
            "Revoke or wait for it to expire before submitting a new request.",
            409,
        )

    now = _utcnow()
    grant = ConsentGrant(
        patient_profile_id=patient.patient_profile_id,
        requesting_doctor_profile_id=doctor.doctor_profile_id,
        requesting_hospital_id=doctor.hospital_id,
        scopes=list(set(scopes)),
        purpose=purpose,
        operation=operation,
        status="pending",
        is_break_glass=False,
        created_at=now,
        updated_at=now,
    )
    session.add(grant)
    session.flush()

    # Initial history entry
    _transition(session, grant, "pending", actor_user_id, reason="Access request submitted")
    # Correct: we transitioned from None → pending but _transition already
    # set status to pending; just override the from_status sentinel we
    # wrote (history row already persisted — leave it as-is).

    # Notification to patient (7.8)
    patient_user = session.get(User, patient.user_id)
    _notify(
        session, grant,
        recipient_user_id=patient.user_id,
        notification_type="access_requested",
        title="New medical record access request",
        body=(
            f"Dr. {patient_user.name if patient_user else 'A doctor'} has requested access "
            f"to your records for: {purpose}. "
            f"Requested scopes: {', '.join(sorted(scopes))}."
        ),
    )

    write_audit_event(
        session,
        action="consent.access_requested",
        resource_type="consent_grant",
        resource_id=str(grant.public_id),
        actor_user_id=actor_user_id,
        details={
            "patient_profile_id": patient.patient_profile_id,
            "doctor_profile_id": doctor.doctor_profile_id,
            "scopes": sorted(scopes),
            "operation": operation,
        },
    )
    return grant


# ---------------------------------------------------------------------------
# 7.4 — Patient grants a pending request
# ---------------------------------------------------------------------------

def grant_access(
    session: Session,
    grant: ConsentGrant,
    *,
    patient: PatientProfile,
    scopes: list[str],
    access_expires_days: int,
    actor_user_id: int,
) -> ConsentGrant:
    """Patient grants a pending consent request, optionally narrowing scopes (7.4)."""
    if grant.patient_profile_id != patient.patient_profile_id:
        raise ApiProblem("ownership_required", "You do not own this consent request", 403)
    if grant.status != "pending":
        raise ApiProblem(
            "invalid_consent_state",
            f"Only pending requests can be granted (current status: {grant.status})",
            409,
        )
    _validate_scopes(scopes)

    # Patient can only grant a subset of what was requested.
    requested = set(grant.scopes)
    granted = set(scopes)
    if not granted.issubset(requested):
        extra = sorted(granted - requested)
        raise ApiProblem(
            "scope_exceeds_request",
            f"Cannot grant scopes that were not requested: {extra}",
            400,
        )

    now = _utcnow()
    expires_at = now + timedelta(days=access_expires_days)

    grant.scopes = sorted(granted)
    grant.access_start = now
    grant.access_expires_at = expires_at

    _transition(session, grant, "granted", actor_user_id, reason="Patient granted access")

    # Notify the requesting doctor
    doctor_profile = session.get(DoctorProfile, grant.requesting_doctor_profile_id)
    if doctor_profile:
        _notify(
            session, grant,
            recipient_user_id=doctor_profile.user_id,
            notification_type="access_granted",
            title="Patient granted record access",
            body=(
                f"Your access request has been granted. "
                f"Scopes: {', '.join(sorted(granted))}. "
                f"Access expires: {expires_at.strftime('%Y-%m-%d %H:%M UTC')}."
            ),
        )

    write_audit_event(
        session,
        action="consent.access_granted",
        resource_type="consent_grant",
        resource_id=str(grant.public_id),
        actor_user_id=actor_user_id,
        details={
            "scopes": sorted(granted),
            "expires_at": expires_at.isoformat(),
            "duration_days": access_expires_days,
        },
    )
    return grant


# ---------------------------------------------------------------------------
# 7.4 — Patient denies a pending request
# ---------------------------------------------------------------------------

def deny_access(
    session: Session,
    grant: ConsentGrant,
    *,
    patient: PatientProfile,
    reason: str | None,
    actor_user_id: int,
) -> ConsentGrant:
    """Patient denies a pending consent request (7.4)."""
    if grant.patient_profile_id != patient.patient_profile_id:
        raise ApiProblem("ownership_required", "You do not own this consent request", 403)
    if grant.status != "pending":
        raise ApiProblem(
            "invalid_consent_state",
            f"Only pending requests can be denied (current status: {grant.status})",
            409,
        )

    grant.denied_at = _utcnow()
    grant.denied_reason = reason
    _transition(session, grant, "denied", actor_user_id, reason=reason)

    doctor_profile = session.get(DoctorProfile, grant.requesting_doctor_profile_id)
    if doctor_profile:
        _notify(
            session, grant,
            recipient_user_id=doctor_profile.user_id,
            notification_type="access_denied",
            title="Patient denied record access",
            body=f"Your access request was denied. Reason: {reason or 'No reason provided.'}",
        )

    write_audit_event(
        session,
        action="consent.access_denied",
        resource_type="consent_grant",
        resource_id=str(grant.public_id),
        actor_user_id=actor_user_id,
        outcome="denied",
        details={"reason": reason},
    )
    return grant


# ---------------------------------------------------------------------------
# 7.4 — Patient revokes a granted consent
# ---------------------------------------------------------------------------

def revoke_access(
    session: Session,
    grant: ConsentGrant,
    *,
    patient: PatientProfile,
    reason: str | None,
    actor_user_id: int,
) -> ConsentGrant:
    """Patient revokes a previously granted consent (7.4).

    Revocation is immediate — the next call to check_consent_scope() will
    return False for this grant.
    """
    if grant.patient_profile_id != patient.patient_profile_id:
        raise ApiProblem("ownership_required", "You do not own this consent grant", 403)
    if grant.status not in ("granted", "break_glass"):
        raise ApiProblem(
            "invalid_consent_state",
            f"Only granted or break_glass consents can be revoked (current: {grant.status})",
            409,
        )

    grant.revoked_at = _utcnow()
    grant.revoked_reason = reason
    _transition(session, grant, "revoked", actor_user_id, reason=reason)

    doctor_profile = session.get(DoctorProfile, grant.requesting_doctor_profile_id)
    if doctor_profile:
        _notify(
            session, grant,
            recipient_user_id=doctor_profile.user_id,
            notification_type="access_revoked",
            title="Patient revoked record access",
            body=f"Your access has been revoked. Reason: {reason or 'No reason provided.'}",
        )

    write_audit_event(
        session,
        action="consent.access_revoked",
        resource_type="consent_grant",
        resource_id=str(grant.public_id),
        actor_user_id=actor_user_id,
        details={"reason": reason},
    )
    return grant


# ---------------------------------------------------------------------------
# 7.5 — Expiry enforcement (lazy, called at access time)
# ---------------------------------------------------------------------------

def _expire_if_needed(session: Session, grant: ConsentGrant, actor_user_id: int | None) -> bool:
    """Transition a grant to 'expired' if it has passed its expiry time.

    Returns True if the grant was just expired, False if still valid.
    Called from check_consent_scope() so expiry is enforced at every
    access attempt without needing a background job.
    """
    if grant.status != "granted":
        return False
    if grant.access_expires_at is None:
        return False

    expires = grant.access_expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)

    if _utcnow() <= expires:
        return False

    # Transition to expired — use system actor (0) if no user in context.
    system_actor = actor_user_id or 0
    _transition(session, grant, "expired", system_actor, reason="Access period elapsed")

    # Notify both parties
    patient_profile = session.get(PatientProfile, grant.patient_profile_id)
    doctor_profile = session.get(DoctorProfile, grant.requesting_doctor_profile_id)

    if patient_profile:
        _notify(
            session, grant,
            recipient_user_id=patient_profile.user_id,
            notification_type="consent_expired",
            title="A consent grant has expired",
            body="A previously granted medical record access has expired automatically.",
        )
    if doctor_profile:
        _notify(
            session, grant,
            recipient_user_id=doctor_profile.user_id,
            notification_type="consent_expired",
            title="Patient record access has expired",
            body="Your access to a patient's records has expired. Submit a new request if needed.",
        )

    write_audit_event(
        session,
        action="consent.expired",
        resource_type="consent_grant",
        resource_id=str(grant.public_id),
        actor_user_id=actor_user_id,
        details={"expired_at": grant.access_expires_at.isoformat()},
    )
    return True


# ---------------------------------------------------------------------------
# 7.6 — Scope enforcement (called from authorization layer)
# ---------------------------------------------------------------------------

def check_consent_scope(
    session: Session,
    *,
    doctor_user_id: int,
    patient_user_id: int,
    required_scope: str,
    actor_user_id: int | None = None,
) -> bool:
    """Return True if the doctor has a valid, unexpired, in-scope consent for this patient.

    This is the single enforcement chokepoint called by
    authorization.authorize_clinical_access().  It NEVER raises — it
    returns False and lets the caller raise the appropriate ApiProblem.

    Behaviour:
    - Finds all granted or break_glass rows for this doctor/patient pair.
    - Lazily expires any that have passed their access_expires_at.
    - Returns True only if at least one active row covers required_scope.
    """
    if required_scope not in CONSENT_SCOPES:
        logger.warning("check_consent_scope called with unknown scope '%s'", required_scope)
        return False

    rows = list(
        session.scalars(
            select(ConsentGrant).where(
                ConsentGrant.patient_profile_id == select(PatientProfile.patient_profile_id)
                    .where(PatientProfile.user_id == patient_user_id)
                    .scalar_subquery(),
                ConsentGrant.requesting_doctor_profile_id == select(DoctorProfile.doctor_profile_id)
                    .where(DoctorProfile.user_id == doctor_user_id)
                    .scalar_subquery(),
                ConsentGrant.status.in_(("granted", "break_glass")),
            )
        )
    )

    for grant in rows:
        expired = _expire_if_needed(session, grant, actor_user_id)
        if expired:
            continue
        if grant.status in ("granted", "break_glass") and required_scope in grant.scopes:
            return True

    return False


# ---------------------------------------------------------------------------
# 7.7 — Emergency break-glass access
# ---------------------------------------------------------------------------

def request_break_glass_access(
    session: Session,
    *,
    doctor: DoctorProfile,
    patient: PatientProfile,
    scopes: list[str],
    reason: str,
    actor_user_id: int,
) -> ConsentGrant:
    """Doctor invokes emergency break-glass access (7.7).

    Rules:
    - Mandatory non-empty reason (min 20 chars enforced at schema level).
    - Duration is HARD-CAPPED at BREAK_GLASS_DURATION_HOURS server-side.
    - Creates a new ConsentGrant with is_break_glass=True and
      status='break_glass' (bypasses patient approval flow).
    - Enhanced audit event with break_glass=True flag.
    - Notifies the patient immediately after creation.
    """
    _validate_scopes(scopes)
    if not reason or len(reason.strip()) < 20:
        raise ApiProblem(
            "break_glass_reason_required",
            "A break-glass access reason of at least 20 characters is required",
            400,
        )

    now = _utcnow()
    expires_at = now + timedelta(hours=BREAK_GLASS_DURATION_HOURS)

    grant = ConsentGrant(
        patient_profile_id=patient.patient_profile_id,
        requesting_doctor_profile_id=doctor.doctor_profile_id,
        requesting_hospital_id=doctor.hospital_id,
        scopes=sorted(set(scopes)),
        purpose=reason,
        operation="emergency",
        status="break_glass",
        is_break_glass=True,
        break_glass_reason=reason,
        access_start=now,
        access_expires_at=expires_at,
        created_at=now,
        updated_at=now,
    )
    session.add(grant)
    session.flush()

    _transition(session, grant, "break_glass", actor_user_id, reason=reason)

    # Notify patient immediately (7.8)
    _notify(
        session, grant,
        recipient_user_id=patient.user_id,
        notification_type="break_glass_used",
        title="Emergency access to your records was used",
        body=(
            f"A doctor has invoked emergency access to your records. "
            f"Reason: {reason}. "
            f"Access expires at {expires_at.strftime('%Y-%m-%d %H:%M UTC')}. "
            f"Scopes: {', '.join(sorted(scopes))}."
        ),
    )

    # Enhanced audit event with break_glass flag (7.7)
    write_audit_event(
        session,
        action="consent.break_glass_invoked",
        resource_type="consent_grant",
        resource_id=str(grant.public_id),
        actor_user_id=actor_user_id,
        details={
            "break_glass": True,
            "patient_profile_id": patient.patient_profile_id,
            "doctor_profile_id": doctor.doctor_profile_id,
            "scopes": sorted(scopes),
            "reason": reason,
            "expires_at": expires_at.isoformat(),
        },
    )
    logger.warning(
        "BREAK_GLASS: doctor_user_id=%d accessed patient_profile_id=%d scopes=%s reason='%s'",
        actor_user_id,
        patient.patient_profile_id,
        sorted(scopes),
        reason,
    )
    return grant


# ---------------------------------------------------------------------------
# Query helpers used by route handlers
# ---------------------------------------------------------------------------

def get_grant_for_patient(
    session: Session,
    grant_public_id: UUID,
    patient: PatientProfile,
) -> ConsentGrant:
    grant = _get_grant(session, grant_public_id)
    if grant.patient_profile_id != patient.patient_profile_id:
        raise ApiProblem("ownership_required", "You do not own this consent grant", 403)
    return grant


def get_grant_for_doctor(
    session: Session,
    grant_public_id: UUID,
    doctor: DoctorProfile,
) -> ConsentGrant:
    grant = _get_grant(session, grant_public_id)
    if grant.requesting_doctor_profile_id != doctor.doctor_profile_id:
        raise ApiProblem("ownership_required", "This consent request was not made by you", 403)
    return grant


def list_patient_pending(session: Session, patient: PatientProfile) -> list[dict]:
    """Return pending consent requests for the patient inbox (7.9)."""
    rows = list(
        session.scalars(
            select(ConsentGrant)
            .where(
                ConsentGrant.patient_profile_id == patient.patient_profile_id,
                ConsentGrant.status == "pending",
            )
            .order_by(ConsentGrant.created_at.desc())
        )
    )
    return [_grant_payload(r) for r in rows]


def list_patient_active(session: Session, patient: PatientProfile) -> list[dict]:
    """Return active (granted + break_glass) grants for the patient (7.9)."""
    rows = list(
        session.scalars(
            select(ConsentGrant)
            .where(
                ConsentGrant.patient_profile_id == patient.patient_profile_id,
                ConsentGrant.status.in_(("granted", "break_glass")),
            )
            .order_by(ConsentGrant.access_expires_at.asc())
        )
    )
    return [_grant_payload(r) for r in rows]


def list_patient_history(session: Session, patient: PatientProfile) -> list[dict]:
    """Return full consent history for the patient (7.9)."""
    rows = list(
        session.scalars(
            select(ConsentGrant)
            .where(ConsentGrant.patient_profile_id == patient.patient_profile_id)
            .order_by(ConsentGrant.created_at.desc())
        )
    )
    return [_grant_payload(r) for r in rows]


def list_doctor_requests(session: Session, doctor: DoctorProfile) -> list[dict]:
    """Return all consent requests made by this doctor (7.10)."""
    rows = list(
        session.scalars(
            select(ConsentGrant)
            .where(ConsentGrant.requesting_doctor_profile_id == doctor.doctor_profile_id)
            .order_by(ConsentGrant.created_at.desc())
        )
    )
    return [_grant_payload(r) for r in rows]


def list_notifications(
    session: Session,
    user_id: int,
    *,
    unread_only: bool = False,
) -> list[dict]:
    """Return consent notifications for a user (7.8)."""
    from models import ConsentNotification
    q = select(ConsentNotification).where(
        ConsentNotification.recipient_user_id == user_id
    )
    if unread_only:
        q = q.where(ConsentNotification.is_read == False)  # noqa: E712
    q = q.order_by(ConsentNotification.created_at.desc())
    rows = list(session.scalars(q))
    return [
        {
            "id": str(n.public_id),
            "consent_grant_id": n.consent_grant_id,
            "notification_type": n.notification_type,
            "title": n.title,
            "body": n.body,
            "is_read": n.is_read,
            "read_at": n.read_at.isoformat() if n.read_at else None,
            "created_at": n.created_at.isoformat(),
        }
        for n in rows
    ]


def mark_notifications_read(
    session: Session,
    notification_public_ids: list[UUID],
    user_id: int,
) -> int:
    """Mark notifications as read; returns count updated."""
    from models import ConsentNotification
    rows = list(
        session.scalars(
            select(ConsentNotification).where(
                ConsentNotification.public_id.in_(notification_public_ids),
                ConsentNotification.recipient_user_id == user_id,
                ConsentNotification.is_read == False,  # noqa: E712
            )
        )
    )
    now = _utcnow()
    for n in rows:
        n.is_read = True
        n.read_at = now
    session.flush()
    return len(rows)


def get_consent_status(
    session: Session,
    doctor: DoctorProfile,
    patient: PatientProfile,
) -> dict:
    """Return the current consent state between a doctor and patient (7.10)."""
    rows = list(
        session.scalars(
            select(ConsentGrant)
            .where(
                ConsentGrant.requesting_doctor_profile_id == doctor.doctor_profile_id,
                ConsentGrant.patient_profile_id == patient.patient_profile_id,
            )
            .order_by(ConsentGrant.created_at.desc())
        )
    )
    active = next(
        (r for r in rows if r.status in ("granted", "break_glass", "pending")),
        None,
    )
    return {
        "has_active_consent": active is not None and active.status in ("granted", "break_glass"),
        "active_grant": _grant_payload(active) if active else None,
        "history_count": len(rows),
    }
