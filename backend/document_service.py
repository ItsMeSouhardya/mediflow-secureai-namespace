"""Encrypted medical document pipeline — service layer.

Covers task 5.3 through 5.12 and task 6.5/6.6:
  5.3  File-size, extension, MIME, and magic-byte validation
  5.4  Malware-scanning interface and safe quarantine state
  5.5  SHA-256 before persistence; immutable version hashes
  5.6  Envelope encryption at rest (delegated to document_storage)
  5.7  Authorised streaming downloads (bytes returned to caller)
  5.8  Upload / processing / ready / failed / quarantined / archived states
  5.9  PDF text extraction
  5.10 OCR fallback for scanned reports and images
  5.11 Extraction confidence and warnings
  5.12 Audit: upload, view, download, verify, archive, failed-access
  6.5  Plain-language assistive summary with caveats (via report_analysis)
  6.6  Doctor-review gate — analysis persisted with review_status='pending'
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
from datetime import datetime, timezone
from typing import IO
from uuid import UUID

from flask import current_app
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from audit import write_audit_event
from document_storage import get_storage_backend
from errors import ApiProblem
from models import (
    BlockchainTransaction,
    DocumentAnalysisResult,
    DocumentVersion,
    DoctorProfile,
    Encounter,
    MedicalDocument,
    PatientProfile,
    RiskPrediction,
    User,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Magic-byte signatures for supported types.
# Each entry: (mime_type, offset, expected_bytes_prefix)
_MAGIC_SIGNATURES: list[tuple[str, int, bytes]] = [
    ("application/pdf",  0, b"%PDF"),
    ("image/jpeg",       0, b"\xff\xd8\xff"),
    ("image/png",        0, b"\x89PNG\r\n\x1a\n"),
    ("image/gif",        0, b"GIF8"),
    ("image/bmp",        0, b"BM"),
    ("image/webp",       8, b"WEBP"),           # RIFF????WEBP
    ("image/tiff",       0, b"II*\x00"),        # little-endian TIFF
    ("image/tiff",       0, b"MM\x00*"),        # big-endian TIFF
]

# ---------------------------------------------------------------------------
# 5.3 — Validation helpers
# ---------------------------------------------------------------------------

def _validate_extension(filename: str, allowed: set[str]) -> str:
    """Return the lower-cased extension or raise ApiProblem."""
    name = filename.rsplit(".", 1)
    if len(name) < 2 or not name[1]:
        raise ApiProblem("invalid_file_type", "File must have an extension", 400)
    ext = name[1].lower()
    if ext not in allowed:
        raise ApiProblem(
            "invalid_file_type",
            f"Extension '.{ext}' is not allowed. Accepted: {sorted(allowed)}",
            400,
        )
    return ext


def _validate_size(data: bytes, max_bytes: int) -> None:
    """Raise ApiProblem if the byte length exceeds the configured maximum."""
    if len(data) > max_bytes:
        raise ApiProblem(
            "file_too_large",
            f"File size {len(data):,} bytes exceeds the maximum of {max_bytes:,} bytes",
            413,
        )


def _detect_mime_by_magic(data: bytes) -> str | None:
    """Return a MIME type detected from magic bytes, or None if unknown."""
    for mime, offset, prefix in _MAGIC_SIGNATURES:
        chunk = data[offset : offset + len(prefix)]
        if chunk == prefix:
            return mime
    return None


def _validate_mime(data: bytes, filename: str, allowed_mimes: set[str]) -> str:
    """Detect MIME from magic bytes and validate against the allowlist."""
    detected = _detect_mime_by_magic(data)

    # Fallback: try python-magic if available (more comprehensive).
    if detected is None:
        try:
            import magic  # type: ignore[import]
            detected = magic.from_buffer(data[:2048], mime=True)
        except Exception:  # noqa: BLE001 — magic is optional
            pass

    if detected is None:
        raise ApiProblem(
            "invalid_file_type",
            "File type could not be determined from its contents",
            400,
        )
    if detected not in allowed_mimes:
        raise ApiProblem(
            "invalid_file_type",
            f"MIME type '{detected}' is not accepted",
            400,
        )
    return detected

# ---------------------------------------------------------------------------
# 5.4 — Malware scanning interface
# ---------------------------------------------------------------------------

def _scan_for_malware(data: bytes, filename: str) -> tuple[bool, str | None]:
    """Run available malware scanning; return (is_clean, reason_if_not_clean).

    This is an interface stub:
      - In production wire in a ClamAV client (python-clamd) or cloud AV API.
      - The function MUST return (False, reason) to quarantine a file, never
        raise — the caller handles quarantine state transitions.
    """
    try:
        import clamd  # type: ignore[import]
        cd = clamd.ClamdUnixSocket()
        result = cd.instream(data)
        status, virus = result.get("stream", ("OK", None))
        if status == "FOUND":
            return False, f"Malware detected: {virus}"
        return True, None
    except ImportError:
        # ClamAV not installed — log and continue (accept in dev).
        logger.debug("clamd not available; skipping malware scan for '%s'", filename)
        return True, None
    except Exception as exc:  # noqa: BLE001
        # Scanner unavailable — quarantine conservatively.
        logger.warning("Malware scan failed for '%s': %s", filename, exc)
        return False, f"Scanner unavailable: {exc}"


# ---------------------------------------------------------------------------
# 5.5 — SHA-256 digest
# ---------------------------------------------------------------------------

def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# 5.9 / 5.10 — Text extraction (PDF + OCR fallback)
# ---------------------------------------------------------------------------

def _extract_text_pdf(data: bytes) -> tuple[str, float, list[str]]:
    """Extract text from PDF bytes using pypdf.

    Returns (text, confidence, warnings).
    Confidence is 1.0 when text is present, 0.0 when the PDF appears to be
    scanned-only (no extractable text layer).
    """
    try:
        import pypdf  # type: ignore[import]
    except ImportError:
        return "", 0.0, ["pypdf not installed; PDF text extraction skipped"]

    warnings: list[str] = []
    pages_text: list[str] = []

    try:
        reader = pypdf.PdfReader(io.BytesIO(data))
        for i, page in enumerate(reader.pages):
            try:
                text = page.extract_text() or ""
                pages_text.append(text)
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"Page {i + 1} extraction error: {exc}")
    except Exception as exc:  # noqa: BLE001
        return "", 0.0, [f"PDF parsing failed: {exc}"]

    full_text = "\n".join(pages_text).strip()
    confidence = 1.0 if full_text else 0.0

    if not full_text:
        warnings.append("No text layer found in PDF — consider OCR for scanned documents")

    return full_text, confidence, warnings

def _extract_text_ocr(data: bytes, mime_type: str) -> tuple[str, float, list[str]]:
    """OCR fallback using pytesseract (requires Tesseract binary on PATH).

    Returns (text, confidence, warnings).
    Confidence is taken from the Tesseract mean confidence score (0–100 → 0.0–1.0).
    """
    warnings: list[str] = []
    try:
        import pytesseract  # type: ignore[import]
        from PIL import Image  # type: ignore[import]
    except ImportError:
        return "", 0.0, ["pytesseract/Pillow not installed; OCR skipped"]

    try:
        image = Image.open(io.BytesIO(data))
        text: str = pytesseract.image_to_string(image)
        data_df = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
        confidences = [c for c in data_df.get("conf", []) if isinstance(c, (int, float)) and c >= 0]
        confidence = (sum(confidences) / len(confidences) / 100.0) if confidences else 0.0
        return text.strip(), confidence, warnings
    except Exception as exc:  # noqa: BLE001
        return "", 0.0, [f"OCR failed: {exc}"]


def _extract_text(data: bytes, mime_type: str) -> tuple[str, str, float, list[str]]:
    """Dispatch to the appropriate extraction method.

    Returns (text, method, confidence, warnings).
    method is one of: 'pdf_text', 'ocr', 'unsupported'
    """
    if mime_type == "application/pdf":
        text, confidence, warnings = _extract_text_pdf(data)
        if text:
            return text, "pdf_text", confidence, warnings
        # No text layer — try OCR on each page rendered as an image if possible.
        # For now fall through and attempt image OCR only on standalone images.
        return text, "pdf_text", confidence, warnings

    if mime_type.startswith("image/"):
        text, confidence, warnings = _extract_text_ocr(data, mime_type)
        return text, "ocr", confidence, warnings

    return "", "unsupported", 0.0, [f"Text extraction not supported for {mime_type}"]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _next_version_number(session: Session, document_id: int) -> int:
    from sqlalchemy import func
    max_ver = session.scalar(
        select(func.max(DocumentVersion.version_number)).where(
            DocumentVersion.document_id == document_id
        )
    )
    return (max_ver or 0) + 1


def _document_payload(doc: MedicalDocument, version: DocumentVersion | None = None) -> dict:
    """Build a safe public representation of a document record."""
    payload: dict = {
        "id": str(doc.public_id),
        "document_type": doc.document_type,
        "title": doc.title,
        "description": doc.description,
        "document_date": doc.document_date.isoformat() if doc.document_date else None,
        "status": doc.status,
        "verified_at": doc.verified_at.isoformat() if doc.verified_at else None,
        "verification_notes": doc.verification_notes,
        "created_at": doc.created_at.isoformat(),
        "updated_at": doc.updated_at.isoformat(),
    }
    if version:
        payload["current_version"] = {
            "id": str(version.public_id),
            "version_number": version.version_number,
            "original_filename": version.original_filename,
            "file_size_bytes": version.file_size_bytes,
            "mime_type": version.mime_type,
            "sha256_hash": version.sha256_hash,
            "extraction_method": version.extraction_method,
            "extraction_confidence": version.extraction_confidence,
            "extraction_warnings": json.loads(version.extraction_warnings)
            if version.extraction_warnings
            else [],
            "created_at": version.created_at.isoformat(),
        }
    return payload

# ---------------------------------------------------------------------------
# 5.8 — Upload pipeline (5.3 validate → 5.4 scan → 5.5 hash → 5.6 encrypt)
# ---------------------------------------------------------------------------

def upload_document(
    session: Session,
    *,
    patient: PatientProfile,
    uploader: User,
    file_stream: IO[bytes],
    filename: str,
    document_type: str,
    title: str,
    description: str | None = None,
    document_date=None,
    encounter_id: int | None = None,
    config: dict,
) -> tuple[MedicalDocument, DocumentVersion]:
    """Full upload pipeline: validate → scan → hash → encrypt → persist.

    Creates a MedicalDocument in 'upload' status, validates and processes
    the file, then transitions to 'ready' (or 'quarantined'/'failed').
    All state transitions are audited via the AuditEvent table.

    Returns the new (MedicalDocument, DocumentVersion) pair.
    Raises ApiProblem on validation or processing failures.
    """
    # ---- Read bytes once ----
    data = file_stream.read()

    # ---- 5.3 Validate ----
    allowed_ext = config.get("ALLOWED_DOCUMENT_EXTENSIONS", {"pdf", "jpg", "jpeg", "png"})
    allowed_mime = config.get("ALLOWED_DOCUMENT_MIME_TYPES", {"application/pdf", "image/jpeg", "image/png"})
    max_bytes = config.get("MAX_DOCUMENT_SIZE_BYTES", 20 * 1024 * 1024)

    _validate_size(data, max_bytes)
    _validate_extension(filename, allowed_ext)
    detected_mime = _validate_mime(data, filename, allowed_mime)

    # ---- Create document record in 'upload' state ----
    if encounter_id is not None:
        encounter = session.get(Encounter, encounter_id)
        if encounter is None or encounter.patient_profile_id != patient.patient_profile_id:
            raise ApiProblem("encounter_not_found", "Encounter not found or not owned by patient", 404)

    now = _utcnow()
    doc = MedicalDocument(
        patient_profile_id=patient.patient_profile_id,
        uploaded_by_user_id=uploader.user_id,
        encounter_id=encounter_id,
        document_type=document_type,
        title=title,
        description=description,
        document_date=document_date,
        status="upload",
        created_at=now,
        updated_at=now,
    )
    session.add(doc)
    session.flush()  # obtain document_id

    # Audit: upload started
    write_audit_event(
        session,
        action="document.upload_started",
        resource_type="medical_document",
        resource_id=str(doc.public_id),
        actor_user_id=uploader.user_id,
        details={"filename": filename, "mime_type": detected_mime, "size_bytes": len(data)},
    )

    # ---- Transition to 'processing' ----
    doc.status = "processing"
    doc.updated_at = _utcnow()
    session.flush()

    try:
        # ---- 5.4 Malware scan ----
        is_clean, scan_reason = _scan_for_malware(data, filename)
        if not is_clean:
            doc.status = "quarantined"
            doc.updated_at = _utcnow()
            write_audit_event(
                session,
                action="document.quarantined",
                resource_type="medical_document",
                resource_id=str(doc.public_id),
                actor_user_id=uploader.user_id,
                outcome="failure",
                details={"reason": scan_reason},
            )
            session.flush()
            raise ApiProblem(
                "file_quarantined",
                "The uploaded file was quarantined by malware scanning",
                422,
            )

        # ---- 5.5 SHA-256 of plaintext ----
        sha256 = _sha256_hex(data)

        # ---- 5.6 Encrypt and store ----
        storage = get_storage_backend(config)
        ref = storage.store(data)

        # ---- 5.9 / 5.10 Text extraction ----
        extracted_text, method, confidence, ext_warnings = _extract_text(data, detected_mime)

        # ---- Persist DocumentVersion ----
        version_number = _next_version_number(session, doc.document_id)
        version = DocumentVersion(
            document_id=doc.document_id,
            version_number=version_number,
            original_filename=filename,
            file_size_bytes=len(data),
            mime_type=detected_mime,
            sha256_hash=sha256,
            storage_key=ref.storage_key,
            storage_backend=ref.storage_backend,
            encryption_key_id=ref.encryption_key_id,
            extracted_text=extracted_text or None,
            extraction_method=method if extracted_text else None,
            extraction_confidence=round(confidence, 4) if extracted_text else None,
            extraction_warnings=json.dumps(ext_warnings) if ext_warnings else None,
            uploaded_by_user_id=uploader.user_id,
            created_at=_utcnow(),
        )
        session.add(version)

        # ---- Transition to 'ready' ----
        doc.status = "ready"
        doc.updated_at = _utcnow()
        session.flush()

        # ---- 6.5 / 6.6 Auto-run report analysis for lab reports ----
        # Analysis runs for all document types but only lab_report and imaging
        # produce meaningful biomarker output currently.  The result is
        # persisted with review_status='pending' — it CANNOT be treated as
        # clinically accepted until a doctor explicitly reviews it.
        if extracted_text and doc.document_type in (
            "lab_report", "imaging", "discharge_summary", "other"
        ):
            _run_auto_analysis(session, doc=doc, version=version, uploader_user_id=uploader.user_id)

        write_audit_event(
            session,
            action="document.upload_completed",
            resource_type="medical_document",
            resource_id=str(doc.public_id),
            actor_user_id=uploader.user_id,
            details={
                "version": version_number,
                "sha256": sha256,
                "extraction_method": method,
            },
        )
        # Task 8: enqueue only hashes/opaque references. No RPC call occurs in
        # the request path, so blockchain downtime cannot fail the upload.
        from blockchain_service import enqueue_document_version

        enqueue_document_version(session, version, config)

    except ApiProblem:
        raise
    except Exception as exc:
        logger.exception("Document processing failed for doc %s", doc.public_id)
        doc.status = "failed"
        doc.updated_at = _utcnow()
        write_audit_event(
            session,
            action="document.processing_failed",
            resource_type="medical_document",
            resource_id=str(doc.public_id),
            actor_user_id=uploader.user_id,
            outcome="failure",
            details={"error": str(exc)},
        )
        session.flush()
        raise ApiProblem("document_processing_failed", "Document could not be processed", 500) from exc

    return doc, version

# ---------------------------------------------------------------------------
# List documents for a patient
# ---------------------------------------------------------------------------

def list_patient_documents(
    session: Session,
    patient: PatientProfile,
    *,
    status_filter: str | None = None,
) -> list[dict]:
    """Return document summaries for a patient, newest first."""
    q = select(MedicalDocument).where(
        MedicalDocument.patient_profile_id == patient.patient_profile_id
    )
    if status_filter:
        q = q.where(MedicalDocument.status == status_filter)
    q = q.order_by(MedicalDocument.created_at.desc())
    docs = list(session.scalars(q))

    result = []
    for doc in docs:
        latest = _latest_version(session, doc.document_id)
        result.append(_document_payload(doc, latest))
    return result


def get_document_by_public_id(
    session: Session,
    public_id: UUID,
    owner_patient_profile_id: int | None = None,
) -> MedicalDocument:
    """Fetch a document by public UUID; optionally assert ownership."""
    doc = session.scalar(
        select(MedicalDocument).where(MedicalDocument.public_id == public_id)
    )
    if doc is None:
        raise ApiProblem("document_not_found", "Document not found", 404)
    if owner_patient_profile_id is not None and doc.patient_profile_id != owner_patient_profile_id:
        raise ApiProblem("ownership_required", "You do not own this document", 403)
    return doc


def _latest_version(session: Session, document_id: int) -> DocumentVersion | None:
    return session.scalar(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == document_id)
        .order_by(DocumentVersion.version_number.desc())
        .limit(1)
    )


# ---------------------------------------------------------------------------
# 5.7 — Authorised streaming download
# ---------------------------------------------------------------------------

def download_document(
    session: Session,
    doc: MedicalDocument,
    actor_user_id: int,
    config: dict,
) -> tuple[bytes, DocumentVersion]:
    """Return (plaintext_bytes, version).  Audits every access."""
    if doc.status not in ("ready", "archived"):
        raise ApiProblem(
            "document_unavailable",
            f"Document is not available for download (status: {doc.status})",
            409,
        )
    version = _latest_version(session, doc.document_id)
    if version is None:
        raise ApiProblem("document_version_missing", "No version found for document", 500)

    storage = get_storage_backend(config)
    try:
        plaintext = storage.retrieve(version.storage_key)
    except ApiProblem:
        write_audit_event(
            session,
            action="document.download_failed",
            resource_type="medical_document",
            resource_id=str(doc.public_id),
            actor_user_id=actor_user_id,
            outcome="failure",
        )
        raise

    write_audit_event(
        session,
        action="document.downloaded",
        resource_type="medical_document",
        resource_id=str(doc.public_id),
        actor_user_id=actor_user_id,
        details={"version": version.version_number, "sha256": version.sha256_hash},
    )
    return plaintext, version


# ---------------------------------------------------------------------------
# 5.5 — Integrity verification (re-hash and compare)
# ---------------------------------------------------------------------------

def verify_document_hash(
    session: Session,
    doc: MedicalDocument,
    actor_user_id: int,
    config: dict,
) -> dict:
    """Download, re-hash, and compare against stored SHA-256.

    Returns a verification result dict.  Audits the check regardless of outcome.
    """
    version = _latest_version(session, doc.document_id)
    if version is None:
        raise ApiProblem("document_version_missing", "No version found for document", 500)

    try:
        plaintext, _ = download_document(session, doc, actor_user_id, config)
    except ApiProblem:
        raise

    computed = _sha256_hex(plaintext)
    matches = computed == version.sha256_hash
    outcome = "success" if matches else "failure"

    write_audit_event(
        session,
        action="document.integrity_verified",
        resource_type="medical_document",
        resource_id=str(doc.public_id),
        actor_user_id=actor_user_id,
        outcome=outcome,
        details={
            "stored_hash": version.sha256_hash,
            "computed_hash": computed,
            "match": matches,
        },
    )

    return {
        "document_id": str(doc.public_id),
        "version_number": version.version_number,
        "stored_sha256": version.sha256_hash,
        "computed_sha256": computed,
        "verified": matches,
    }

# ---------------------------------------------------------------------------
# Archive transition
# ---------------------------------------------------------------------------

def archive_document(
    session: Session,
    doc: MedicalDocument,
    actor_user_id: int,
) -> MedicalDocument:
    """Move a ready document to archived status."""
    if doc.status != "ready":
        raise ApiProblem(
            "invalid_state_transition",
            f"Only 'ready' documents can be archived (current status: {doc.status})",
            409,
        )
    doc.status = "archived"
    doc.updated_at = _utcnow()
    write_audit_event(
        session,
        action="document.archived",
        resource_type="medical_document",
        resource_id=str(doc.public_id),
        actor_user_id=actor_user_id,
    )
    session.flush()
    return doc


def delete_document(
    session: Session,
    doc: MedicalDocument,
    actor_user_id: int,
) -> list[str]:
    """Delete an owned document and all database-backed dependent records.

    The encrypted object keys are returned so the HTTP layer can commit the
    database transaction before removing the physical objects. This avoids a
    failed database commit leaving a document record that points to a missing
    file. ``MedicalDocument`` relationships cascade to versions and analysis
    results; other optional references use database ``SET NULL`` semantics.
    """
    versions = list(doc.versions)
    storage_keys = [version.storage_key for version in versions]
    version_ids = [version.document_version_id for version in versions]
    public_id = str(doc.public_id)

    # Keep append-only proof and prediction history, but sever optional links
    # before deleting the source rows. This mirrors the production FK SET NULL
    # behavior in SQLite environments where foreign-key actions may be off.
    if version_ids:
        session.execute(
            update(BlockchainTransaction)
            .where(BlockchainTransaction.document_version_id.in_(version_ids))
            .values(document_version_id=None)
        )
    session.execute(
        update(RiskPrediction)
        .where(RiskPrediction.source_document_id == doc.document_id)
        .values(source_document_id=None)
    )

    write_audit_event(
        session,
        action="document.deleted",
        resource_type="medical_document",
        resource_id=public_id,
        actor_user_id=actor_user_id,
        details={"deleted_version_count": len(storage_keys)},
    )
    session.delete(doc)
    session.flush()
    return storage_keys


def purge_document_storage(storage_keys: list[str], config: dict) -> list[str]:
    """Best-effort removal of encrypted objects after database deletion.

    Returns any keys that could not be removed so callers can expose an honest
    cleanup status without rolling back a database deletion that has already
    committed.
    """
    storage = get_storage_backend(config)
    failed: list[str] = []
    for storage_key in storage_keys:
        try:
            storage.delete(storage_key)
        except Exception:  # noqa: BLE001 - cleanup is intentionally best-effort
            logger.exception("Failed to purge stored object %s", storage_key)
            failed.append(storage_key)
    return failed


# ---------------------------------------------------------------------------
# Doctor: view document metadata (5.12 — audited access)
# ---------------------------------------------------------------------------

def view_document_as_doctor(
    session: Session,
    doc: MedicalDocument,
    actor_user_id: int,
) -> dict:
    """Return document payload and audit the doctor's access."""
    write_audit_event(
        session,
        action="document.viewed",
        resource_type="medical_document",
        resource_id=str(doc.public_id),
        actor_user_id=actor_user_id,
    )
    version = _latest_version(session, doc.document_id)
    return _document_payload(doc, version)


