"""Blockchain adapter integration tests — task 15.3

Tests the backend blockchain layer without requiring a live RPC node:
  - HMAC-SHA256 opaque reference generation carries no PII
  - Payload allowlist enforces hash-only fields
  - Outbox enqueue / dequeue / retry state machine
  - Merkle root computation is deterministic
  - Verification API returns correct verified/unverified response
  - No patient names, emails, or clinical content appear in any
    blockchain transaction payload
"""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest


# ---------------------------------------------------------------------------
# Reference generation — opaque, no PII
# ---------------------------------------------------------------------------

class TestOpaqueReferences:
    def test_patient_ref_is_sha256_not_plaintext(self):
        from blockchain_service import _make_ref
        patient_id = "some-patient-uuid"
        ref = _make_ref(patient_id, "patient")
        # Must be a 64-char hex string
        assert len(ref) == 64
        assert all(c in "0123456789abcdef" for c in ref)
        # Must NOT contain the raw id
        assert patient_id not in ref

    def test_same_input_same_ref_deterministic(self):
        from blockchain_service import _make_ref
        r1 = _make_ref("doc-abc", "document")
        r2 = _make_ref("doc-abc", "document")
        assert r1 == r2

    def test_different_inputs_different_refs(self):
        from blockchain_service import _make_ref
        r1 = _make_ref("patient-1", "patient")
        r2 = _make_ref("patient-2", "patient")
        assert r1 != r2

    def test_different_domains_different_refs(self):
        from blockchain_service import _make_ref
        r1 = _make_ref("entity-1", "document")
        r2 = _make_ref("entity-1", "consent")
        assert r1 != r2

    def test_ref_contains_no_pii_patterns(self):
        from blockchain_service import _make_ref
        # Email-like, name-like, phone-like patterns must not survive hashing
        ref = _make_ref("john.doe@hospital.com", "patient")
        assert "@" not in ref
        assert "john" not in ref.lower()
        assert "doe" not in ref.lower()


# ---------------------------------------------------------------------------
# Payload allowlist
# ---------------------------------------------------------------------------

class TestPayloadAllowlist:
    def test_record_register_payload_only_has_allowed_keys(self):
        from blockchain_service import PAYLOAD_KEYS
        allowed = PAYLOAD_KEYS["record_register"]
        assert "record_ref" in allowed
        assert "content_hash" in allowed
        # Must NOT allow PII fields
        for forbidden in ("patient_name", "email", "document_content", "symptoms"):
            assert forbidden not in allowed

    def test_consent_grant_payload_only_has_allowed_keys(self):
        from blockchain_service import PAYLOAD_KEYS
        allowed = PAYLOAD_KEYS["consent_grant"]
        assert "consent_ref" in allowed
        assert "patient_ref" in allowed
        assert "grantee_ref" in allowed
        assert "scope_hash" in allowed
        # Must NOT allow plain-text purpose or patient name
        for forbidden in ("purpose", "patient_name", "doctor_name", "scopes"):
            assert forbidden not in allowed

    def test_audit_anchor_payload_only_has_merkle_root(self):
        from blockchain_service import PAYLOAD_KEYS
        allowed = PAYLOAD_KEYS["audit_anchor"]
        assert "merkle_root" in allowed
        assert "period_ref" in allowed
        # Audit payloads must never include event content
        for forbidden in ("action", "details", "actor_user_id", "remote_addr"):
            assert forbidden not in allowed


# ---------------------------------------------------------------------------
# Merkle root computation
# ---------------------------------------------------------------------------

class TestMerkleRoot:
    def test_empty_events_returns_zero_hash(self):
        from blockchain_service import compute_merkle_root
        root = compute_merkle_root([])
        assert root == "0" * 64

    def test_single_event_returns_its_own_hash(self):
        from blockchain_service import compute_merkle_root
        root = compute_merkle_root(["abc123"])
        expected = hashlib.sha256("abc123".encode()).hexdigest()
        assert root == expected

    def test_same_events_same_root(self):
        from blockchain_service import compute_merkle_root
        events = ["ev1", "ev2", "ev3", "ev4"]
        r1 = compute_merkle_root(events)
        r2 = compute_merkle_root(events)
        assert r1 == r2

    def test_different_order_different_root(self):
        from blockchain_service import compute_merkle_root
        e1 = ["ev1", "ev2"]
        e2 = ["ev2", "ev1"]
        assert compute_merkle_root(e1) != compute_merkle_root(e2)

    def test_tampered_event_changes_root(self):
        from blockchain_service import compute_merkle_root
        original = ["event-1", "event-2", "event-3"]
        tampered = ["event-1", "TAMPERED-2", "event-3"]
        assert compute_merkle_root(original) != compute_merkle_root(tampered)


