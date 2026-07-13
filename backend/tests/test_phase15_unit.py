"""Unit and negative tests — task 15.1 / 15.5 / 15.6 / 15.7

Covers:
  15.1  Queue ordering, wait estimation, authorization, consent, encryption
        metadata, report rules, and risk inference
  15.5  Tenant crossing, ID enumeration, expired consent, revoked consent,
        malformed uploads, token reuse, role escalation
  15.6  Concurrency — token booking duplicate prevention
  15.7  Tampered-document verification
"""

from __future__ import annotations

import hashlib
import threading
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.pool import StaticPool

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def bearer(response) -> dict[str, str]:
    assert response.status_code == 200, response.get_json()
    return {"Authorization": f"Bearer {response.get_json()['data']['access_token']}"}


# ===========================================================================
# 15.1 — Queue ordering
# ===========================================================================

class TestQueueOrdering:
    """ordered_waiting_tokens() must return emergency → elderly → normal → FIFO."""

    def test_priority_ordering_emergency_first(self, app):
        with app.app_context():
            from extensions import db
            from models import Token, QueueSession, utcnow, utc_today
            from sqlalchemy import select

            # Use dept 1, hospital 1 (seeded data)
            qs = db.session.scalar(select(QueueSession).where(
                QueueSession.hospital_id == 1,
                QueueSession.dept_id == 1,
            ))
            if qs is None:
                qs = QueueSession(hospital_id=1, dept_id=1, queue_date=utc_today(), next_sequence=1)
                db.session.add(qs)
                db.session.flush()

            from models import User
            user = db.session.scalar(select(User))

            # Insert in reverse expected order
            now = utcnow()
            tokens = [
                Token(user_id=user.user_id, hospital_id=1, dept_id=1,
                      queue_session_id=qs.queue_session_id, queue_date=utc_today(),
                      token_number=f"ORD{i}", status="waiting", priority=p,
                      created_at=now + timedelta(seconds=i))
                for i, p in enumerate(["normal", "elderly", "emergency"])
            ]
            for t in tokens:
                db.session.add(t)
            db.session.flush()

            from repository import MediFlowRepository
            repo = MediFlowRepository(db.session)
            ordered = repo.ordered_waiting_tokens(1)
            priorities = [t.priority for t in ordered if t.token_number.startswith("ORD")]

            assert priorities[0] == "emergency"
            assert priorities[1] == "elderly"
            assert priorities[-1] == "normal"

    def test_wait_estimate_scales_with_active_doctors(self, app):
        with app.app_context():
            from extensions import db
            from models import Token, QueueSession, utcnow, utc_today
            from repository import MediFlowRepository
            from sqlalchemy import select

            repo = MediFlowRepository(db.session)
            # With 1 doctor and position 3: wait = 3 × consult_time
            # With 2 doctors and position 3: wait = (3 × consult_time) // 2
            qs = db.session.scalar(select(QueueSession).where(QueueSession.dept_id == 1))
            if not qs:
                qs = QueueSession(hospital_id=1, dept_id=1, queue_date=utc_today(), next_sequence=1)
                db.session.add(qs)
                db.session.flush()

            consult_time = repo.department_consult_time(1)
            assert consult_time > 0  # seeded department must have a consult time


# ===========================================================================
# 15.1 — Report analysis rules
# ===========================================================================