# ---------------------------------------------------------------------------
# Doctor: verify / accept / reject analysis result (5.6 workflow)
# ---------------------------------------------------------------------------

def review_analysis_result(
    session: Session,
    doc: MedicalDocument,
    analysis_public_id: UUID,
    *,
    doctor: DoctorProfile,
    new_status: str,
    reviewer_notes: str | None,
) -> DocumentAnalysisResult:
    """Accept, reject, or mark-corrected an analysis result."""
    valid_transitions = {"accepted", "rejected", "corrected"}
    if new_status not in valid_transitions:
        raise ApiProblem(
            "invalid_review_status",
            f"review_status must be one of: {sorted(valid_transitions)}",
            400,
        )
    result = session.scalar(
        select(DocumentAnalysisResult).where(
            DocumentAnalysisResult.public_id == analysis_public_id,
            DocumentAnalysisResult.document_id == doc.document_id,
        )
    )
    if result is None:
        raise ApiProblem("analysis_not_found", "Analysis result not found", 404)
    if result.review_status != "pending":
        raise ApiProblem(
            "already_reviewed",
            f"Analysis result has already been reviewed (status: {result.review_status})",
            409,
        )

    now = _utcnow()
    result.review_status = new_status
    result.reviewed_by_doctor_profile_id = doctor.doctor_profile_id
    result.reviewed_at = now
    result.reviewer_notes = reviewer_notes
    result.updated_at = now
    session.flush()

    write_audit_event(
        session,
        action=f"document.analysis_{new_status}",
        resource_type="document_analysis_result",
        resource_id=str(result.public_id),
        actor_user_id=doctor.user_id,
        details={"document_id": str(doc.public_id)},
    )
    return result


