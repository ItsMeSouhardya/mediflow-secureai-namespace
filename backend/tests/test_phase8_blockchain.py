from __future__ import annotations

from datetime import datetime, timedelta, timezone

from blockchain_adapter import ChainReceipt, ChainSubmission
from blockchain_service import (
    consent_proof_status,
    create_audit_anchor,
    document_integrity_status,
    enqueue_consent_grant,
    enqueue_consent_revocation,
    enqueue_document_version,
    merkle_root,
    process_pending_transactions,
)
from extensions import db
from models import (
    BlockchainTransaction,
    AuditEvent,
    ConsentGrant,
    Doctor,
    DoctorProfile,
    DocumentVersion,
    MedicalDocument,
    PatientProfile,
    User,
)


class ConfirmingAdapter:
    def __init__(self, verifies=True):
        self.verifies = verifies
        self.submissions = []

    def submit(self, operation, payload):
        self.submissions.append((operation, payload))
        return ChainSubmission("0x" + f"{len(self.submissions):064x}", 31337, "0x" + "1" * 40)

    def wait_for_receipt(self, transaction_hash):
        return ChainReceipt(transaction_hash, 42, True)

    def verify_record(self, record_ref, content_hash):
        return self.verifies


class FailingAdapter:
    def submit(self, operation, payload):
        raise ConnectionError("development chain offline")


def create_document_version(session):
    patient = session.scalar(db.select(PatientProfile).join(User).where(User.email == "patient@mediflow.test"))
    user = session.get(User, patient.user_id)
    document = MedicalDocument(
        patient_profile_id=patient.patient_profile_id,
        uploaded_by_user_id=user.user_id,
        document_type="lab_report",
        title="Sensitive title that must not reach chain",
        status="ready",
    )
    session.add(document)
    session.flush()
    version = DocumentVersion(
        document_id=document.document_id,
        version_number=1,
        original_filename="private-patient-name.pdf",
        file_size_bytes=100,
        mime_type="application/pdf",
        sha256_hash="a" * 64,
        storage_key="opaque-storage-key",
        storage_backend="local",
        encryption_key_id="kek-v1",
        uploaded_by_user_id=user.user_id,
    )
    session.add(version)
    session.flush()
    return document, version, patient


def create_consent(session, patient):
    provider = session.get(Doctor, 1)
    doctor_user = User(
        name="Blockchain Doctor",
        email="blockchain.doctor@example.test",
        password_hash="not-used-in-service-test",
        is_active=True,
    )
    session.add(doctor_user)
    session.flush()
    doctor = DoctorProfile(
        user_id=doctor_user.user_id,
        hospital_id=1,
        doctor_id=provider.doctor_id,
        status="active",
    )
    session.add(doctor)
    session.flush()
    now = datetime.now(timezone.utc)
    grant = ConsentGrant(
        patient_profile_id=patient.patient_profile_id,
        requesting_doctor_profile_id=doctor.doctor_profile_id,
        requesting_hospital_id=1,
        scopes=["reports", "summary"],
        purpose="Treatment review kept only in PostgreSQL",
        operation="treatment",
        status="granted",
        access_start=now,
        access_expires_at=now + timedelta(days=7),
    )
    session.add(grant)
    session.flush()
    return grant


def test_document_proof_is_hash_only_and_confirms_without_exposing_phi(app):
    with app.app_context():
        document, version, _ = create_document_version(db.session)
        transaction = enqueue_document_version(db.session, version, app.config)
        db.session.commit()

        serialized = str(transaction.proof_payload).lower()
        assert set(transaction.proof_payload) == {"record_ref", "content_hash"}
        assert all(len(value) == 64 for value in transaction.proof_payload.values())
        for forbidden in ("sensitive", "patient", "private", ".pdf", "ramesh"):
            assert forbidden not in serialized

        adapter = ConfirmingAdapter()
        result = process_pending_transactions(db.session, app.config, adapter=adapter)
        assert result["confirmed"] == 1
        assert transaction.state == "confirmed"
        assert transaction.block_number == 42

        valid = document_integrity_status(
            db.session,
            document=document,
            local_verification={"verified": True, "computed_sha256": "a" * 64},
            config=app.config,
            adapter=adapter,
        )
        assert valid["tamper_status"] == "verified"
        modified = document_integrity_status(
            db.session,
            document=document,
            local_verification={"verified": False, "computed_sha256": "b" * 64},
            config=app.config,
            adapter=adapter,
        )
        assert modified["tamper_status"] == "modified"


def test_chain_downtime_leaves_healthcare_data_available_and_retriable(app):
    with app.app_context():
        document, version, _ = create_document_version(db.session)
        transaction = enqueue_document_version(db.session, version, app.config)
        db.session.commit()
        result = process_pending_transactions(db.session, app.config, adapter=FailingAdapter())
        assert result["retry"] == 1
        assert transaction.state == "retry"
        assert transaction.attempts == 1
        assert "offline" in transaction.last_error
        assert db.session.get(MedicalDocument, document.document_id).status == "ready"


def test_consent_grant_and_revocation_proofs_have_visible_states(app):
    with app.app_context():
        _, _, patient = create_document_version(db.session)
        grant = create_consent(db.session, patient)
        grant_tx = enqueue_consent_grant(db.session, grant, app.config)
        grant.status = "revoked"
        grant.revoked_at = datetime.now(timezone.utc)
        revoke_tx = enqueue_consent_revocation(db.session, grant, app.config)
        db.session.commit()

        payload_text = str({**grant_tx.proof_payload, **revoke_tx.proof_payload}).lower()
        assert "treatment" not in payload_text
        assert "reports" not in payload_text
        assert all(len(value) == 64 for value in grant_tx.proof_payload.values())

        adapter = ConfirmingAdapter()
        result = process_pending_transactions(db.session, app.config, adapter=adapter)
        assert result["confirmed"] == 2
        status = consent_proof_status(db.session, grant)
        assert status["grant_proof"]["state"] == "confirmed"
        assert status["revocation_proof"]["state"] == "confirmed"


def test_periodic_audit_merkle_anchor_is_deterministic(app):
    assert merkle_root(["a" * 64, "b" * 64]) == merkle_root(["a" * 64, "b" * 64])
    assert merkle_root(["a" * 64, "b" * 64]) != merkle_root(["b" * 64, "a" * 64])
    with app.app_context():
        db.session.add(
            AuditEvent(
                action="test.audit_anchor_source",
                resource_type="test_resource",
                resource_id="internal-reference",
                outcome="success",
                details={},
            )
        )
        db.session.commit()
        end = datetime.now(timezone.utc) + timedelta(seconds=1)
        start = end - timedelta(days=1)
        anchor = create_audit_anchor(db.session, period_start=start, period_end=end, config=app.config)
        db.session.commit()
        assert len(anchor.merkle_root) == 64
        assert anchor.event_count > 0
        transaction = db.session.get(BlockchainTransaction, anchor.blockchain_transaction_id)
        assert transaction.operation == "audit_anchor"
        assert set(transaction.proof_payload) == {"period_ref", "merkle_root"}