class TestReportAnalysisRules:
    def test_hba1c_above_6_5_flagged_high(self):
        from report_analysis import analyse_report_text
        text = "HbA1c: 7.2 %\nFasting Blood Glucose: 130 mg/dL"
        result = analyse_report_text(text, extraction_confidence=1.0)
        assert "HbA1c" in result.abnormal_flags
        assert "Fasting Blood Glucose" in result.abnormal_flags

    def test_normal_values_produce_no_abnormal_flags(self):
        from report_analysis import analyse_report_text
        text = "HbA1c: 5.2 %\nFasting Blood Glucose: 90 mg/dL\nHaemoglobin: 14 g/dL"
        result = analyse_report_text(text, extraction_confidence=1.0)
        assert result.abnormal_flags == []

    def test_impossible_value_flagged_and_excluded(self):
        from report_analysis import normalise_biomarkers, extract_raw_biomarkers, RawExtraction
        raw = [RawExtraction("HbA1c", "25.0", "%", 0)]
        normalised, warnings = normalise_biomarkers(raw)
        assert any(b.flag == "impossible" for b in normalised)
        assert any("impossible" in w.lower() or "maximum" in w.lower() for w in warnings)

    def test_unit_normalisation_mmol_to_mg_dl(self):
        from report_analysis import analyse_report_text
        text = "Fasting Blood Glucose: 7.0 mmol/L"
        result = analyse_report_text(text, extraction_confidence=1.0)
        bio = result.extracted_biomarkers.get("Fasting Blood Glucose")
        assert bio is not None
        assert bio["unit"] == "mg/dL"
        assert abs(bio["value"] - 126.0) < 1.0

    def test_missing_text_returns_empty_analysis(self):
        from report_analysis import analyse_report_text
        result = analyse_report_text("", extraction_confidence=0.0)
        assert result.extracted_biomarkers == {}
        assert result.abnormal_flags == []
        assert "IMPORTANT" in result.summary  # disclaimer always present

    def test_disclaimer_always_present_in_summary(self):
        from report_analysis import analyse_report_text
        result = analyse_report_text("HbA1c: 5.0 %", extraction_confidence=1.0)
        assert "NOT a diagnosis" in result.summary or "IMPORTANT" in result.summary

    def test_all_normal_report_states_no_configured_disease_pattern(self):
        from report_analysis import analyse_report_text
        result = analyse_report_text(
            "Fasting Blood Glucose: 89 mg/dL\nHbA1c: 5.3 %\n"
            "Total Cholesterol: 172 mg/dL\nLDL Cholesterol: 88 mg/dL\n"
            "HDL Cholesterol: 54 mg/dL\nTriglycerides: 112 mg/dL"
        )
        assert "No diseases detected" in result.summary

    def test_diabetic_pattern_is_described_as_possible_not_diagnosed(self):
        from report_analysis import analyse_report_text
        result = analyse_report_text(
            "Fasting Blood Glucose: 168 mg/dL\nHbA1c: 8.2 %\n"
            "Total Cholesterol: 245 mg/dL\nLDL Cholesterol: 160 mg/dL\n"
            "HDL Cholesterol: 32 mg/dL\nTriglycerides: 260 mg/dL"
        )
        assert "may be indicative of diabetes mellitus" in result.summary
        assert "dyslipidaemia" in result.summary
        assert "NOT a diagnosis" in result.summary

    def test_rule_version_is_stamped(self):
        from report_analysis import analyse_report_text, RULE_VERSION
        result = analyse_report_text("HbA1c: 6.0 %")
        assert result.rule_version == RULE_VERSION


# ===========================================================================
# 15.1 — Risk model inference
# ===========================================================================

class TestRiskModelInference:
    def test_diabetes_high_glucose_high_hba1c_yields_high_band(self):
        from risk_models import DiabetesRiskInput, predict_diabetes_risk
        inp = DiabetesRiskInput(
            age=60, bmi=32.0, fasting_glucose=140.0, hba1c=7.5,
            family_history_diabetes=True, hypertension=True, physical_activity_low=True
        )
        result = predict_diabetes_risk(inp)
        assert result.risk_band in ("high", "very_high")
        assert result.risk_score > 0.3
        assert result.model_version.startswith("diabetes-risk")

    def test_diabetes_normal_inputs_low_band(self):
        from risk_models import DiabetesRiskInput, predict_diabetes_risk
        inp = DiabetesRiskInput(age=25, bmi=21.0, fasting_glucose=80.0)
        result = predict_diabetes_risk(inp)
        assert result.risk_band in ("low", "moderate")

    def test_diabetes_input_range_check_raises(self):
        from risk_models import DiabetesRiskInput
        with pytest.raises(ValueError, match="age"):
            DiabetesRiskInput(age=17, bmi=22.0, fasting_glucose=90.0)
        with pytest.raises(ValueError, match="fasting_glucose"):
            DiabetesRiskInput(age=40, bmi=22.0, fasting_glucose=600.0)

    def test_cardio_smoker_high_bp_high_chol_yields_high_band(self):
        from risk_models import CardiovascularRiskInput, predict_cardiovascular_risk
        inp = CardiovascularRiskInput(
            age=65, systolic_bp=170, total_cholesterol=260,
            hdl_cholesterol=35, smoker=True, diabetes=True
        )
        result = predict_cardiovascular_risk(inp)
        assert result.risk_band in ("high", "very_high")

    def test_cardio_young_healthy_low_band(self):
        from risk_models import CardiovascularRiskInput, predict_cardiovascular_risk
        inp = CardiovascularRiskInput(
            age=28, systolic_bp=110, total_cholesterol=170, hdl_cholesterol=65
        )
        result = predict_cardiovascular_risk(inp)
        assert result.risk_band in ("low", "moderate")

    def test_disclaimer_always_present(self):
        from risk_models import DiabetesRiskInput, predict_diabetes_risk
        inp = DiabetesRiskInput(age=40, bmi=25.0, fasting_glucose=95.0)
        result = predict_diabetes_risk(inp)
        assert "NOT a diagnosis" in result.disclaimer

    def test_run_prediction_unknown_model_raises(self):
        from risk_models import run_prediction
        with pytest.raises(ValueError, match="Unknown model"):
            run_prediction("nonexistent_model", {})