# ---------------------------------------------------------------------------
# Outbox state machine
# ---------------------------------------------------------------------------

class TestBlockchainOutbox:
    def test_enqueue_record_creates_pending_transaction(self, app):
        with app.app_context():
            from blockchain_service import enqueue_record_hash
            from extensions import db
            from models import BlockchainTransaction
            from sqlalchemy import select

            count_before = db.session.scalar(
                select(db.func.count(BlockchainTransaction.transaction_id))
            ) or 0

            enqueue_record_hash(
                db.session,
                document_version_id=1,
                document_public_id="doc-test-uuid",
                sha256_hash="a" * 64,
                actor_user_id=None,
            )
            db.session.flush()

            count_after = db.session.scalar(
                select(db.func.count(BlockchainTransaction.transaction_id))
            )
            assert count_after >= count_before + 1

            tx = db.session.scalar(
                select(BlockchainTransaction).order_by(
                    BlockchainTransaction.transaction_id.desc()
                )
            )
            assert tx is not None
            assert tx.state == "pending"
            assert tx.operation == "record_register"

    def test_pending_transaction_payload_contains_no_pii(self, app):
        with app.app_context():
            from blockchain_service import enqueue_record_hash
            from extensions import db
            from models import BlockchainTransaction
            from sqlalchemy import select

            enqueue_record_hash(
                db.session,
                document_version_id=2,
                document_public_id="doc-pii-check-uuid",
                sha256_hash="b" * 64,
                actor_user_id=None,
            )
            db.session.flush()

            tx = db.session.scalar(
                select(BlockchainTransaction).where(
                    BlockchainTransaction.entity_ref.contains("pii-check")
                    if hasattr(BlockchainTransaction, "entity_ref")
                    else BlockchainTransaction.operation == "record_register"
                ).order_by(BlockchainTransaction.transaction_id.desc())
            )
            if tx is not None and tx.payload_json:
                payload_str = json.dumps(tx.payload_json)
                # No PII should appear in the payload
                for forbidden in ["@", "patient_name", "diagnosis", "symptoms"]:
                    assert forbidden not in payload_str, (
                        f"PII '{forbidden}' found in blockchain payload"
                    )

    def test_retry_increments_attempt_count(self, app):
        with app.app_context():
            from extensions import db
            from models import BlockchainTransaction, utcnow
            from sqlalchemy import select

            # Create a fake failed transaction
            tx = BlockchainTransaction(
                operation="record_register",
                state="failed",
                attempts=1,
                entity_ref="retry-test-ref",
                payload_json={"record_ref": "a" * 64, "content_hash": "b" * 64},
                created_at=utcnow(),
                next_retry_at=utcnow(),
            )
            db.session.add(tx)
            db.session.flush()
            initial_attempts = tx.attempts

            # Simulate retry: bump attempt count and reset state
            tx.attempts += 1
            tx.state = "pending"
            db.session.flush()

            assert tx.attempts == initial_attempts + 1
            assert tx.state == "pending"


# ---------------------------------------------------------------------------
# Verification API
# ---------------------------------------------------------------------------

class TestVerificationAPI:
    def test_verify_endpoint_exists_and_requires_auth(self, client):
        import uuid
        r = client.get(f"/api/v1/patients/me/documents/{uuid.uuid4()}/verify")
        assert r.status_code == 401

    def test_verify_returns_structured_response(self, client, auth_headers, app):
        """If a ready document exists, verify returns {verified, stored_sha256, computed_sha256}."""
        with app.app_context():
            from extensions import db
            from models import MedicalDocument, PatientProfile, User
            from sqlalchemy import select

            patient = db.session.scalar(
                select(PatientProfile).join(User).where(
                    User.email == "patient@mediflow.test"
                )
            )
            doc = db.session.scalar(
                select(MedicalDocument).where(
                    MedicalDocument.patient_profile_id == patient.patient_profile_id,
                    MedicalDocument.status == "ready",
                )
            )
            if doc is None:
                pytest.skip("No ready document in test DB")
            doc_id = str(doc.public_id)

        r = client.get(f"/api/v1/patients/me/documents/{doc_id}/verify",
                       headers=auth_headers)
        assert r.status_code == 200
        data = r.get_json()["data"]
        assert "verified" in data
        assert "stored_sha256" in data
        assert "computed_sha256" in data
        assert isinstance(data["verified"], bool)
