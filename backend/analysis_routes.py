"""Medical report analysis and disease-risk prediction endpoints.

Covers task 6.15 and 6.16:

  6.15  Patient report-analysis and health-risk views:
    GET  /api/v1/patients/me/documents/<id>/analyses
         List all analysis results for a document (newest first).
    POST /api/v1/patients/me/documents/<id>/analyses
         Manually trigger (or re-trigger) analysis on a ready document.
    GET  /api/v1/patients/me/risk-predictions
         List all risk predictions for the authenticated patient.
    POST /api/v1/patients/me/risk-predictions/diabetes
         Run the diabetes risk model and persist the result.
    POST /api/v1/patients/me/risk-predictions/cardiovascular
         Run the cardiovascular risk model and persist the result.
    GET  /api/v1/patients/me/risk-predictions/<id>
         Retrieve a specific risk prediction (read-only for patient).

  6.16  Doctor review/accept/reject/correct workflow:
    GET  /api/v1/doctors/me/patients/<pid>/documents/<id>/analyses
         List analysis results for a patient document.
    POST /api/v1/doctors/me/patients/<pid>/documents/<id>/analyses
         Re-trigger analysis on a patient document.
    GET  /api/v1/doctors/me/patients/<pid>/risk-predictions
         List risk predictions for a patient.
    POST /api/v1/doctors/me/risk-predictions/<pred_id>/review
         Accept, reject, or mark-corrected a pending risk prediction.

  Supporting endpoints (available to both roles):
    GET  /api/v1/risk-models
         List supported prediction models, versions, and their limitations.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from flask import Flask, g, jsonify
from sqlalchemy import select

from audit import write_audit_event
from auth_service import ROLE_DOCTOR, ROLE_PATIENT
from authorization import require_auth
from document_service import (
    get_document_by_public_id,
    list_document_analyses,
    run_document_analysis,
)
from ehr_service import (
    doctor_profile_for_user,
    ensure_patient_profile,
    patient_profile_by_public_id,
    require_doctor_patient_access,
)
from errors import ApiProblem
from extensions import db, limiter
from models import RiskPrediction, PatientProfile
from rate_limits import PREDICTION_RATE_LIMIT, SENSITIVE_WRITE_RATE_LIMIT
from risk_models import (
    SUPPORTED_MODELS,
    CardiovascularRiskInput,
    DiabetesRiskInput,
    run_prediction,
)
from schemas import (
    CardiovascularRiskRequest,
    DiabetesRiskRequest,
    RiskPredictionReviewRequest,
    validate_json,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _success(data, status: int = 200):
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


def _prediction_payload(pred: RiskPrediction) -> dict:
    """Safe public representation of a RiskPrediction row."""
    return {
        "id": str(pred.public_id),
        "model_name": pred.model_name,
        "model_version": pred.model_version,
        "risk_score": pred.risk_score,
        "risk_band": pred.risk_band,
        "contributing_factors": pred.output_snapshot.get("contributing_factors", []),
        "protective_factors": pred.output_snapshot.get("protective_factors", []),
        "limitations": pred.output_snapshot.get("limitations", []),
        "review_status": pred.review_status,
        "reviewed_at": pred.reviewed_at.isoformat() if pred.reviewed_at else None,
        "reviewer_notes": pred.reviewer_notes,
        "created_at": pred.created_at.isoformat(),
        # Mandatory clinical-safety label in every response (task 6.10).
        "_disclaimer": pred.output_snapshot.get(
            "disclaimer",
            "This risk estimate is decision support only. "
            "It is NOT a diagnosis and requires clinician review before any clinical use.",
        ),
    }


def _persist_prediction(
    patient: PatientProfile,
    model_name: str,
    output,
    source_document_id: int | None,
) -> RiskPrediction:
    """Store an immutable RiskPrediction snapshot and return the row."""
    import dataclasses

    pred = RiskPrediction(
        patient_profile_id=patient.patient_profile_id,
        requested_by_user_id=g.current_user.user_id,
        source_document_id=source_document_id,
        model_name=model_name,
        model_version=output.model_version,
        input_snapshot=output.input_snapshot,
        output_snapshot=dataclasses.asdict(output),
        risk_score=output.risk_score,
        risk_band=output.risk_band,
        review_status="pending",
        created_at=_utcnow(),
    )
    db.session.add(pred)
    db.session.flush()
    return pred


def _resolve_source_doc_id(source_document_id: UUID | None, patient: PatientProfile) -> int | None:
    """Validate source_document_id belongs to the patient; return the integer PK."""
    if source_document_id is None:
        return None
    from models import MedicalDocument
    doc = db.session.scalar(
        select(MedicalDocument).where(MedicalDocument.public_id == source_document_id)
    )
    if doc is None or doc.patient_profile_id != patient.patient_profile_id:
        raise ApiProblem("document_not_found", "Source document not found or not owned by patient", 404)
    return doc.document_id


def _get_prediction_by_public_id(pred_id: UUID) -> RiskPrediction:
    pred = db.session.scalar(
        select(RiskPrediction).where(RiskPrediction.public_id == pred_id)
    )
    if pred is None:
        raise ApiProblem("prediction_not_found", "Risk prediction not found", 404)
    return pred


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------

def register_analysis_routes(app: Flask) -> None:

    # ======================================================================
    # Shared — model catalogue
    # ======================================================================

    @app.get("/api/v1/risk-models")
    @require_auth(ROLE_PATIENT, ROLE_DOCTOR)
    def list_risk_models():
        """Return supported prediction models with versions and limitations."""
        return _success(
            [
                {
                    "model_name": name,
                    "version": meta["version"],
                    "description": meta["description"],
                    "limitations": meta["limitations"],
                }
                for name, meta in SUPPORTED_MODELS.items()
            ]
        )

    # ======================================================================
    # Patient — document analysis views (6.15)
    # ======================================================================

    @app.get("/api/v1/patients/me/documents/<uuid:doc_id>/analyses")
    @require_auth(ROLE_PATIENT)
    def patient_list_analyses(doc_id: UUID):
        """List all analysis results for one of the patient's documents."""
        patient = ensure_patient_profile(db.session, g.current_user)
        doc = get_document_by_public_id(
            db.session, doc_id, owner_patient_profile_id=patient.patient_profile_id
        )
        results = list_document_analyses(db.session, doc, g.current_user.user_id)
        db.session.commit()
        return _success(results)

    @app.post("/api/v1/patients/me/documents/<uuid:doc_id>/analyses")
    @require_auth(ROLE_PATIENT)
    @limiter.limit(PREDICTION_RATE_LIMIT)
    def patient_run_analysis(doc_id: UUID):
        """Manually trigger (or re-trigger) analysis on a ready document."""
        patient = ensure_patient_profile(db.session, g.current_user)
        doc = get_document_by_public_id(
            db.session, doc_id, owner_patient_profile_id=patient.patient_profile_id
        )
        result = run_document_analysis(db.session, doc, g.current_user.user_id)
        db.session.commit()

        from document_service import _analysis_payload
        return _success(_analysis_payload(result), 201)

    # ======================================================================
    # Patient — risk predictions (6.15)
    # ======================================================================

    @app.get("/api/v1/patients/me/risk-predictions")
    @require_auth(ROLE_PATIENT)
    def patient_list_predictions():
        """List all risk predictions for the authenticated patient."""
        patient = ensure_patient_profile(db.session, g.current_user)
        preds = list(
            db.session.scalars(
                select(RiskPrediction)
                .where(RiskPrediction.patient_profile_id == patient.patient_profile_id)
                .order_by(RiskPrediction.created_at.desc())
            )
        )
        _audit("risk.predictions_listed", "patient_profile", patient.public_id)
        db.session.commit()
        return _success([_prediction_payload(p) for p in preds])

    @app.get("/api/v1/patients/me/risk-predictions/<uuid:pred_id>")
    @require_auth(ROLE_PATIENT)
    def patient_get_prediction(pred_id: UUID):
        """Retrieve a specific risk prediction owned by the patient."""
        patient = ensure_patient_profile(db.session, g.current_user)
        pred = _get_prediction_by_public_id(pred_id)
        if pred.patient_profile_id != patient.patient_profile_id:
            raise ApiProblem("ownership_required", "You do not own this prediction", 403)
        _audit("risk.prediction_viewed", "risk_prediction", pred.public_id)
        db.session.commit()
        return _success(_prediction_payload(pred))

    @app.post("/api/v1/patients/me/risk-predictions/diabetes")
    @require_auth(ROLE_PATIENT)
    @limiter.limit(PREDICTION_RATE_LIMIT)
    def patient_diabetes_risk():
        """Run the diabetes risk model and persist the result."""
        body = validate_json(DiabetesRiskRequest)
        patient = ensure_patient_profile(db.session, g.current_user)

        source_doc_id = _resolve_source_doc_id(body.source_document_id, patient)

        try:
            output = run_prediction("diabetes_risk", body.model_dump(exclude={"source_document_id"}))
        except ValueError as exc:
            raise ApiProblem("invalid_prediction_input", str(exc), 422) from exc

        pred = _persist_prediction(patient, "diabetes_risk", output, source_doc_id)

        _audit(
            "risk.prediction_created",
            "risk_prediction",
            pred.public_id,
            {
                "model": "diabetes_risk",
                "version": output.model_version,
                "risk_band": output.risk_band,
            },
        )
        db.session.commit()
        return _success(_prediction_payload(pred), 201)

    @app.post("/api/v1/patients/me/risk-predictions/cardiovascular")
    @require_auth(ROLE_PATIENT)
    @limiter.limit(PREDICTION_RATE_LIMIT)
    def patient_cardiovascular_risk():
        """Run the cardiovascular risk model and persist the result."""
        body = validate_json(CardiovascularRiskRequest)
        patient = ensure_patient_profile(db.session, g.current_user)

        source_doc_id = _resolve_source_doc_id(body.source_document_id, patient)

        try:
            output = run_prediction(
                "cardiovascular_risk", body.model_dump(exclude={"source_document_id"})
            )
        except ValueError as exc:
            raise ApiProblem("invalid_prediction_input", str(exc), 422) from exc

        pred = _persist_prediction(patient, "cardiovascular_risk", output, source_doc_id)

        _audit(
            "risk.prediction_created",
            "risk_prediction",
            pred.public_id,
            {
                "model": "cardiovascular_risk",
                "version": output.model_version,
                "risk_band": output.risk_band,
            },
        )
        db.session.commit()
        return _success(_prediction_payload(pred), 201)

    # ======================================================================
    # Doctor — document analysis (6.16)
    # ======================================================================

    @app.get("/api/v1/doctors/me/patients/<uuid:patient_id>/documents/<uuid:doc_id>/analyses")
    @require_auth(ROLE_DOCTOR)
    def doctor_list_analyses(patient_id: UUID, doc_id: UUID):
        """List analysis results for a patient document."""
        doctor = doctor_profile_for_user(db.session, g.current_user.user_id)
        patient = patient_profile_by_public_id(db.session, patient_id)
        require_doctor_patient_access(db.session, doctor, patient)
        doc = get_document_by_public_id(
            db.session, doc_id, owner_patient_profile_id=patient.patient_profile_id
        )
        results = list_document_analyses(db.session, doc, g.current_user.user_id)
        db.session.commit()
        return _success(results)

    @app.post("/api/v1/doctors/me/patients/<uuid:patient_id>/documents/<uuid:doc_id>/analyses")
    @require_auth(ROLE_DOCTOR)
    @limiter.limit(PREDICTION_RATE_LIMIT)
    def doctor_run_analysis(patient_id: UUID, doc_id: UUID):
        """Re-trigger analysis on a patient document."""
        doctor = doctor_profile_for_user(db.session, g.current_user.user_id)
        patient = patient_profile_by_public_id(db.session, patient_id)
        require_doctor_patient_access(db.session, doctor, patient)
        doc = get_document_by_public_id(
            db.session, doc_id, owner_patient_profile_id=patient.patient_profile_id
        )
        result = run_document_analysis(db.session, doc, g.current_user.user_id)
        db.session.commit()

        from document_service import _analysis_payload
        return _success(_analysis_payload(result), 201)

    # ======================================================================
    # Doctor — risk prediction review (6.16)
    # ======================================================================

    @app.get("/api/v1/doctors/me/patients/<uuid:patient_id>/risk-predictions")
    @require_auth(ROLE_DOCTOR)
    def doctor_list_patient_predictions(patient_id: UUID):
        """List all risk predictions for an authorised patient."""
        doctor = doctor_profile_for_user(db.session, g.current_user.user_id)
        patient = patient_profile_by_public_id(db.session, patient_id)
        require_doctor_patient_access(db.session, doctor, patient)

        preds = list(
            db.session.scalars(
                select(RiskPrediction)
                .where(RiskPrediction.patient_profile_id == patient.patient_profile_id)
                .order_by(RiskPrediction.created_at.desc())
            )
        )
        _audit(
            "risk.doctor_predictions_viewed",
            "patient_profile",
            patient.public_id,
            {"doctor_profile_id": str(doctor.public_id)},
        )
        db.session.commit()
        return _success([_prediction_payload(p) for p in preds])

    @app.post("/api/v1/doctors/me/risk-predictions/<uuid:pred_id>/review")
    @require_auth(ROLE_DOCTOR)
    @limiter.limit(SENSITIVE_WRITE_RATE_LIMIT)
    def doctor_review_prediction(pred_id: UUID):
        """Accept, reject, or mark-corrected a pending risk prediction."""
        body = validate_json(RiskPredictionReviewRequest)
        doctor = doctor_profile_for_user(db.session, g.current_user.user_id)
        pred = _get_prediction_by_public_id(pred_id)

        # Verify the doctor has a care relationship with this patient.
        patient = db.session.scalar(
            select(PatientProfile).where(
                PatientProfile.patient_profile_id == pred.patient_profile_id
            )
        )
        if patient is None:
            raise ApiProblem("patient_not_found", "Patient profile not found", 404)
        require_doctor_patient_access(db.session, doctor, patient)

        if pred.review_status != "pending":
            raise ApiProblem(
                "already_reviewed",
                f"This prediction has already been reviewed (status: {pred.review_status})",
                409,
            )

        now = _utcnow()
        pred.review_status = body.review_status
        pred.reviewed_by_doctor_profile_id = doctor.doctor_profile_id
        pred.reviewed_at = now
        pred.reviewer_notes = body.reviewer_notes
        db.session.flush()

        _audit(
            f"risk.prediction_{body.review_status}",
            "risk_prediction",
            pred.public_id,
            {
                "doctor_profile_id": str(doctor.public_id),
                "model_name": pred.model_name,
            },
        )
        db.session.commit()
        return _success(
            {
                "id": str(pred.public_id),
                "review_status": pred.review_status,
                "reviewed_at": pred.reviewed_at.isoformat(),
            }
        )