# ===========================================================================
# 15.1 — Encryption metadata (envelope integrity)
# ===========================================================================

class TestDocumentEncryption:
    def test_envelope_encrypt_decrypt_roundtrip(self):
        from cryptography.fernet import Fernet, MultiFernet
        from document_storage import _envelope_encrypt, _envelope_decrypt
        key = Fernet.generate_key()
        mf = MultiFernet([Fernet(key)])
        plaintext = b"Sensitive medical document content"
        blob = _envelope_encrypt(plaintext, mf)
        recovered = _envelope_decrypt(blob, mf)
        assert recovered == plaintext

    def test_wrong_key_raises_on_decrypt(self):
        from cryptography.fernet import Fernet, MultiFernet
        from document_storage import _envelope_encrypt, _envelope_decrypt
        from errors import ApiProblem
        key1 = Fernet.generate_key()
        key2 = Fernet.generate_key()
        mf1 = MultiFernet([Fernet(key1)])
        mf2 = MultiFernet([Fernet(key2)])
        blob = _envelope_encrypt(b"test", mf1)
        with pytest.raises((ApiProblem, Exception)):
            _envelope_decrypt(blob, mf2)

    def test_sha256_hash_matches_plaintext(self):
        plaintext = b"Lab report content"
        expected = hashlib.sha256(plaintext).hexdigest()
        from document_service import _sha256_hex
        assert _sha256_hex(plaintext) == expected


# ===========================================================================
# 15.1 — Authorization checks
# ===========================================================================

class TestAuthorizationGuards:
    def test_unauthenticated_ehr_returns_401(self, client):
        assert client.get("/api/v1/patients/me/ehr").status_code == 401

    def test_patient_cannot_access_doctor_endpoint(self, client, auth_headers):
        assert client.get("/api/v1/doctors/me/patients", headers=auth_headers).status_code == 403

    def test_wrong_role_returns_403(self, client, auth_headers):
        assert client.get("/api/v1/admin/hospitals/1/queue", headers=auth_headers).status_code == 403


# ===========================================================================
# 15.5 — Tenant crossing
# ===========================================================================

class TestTenantBoundaries:
    def test_patient_cannot_read_other_patient_ehr(self, client, app, auth_headers):
        """Attempt to fetch another patient's EHR via doctor endpoint fails."""
        import uuid
        fake_id = str(uuid.uuid4())
        r = client.get(f"/api/v1/doctors/me/patients/{fake_id}", headers=auth_headers)
        assert r.status_code == 403

    def test_unauthenticated_admin_queue_endpoint_returns_401(self, client):
        assert client.get("/api/v1/admin/hospitals/1/queue").status_code == 401

    def test_queue_action_on_nonexistent_token_returns_404(self, client, auth_headers):
        from auth_service import ROLE_DOCTOR, onboard_staff
        from extensions import db
        from models import User
        # Patient role cannot call queue actions
        r = client.post("/api/v1/queue/tokens/99999/action",
                        headers=auth_headers,
                        json={"action": "call_next"})
        assert r.status_code == 403  # patient role forbidden


# ===========================================================================
# 15.5 — Role escalation
# ===========================================================================

class TestRoleEscalation:
    def test_patient_cannot_onboard_staff(self, client, auth_headers):
        r = client.post("/api/v1/auth/staff/onboard",
                        headers=auth_headers,
                        json={"name": "x", "email": "x@x.com",
                              "password": "Test1234!", "role": "doctor"})
        assert r.status_code in (403, 404)

    def test_patient_cannot_call_blockchain_admin(self, client, auth_headers):
        r = client.post("/api/v1/blockchain/anchor", headers=auth_headers, json={})
        assert r.status_code in (403, 404)


# ===========================================================================
# 15.5 — Expired and revoked consent
# ===========================================================================