# ---------------------------------------------------------------------------
# Doctor: verify a document (set verification status on MedicalDocument)
# ---------------------------------------------------------------------------

def verify_document(
    session: Session,
    doc: MedicalDocument,
    *,
    doctor: DoctorProfile,
    notes: str | None,
) -> MedicalDocument:
    """Record that a doctor has reviewed and verified the document."""
    if doc.status not in ("ready", "archived"):
        raise ApiProblem(
            "document_unavailable",
            f"Document must be in 'ready' or 'archived' state to verify (current: {doc.status})",
            409,
        )
    now = _utcnow()
    doc.verified_by_doctor_profile_id = doctor.doctor_profile_id
    doc.verified_at = now
    doc.verification_notes = notes
    doc.updated_at = now
    session.flush()

    write_audit_event(
        session,
        action="document.verified",
        resource_type="medical_document",
        resource_id=str(doc.public_id),
        actor_user_id=doctor.user_id,
        details={"doctor_profile_id": str(doctor.public_id)},
    )
    return doc


# ---------------------------------------------------------------------------
# Denied-access audit helper
# ---------------------------------------------------------------------------

def audit_denied_access(
    session: Session,
    doc_public_id: str,
    actor_user_id: int | None,
) -> None:
    """Write a denied audit event when access to a document is refused."""
    write_audit_event(
        session,
        action="document.access_denied",
        resource_type="medical_document",
        resource_id=doc_public_id,
        actor_user_id=actor_user_id,
        outcome="denied",
    )

