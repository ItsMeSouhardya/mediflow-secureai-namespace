from __future__ import annotations

import hashlib

import pytest
from sqlalchemy import select

from blockchain_service import enqueue_document_version
from document_storage import get_storage_backend
from errors import ApiProblem
from extensions import db
from models import (
    DocumentAnalysisResult,
    DocumentVersion,
    BlockchainTransaction,
    MedicalDocument,
    PatientProfile,
    User,
)


@pytest.mark.parametrize("delete_method", ["delete", "post_action"])
def test_patient_delete_removes_database_rows_and_encrypted_file(
    app, client, auth_headers, delete_method
):
    plaintext = b"%PDF-1.4\nprototype deletion test\n%%EOF"

    with app.app_context():
        patient = db.session.scalar(select(PatientProfile))
        uploader = db.session.scalar(
            select(User).where(User.email == "patient@mediflow.test")
        )
        storage = get_storage_backend(app.config)
        stored = storage.store(plaintext)

        document = MedicalDocument(
            patient_profile_id=patient.patient_profile_id,
            uploaded_by_user_id=uploader.user_id,
            document_type="lab_report",
            title="Deletion test report",
            status="ready",
        )
        db.session.add(document)
        db.session.flush()

        version = DocumentVersion(
            document_id=document.document_id,
            version_number=1,
            original_filename="deletion-test.pdf",
            file_size_bytes=len(plaintext),
            mime_type="application/pdf",
            sha256_hash=hashlib.sha256(plaintext).hexdigest(),
            storage_key=stored.storage_key,
            storage_backend=stored.storage_backend,
            encryption_key_id=stored.encryption_key_id,
            uploaded_by_user_id=uploader.user_id,
        )
        db.session.add(version)
        db.session.flush()

        analysis = DocumentAnalysisResult(
            document_id=document.document_id,
            document_version_id=version.document_version_id,
            analysis_type="lab_report_extraction",
            review_status="pending",
        )
        db.session.add(analysis)
        proof = enqueue_document_version(db.session, version, app.config)
        db.session.commit()

        public_id = document.public_id
        document_id = document.document_id
        version_id = version.document_version_id
        analysis_id = analysis.analysis_result_id
        proof_id = proof.blockchain_transaction_id
        storage_key = version.storage_key

    if delete_method == "post_action":
        response = client.post(
            f"/api/v1/patients/me/documents/{public_id}/delete", headers=auth_headers
        )
    else:
        response = client.delete(
            f"/api/v1/patients/me/documents/{public_id}", headers=auth_headers
        )
    assert response.status_code == 200
    assert response.get_json()["data"] == {
        "id": str(public_id),
        "deleted": True,
        "storage_cleanup": "complete",
    }

    with app.app_context():
        assert db.session.get(MedicalDocument, document_id) is None
        assert db.session.get(DocumentVersion, version_id) is None
        assert db.session.get(DocumentAnalysisResult, analysis_id) is None
        retained_proof = db.session.get(BlockchainTransaction, proof_id)
        assert retained_proof is not None
        assert retained_proof.document_version_id is None
        with pytest.raises(ApiProblem):
            get_storage_backend(app.config).retrieve(storage_key)


def test_patient_cannot_delete_unknown_document(client, auth_headers):
    import uuid

    response = client.delete(
        f"/api/v1/patients/me/documents/{uuid.uuid4()}", headers=auth_headers
    )
    assert response.status_code == 404