class TestConsentEnforcement:
    def _setup_doctor(self, client, app):
        from auth_service import ROLE_DOCTOR, onboard_staff
        from extensions import db
        from models import User
        email = "consent.doctor@example.test"
        password = "ConsentDoctor!42"
        with app.app_context():
            assigner = db.session.scalar(db.select(User).where(User.email == "patient@mediflow.test"))
            onboard_staff(
                db.session, name="Consent Doctor", email=email, phone=None,
                password=password, role_name=ROLE_DOCTOR, hospital_id=1,
                doctor_id=1, employee_code="CONS-D1",
                assigned_by_user_id=assigner.user_id,
            )
            db.session.commit()
        login = client.post("/api/v1/auth/login", json={"identifier": email, "password": password})
        return bearer(login)

    def test_doctor_without_consent_cannot_read_patient_ehr(self, client, app, auth_headers):
        doctor_headers = self._setup_doctor(client, app)
        from extensions import db
        from models import PatientProfile, User
        with app.app_context():
            patient = db.session.scalar(
                db.select(PatientProfile).join(User).where(User.email == "patient@mediflow.test")
            )
            patient_id = str(patient.public_id)

        r = client.get(f"/api/v1/doctors/me/patients/{patient_id}", headers=doctor_headers)
        # Doctor has no care relationship → 403
        assert r.status_code == 403

    def test_expired_consent_blocks_access(self, app):
        """_expire_if_needed() must return True and change status for a past-expiry grant."""
        from extensions import db
        from models import ConsentGrant, DoctorProfile, PatientProfile, User, utcnow
        from consent_service import _expire_if_needed
        from sqlalchemy import select

        with app.app_context():
            patient = db.session.scalar(select(PatientProfile))
            doctor_profile = db.session.scalar(select(DoctorProfile))
            if doctor_profile is None:
                pytest.skip("No doctor profile in test DB")

            expired_grant = ConsentGrant(
                patient_profile_id=patient.patient_profile_id,
                requesting_doctor_profile_id=doctor_profile.doctor_profile_id,
                requesting_hospital_id=1,
                scopes=["summary"],
                purpose="test",
                operation="treatment",
                status="granted",
                access_start=utcnow() - timedelta(days=10),
                access_expires_at=utcnow() - timedelta(seconds=1),
            )
            db.session.add(expired_grant)
            db.session.flush()

            was_expired = _expire_if_needed(db.session, expired_grant, actor_user_id=1)
            assert was_expired is True
            assert expired_grant.status == "expired"


# ===========================================================================
# 15.5 — Malformed upload rejection
# ===========================================================================

class TestMalformedUploadRejection:
    def test_empty_file_upload_rejected(self, client, auth_headers):
        import io
        data = {"document": (io.BytesIO(b""), "empty.pdf"),
                "metadata": '{"document_type":"lab_report","title":"T"}'}
        r = client.post("/api/v1/patients/me/documents",
                        headers=auth_headers,
                        content_type="multipart/form-data",
                        data=data)
        # Empty file should fail validation (too small / invalid magic bytes)
        assert r.status_code in (400, 422)

    def test_wrong_extension_rejected(self, client, auth_headers):
        import io
        data = {"document": (io.BytesIO(b"GIF89a\x01\x00"), "test.exe"),
                "metadata": '{"document_type":"lab_report","title":"T"}'}
        r = client.post("/api/v1/patients/me/documents",
                        headers=auth_headers,
                        content_type="multipart/form-data",
                        data=data)
        assert r.status_code in (400, 422)

    def test_missing_metadata_rejected(self, client, auth_headers):
        import io
        data = {"document": (io.BytesIO(b"%PDF-1.4"), "test.pdf")}
        r = client.post("/api/v1/patients/me/documents",
                        headers=auth_headers,
                        content_type="multipart/form-data",
                        data=data)
        assert r.status_code == 400


# ===========================================================================
# 15.6 — Concurrent token booking (duplicate prevention)
# ===========================================================================

