"""Document pipeline HTTP endpoints — /api/v1/documents/*

Patient routes (5.13):
  POST   /api/v1/patients/me/documents              — upload a new document
  GET    /api/v1/patients/me/documents              — list own documents
  GET    /api/v1/patients/me/documents/<id>         — get document metadata
  GET    /api/v1/patients/me/documents/<id>/download — stream decrypted bytes
  GET    /api/v1/patients/me/documents/<id>/verify   — re-hash and verify integrity
  POST   /api/v1/patients/me/documents/<id>/archive  — archive a ready document
  DELETE /api/v1/patients/me/documents/<id>          — delete owned document and file
  POST   /api/v1/patients/me/documents/<id>/delete   — browser-compatible delete action

Doctor routes (5.14):
  GET    /api/v1/doctors/me/patients/<pid>/documents          — list patient docs
  GET    /api/v1/doctors/me/patients/<pid>/documents/<id>     — view doc metadata
  GET    /api/v1/doctors/me/patients/<pid>/documents/<id>/download — stream bytes
  GET    /api/v1/doctors/me/patients/<pid>/documents/<id>/verify  — verify hash
  POST   /api/v1/doctors/me/patients/<pid>/documents/<id>/verify-document — mark verified
  POST   /api/v1/doctors/me/patients/<pid>/documents/<id>/analyses/<aid>/review — review AI result
"""

from __future__ import annotations

import io
from uuid import UUID

from flask import Flask, Response, g, jsonify, request