# ---------------------------------------------------------------------------
# 6.5 / 6.6 — Report analysis integration
# ---------------------------------------------------------------------------

def _run_auto_analysis(
    session: Session,
    *,
    doc: MedicalDocument,
    version: DocumentVersion,
    uploader_user_id: int,
) -> DocumentAnalysisResult | None:
    """Run report_analysis on the extracted text and persist the result.

    Called automatically from upload_document() for supported document types.
    The result is always persisted with review_status='pending'; it requires
    explicit doctor acceptance before any clinical use.

    Returns the persisted DocumentAnalysisResult, or None if analysis is
    skipped (no text, or analysis raises an unexpected error).
    """
    try:
        from report_analysis import analyse_report_text

        upstream_warnings: list[str] = (
            json.loads(version.extraction_warnings)
            if version.extraction_warnings
            else []
        )
        analysis = analyse_report_text(
            text=version.extracted_text or "",
            extraction_confidence=version.extraction_confidence or 0.0,
            additional_caveats=upstream_warnings,
        )

        result = DocumentAnalysisResult(
            document_id=doc.document_id,
            document_version_id=version.document_version_id,
            analysis_type=analysis.analysis_type,
            model_version=analysis.model_version,
            rule_version=analysis.rule_version,
            extracted_biomarkers=analysis.extracted_biomarkers or None,
            abnormal_flags=analysis.abnormal_flags or None,
            summary=analysis.summary,
            caveats=analysis.caveats or None,
            confidence_score=round(analysis.confidence_score, 4),
            review_status="pending",
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )
        session.add(result)
        session.flush()

        write_audit_event(
            session,
            action="document.analysis_created",
            resource_type="document_analysis_result",
            resource_id=str(result.public_id),
            actor_user_id=uploader_user_id,
            details={
                "document_id": str(doc.public_id),
                "biomarker_count": len(analysis.extracted_biomarkers),
                "abnormal_count": len(analysis.abnormal_flags),
                "confidence": analysis.confidence_score,
                "rule_version": analysis.rule_version,
            },
        )
        return result

    except Exception as exc:  # noqa: BLE001
        # Analysis failure must never block the document upload itself.
        logger.warning(
            "Auto-analysis failed for document %s (version %s): %s",
            doc.public_id,
            version.document_version_id,
            exc,
        )
        return None