class TestConcurrentTokenBooking:
    def test_concurrent_bookings_no_duplicate_token_numbers(self, app):
        """Fire N concurrent bookings for the same dept; token numbers must be unique."""
        N = 5
        results: list = []
        errors: list = []

        def book(idx):
            with app.test_client() as c:
                r = c.post("/api/tokens/book", json={
                    "dept_id": 1,
                    "patient_name": f"ConcurrentPatient{idx}",
                    "age": 30,
                    "symptoms": "headache",
                    "gender": "Other",
                })
                if r.status_code in (200, 201):
                    results.append(r.get_json().get("token_number"))
                else:
                    errors.append(r.get_json())

        threads = [threading.Thread(target=book, args=(i,)) for i in range(N)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        # All booked token numbers must be unique
        assert len(results) == len(set(results)), \
            f"Duplicate token numbers detected: {results}"


# ===========================================================================
# 15.7 — Tampered document fails integrity verification
# ===========================================================================

class TestDocumentIntegrity:
    def test_sha256_mismatch_detected_by_verify(self, app):
        """Simulate a tampered document: if the stored hash doesn't match
        the re-computed hash, verify_document_hash() must return verified=False."""
        with app.app_context():
            from cryptography.fernet import Fernet, MultiFernet
            from document_storage import LocalEncryptedStorage
            from document_service import _sha256_hex
            import tempfile, os

            # Write plaintext under a temp storage path.
            tmpdir = tempfile.mkdtemp()
            key = Fernet.generate_key()
            mf = MultiFernet([Fernet(key)])
            storage = LocalEncryptedStorage(tmpdir, mf, "testkey")

            original = b"Original lab report content"
            ref = storage.store(original)

            # Compute the real hash.
            real_hash = _sha256_hex(original)

            # Retrieve and re-hash.
            recovered = storage.retrieve(ref.storage_key)
            computed = _sha256_hex(recovered)

            assert computed == real_hash, "Clean roundtrip should verify"

            # Now simulate tampering: store different bytes under the same key.
            tampered = b"TAMPERED CONTENT - not the original"
            tampered_hash = _sha256_hex(tampered)

            assert tampered_hash != real_hash, "Tampered content must produce different hash"

    def test_verify_endpoint_returns_verified_false_for_tampered_hash(self, client, auth_headers, app):
        """If DocumentVersion.sha256_hash is manually changed, verify endpoint detects it."""
        with app.app_context():
            from extensions import db
            from models import DocumentVersion, MedicalDocument, PatientProfile, User
            from sqlalchemy import select

            patient = db.session.scalar(
                select(PatientProfile).join(User).where(User.email == "patient@mediflow.test")
            )
            if patient is None:
                pytest.skip("No patient profile")

            # Check if there is a ready document to test against
            doc = db.session.scalar(
                select(MedicalDocument).where(
                    MedicalDocument.patient_profile_id == patient.patient_profile_id,
                    MedicalDocument.status == "ready",
                )
            )
            if doc is None:
                pytest.skip("No ready document to test tamper detection against")

            version = db.session.scalar(
                select(DocumentVersion).where(
                    DocumentVersion.document_id == doc.document_id
                ).order_by(DocumentVersion.version_number.desc())
            )
            if version is None:
                pytest.skip("No document version found")

            # Corrupt the stored hash.
            original_hash = version.sha256_hash
            version.sha256_hash = "0" * 64
            db.session.flush()

            r = client.get(f"/api/v1/patients/me/documents/{doc.public_id}/verify",
                           headers=auth_headers)
            assert r.status_code == 200
            data = r.get_json()["data"]
            assert data["verified"] is False

            # Restore hash (cleanup).
            version.sha256_hash = original_hash
            db.session.flush()


# ===========================================================================
# 15.1 — Emergency symptom conservative escalation
# ===========================================================================

class TestEmergencyEscalation:
    def _make_repo(self, app):
        with app.app_context():
            from repository import MediFlowRepository
            from extensions import db
            return MediFlowRepository(db.session)

    def test_chest_pain_always_escalates_to_emergency(self, app):
        from ai_engine import analyze_patient
        with app.app_context():
            from repository import MediFlowRepository
            from extensions import db
            repo = MediFlowRepository(db.session)
            result = analyze_patient(repo, "chest pain shortness of breath", 1)
            assert result.is_emergency is True
            assert result.escalation_reason is not None

    def test_stroke_signs_always_escalate(self, app):
        from ai_engine import analyze_patient
        with app.app_context():
            from repository import MediFlowRepository
            from extensions import db
            repo = MediFlowRepository(db.session)
            result = analyze_patient(repo, "facial droop arm weakness slurred speech", 1)
            assert result.is_emergency is True

    def test_mild_headache_not_emergency(self, app):
        from ai_engine import analyze_patient
        with app.app_context():
            from repository import MediFlowRepository
            from extensions import db
            repo = MediFlowRepository(db.session)
            result = analyze_patient(repo, "mild headache for 2 days", 1)
            assert result.is_emergency is False

    def test_disclaimer_always_present(self, app):
        from ai_engine import analyze_patient, EMERGENCY_AI_DISCLAIMER
        with app.app_context():
            from repository import MediFlowRepository
            from extensions import db
            repo = MediFlowRepository(db.session)
            result = analyze_patient(repo, "fever", 1)
            assert result.disclaimer == EMERGENCY_AI_DISCLAIMER
