"""Asynchronous integrity-proof outbox, Merkle anchoring, and verification."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from blockchain_adapter import BlockchainUnavailable, Web3IntegrityAdapter
from models import (
    AuditEvent,
    BlockchainAuditAnchor,
    BlockchainTransaction,
    ConsentGrant,
    DoctorProfile,
    DocumentVersion,
    MedicalDocument,
    PatientProfile,
)


PAYLOAD_KEYS = {
    "record_register": {"record_ref", "content_hash"},
    "consent_grant": {"consent_ref", "patient_ref", "grantee_ref", "scope_hash", "period_ref"},
    "consent_revoke": {"consent_ref", "revocation_hash"},
    "audit_anchor": {"period_ref", "merkle_root"},
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _hash_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_hash(value) -> str:
    return _hash_bytes(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8"))


def opaque_reference(config: dict, namespace: str, value) -> str:
    secret = str(config["BLOCKCHAIN_REFERENCE_SECRET"]).encode("utf-8")
    return hmac.new(secret, f"{namespace}:{value}".encode("utf-8"), hashlib.sha256).hexdigest()


def _validate_payload(operation: str, payload: dict) -> None:
    if set(payload) != PAYLOAD_KEYS[operation]:
        raise ValueError("Blockchain proof payload has unexpected fields")
    if any(
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value.lower())
        for value in payload.values()
    ):
        raise ValueError("Blockchain proof payload values must be 32-byte hexadecimal hashes")


def _enqueue(
    session: Session,
    *,
    operation: str,
    entity_type: str,
    entity_reference_hash: str,
    payload: dict,
    document_version_id: int | None = None,
    consent_grant_id: int | None = None,
) -> BlockchainTransaction:
    _validate_payload(operation, payload)
    existing = session.scalar(
        select(BlockchainTransaction).where(
            BlockchainTransaction.operation == operation,
            BlockchainTransaction.entity_reference_hash == entity_reference_hash,
        )
    )
    if existing:
        return existing
    transaction = BlockchainTransaction(
        operation=operation,
        entity_type=entity_type,
        entity_reference_hash=entity_reference_hash,
        payload_hash=canonical_hash(payload),
        proof_payload=payload,
        document_version_id=document_version_id,
        consent_grant_id=consent_grant_id,
        state="pending",
        attempts=0,
    )
    session.add(transaction)
    session.flush()
    return transaction


def enqueue_document_version(
    session: Session, version: DocumentVersion, config: dict
) -> BlockchainTransaction:
    record_ref = opaque_reference(config, "document-version", version.public_id)
    return _enqueue(
        session,
        operation="record_register",
        entity_type="document_version",
        entity_reference_hash=record_ref,
        payload={"record_ref": record_ref, "content_hash": version.sha256_hash.lower()},
        document_version_id=version.document_version_id,
    )


def enqueue_consent_grant(
    session: Session, grant: ConsentGrant, config: dict
) -> BlockchainTransaction:
    patient = session.get(PatientProfile, grant.patient_profile_id)
    doctor = session.get(DoctorProfile, grant.requesting_doctor_profile_id)
    consent_ref = opaque_reference(config, "consent", grant.public_id)
    payload = {
        "consent_ref": consent_ref,
        "patient_ref": opaque_reference(config, "patient", patient.public_id),
        "grantee_ref": opaque_reference(config, "doctor", doctor.public_id),
        "scope_hash": canonical_hash(sorted(grant.scopes)),
        "period_ref": opaque_reference(
            config,
            "consent-period",
            f"{grant.access_start.isoformat()}:{grant.access_expires_at.isoformat()}",
        ),
    }
    return _enqueue(
        session,
        operation="consent_grant",
        entity_type="consent_grant",
        entity_reference_hash=consent_ref,
        payload=payload,
        consent_grant_id=grant.consent_grant_id,
    )


def enqueue_consent_revocation(
    session: Session, grant: ConsentGrant, config: dict
) -> BlockchainTransaction:
    consent_ref = opaque_reference(config, "consent", grant.public_id)
    payload = {
        "consent_ref": consent_ref,
        "revocation_hash": canonical_hash(
            {"status": grant.status, "revoked_at": grant.revoked_at.isoformat() if grant.revoked_at else None}
        ),
    }
    return _enqueue(
        session,
        operation="consent_revoke",
        entity_type="consent_grant",
        entity_reference_hash=consent_ref,
        payload=payload,
        consent_grant_id=grant.consent_grant_id,
    )


def _audit_leaf(event: AuditEvent) -> str:
    return canonical_hash(
        {
            "event": str(event.public_id),
            "action": event.action,
            "resource_type": event.resource_type,
            "resource_reference": _hash_bytes((event.resource_id or "").encode("utf-8")),
            "outcome": event.outcome,
            "created_at": event.created_at.isoformat(),
        }
    )


def merkle_root(leaves: list[str]) -> str:
    if not leaves:
        return _hash_bytes(b"")
    level = [bytes.fromhex(leaf) for leaf in leaves]
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        level = [hashlib.sha256(level[index] + level[index + 1]).digest() for index in range(0, len(level), 2)]
    return level[0].hex()


def create_audit_anchor(
    session: Session, *, period_start: datetime, period_end: datetime, config: dict
) -> BlockchainAuditAnchor:
    if period_end <= period_start:
        raise ValueError("Audit anchor period must have a positive duration")
    period_ref = opaque_reference(config, "audit-period", f"{period_start.isoformat()}:{period_end.isoformat()}")
    existing = session.scalar(
        select(BlockchainAuditAnchor).where(BlockchainAuditAnchor.period_reference_hash == period_ref)
    )
    if existing:
        return existing
    events = list(
        session.scalars(
            select(AuditEvent)
            .where(AuditEvent.created_at >= period_start, AuditEvent.created_at < period_end)
            .order_by(AuditEvent.audit_event_id)
        )
    )
    root = merkle_root([_audit_leaf(event) for event in events])
    transaction = _enqueue(
        session,
        operation="audit_anchor",
        entity_type="audit_period",
        entity_reference_hash=period_ref,
        payload={"period_ref": period_ref, "merkle_root": root},
    )
    anchor = BlockchainAuditAnchor(
        period_start=period_start,
        period_end=period_end,
        period_reference_hash=period_ref,
        merkle_root=root,
        event_count=len(events),
        blockchain_transaction_id=transaction.blockchain_transaction_id,
    )
    session.add(anchor)
    session.flush()
    return anchor


def create_due_audit_anchor(
    session: Session, config: dict, *, now: datetime | None = None
) -> BlockchainAuditAnchor:
    """Create the immediately preceding fixed UTC audit period idempotently."""
    current = now or _utcnow()
    minutes = max(1, int(config.get("BLOCKCHAIN_AUDIT_PERIOD_MINUTES", 60)))
    period_seconds = minutes * 60
    boundary_epoch = int(current.timestamp()) // period_seconds * period_seconds
    period_end = datetime.fromtimestamp(boundary_epoch, tz=timezone.utc)
    period_start = period_end - timedelta(seconds=period_seconds)
    return create_audit_anchor(
        session, period_start=period_start, period_end=period_end, config=config
    )


def process_pending_transactions(
    session: Session,
    config: dict,
    *,
    limit: int = 50,
    adapter=None,
) -> dict:
    now = _utcnow()
    transactions = list(
        session.scalars(
            select(BlockchainTransaction)
            .where(
                BlockchainTransaction.state.in_(("pending", "retry", "submitted")),
                or_(BlockchainTransaction.next_retry_at.is_(None), BlockchainTransaction.next_retry_at <= now),
            )
            .order_by(BlockchainTransaction.created_at)
            .limit(limit)
        )
    )
    if not transactions:
        return {"processed": 0, "confirmed": 0, "retry": 0, "failed": 0}
    maximum = int(config.get("BLOCKCHAIN_RETRY_MAX_ATTEMPTS", 8))
    base_seconds = int(config.get("BLOCKCHAIN_RETRY_BASE_SECONDS", 30))
    try:
        chain = adapter or Web3IntegrityAdapter(config)
    except Exception as error:
        # Blockchain downtime never changes primary healthcare records.
        failed = 0
        retry = 0
        for transaction in transactions:
            transaction.attempts += 1
            transaction.last_error = str(error)[:2000]
            if transaction.attempts >= maximum:
                transaction.state = "failed"
                transaction.next_retry_at = None
                failed += 1
            else:
                transaction.state = "retry"
                transaction.next_retry_at = now + timedelta(
                    seconds=base_seconds * (2 ** max(0, transaction.attempts - 1))
                )
                retry += 1
            transaction.updated_at = now
        session.commit()
        return {
            "processed": len(transactions),
            "confirmed": 0,
            "retry": retry,
            "failed": failed,
            "error": str(error),
        }

    counts = {"processed": 0, "confirmed": 0, "retry": 0, "failed": 0}
    for transaction in transactions:
        counts["processed"] += 1
        try:
            transaction.attempts += 1
            if transaction.transaction_hash:
                receipt = chain.wait_for_receipt(transaction.transaction_hash)
            else:
                submission = chain.submit(transaction.operation, transaction.proof_payload)
                transaction.state = "submitted"
                transaction.transaction_hash = submission.transaction_hash
                transaction.chain_id = submission.chain_id
                transaction.contract_address = submission.contract_address
                transaction.submitted_at = _utcnow()
                transaction.last_error = None
                session.commit()  # persist submitted state before waiting for confirmations
                receipt = chain.wait_for_receipt(submission.transaction_hash)
            if not receipt.success:
                raise BlockchainUnavailable("Blockchain transaction receipt reported failure")
            transaction.state = "confirmed"
            transaction.block_number = receipt.block_number
            transaction.confirmed_at = _utcnow()
            transaction.next_retry_at = None
            counts["confirmed"] += 1
        except Exception as error:
            transaction.last_error = str(error)[:2000]
            if transaction.attempts >= maximum:
                transaction.state = "failed"
                transaction.next_retry_at = None
                counts["failed"] += 1
            else:
                transaction.state = "retry"
                transaction.next_retry_at = _utcnow() + timedelta(
                    seconds=base_seconds * (2 ** max(0, transaction.attempts - 1))
                )
                counts["retry"] += 1
        transaction.updated_at = _utcnow()
        session.commit()
    return counts


def transaction_payload(transaction: BlockchainTransaction | None) -> dict:
    if transaction is None:
        return {"state": "not_registered"}
    return {
        "id": str(transaction.public_id),
        "operation": transaction.operation,
        "state": transaction.state,
        "chain_id": transaction.chain_id,
        "contract_address": transaction.contract_address,
        "transaction_hash": transaction.transaction_hash,
        "block_number": transaction.block_number,
        "attempts": transaction.attempts,
        "confirmed_at": transaction.confirmed_at.isoformat() if transaction.confirmed_at else None,
        "last_error": transaction.last_error if transaction.state == "failed" else None,
    }


def document_integrity_status(
    session: Session,
    *,
    document: MedicalDocument,
    local_verification: dict,
    config: dict,
    adapter=None,
) -> dict:
    version = session.scalar(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == document.document_id)
        .order_by(DocumentVersion.version_number.desc())
        .limit(1)
    )
    transaction = session.scalar(
        select(BlockchainTransaction).where(
            BlockchainTransaction.document_version_id == version.document_version_id,
            BlockchainTransaction.operation == "record_register",
        )
    )
    chain_verified = None
    if transaction and transaction.state == "confirmed" and local_verification["verified"]:
        try:
            chain = adapter or Web3IntegrityAdapter(config)
            chain_verified = chain.verify_record(
                transaction.entity_reference_hash, local_verification["computed_sha256"]
            )
        except Exception:
            chain_verified = None
    return {
        "document_id": str(document.public_id),
        "version": version.version_number,
        "local_hash_verified": local_verification["verified"],
        "chain_hash_verified": chain_verified,
        "tamper_status": (
            "modified"
            if not local_verification["verified"] or chain_verified is False
            else "verified"
            if chain_verified is True
            else "pending"
        ),
        "proof": transaction_payload(transaction),
    }


def consent_proof_status(session: Session, grant: ConsentGrant) -> dict:
    transactions = list(
        session.scalars(
            select(BlockchainTransaction)
            .where(BlockchainTransaction.consent_grant_id == grant.consent_grant_id)
            .order_by(BlockchainTransaction.created_at)
        )
    )
    by_operation = {item.operation: transaction_payload(item) for item in transactions}
    return {
        "consent_id": str(grant.public_id),
        "consent_status": grant.status,
        "grant_proof": by_operation.get("consent_grant", {"state": "not_registered"}),
        "revocation_proof": by_operation.get("consent_revoke", {"state": "not_registered"}),
    }