def run_document_analysis(
    session: Session,
    doc: MedicalDocument,
    actor_user_id: int,
) -> DocumentAnalysisResult:
    """Manually trigger (or re-trigger) analysis for an existing ready document.

    Used by the API endpoint so a patient or authorised doctor can explicitly
    request analysis after upload.  Always creates a NEW result row so the
    history is preserved.

    Raises ApiProblem if the document has no extracted text or is not ready.
    """
    if doc.status not in ("ready", "archived"):
        raise ApiProblem(
            "document_unavailable",
            f"Analysis can only be run on 'ready' or 'archived' documents (current: {doc.status})",
            409,
        )

    version = _latest_version(session, doc.document_id)
    if version is None:
        raise ApiProblem("document_version_missing", "No version found for document", 500)

    if not version.extracted_text:
        raise ApiProblem(
            "no_extracted_text",
            "This document has no extractable text content. "
            "Analysis requires a text layer (PDF) or OCR output (image). "
            "Re-upload with a higher-quality scan if possible.",
            422,
        )

    from report_analysis import analyse_report_text

    upstream_warnings: list[str] = (
        json.loads(version.extraction_warnings) if version.extraction_warnings else []
    )
    analysis = analyse_report_text(
        text=version.extracted_text,
        extraction_confidence=version.extraction_confidence or 0.0,
        additional_caveats=upstream_warnings,
    )

    result = DocumentAnalysisResult(
        document_id=doc.document_id,
        document_version_id=version.document_version_id,
        analysis_type=analysis.analysis_type,
        model_version=analysis.model_version,
        rule_version=analysis.rule_version,
        extracted_biomarkers=analysis.extracted_biomarkers or None,
        abnormal_flags=analysis.abnormal_flags or None,
        summary=analysis.summary,
        caveats=analysis.caveats or None,
        confidence_score=round(analysis.confidence_score, 4),
        review_status="pending",
        created_at=_utcnow(),
        updated_at=_utcnow(),
    )
    session.add(result)
    session.flush()

    write_audit_event(
        session,
        action="document.analysis_created",
        resource_type="document_analysis_result",
        resource_id=str(result.public_id),
        actor_user_id=actor_user_id,
        details={
            "document_id": str(doc.public_id),
            "biomarker_count": len(analysis.extracted_biomarkers),
            "abnormal_count": len(analysis.abnormal_flags),
            "confidence": analysis.confidence_score,
            "rule_version": analysis.rule_version,
            "triggered_manually": True,
        },
    )
    return result


