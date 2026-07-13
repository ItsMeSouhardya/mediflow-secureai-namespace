"""Integrity proof, consent proof, and blockchain operations endpoints."""

from __future__ import annotations

from uuid import UUID

import click
from flask import Flask, current_app, g, jsonify
from sqlalchemy import select

from audit import write_audit_event
from auth_service import ROLE_DOCTOR, ROLE_PATIENT, ROLE_SECURITY_ADMIN
from authorization import require_auth, require_consent_scope
from blockchain_service import (
    consent_proof_status,
    create_audit_anchor,
    create_due_audit_anchor,
    document_integrity_status,
    enqueue_document_version,
    process_pending_transactions,
    transaction_payload,
)
from consent_service import get_grant_for_patient
from document_service import _latest_version, get_document_by_public_id, verify_document_hash
from ehr_service import doctor_profile_for_user, ensure_patient_profile, patient_profile_by_public_id
from errors import ApiProblem
from extensions import db
from models import BlockchainTransaction, ConsentGrant
from schemas import AuditAnchorRequest, validate_json


def _success(data, status: int = 200):
    return jsonify({"status": "success", "data": data}), status


def register_blockchain_routes(app: Flask) -> None:
    @app.get("/api/v1/patients/me/documents/<uuid:document_id>/integrity")
    @require_auth(ROLE_PATIENT)
    def patient_document_integrity(document_id: UUID):
        patient = ensure_patient_profile(db.session, g.current_user)
        document = get_document_by_public_id(
            db.session, document_id, owner_patient_profile_id=patient.patient_profile_id
        )
        version = _latest_version(db.session, document.document_id)
        enqueue_document_version(db.session, version, current_app.config)
        local = verify_document_hash(db.session, document, g.current_user.user_id, current_app.config)
        result = document_integrity_status(
            db.session, document=document, local_verification=local, config=current_app.config
        )
        db.session.commit()
        return _success(result)

    @app.get(
        "/api/v1/doctors/me/patients/<uuid:patient_id>/documents/"
        "<uuid:document_id>/integrity"
    )
    @require_auth(ROLE_DOCTOR)
    def doctor_document_integrity(patient_id: UUID, document_id: UUID):
        doctor_profile_for_user(db.session, g.current_user.user_id)
        patient = patient_profile_by_public_id(db.session, patient_id)
        require_consent_scope("reports", patient.user_id)
        document = get_document_by_public_id(
            db.session, document_id, owner_patient_profile_id=patient.patient_profile_id
        )
        version = _latest_version(db.session, document.document_id)
        enqueue_document_version(db.session, version, current_app.config)
        local = verify_document_hash(db.session, document, g.current_user.user_id, current_app.config)
        result = document_integrity_status(
            db.session, document=document, local_verification=local, config=current_app.config
        )
        db.session.commit()
        return _success(result)

    @app.get("/api/v1/patients/me/consent/<uuid:grant_id>/blockchain-proof")
    @require_auth(ROLE_PATIENT)
    def patient_consent_proof(grant_id: UUID):
        patient = ensure_patient_profile(db.session, g.current_user)
        grant = get_grant_for_patient(db.session, grant_id, patient)
        return _success(consent_proof_status(db.session, grant))

    @app.get("/api/v1/doctors/me/consent/<uuid:grant_id>/blockchain-proof")
    @require_auth(ROLE_DOCTOR)
    def doctor_consent_proof(grant_id: UUID):
        doctor = doctor_profile_for_user(db.session, g.current_user.user_id)
        grant = db.session.scalar(select(ConsentGrant).where(ConsentGrant.public_id == grant_id))
        if grant is None:
            raise ApiProblem("consent_not_found", "Consent grant not found", 404)
        if grant.requesting_doctor_profile_id != doctor.doctor_profile_id:
            raise ApiProblem("ownership_required", "This consent proof belongs to another doctor", 403)
        return _success(consent_proof_status(db.session, grant))

    @app.get("/api/v1/security/blockchain/transactions")
    @require_auth(ROLE_SECURITY_ADMIN)
    def security_blockchain_transactions():
        transactions = list(
            db.session.scalars(
                select(BlockchainTransaction).order_by(BlockchainTransaction.created_at.desc()).limit(200)
            )
        )
        return _success([transaction_payload(transaction) for transaction in transactions])

    @app.post("/api/v1/security/blockchain/audit-anchors")
    @require_auth(ROLE_SECURITY_ADMIN)
    def security_create_audit_anchor():
        body = validate_json(AuditAnchorRequest)
        anchor = create_audit_anchor(
            db.session,
            period_start=body.period_start,
            period_end=body.period_end,
            config=current_app.config,
        )
        transaction = db.session.get(BlockchainTransaction, anchor.blockchain_transaction_id)
        write_audit_event(
            db.session,
            action="blockchain.audit_anchor_queued",
            resource_type="blockchain_audit_anchor",
            resource_id=anchor.public_id,
            actor_user_id=g.current_user.user_id,
            details={"event_count": anchor.event_count},
        )
        db.session.commit()
        return _success(
            {
                "id": str(anchor.public_id),
                "period_start": anchor.period_start.isoformat(),
                "period_end": anchor.period_end.isoformat(),
                "event_count": anchor.event_count,
                "proof": transaction_payload(transaction),
            },
            201,
        )


def register_blockchain_commands(app: Flask) -> None:
    @app.cli.command("blockchain-process")
    @click.option("--limit", default=50, type=click.IntRange(1, 500))
    def blockchain_process_command(limit: int):
        result = process_pending_transactions(db.session, current_app.config, limit=limit)
        click.echo(result)

    @app.cli.command("blockchain-anchor-audit")
    @click.option("--start", required=True, help="UTC ISO-8601 period start")
    @click.option("--end", required=True, help="UTC ISO-8601 period end")
    def blockchain_anchor_audit_command(start: str, end: str):
        from datetime import datetime

        anchor = create_audit_anchor(
            db.session,
            period_start=datetime.fromisoformat(start.replace("Z", "+00:00")),
            period_end=datetime.fromisoformat(end.replace("Z", "+00:00")),
            config=current_app.config,
        )
        db.session.commit()
        click.echo({"anchor_id": str(anchor.public_id), "event_count": anchor.event_count})

    @app.cli.command("blockchain-worker")
    @click.option("--once", is_flag=True, help="Process one cycle and exit")
    @click.option("--interval", default=30, type=click.IntRange(5, 3600))
    @click.option("--limit", default=50, type=click.IntRange(1, 500))
    def blockchain_worker_command(once: bool, interval: int, limit: int):
        """Background outbox worker with periodic Merkle-root anchoring."""
        import time

        if not current_app.config.get("BLOCKCHAIN_ENABLED"):
            raise click.ClickException("BLOCKCHAIN_ENABLED must be true to run the worker")
        while True:
            anchor = create_due_audit_anchor(db.session, current_app.config)
            db.session.commit()
            result = process_pending_transactions(db.session, current_app.config, limit=limit)
            click.echo({"anchor_id": str(anchor.public_id), **result})
            if once:
                return
            time.sleep(interval)
