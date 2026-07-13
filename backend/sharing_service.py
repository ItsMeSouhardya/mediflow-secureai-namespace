"""Secure cross-hospital sharing — service layer.

Covers task 9.3 through 9.6:
  9.3  Minimum-necessary record projection — shared responses include only
       the fields covered by the approved scopes; no extras leak through.
  9.4  No raw storage paths or public links — document payloads in shared
       responses carry only metadata (id, title, type, date, status).
       Downloads go through the authorised download endpoint, never direct
       object-storage URLs.
  9.5  Source and requesting-hospital tenant checks — the doctor must
       belong to the requesting hospital; the patient's source hospital
       is verified; the two hospitals must differ.
  9.6  Full audit trail — every access attempt (success, scope-denied,
       tenant-denied, expired, revoked) writes an AuditEvent row.

Architecture rules
------------------
- All enforcement happens here, not in route handlers.
- _project_shared_record() is the single chokepoint that strips any
  field not covered by the share's approved scopes.
- _check_share_active() evaluates expiry lazily at access time, just
  like consent_service._expire_if_needed(), so no background job is
  required.
- No patient identifiers, document bytes, or storage keys are returned
  in cross-hospital responses.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from audit import write_audit_event
from errors import ApiProblem
from models import (
    CONSENT_SCOPES,
    Allergy,
    CrossHospitalShare,
    CrossHospitalShareHistory,
    Department,
    Diagnosis,
    Doctor,
    DoctorProfile,
    Encounter,
    Hospital,
    MedicalDocument,
    DocumentVersion,
    PatientProfile,
    Prescription,
    RiskPrediction,
    User,
    Vaccination,
)
from ehr_service import patient_ehr_summary

BREAK_GLASS_HOURS = 4

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _validate_scopes(scopes: list[str]) -> None:
    unknown = set(scopes) - CONSENT_SCOPES
    if unknown:
        raise ApiProblem(
            "invalid_scope",
            f"Unknown scopes: {sorted(unknown)}. Valid: {sorted(CONSENT_SCOPES)}",
            400,
        )


def _share_payload(session: Session, share: CrossHospitalShare) -> dict:
    patient = session.get(PatientProfile, share.patient_profile_id)
    patient_user = session.get(User, patient.user_id) if patient else None
    doctor_profile = session.get(DoctorProfile, share.requesting_doctor_profile_id)
    doctor = session.get(Doctor, doctor_profile.doctor_id) if doctor_profile else None
    source_hospital = session.get(Hospital, share.source_hospital_id)
    requesting_hospital = session.get(Hospital, share.requesting_hospital_id)
    return {
        "id": str(share.public_id),
        "patient": {
            "id": str(patient.public_id) if patient else None,
            "name": patient_user.name if patient_user else None,
        },
        "source_hospital_id": share.source_hospital_id,
        "source_hospital": source_hospital.hospital_name if source_hospital else None,
        "requesting_hospital_id": share.requesting_hospital_id,
        "requesting_hospital": requesting_hospital.hospital_name if requesting_hospital else None,
        "requesting_doctor": {
            "id": str(doctor_profile.public_id) if doctor_profile else None,
            "name": doctor.doctor_name if doctor else None,
        },
        "scopes": share.scopes,
        "purpose": share.purpose,
        "operation": share.operation,
        "requested_duration_days": share.requested_duration_days,
        "status": share.status,
        "access_start": share.access_start.isoformat() if share.access_start else None,
        "access_expires_at": share.access_expires_at.isoformat() if share.access_expires_at else None,
        "denied_at": share.denied_at.isoformat() if share.denied_at else None,
        "denied_reason": share.denied_reason,
        "revoked_at": share.revoked_at.isoformat() if share.revoked_at else None,
        "revoked_reason": share.revoked_reason,
        "is_break_glass": share.is_break_glass,
        "break_glass_reason": share.break_glass_reason,
        "created_at": share.created_at.isoformat(),
        "updated_at": share.updated_at.isoformat(),
    }


def _transition(
    session: Session,
    share: CrossHospitalShare,
    to_status: str,
    actor_user_id: int,
    reason: str | None = None,
) -> None:
    previous = share.status
    share.status = to_status
    share.updated_at = _utcnow()
    session.add(
        CrossHospitalShareHistory(
            share_id=share.share_id,
            from_status=previous,
            to_status=to_status,
            actor_user_id=actor_user_id,
            reason=reason,
        )
    )
    session.flush()


def _get_share(session: Session, public_id: UUID) -> CrossHospitalShare:
    share = session.scalar(
        select(CrossHospitalShare).where(CrossHospitalShare.public_id == public_id)
    )
    if share is None:
        raise ApiProblem("share_not_found", "Cross-hospital share not found", 404)
    return share


# ---------------------------------------------------------------------------
# 9.5 — Tenant checks
# ---------------------------------------------------------------------------

def _check_requesting_doctor_tenant(
    session: Session,
    doctor: DoctorProfile,
    requesting_hospital_id: int,
) -> None:
    """Doctor must belong to the requesting hospital (9.5)."""
    provider = session.get(Doctor, doctor.doctor_id)
    department = session.get(Department, provider.dept_id) if provider else None
    if (
        doctor.hospital_id != requesting_hospital_id
        or department is None
        or department.hospital_id != requesting_hospital_id
    ):
        raise ApiProblem(
            "tenant_forbidden",
            "You do not belong to the requesting hospital",
            403,
        )


def _check_source_hospital(
    session: Session,
    patient: PatientProfile,
    source_hospital_id: int,
) -> None:
    """Patient must have records at the source hospital (9.5).

    We verify by checking for at least one encounter or token at that hospital.
    """
    from models import Encounter, Token
    from sqlalchemy import exists

    has_encounter = session.scalar(
        select(exists().where(
            Encounter.patient_profile_id == patient.patient_profile_id,
            Encounter.hospital_id == source_hospital_id,
        ))
    )
    has_token = session.scalar(
        select(exists().where(
            Token.patient_profile_id == patient.patient_profile_id,
            Token.hospital_id == source_hospital_id,
        ))
    )
    if not (has_encounter or has_token):
        raise ApiProblem(
            "source_hospital_mismatch",
            "The patient has no records at the specified source hospital",
            404,
        )


# ---------------------------------------------------------------------------
# 9.5 — Expiry enforcement (lazy, at access time)
# ---------------------------------------------------------------------------

def _check_share_active(
    session: Session,
    share: CrossHospitalShare,
    actor_user_id: int,
) -> None:
    """Raise ApiProblem if the share is not currently active.

    Lazily transitions 'granted' → 'expired' when the expiry time has passed
    and writes an audit event, matching the pattern in consent_service (9.5).
    """
    if share.status == "revoked":
        write_audit_event(
            session,
            action="sharing.access_denied_revoked",
            resource_type="cross_hospital_share",
            resource_id=str(share.public_id),
            actor_user_id=actor_user_id,
            outcome="denied",
        )
        raise ApiProblem(
            "share_revoked",
            "This cross-hospital share has been revoked by the patient",
            403,
        )

    if share.status in ("denied", "pending"):
        write_audit_event(
            session,
            action="sharing.access_denied_not_granted",
            resource_type="cross_hospital_share",
            resource_id=str(share.public_id),
            actor_user_id=actor_user_id,
            outcome="denied",
            details={"status": share.status},
        )
        raise ApiProblem(
            "share_not_active",
            f"This share is not active (status: {share.status})",
            403,
        )

    if share.status == "expired":
        write_audit_event(
            session,
            action="sharing.access_denied_expired",
            resource_type="cross_hospital_share",
            resource_id=str(share.public_id),
            actor_user_id=actor_user_id,
            outcome="denied",
        )
        raise ApiProblem(
            "share_expired",
            "This cross-hospital share has expired",
            403,
        )

    if share.status not in ("granted", "break_glass"):
        raise ApiProblem("share_not_active", "This share is not active", 403)

    # Lazy expiry check for granted and emergency break-glass shares.
    if share.status in ("granted", "break_glass") and share.access_expires_at is not None:
        expires = share.access_expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if _utcnow() > expires:
            _transition(session, share, "expired", actor_user_id, reason="Share validity period elapsed")
            write_audit_event(
                session,
                action="sharing.share_expired",
                resource_type="cross_hospital_share",
                resource_id=str(share.public_id),
                actor_user_id=actor_user_id,
                details={"expired_at": share.access_expires_at.isoformat()},
            )
            raise ApiProblem(
                "share_expired",
                "This cross-hospital share has expired",
                403,
            )


# ---------------------------------------------------------------------------
# 9.3 — Minimum-necessary record projection
# ---------------------------------------------------------------------------

# Maps each scope to the keys that are included in the shared response.
# Any key not listed here is stripped — this is enforced at the service
# layer, not the route layer (9.3).

_SCOPE_FIELDS: dict[str, set[str]] = {
    "summary": {
        "patient",          # name, age, gender, blood_group, date_of_birth
    },
    "encounters": {
        "encounters",       # encounter list WITHOUT clinical_notes unless also granted
    },
    "diagnoses": {
        "encounters",       # diagnosis sub-list inside encounter payload
    },
    "prescriptions": {
        "prescriptions",
    },
    "allergies": {
        "allergies",
    },
    "vaccinations": {
        "vaccinations",
    },
    "reports": {
        "documents",        # metadata only — no storage_key, no bytes
    },
    "risk_predictions": {
        "risk_predictions",
    },
}

# Patient fields always included if "summary" scope is granted.
_SUMMARY_PATIENT_FIELDS = {
    "id", "name", "age", "gender",
    "blood_group", "date_of_birth",
    # Emergency contact is deliberately excluded from shared projections.
}


def _project_shared_record(
    session: Session,
    patient: PatientProfile,
    approved_scopes: list[str],
    actor_user_id: int,
    share_id: str,
    source_hospital_id: int,
) -> dict:
    """Build a scope-projected record response for cross-hospital access (9.3).

    Only fields covered by approved_scopes are included.
    No raw storage paths, document bytes, or internal PKs are returned (9.4).
    """
    scope_set = set(approved_scopes)
    result: dict = {"approved_scopes": sorted(scope_set)}
    full = patient_ehr_summary(session, patient)

    # summary scope — strip internal fields, keep only _SUMMARY_PATIENT_FIELDS
    if "summary" in scope_set:
        raw_patient = full.get("patient", {})
        result["patient"] = {
            k: v for k, v in raw_patient.items() if k in _SUMMARY_PATIENT_FIELDS
        }

    source_encounter_ids = {
        str(encounter.public_id)
        for encounter in session.scalars(
            select(Encounter).where(
                Encounter.patient_profile_id == patient.patient_profile_id,
                Encounter.hospital_id == source_hospital_id,
            )
        )
    }

    # encounters scope — include source-hospital encounters only.
    # diagnoses scope is also granted (minimum-necessary)
    if "encounters" in scope_set or "diagnoses" in scope_set:
        include_diagnoses = "diagnoses" in scope_set
        encounters_out = []
        for enc in full.get("encounters", []):
            if enc.get("id") not in source_encounter_ids:
                continue
            enc_copy = {
                k: v for k, v in enc.items()
                if k not in {"clinical_notes", "diagnoses"}
            }
            # clinical_notes only if encounters scope granted (not just diagnoses)
            if "encounters" in scope_set:
                enc_copy["clinical_notes"] = enc.get("clinical_notes")
            if include_diagnoses:
                enc_copy["diagnoses"] = enc.get("diagnoses", [])
            encounters_out.append(enc_copy)
        result["encounters"] = encounters_out

    if "prescriptions" in scope_set:
        prescriptions = list(
            session.scalars(
                select(Prescription)
                .join(Encounter, Encounter.encounter_id == Prescription.encounter_id)
                .where(
                    Prescription.patient_profile_id == patient.patient_profile_id,
                    Encounter.hospital_id == source_hospital_id,
                )
                .order_by(Prescription.created_at.desc())
            )
        )
        result["prescriptions"] = [
            {
                "id": str(item.public_id), "medicine": item.medicine, "dosage": item.dosage,
                "frequency": item.frequency, "duration": item.duration,
                "instructions": item.instructions, "status": item.status,
                "created_at": item.created_at.isoformat(),
            }
            for item in prescriptions
        ]

    if "allergies" in scope_set:
        allergies = list(
            session.scalars(
                select(Allergy)
                .join(
                    DoctorProfile,
                    DoctorProfile.doctor_profile_id == Allergy.recorded_by_doctor_profile_id,
                )
                .where(
                    Allergy.patient_profile_id == patient.patient_profile_id,
                    Allergy.is_active.is_(True),
                    DoctorProfile.hospital_id == source_hospital_id,
                )
                .order_by(Allergy.created_at.desc())
            )
        )
        result["allergies"] = [
            {
                "id": str(item.public_id), "substance": item.substance,
                "severity": item.severity, "reaction": item.reaction,
                "verification_status": item.verification_status, "source": item.source,
            }
            for item in allergies
        ]

    if "vaccinations" in scope_set:
        vaccinations = list(
            session.scalars(
                select(Vaccination)
                .join(
                    DoctorProfile,
                    DoctorProfile.doctor_profile_id == Vaccination.recorded_by_doctor_profile_id,
                )
                .where(
                    Vaccination.patient_profile_id == patient.patient_profile_id,
                    DoctorProfile.hospital_id == source_hospital_id,
                )
                .order_by(Vaccination.administered_on.desc())
            )
        )
        result["vaccinations"] = [
            {
                "id": str(item.public_id), "vaccine_name": item.vaccine_name,
                "administered_on": item.administered_on.isoformat(),
                "dose_number": item.dose_number, "provider_name": item.provider_name,
                "verification_status": item.verification_status,
            }
            for item in vaccinations
        ]

    # reports scope — metadata only, NO storage_key, NO download URL (9.4)
    if "reports" in scope_set:
        docs = list(
            session.scalars(
                select(MedicalDocument).where(
                    MedicalDocument.patient_profile_id == patient.patient_profile_id,
                    MedicalDocument.status.in_(("ready", "archived")),
                    MedicalDocument.encounter_id.in_(
                        select(Encounter.encounter_id).where(
                            Encounter.patient_profile_id == patient.patient_profile_id,
                            Encounter.hospital_id == source_hospital_id,
                        )
                    ),
                ).order_by(MedicalDocument.created_at.desc())
            )
        )
        result["documents"] = [
            {
                "id": str(d.public_id),
                "document_type": d.document_type,
                "title": d.title,
                "document_date": d.document_date.isoformat() if d.document_date else None,
                "status": d.status,
                "verified_at": d.verified_at.isoformat() if d.verified_at else None,
                # storage_key and download URLs are intentionally omitted (9.4)
            }
            for d in docs
        ]

    # risk_predictions scope — output snapshots only, no input snapshots
    if "risk_predictions" in scope_set:
        preds = list(
            session.scalars(
                select(RiskPrediction).where(
                    RiskPrediction.patient_profile_id == patient.patient_profile_id,
                    RiskPrediction.review_status == "accepted",
                    RiskPrediction.source_document_id.in_(
                        select(MedicalDocument.document_id).where(
                            MedicalDocument.encounter_id.in_(
                                select(Encounter.encounter_id).where(
                                    Encounter.patient_profile_id == patient.patient_profile_id,
                                    Encounter.hospital_id == source_hospital_id,
                                )
                            )
                        )
                    ),
                ).order_by(RiskPrediction.created_at.desc())
            )
        )
        result["risk_predictions"] = [
            {
                "id": str(p.public_id),
                "model_name": p.model_name,
                "model_version": p.model_version,
                "risk_score": p.risk_score,
                "risk_band": p.risk_band,
                "review_status": p.review_status,
                "created_at": p.created_at.isoformat(),
                # input_snapshot deliberately omitted from shared projection
            }
            for p in preds
        ]

    return result


# ---------------------------------------------------------------------------
# 9.3 — Request submission (doctor at requesting hospital)
# ---------------------------------------------------------------------------

def request_share(
    session: Session,
    *,
    doctor: DoctorProfile,
    patient: PatientProfile,
    source_hospital_id: int,
    scopes: list[str],
    purpose: str,
    operation: str,
    requested_duration_days: int,
    actor_user_id: int,
) -> CrossHospitalShare:
    """Doctor submits a cross-hospital share request (9.1 / 9.5).

    Enforces:
    - Doctor belongs to requesting_hospital (9.5).
    - requesting_hospital != source_hospital (DB constraint + service check).
    - Patient has records at source_hospital (9.5).
    - No duplicate active/pending request from same doctor for same patient.
    """
    _validate_scopes(scopes)

    # Tenant: doctor must be at the requesting hospital.
    _check_requesting_doctor_tenant(session, doctor, doctor.hospital_id)

    # Source != requesting.
    if source_hospital_id == doctor.hospital_id:
        raise ApiProblem(
            "same_hospital_share",
            "Cross-hospital sharing requires a different source and requesting hospital. "
            "Use the consent system for same-hospital access.",
            400,
        )

    # Patient has records at source hospital.
    _check_source_hospital(session, patient, source_hospital_id)

    # Block duplicate active requests.
    existing = session.scalar(
        select(CrossHospitalShare).where(
            CrossHospitalShare.requesting_doctor_profile_id == doctor.doctor_profile_id,
            CrossHospitalShare.patient_profile_id == patient.patient_profile_id,
            CrossHospitalShare.source_hospital_id == source_hospital_id,
            CrossHospitalShare.status.in_(("pending", "granted", "break_glass")),
        )
    )
    if existing is not None:
        raise ApiProblem(
            "share_request_exists",
            f"An active share request already exists (status: {existing.status}). "
            "Wait for it to expire or ask the patient to revoke it first.",
            409,
        )

    now = _utcnow()
    share = CrossHospitalShare(
        patient_profile_id=patient.patient_profile_id,
        source_hospital_id=source_hospital_id,
        requesting_hospital_id=doctor.hospital_id,
        requesting_doctor_profile_id=doctor.doctor_profile_id,
        scopes=sorted(set(scopes)),
        purpose=purpose,
        operation=operation,
        requested_duration_days=requested_duration_days,
        status="pending",
        created_at=now,
        updated_at=now,
    )
    session.add(share)
    session.flush()
    session.add(CrossHospitalShareHistory(
        share_id=share.share_id,
        from_status=None,
        to_status="pending",
        actor_user_id=actor_user_id,
        reason="Cross-hospital access requested",
    ))

    write_audit_event(
        session,
        action="sharing.request_submitted",
        resource_type="cross_hospital_share",
        resource_id=str(share.public_id),
        actor_user_id=actor_user_id,
        details={
            "source_hospital_id": source_hospital_id,
            "requesting_hospital_id": doctor.hospital_id,
            "scopes": sorted(scopes),
            "operation": operation,
        },
    )
    return share


# ---------------------------------------------------------------------------
# Patient lifecycle actions
# ---------------------------------------------------------------------------

def grant_share(
    session: Session,
    share: CrossHospitalShare,
    *,
    patient: PatientProfile,
    scopes: list[str],
    access_expires_days: int,
    actor_user_id: int,
) -> CrossHospitalShare:
    """Patient approves a pending share request, optionally narrowing scopes."""
    if share.patient_profile_id != patient.patient_profile_id:
        raise ApiProblem("ownership_required", "You do not own this share request", 403)
    if share.status != "pending":
        raise ApiProblem(
            "invalid_share_state",
            f"Only pending shares can be granted (current: {share.status})",
            409,
        )
    _validate_scopes(scopes)

    # Patient may only grant a subset of what was requested.
    if not set(scopes).issubset(set(share.scopes)):
        extra = sorted(set(scopes) - set(share.scopes))
        raise ApiProblem(
            "scope_exceeds_request",
            f"Cannot grant scopes not in the original request: {extra}",
            400,
        )

    now = _utcnow()
    share.scopes = sorted(set(scopes))
    share.access_start = now
    share.access_expires_at = now + timedelta(days=access_expires_days)
    _transition(session, share, "granted", actor_user_id, reason="Approved by patient")

    write_audit_event(
        session,
        action="sharing.share_granted",
        resource_type="cross_hospital_share",
        resource_id=str(share.public_id),
        actor_user_id=actor_user_id,
        details={
            "scopes": sorted(scopes),
            "expires_at": share.access_expires_at.isoformat(),
            "duration_days": access_expires_days,
        },
    )
    return share


def deny_share(
    session: Session,
    share: CrossHospitalShare,
    *,
    patient: PatientProfile,
    reason: str | None,
    actor_user_id: int,
) -> CrossHospitalShare:
    """Patient denies a pending share request."""
    if share.patient_profile_id != patient.patient_profile_id:
        raise ApiProblem("ownership_required", "You do not own this share request", 403)
    if share.status != "pending":
        raise ApiProblem(
            "invalid_share_state",
            f"Only pending shares can be denied (current: {share.status})",
            409,
        )
    share.denied_at = _utcnow()
    share.denied_reason = reason
    _transition(session, share, "denied", actor_user_id, reason=reason)

    write_audit_event(
        session,
        action="sharing.share_denied",
        resource_type="cross_hospital_share",
        resource_id=str(share.public_id),
        actor_user_id=actor_user_id,
        outcome="denied",
        details={"reason": reason},
    )
    return share


def revoke_share(
    session: Session,
    share: CrossHospitalShare,
    *,
    patient: PatientProfile,
    reason: str | None,
    actor_user_id: int,
) -> CrossHospitalShare:
    """Patient revokes a granted share (immediate effect — 9.6)."""
    if share.patient_profile_id != patient.patient_profile_id:
        raise ApiProblem("ownership_required", "You do not own this share", 403)
    if share.status not in ("granted", "break_glass"):
        raise ApiProblem(
            "invalid_share_state",
            f"Only active shares can be revoked (current: {share.status})",
            409,
        )
    share.revoked_at = _utcnow()
    share.revoked_reason = reason
    _transition(session, share, "revoked", actor_user_id, reason=reason)

    write_audit_event(
        session,
        action="sharing.share_revoked",
        resource_type="cross_hospital_share",
        resource_id=str(share.public_id),
        actor_user_id=actor_user_id,
        details={"reason": reason},
    )
    return share


# ---------------------------------------------------------------------------
# 9.7 — Patient list helpers
# ---------------------------------------------------------------------------

def list_patient_shares(
    session: Session,
    patient: PatientProfile,
    *,
    status_filter: str | None = None,
) -> list[dict]:
    """Return cross-hospital shares for a patient (history + active, 9.7)."""
    q = select(CrossHospitalShare).where(
        CrossHospitalShare.patient_profile_id == patient.patient_profile_id
    )
    if status_filter:
        q = q.where(CrossHospitalShare.status == status_filter)
    q = q.order_by(CrossHospitalShare.created_at.desc())
    return [_share_payload(session, s) for s in session.scalars(q)]


# ---------------------------------------------------------------------------
# 9.8 — Doctor / hospital incoming-share helpers
# ---------------------------------------------------------------------------

def list_incoming_shares(
    session: Session,
    doctor: DoctorProfile,
    *,
    status_filter: str | None = None,
) -> list[dict]:
    """Return incoming share requests for a doctor (9.8)."""
    q = select(CrossHospitalShare).where(
        CrossHospitalShare.requesting_doctor_profile_id == doctor.doctor_profile_id
    )
    if status_filter:
        q = q.where(CrossHospitalShare.status == status_filter)
    q = q.order_by(CrossHospitalShare.created_at.desc())
    return [_share_payload(session, s) for s in session.scalars(q)]


def list_hospital_incoming_shares(
    session: Session,
    hospital_ids: list[int],
    *,
    status_filter: str | None = None,
) -> list[dict]:
    """Metadata-only tenant view for hospital administrators."""
    q = select(CrossHospitalShare).where(
        CrossHospitalShare.requesting_hospital_id.in_(hospital_ids)
    )
    if status_filter:
        q = q.where(CrossHospitalShare.status == status_filter)
    q = q.order_by(CrossHospitalShare.created_at.desc())
    return [_share_payload(session, item) for item in session.scalars(q)]


def access_shared_record(
    session: Session,
    share: CrossHospitalShare,
    *,
    doctor: DoctorProfile,
    actor_user_id: int,
) -> dict:
    """Return the minimum-necessary projected record for an authorised doctor (9.3–9.6).

    Enforces:
    - Doctor belongs to the requesting hospital (9.5).
    - Share is active and not expired/revoked (9.5 lazy expiry).
    - Returns only scope-projected fields; no raw storage paths (9.3 / 9.4).
    - Audits success (9.6).
    """
    # 9.5 — doctor must be at the requesting hospital
    if doctor.hospital_id != share.requesting_hospital_id:
        write_audit_event(
            session,
            action="sharing.access_denied_wrong_tenant",
            resource_type="cross_hospital_share",
            resource_id=str(share.public_id),
            actor_user_id=actor_user_id,
            outcome="denied",
            details={
                "doctor_hospital": doctor.hospital_id,
                "required_hospital": share.requesting_hospital_id,
            },
        )
        raise ApiProblem(
            "tenant_forbidden",
            "You do not belong to the requesting hospital for this share",
            403,
        )

    try:
        _check_requesting_doctor_tenant(session, doctor, share.requesting_hospital_id)
    except ApiProblem:
        write_audit_event(
            session,
            action="sharing.access_denied_tenant_integrity",
            resource_type="cross_hospital_share",
            resource_id=str(share.public_id),
            actor_user_id=actor_user_id,
            outcome="denied",
        )
        raise

    # 9.5 — doctor must be the one who requested the share
    if share.requesting_doctor_profile_id != doctor.doctor_profile_id:
        write_audit_event(
            session,
            action="sharing.access_denied_wrong_doctor",
            resource_type="cross_hospital_share",
            resource_id=str(share.public_id),
            actor_user_id=actor_user_id,
            outcome="denied",
        )
        raise ApiProblem(
            "ownership_required",
            "This share was not requested by you",
            403,
        )

    # 9.5 — expiry / state check (also writes audit on denial)
    _check_share_active(session, share, actor_user_id)

    # Load patient profile
    patient = session.get(PatientProfile, share.patient_profile_id)
    if patient is None:
        raise ApiProblem("patient_not_found", "Patient profile not found", 500)

    # 9.3 — build minimum-necessary projection
    projected = _project_shared_record(
        session,
        patient,
        share.scopes,
        actor_user_id,
        str(share.public_id),
        share.source_hospital_id,
    )

    # 9.6 — audit successful access
    write_audit_event(
        session,
        action="sharing.record_accessed",
        resource_type="cross_hospital_share",
        resource_id=str(share.public_id),
        actor_user_id=actor_user_id,
        details={
            "scopes_accessed": share.scopes,
            "source_hospital_id": share.source_hospital_id,
            "requesting_hospital_id": share.requesting_hospital_id,
        },
    )
    return projected


def request_break_glass_share(
    session: Session,
    *,
    doctor: DoctorProfile,
    patient: PatientProfile,
    source_hospital_id: int,
    scopes: list[str],
    reason: str,
    actor_user_id: int,
) -> CrossHospitalShare:
    """Create a four-hour, fully audited emergency cross-hospital share."""
    _validate_scopes(scopes)
    if len(reason.strip()) < 20:
        raise ApiProblem("break_glass_reason_required", "A detailed emergency reason is required", 400)
    _check_requesting_doctor_tenant(session, doctor, doctor.hospital_id)
    if source_hospital_id == doctor.hospital_id:
        raise ApiProblem("same_hospital_share", "Break-glass sharing must be cross-hospital", 400)
    _check_source_hospital(session, patient, source_hospital_id)

    now = _utcnow()
    share = CrossHospitalShare(
        patient_profile_id=patient.patient_profile_id,
        source_hospital_id=source_hospital_id,
        requesting_hospital_id=doctor.hospital_id,
        requesting_doctor_profile_id=doctor.doctor_profile_id,
        scopes=sorted(set(scopes)),
        purpose=reason.strip(),
        operation="emergency",
        requested_duration_days=1,
        status="break_glass",
        access_start=now,
        access_expires_at=now + timedelta(hours=BREAK_GLASS_HOURS),
        is_break_glass=True,
        break_glass_reason=reason.strip(),
        created_at=now,
        updated_at=now,
    )
    session.add(share)
    session.flush()
    session.add(CrossHospitalShareHistory(
        share_id=share.share_id,
        from_status=None,
        to_status="break_glass",
        actor_user_id=actor_user_id,
        reason=reason.strip(),
    ))
    write_audit_event(
        session,
        action="sharing.break_glass_activated",
        resource_type="cross_hospital_share",
        resource_id=str(share.public_id),
        actor_user_id=actor_user_id,
        details={
            "reason": reason.strip(),
            "scopes": share.scopes,
            "source_hospital_id": source_hospital_id,
            "requesting_hospital_id": doctor.hospital_id,
            "expires_at": share.access_expires_at.isoformat(),
        },
    )
    return share


def share_payload(session: Session, share: CrossHospitalShare) -> dict:
    return _share_payload(session, share)


def get_share(session: Session, public_id: UUID) -> CrossHospitalShare:
    return _get_share(session, public_id)