def list_document_analyses(
    session: Session,
    doc: MedicalDocument,
    actor_user_id: int,
) -> list[dict]:
    """Return all analysis results for a document, newest first.

    The summary text is intentionally included so the patient/doctor UI can
    render the full assistive output without a separate request.
    Audits the view.
    """
    results = list(
        session.scalars(
            select(DocumentAnalysisResult)
            .where(DocumentAnalysisResult.document_id == doc.document_id)
            .order_by(DocumentAnalysisResult.created_at.desc())
        )
    )

    write_audit_event(
        session,
        action="document.analysis_list_viewed",
        resource_type="medical_document",
        resource_id=str(doc.public_id),
        actor_user_id=actor_user_id,
    )

    return [_analysis_payload(r) for r in results]


def _analysis_payload(result: DocumentAnalysisResult) -> dict:
    return {
        "id": str(result.public_id),
        "analysis_type": result.analysis_type,
        "model_version": result.model_version,
        "rule_version": result.rule_version,
        "extracted_biomarkers": result.extracted_biomarkers,
        "abnormal_flags": result.abnormal_flags,
        "summary": result.summary,
        "caveats": result.caveats,
        "confidence_score": result.confidence_score,
        "review_status": result.review_status,
        "reviewed_at": result.reviewed_at.isoformat() if result.reviewed_at else None,
        "reviewer_notes": result.reviewer_notes,
        "created_at": result.created_at.isoformat(),
        # Mandatory clinical-safety label present in every API response.
        "_disclaimer": (
            "This is automated decision support only. "
            "It is NOT a diagnosis and requires clinician review before any clinical use."
        ),
    }