from audit import write_audit_event
from blockchain_service import enqueue_document_version, transaction_payload
from auth_service import ROLE_DOCTOR, ROLE_PATIENT
from authorization import require_auth
from document_service import (
    archive_document,
    audit_denied_access,
    delete_document,
    download_document,
    get_document_by_public_id,
    list_patient_documents,
    purge_document_storage,
    review_analysis_result,
    upload_document,
    verify_document,
    verify_document_hash,
    view_document_as_doctor,
)
from ehr_service import (
    doctor_profile_for_user,
    ensure_patient_profile,
    patient_profile_by_public_id,
    require_doctor_patient_access,
)
from errors import ApiProblem
from extensions import db, limiter
from rate_limits import SENSITIVE_WRITE_RATE_LIMIT
from schemas import (
    AnalysisReviewRequest,
    DocumentUploadMetadata,
    DocumentVerifyRequest,
    validate_json,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _document_upload_rate_limit() -> str:
    return "10 per minute"


def _success(data: dict | list, status: int = 200):
    return jsonify({"status": "success", "data": data}), status


def _audit(action: str, resource_type: str, resource_id, details: dict | None = None) -> None:
    write_audit_event(
        db.session,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        actor_user_id=g.current_user.user_id,
        details=details or {},
    )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register_document_routes(app: Flask) -> None:

    # ======================================================================
    # Patient routes (5.13)
    # ======================================================================

    @app.post("/api/v1/patients/me/documents")
    @require_auth(ROLE_PATIENT)
    @limiter.limit(_document_upload_rate_limit)
    def patient_upload_document():
        """Multipart upload: file field 'document' + JSON metadata field 'metadata'."""
        if "document" not in request.files:
            raise ApiProblem("missing_file", "A file field named 'document' is required", 400)

        file = request.files["document"]
        if not file.filename:
            raise ApiProblem("missing_filename", "Uploaded file must have a filename", 400)

        # Metadata comes as a separate JSON form field so we can validate it
        # independently of the file bytes.
        raw_meta = request.form.get("metadata")
        if not raw_meta:
            raise ApiProblem(
                "missing_metadata",
                "A 'metadata' form field with JSON document metadata is required",
                400,
            )
        import json as _json
        try:
            meta_dict = _json.loads(raw_meta)
        except ValueError as exc:
            raise ApiProblem("invalid_json", "metadata field must be valid JSON", 400) from exc

        meta = DocumentUploadMetadata.model_validate(meta_dict)
        patient = ensure_patient_profile(db.session, g.current_user)

        try:
            doc, version = upload_document(
                db.session,
                patient=patient,
                uploader=g.current_user,
                file_stream=io.BytesIO(file.read()),
                filename=file.filename,
                document_type=meta.document_type,
                title=meta.title,
                description=meta.description,
                document_date=meta.document_date,
                encounter_id=meta.encounter_id,
                config=app.config,
            )
        except ApiProblem as error:
            if error.code == "file_quarantined":
                db.session.commit()
            raise
        proof_transaction = enqueue_document_version(db.session, version, app.config)
        db.session.commit()
        return _success(
            {
                "id": str(doc.public_id),
                "status": doc.status,
                "version": version.version_number,
                "sha256": version.sha256_hash,
                "extraction_method": version.extraction_method,
                "integrity_proof": transaction_payload(proof_transaction),
            },
            201,
        )

    @app.get("/api/v1/patients/me/documents")
    @require_auth(ROLE_PATIENT)
    def patient_list_documents():
        patient = ensure_patient_profile(db.session, g.current_user)
        status_filter = request.args.get("status")
        docs = list_patient_documents(db.session, patient, status_filter=status_filter)
        _audit("document.list_viewed", "patient_profile", patient.public_id)
        db.session.commit()
        return _success(docs)

    @app.get("/api/v1/patients/me/documents/<uuid:doc_id>")
    @require_auth(ROLE_PATIENT)
    def patient_get_document(doc_id: UUID):
        patient = ensure_patient_profile(db.session, g.current_user)
        doc = get_document_by_public_id(
            db.session, doc_id, owner_patient_profile_id=patient.patient_profile_id
        )
        _audit("document.viewed", "medical_document", doc.public_id)
        db.session.commit()
        from document_service import _document_payload, _latest_version
        version = _latest_version(db.session, doc.document_id)
        return _success(_document_payload(doc, version))

    @app.get("/api/v1/patients/me/documents/<uuid:doc_id>/download")
    @require_auth(ROLE_PATIENT)
    def patient_download_document(doc_id: UUID):
        patient = ensure_patient_profile(db.session, g.current_user)
        doc = get_document_by_public_id(
            db.session, doc_id, owner_patient_profile_id=patient.patient_profile_id
        )
        plaintext, version = download_document(
            db.session, doc, g.current_user.user_id, app.config
        )
        db.session.commit()
        return Response(
            plaintext,
            status=200,
            mimetype=version.mime_type,
            headers={
                "Content-Disposition": f'attachment; filename="{version.original_filename}"',
                "Content-Length": str(len(plaintext)),
                # Prevent browsers from sniffing the MIME type.
                "X-Content-Type-Options": "nosniff",
                # Do not cache medical document downloads.
                "Cache-Control": "no-store, no-cache, must-revalidate, private",
            },
        )

    @app.get("/api/v1/patients/me/documents/<uuid:doc_id>/verify")
    @require_auth(ROLE_PATIENT)
    def patient_verify_document(doc_id: UUID):
        patient = ensure_patient_profile(db.session, g.current_user)
        doc = get_document_by_public_id(
            db.session, doc_id, owner_patient_profile_id=patient.patient_profile_id
        )
        result = verify_document_hash(db.session, doc, g.current_user.user_id, app.config)
        db.session.commit()
        return _success(result)

    @app.post("/api/v1/patients/me/documents/<uuid:doc_id>/archive")
    @require_auth(ROLE_PATIENT)
    @limiter.limit(SENSITIVE_WRITE_RATE_LIMIT)
    def patient_archive_document(doc_id: UUID):
        patient = ensure_patient_profile(db.session, g.current_user)
        doc = get_document_by_public_id(
            db.session, doc_id, owner_patient_profile_id=patient.patient_profile_id
        )
        archive_document(db.session, doc, g.current_user.user_id)
        db.session.commit()
        return _success({"id": str(doc.public_id), "status": doc.status})

    @app.post("/api/v1/patients/me/documents/<uuid:doc_id>/delete")
    @app.delete("/api/v1/patients/me/documents/<uuid:doc_id>")
    @require_auth(ROLE_PATIENT)
    @limiter.limit(SENSITIVE_WRITE_RATE_LIMIT)
    def patient_delete_document(doc_id: UUID):
        """Permanently delete an owned document, its rows, and encrypted bytes."""
        patient = ensure_patient_profile(db.session, g.current_user)
        doc = get_document_by_public_id(
            db.session, doc_id, owner_patient_profile_id=patient.patient_profile_id
        )
        deleted_id = str(doc.public_id)
        storage_keys = delete_document(db.session, doc, g.current_user.user_id)
        db.session.commit()

        failed_keys = purge_document_storage(storage_keys, app.config)
        return _success({
            "id": deleted_id,
            "deleted": True,
            "storage_cleanup": "complete" if not failed_keys else "pending",
        })

    # ======================================================================
    # Doctor routes (5.14)
    # ======================================================================

    @app.get("/api/v1/doctors/me/patients/<uuid:patient_id>/documents")
    @require_auth(ROLE_DOCTOR)
    def doctor_list_patient_documents(patient_id: UUID):
        doctor = doctor_profile_for_user(db.session, g.current_user.user_id)
        patient = patient_profile_by_public_id(db.session, patient_id)
        require_doctor_patient_access(db.session, doctor, patient)
        status_filter = request.args.get("status")
        docs = list_patient_documents(db.session, patient, status_filter=status_filter)
        _audit(
            "document.doctor_list_viewed",
            "patient_profile",
            patient.public_id,
            {"doctor_profile_id": str(doctor.public_id)},
        )
        db.session.commit()
        return _success(docs)

    @app.get("/api/v1/doctors/me/patients/<uuid:patient_id>/documents/<uuid:doc_id>")
    @require_auth(ROLE_DOCTOR)
    def doctor_get_patient_document(patient_id: UUID, doc_id: UUID):
        doctor = doctor_profile_for_user(db.session, g.current_user.user_id)
        patient = patient_profile_by_public_id(db.session, patient_id)
        require_doctor_patient_access(db.session, doctor, patient)
        doc = get_document_by_public_id(
            db.session, doc_id, owner_patient_profile_id=patient.patient_profile_id
        )
        payload = view_document_as_doctor(db.session, doc, g.current_user.user_id)
        db.session.commit()
        return _success(payload)

    @app.get("/api/v1/doctors/me/patients/<uuid:patient_id>/documents/<uuid:doc_id>/download")
    @require_auth(ROLE_DOCTOR)
    def doctor_download_patient_document(patient_id: UUID, doc_id: UUID):
        doctor = doctor_profile_for_user(db.session, g.current_user.user_id)
        patient = patient_profile_by_public_id(db.session, patient_id)
        require_doctor_patient_access(db.session, doctor, patient)
        doc = get_document_by_public_id(
            db.session, doc_id, owner_patient_profile_id=patient.patient_profile_id
        )
        plaintext, version = download_document(
            db.session, doc, g.current_user.user_id, app.config
        )
        db.session.commit()
        return Response(
            plaintext,
            status=200,
            mimetype=version.mime_type,
            headers={
                "Content-Disposition": f'attachment; filename="{version.original_filename}"',
                "Content-Length": str(len(plaintext)),
                "X-Content-Type-Options": "nosniff",
                "Cache-Control": "no-store, no-cache, must-revalidate, private",
            },
        )

    @app.get("/api/v1/doctors/me/patients/<uuid:patient_id>/documents/<uuid:doc_id>/verify")
    @require_auth(ROLE_DOCTOR)
    def doctor_verify_patient_document(patient_id: UUID, doc_id: UUID):
        doctor = doctor_profile_for_user(db.session, g.current_user.user_id)
        patient = patient_profile_by_public_id(db.session, patient_id)
        require_doctor_patient_access(db.session, doctor, patient)
        doc = get_document_by_public_id(
            db.session, doc_id, owner_patient_profile_id=patient.patient_profile_id
        )
        result = verify_document_hash(db.session, doc, g.current_user.user_id, app.config)
        db.session.commit()
        return _success(result)

    @app.post("/api/v1/doctors/me/patients/<uuid:patient_id>/documents/<uuid:doc_id>/verify-document")
    @require_auth(ROLE_DOCTOR)
    @limiter.limit(SENSITIVE_WRITE_RATE_LIMIT)
    def doctor_verify_document_record(patient_id: UUID, doc_id: UUID):
        """Mark a document as clinically reviewed/verified by this doctor."""
        body = validate_json(DocumentVerifyRequest)
        doctor = doctor_profile_for_user(db.session, g.current_user.user_id)
        patient = patient_profile_by_public_id(db.session, patient_id)
        require_doctor_patient_access(db.session, doctor, patient)
        doc = get_document_by_public_id(
            db.session, doc_id, owner_patient_profile_id=patient.patient_profile_id
        )
        verify_document(db.session, doc, doctor=doctor, notes=body.notes)
        db.session.commit()
        return _success(
            {
                "id": str(doc.public_id),
                "verified_at": doc.verified_at.isoformat(),
                "verification_notes": doc.verification_notes,
            }
        )

    @app.post(
        "/api/v1/doctors/me/patients/<uuid:patient_id>/documents/<uuid:doc_id>"
        "/analyses/<uuid:analysis_id>/review"
    )
    @require_auth(ROLE_DOCTOR)
    @limiter.limit(SENSITIVE_WRITE_RATE_LIMIT)
    def doctor_review_analysis(patient_id: UUID, doc_id: UUID, analysis_id: UUID):
        """Accept, reject, or mark-corrected an AI analysis result."""
        body = validate_json(AnalysisReviewRequest)
        doctor = doctor_profile_for_user(db.session, g.current_user.user_id)
        patient = patient_profile_by_public_id(db.session, patient_id)
        require_doctor_patient_access(db.session, doctor, patient)
        doc = get_document_by_public_id(
            db.session, doc_id, owner_patient_profile_id=patient.patient_profile_id
        )
        result = review_analysis_result(
            db.session,
            doc,
            analysis_id,
            doctor=doctor,
            new_status=body.review_status,
            reviewer_notes=body.reviewer_notes,
        )
        db.session.commit()
        return _success(
            {
                "id": str(result.public_id),
                "review_status": result.review_status,
                "reviewed_at": result.reviewed_at.isoformat(),
            }
        )
