"""Pydantic request and response contracts for `/api/v1`."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal, TypeVar
from uuid import UUID

from flask import request
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from errors import ApiProblem


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PaginationQuery(StrictSchema):
    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=25, ge=1, le=100)
    sort_order: Literal["asc", "desc"] = "desc"
    search: str | None = Field(default=None, max_length=100)
    date_from: date | None = None
    date_to: date | None = None

    @model_validator(mode="after")
    def validate_date_range(self):
        if self.date_from and self.date_to and self.date_to < self.date_from:
            raise ValueError("date_to must be on or after date_from")
        return self


class DepartmentQuery(StrictSchema):
    dept_id: int = Field(gt=0)


class OptionalDepartmentQuery(StrictSchema):
    dept_id: int | None = Field(default=None, gt=0)


class HospitalQuery(StrictSchema):
    hospital_id: int = Field(default=1, gt=0)


class AIReportQuery(DepartmentQuery):
    token: str | None = Field(default=None, max_length=24)
    symptoms: str = Field(min_length=1, max_length=2000)
    age: int = Field(ge=0, le=130)


class AnalyzeQuery(DepartmentQuery):
    symptoms: str = Field(min_length=1, max_length=2000)


class ElderlyQuery(StrictSchema):
    age: int = Field(ge=0, le=130)


class PriorityQuery(StrictSchema):
    dept_id: int = Field(default=1, gt=0)
    age: int = Field(ge=0, le=130)
    symptoms: str = Field(default="", max_length=2000)


class PositionQuery(DepartmentQuery):
    token: str = Field(min_length=1, max_length=24)


class UserPaginationQuery(PaginationQuery):
    user_id: int | None = Field(default=None, gt=0)


class BookTokenRequest(StrictSchema):
    dept_id: int = Field(gt=0)
    patient_name: str = Field(min_length=1, max_length=120)
    age: int = Field(ge=0, le=130)
    phone: str | None = Field(default=None, min_length=7, max_length=32)
    gender: str = Field(default="Other", max_length=32)
    symptoms: str = Field(default="", max_length=2000)

    @field_validator("phone")
    @classmethod
    def phone_characters(cls, value: str | None):
        if value and not all(character.isdigit() or character in "+- ()" for character in value):
            raise ValueError("phone contains unsupported characters")
        return value


class SymptomsHistoryRequest(StrictSchema):
    user_id: int | None = Field(default=None, gt=0)
    symptoms: str = Field(min_length=1, max_length=2000)
    severity_score: int | None = Field(default=None, ge=0, le=100)
    predicted_department: str | None = Field(default=None, max_length=120)
    visit_date: date | None = None


class AppointmentRequest(StrictSchema):
    user_id: int = Field(gt=0)
    doctor_id: int = Field(gt=0)
    appointment_date: date
    appointment_time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d(?::[0-5]\d)?$")
    status: str = Field(default="Booked", max_length=32)


class FeedbackRequest(StrictSchema):
    user_id: int = Field(gt=0)
    rating: int = Field(ge=1, le=5)
    feedback_text: str | None = Field(default=None, max_length=2000)


def _validate_password_strength(value: str) -> str:
    if len(value) < 12:
        raise ValueError("password must contain at least 12 characters")
    checks = [
        any(character.islower() for character in value),
        any(character.isupper() for character in value),
        any(character.isdigit() for character in value),
        any(not character.isalnum() for character in value),
    ]
    if not all(checks):
        raise ValueError("password must include uppercase, lowercase, number, and symbol")
    return value


class PatientRegisterRequest(StrictSchema):
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=255, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    phone: str | None = Field(default=None, min_length=7, max_length=32)
    password: str = Field(min_length=12, max_length=128)
    age: int | None = Field(default=None, ge=0, le=130)
    gender: str | None = Field(default=None, max_length=32)

    @field_validator("password")
    @classmethod
    def password_strength(cls, value: str):
        return _validate_password_strength(value)


class LoginRequest(StrictSchema):
    identifier: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=128)


class PasswordResetRequest(StrictSchema):
    identifier: str = Field(min_length=3, max_length=255)


class PasswordResetConfirmRequest(StrictSchema):
    token: str = Field(min_length=32, max_length=256)
    new_password: str = Field(min_length=12, max_length=128)

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, value: str):
        return _validate_password_strength(value)


class AccountActivationConfirmRequest(StrictSchema):
    token: str = Field(min_length=32, max_length=256)


class EncounterCreateRequest(StrictSchema):
    patient_id: UUID
    appointment_id: int | None = Field(default=None, gt=0)
    token_id: int | None = Field(default=None, gt=0)
    encounter_type: Literal["outpatient", "emergency", "inpatient", "telemedicine"] = "outpatient"
    chief_complaint: str | None = Field(default=None, max_length=2000)
    reason: str = Field(min_length=3, max_length=500)

    @model_validator(mode="after")
    def source_required(self):
        if self.appointment_id is None and self.token_id is None:
            raise ValueError("appointment_id or token_id is required to establish the care relationship")
        return self


class EncounterUpdateRequest(StrictSchema):
    clinical_notes: str | None = Field(default=None, max_length=10000)
    status: Literal["planned", "in_progress", "completed", "cancelled"] | None = None
    reason: str = Field(min_length=3, max_length=500)

    @model_validator(mode="after")
    def update_required(self):
        if self.clinical_notes is None and self.status is None:
            raise ValueError("clinical_notes or status is required")
        return self


class DiagnosisCreateRequest(StrictSchema):
    code: str | None = Field(default=None, max_length=32)
    description: str = Field(min_length=2, max_length=500)
    review_status: Literal["draft", "confirmed"] = "draft"
    reason: str = Field(min_length=3, max_length=500)


class DiagnosisStatusRequest(StrictSchema):
    review_status: Literal["draft", "confirmed", "rejected"]
    reason: str = Field(min_length=3, max_length=500)


class PrescriptionCreateRequest(StrictSchema):
    medicine: str = Field(min_length=2, max_length=200)
    dosage: str = Field(min_length=1, max_length=120)
    frequency: str = Field(min_length=1, max_length=120)
    duration: str = Field(min_length=1, max_length=120)
    instructions: str | None = Field(default=None, max_length=2000)
    reason: str = Field(min_length=3, max_length=500)


class PrescriptionStatusRequest(StrictSchema):
    status: Literal["active", "completed", "cancelled"]
    reason: str = Field(min_length=3, max_length=500)


class AllergyCreateRequest(StrictSchema):
    substance: str = Field(min_length=2, max_length=160)
    severity: Literal["unknown", "mild", "moderate", "severe"] = "unknown"
    reaction: str | None = Field(default=None, max_length=500)
    verification_status: Literal["unverified", "confirmed"] = "confirmed"
    source: str = Field(default="clinician_recorded", min_length=2, max_length=80)
    reason: str = Field(min_length=3, max_length=500)


class VaccinationCreateRequest(StrictSchema):
    vaccine_name: str = Field(min_length=2, max_length=200)
    administered_on: date
    dose_number: str | None = Field(default=None, max_length=40)
    lot_number: str | None = Field(default=None, max_length=80)
    provider_name: str | None = Field(default=None, max_length=160)
    source: str = Field(default="provider_recorded", min_length=2, max_length=80)
    verification_status: Literal["unverified", "confirmed"] = "confirmed"
    reason: str = Field(min_length=3, max_length=500)


class ProfileUpdateRequest(StrictSchema):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    email: str | None = Field(default=None, min_length=5, max_length=255, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    phone: str | None = Field(default=None, min_length=7, max_length=32)
    age: int | None = Field(default=None, ge=0, le=130)
    gender: str | None = Field(default=None, max_length=32)

    @model_validator(mode="after")
    def at_least_one_field(self):
        if not self.model_fields_set:
            raise ValueError("at least one profile field is required")
        return self


class AccountDeleteRequest(StrictSchema):
    password: str = Field(min_length=1, max_length=128)
    confirmation: Literal["DELETE"]


class StaffOnboardRequest(StrictSchema):
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=255, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    phone: str | None = Field(default=None, min_length=7, max_length=32)
    password: str = Field(min_length=12, max_length=128)
    role: Literal["doctor", "hospital_admin", "security_admin"]
    hospital_id: int | None = Field(default=None, gt=0)
    doctor_id: int | None = Field(default=None, gt=0)
    employee_code: str | None = Field(default=None, max_length=80)

    @field_validator("password")
    @classmethod
    def password_strength(cls, value: str):
        return _validate_password_strength(value)


class UserStatusRequest(StrictSchema):
    is_active: bool
    reason: str = Field(min_length=3, max_length=200)


class ApiMeta(BaseModel):
    model_config = ConfigDict(extra="allow")
    request_id: str
    timestamp: str


class SuccessEnvelope(BaseModel):
    status: Literal["success"] = "success"
    data: Any
    meta: ApiMeta


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[dict[str, Any]] = Field(default_factory=list)


class ErrorEnvelope(BaseModel):
    status: Literal["error"] = "error"
    error: ErrorBody
    meta: ApiMeta


SchemaT = TypeVar("SchemaT", bound=BaseModel)


def _safe_validation_details(error: ValidationError) -> list[dict[str, Any]]:
    return [
        {
            "field": ".".join(str(part) for part in item["loc"]),
            "message": item["msg"],
            "type": item["type"],
        }
        for item in error.errors(include_input=False, include_url=False)
    ]


def validate_query(schema: type[SchemaT]) -> SchemaT:
    try:
        return schema.model_validate(request.args.to_dict(flat=True))
    except ValidationError as error:
        raise ApiProblem(
            "validation_error",
            "Query parameters are invalid",
            422,
            _safe_validation_details(error),
        ) from error


def validate_json(schema: type[SchemaT]) -> SchemaT:
    payload = request.get_json(silent=True)
    if payload is None:
        raise ApiProblem("invalid_json", "A JSON request body is required", 400)
    try:
        return schema.model_validate(payload)
    except ValidationError as error:
        raise ApiProblem(
            "validation_error",
            "Request body is invalid",
            422,
            _safe_validation_details(error),
        ) from error


# ---------------------------------------------------------------------------
# Task 5: Encrypted document pipeline schemas
# ---------------------------------------------------------------------------

class DocumentUploadMetadata(StrictSchema):
    """JSON metadata submitted alongside the multipart file upload."""

    document_type: Literal[
        "lab_report",
        "imaging",
        "prescription",
        "discharge_summary",
        "referral",
        "vaccination_certificate",
        "insurance",
        "other",
    ]
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    document_date: date | None = None
    encounter_id: int | None = Field(default=None, gt=0)


class DocumentVerifyRequest(StrictSchema):
    """Request body for a doctor marking a document as clinically verified."""

    notes: str | None = Field(default=None, max_length=2000)


class AnalysisReviewRequest(StrictSchema):
    """Request body for a doctor reviewing an AI analysis result."""

    review_status: Literal["accepted", "rejected", "corrected"]
    reviewer_notes: str | None = Field(default=None, max_length=2000)


# ---------------------------------------------------------------------------
# Task 6: Risk prediction and analysis review schemas
# ---------------------------------------------------------------------------

class DiabetesRiskRequest(StrictSchema):
    """Input for the diabetes risk model (task 6.8)."""

    age: float = Field(ge=18, le=100)
    bmi: float = Field(ge=10, le=70)
    fasting_glucose: float = Field(ge=50, le=500, description="mg/dL")
    hba1c: float | None = Field(default=None, ge=3, le=15, description="% (optional)")
    family_history_diabetes: bool = False
    hypertension: bool = False
    physical_activity_low: bool = False
    source_document_id: UUID | None = None  # optional link to an uploaded lab report


class CardiovascularRiskRequest(StrictSchema):
    """Input for the cardiovascular risk model (task 6.8)."""

    age: float = Field(ge=18, le=100)
    systolic_bp: float = Field(ge=70, le=250, description="mmHg")
    total_cholesterol: float = Field(ge=50, le=500, description="mg/dL")
    hdl_cholesterol: float = Field(ge=10, le=200, description="mg/dL")
    smoker: bool = False
    diabetes: bool = False
    hypertension_treatment: bool = False
    source_document_id: UUID | None = None


class RiskPredictionReviewRequest(StrictSchema):
    """Doctor review of a stored risk prediction (task 6.16)."""

    review_status: Literal["accepted", "rejected", "corrected"]
    reviewer_notes: str | None = Field(default=None, max_length=2000)


# ---------------------------------------------------------------------------
# Task 7: Consent and authorization domain schemas
# ---------------------------------------------------------------------------

class ConsentRequestCreate(StrictSchema):
    """Doctor submits an access request for a patient's records."""

    patient_id: UUID                  # patient public_id
    scopes: list[Literal[
        "summary", "encounters", "diagnoses", "prescriptions",
        "allergies", "vaccinations", "reports", "risk_predictions", "monitoring",
    ]] = Field(min_length=1)
    purpose: str = Field(min_length=10, max_length=500)
    operation: Literal[
        "treatment", "second_opinion", "research_review", "referral", "emergency", "other"
    ] = "treatment"
    # How many days of access the doctor is requesting (patient can shorten this on grant).
    requested_duration_days: int = Field(default=30, ge=1, le=365)

    @field_validator("scopes")
    @classmethod
    def no_duplicate_scopes(cls, v: list) -> list:
        if len(v) != len(set(v)):
            raise ValueError("scopes must not contain duplicates")
        return v


class ConsentGrantRequest(StrictSchema):
    """Patient grants a pending consent request."""

    # Patient can narrow the scopes from what the doctor requested.
    scopes: list[Literal[
        "summary", "encounters", "diagnoses", "prescriptions",
        "allergies", "vaccinations", "reports", "risk_predictions", "monitoring",
    ]] = Field(min_length=1)
    # Patient sets the actual expiry (must be in the future, max 365 days).
    access_expires_days: int = Field(default=30, ge=1, le=365)

    @field_validator("scopes")
    @classmethod
    def no_duplicate_scopes(cls, v: list) -> list:
        if len(v) != len(set(v)):
            raise ValueError("scopes must not contain duplicates")
        return v


class ConsentDenyRequest(StrictSchema):
    """Patient denies a pending consent request."""

    reason: str | None = Field(default=None, max_length=500)


class ConsentRevokeRequest(StrictSchema):
    """Patient revokes a previously granted consent."""

    reason: str | None = Field(default=None, max_length=500)


class BreakGlassRequest(StrictSchema):
    """Doctor invokes emergency break-glass access (7.7).

    Requires a mandatory clinical reason. Duration is capped server-side
    at BREAK_GLASS_DURATION_HOURS (4 hours).
    """

    patient_id: UUID
    scopes: list[Literal[
        "summary", "encounters", "diagnoses", "prescriptions",
        "allergies", "vaccinations", "reports", "risk_predictions", "monitoring",
    ]] = Field(min_length=1)
    reason: str = Field(
        min_length=20, max_length=1000,
        description="Mandatory clinical justification for emergency access",
    )

    @field_validator("scopes")
    @classmethod
    def no_duplicate_scopes(cls, v: list) -> list:
        if len(v) != len(set(v)):
            raise ValueError("scopes must not contain duplicates")
        return v


class MarkNotificationReadRequest(StrictSchema):
    """Mark one or more notifications as read."""

    notification_ids: list[UUID] = Field(min_length=1, max_length=50)


class AuditAnchorRequest(StrictSchema):
    period_start: datetime
    period_end: datetime

    @model_validator(mode="after")
    def positive_period(self):
        if self.period_end <= self.period_start:
            raise ValueError("period_end must be after period_start")
        return self


# ---------------------------------------------------------------------------
# Task 9: Cross-hospital sharing schemas
# ---------------------------------------------------------------------------

class CrossHospitalShareRequest(StrictSchema):
    """Doctor at requesting hospital submits a cross-hospital share request."""

    patient_id: UUID                  # patient public_id
    source_hospital_id: int = Field(gt=0)
    scopes: list[Literal[
        "summary", "encounters", "diagnoses", "prescriptions",
        "allergies", "vaccinations", "reports", "risk_predictions", "monitoring",
    ]] = Field(min_length=1)
    purpose: str = Field(min_length=10, max_length=500)
    operation: Literal[
        "treatment", "second_opinion", "research_review", "referral", "emergency", "other"
    ] = "treatment"
    requested_duration_days: int = Field(default=30, ge=1, le=365)

    @field_validator("scopes")
    @classmethod
    def no_duplicate_scopes(cls, v: list) -> list:
        if len(v) != len(set(v)):
            raise ValueError("scopes must not contain duplicates")
        return v


class ShareGrantRequest(StrictSchema):
    """Patient approves a pending cross-hospital share request."""

    scopes: list[Literal[
        "summary", "encounters", "diagnoses", "prescriptions",
        "allergies", "vaccinations", "reports", "risk_predictions", "monitoring",
    ]] = Field(min_length=1)
    access_expires_days: int = Field(default=30, ge=1, le=365)

    @field_validator("scopes")
    @classmethod
    def no_duplicate_scopes(cls, v: list) -> list:
        if len(v) != len(set(v)):
            raise ValueError("scopes must not contain duplicates")
        return v


class ShareDenyRequest(StrictSchema):
    """Patient denies a pending cross-hospital share request."""

    reason: str | None = Field(default=None, max_length=500)


class ShareRevokeRequest(StrictSchema):
    """Patient revokes an active cross-hospital share (immediate effect)."""

    reason: str | None = Field(default=None, max_length=500)


class CrossHospitalBreakGlassRequest(StrictSchema):
    patient_id: UUID
    source_hospital_id: int = Field(gt=0)
    scopes: list[Literal[
        "summary", "encounters", "diagnoses", "prescriptions",
        "allergies", "vaccinations", "reports", "risk_predictions", "monitoring",
    ]] = Field(min_length=1)
    reason: str = Field(min_length=20, max_length=1000)

    @field_validator("scopes")
    @classmethod
    def no_duplicate_scopes(cls, value: list) -> list:
        if len(value) != len(set(value)):
            raise ValueError("scopes must not contain duplicates")
        return value


# ---------------------------------------------------------------------------
# Task 10: Monitoring schemas
# ---------------------------------------------------------------------------

ObservationType = Literal[
    "heart_rate", "blood_pressure", "blood_oxygen", "temperature", "blood_glucose", "respiratory_rate"
]


class ManualObservationRequest(StrictSchema):
    observation_type: ObservationType
    value: float
    secondary_value: float | None = None
    source_reference: str | None = Field(default=None, max_length=160)
    recorded_at: datetime | None = None


class ObservationSimulationRequest(StrictSchema):
    observation_types: list[ObservationType] = Field(default_factory=lambda: [
        "heart_rate", "blood_pressure", "blood_oxygen", "temperature", "blood_glucose", "respiratory_rate"
    ], min_length=1, max_length=6)
    count: int = Field(default=10, ge=1, le=100)
    seed: int = Field(default=42, ge=0, le=2_147_483_647)
    abnormal_every: int | None = Field(default=5, ge=1, le=100)

    @field_validator("observation_types")
    @classmethod
    def unique_types(cls, value: list) -> list:
        if len(value) != len(set(value)):
            raise ValueError("observation_types must not contain duplicates")
        return value


class MonitoringAlertActionRequest(StrictSchema):
    action: Literal["acknowledge", "escalate", "resolve"]
    notes: str | None = Field(default=None, max_length=1000)


class MonitoringRuleRequest(StrictSchema):
    name: str = Field(min_length=5, max_length=160)
    observation_type: ObservationType
    minimum_value: float | None = None
    maximum_value: float | None = None
    secondary_minimum_value: float | None = None
    secondary_maximum_value: float | None = None
    trend_window_count: int | None = Field(default=None, ge=2, le=50)
    trend_delta: float | None = Field(default=None, gt=0)
    severity: Literal["info", "warning", "critical"] = "warning"
    is_enabled: bool = True

    @model_validator(mode="after")
    def usable_rule(self):
        threshold = any(value is not None for value in (
            self.minimum_value, self.maximum_value,
            self.secondary_minimum_value, self.secondary_maximum_value,
        ))
        trend = self.trend_window_count is not None and self.trend_delta is not None
        if not threshold and not trend:
            raise ValueError("At least one threshold or a complete trend rule is required")
        if (self.trend_window_count is None) != (self.trend_delta is None):
            raise ValueError("trend_window_count and trend_delta must be provided together")
        if self.minimum_value is not None and self.maximum_value is not None and self.minimum_value >= self.maximum_value:
            raise ValueError("minimum_value must be lower than maximum_value")
        return self


# ---------------------------------------------------------------------------
# Task 12: Security administration schemas
# ---------------------------------------------------------------------------

class SecurityAlertActionRequest(StrictSchema):
    action: Literal["acknowledged", "investigating", "resolved", "dismissed", "reopened"]
    notes: str = Field(min_length=10, max_length=1000)


class SecurityBlockRequest(StrictSchema):
    target_type: Literal["account", "session", "ip"]
    target: str = Field(min_length=1, max_length=160)
    reason: str = Field(min_length=10, max_length=500)
    duration_minutes: int = Field(default=30, ge=1, le=10080)


class SecurityBlockReleaseRequest(StrictSchema):
    reason: str = Field(min_length=10, max_length=500)


class SecurityAllowlistRequest(StrictSchema):
    target_type: Literal["account", "ip", "device"]
    target: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=10, max_length=300)
    expires_at: datetime | None = None


# ---------------------------------------------------------------------------
# Task 11: Telemedicine schemas
# ---------------------------------------------------------------------------

class TelemedicineScheduleRequest(StrictSchema):
    """Doctor schedules a telemedicine session for an appointment (11.4)."""

    scheduled_start: datetime
    scheduled_end: datetime | None = None

    @model_validator(mode="after")
    def end_after_start(self):
        if self.scheduled_end is not None and self.scheduled_end <= self.scheduled_start:
            raise ValueError("scheduled_end must be after scheduled_start")
        return self


class TelemedicineRescheduleRequest(StrictSchema):
    """Doctor reschedules an existing session (11.4). Old room URL is invalidated."""

    scheduled_start: datetime
    scheduled_end: datetime | None = None

    @model_validator(mode="after")
    def end_after_start(self):
        if self.scheduled_end is not None and self.scheduled_end <= self.scheduled_start:
            raise ValueError("scheduled_end must be after scheduled_start")
        return self


class ConsultationCompleteRequest(StrictSchema):
    """Doctor completes a consultation and links the outcome to an encounter (11.7)."""

    # Optional plain-text summary stored on the session row itself.
    # Full clinical notes, diagnoses, and prescriptions go on the Encounter.
    consultation_summary: str | None = Field(default=None, max_length=5000)
    # FK to an existing Encounter row — links this session to clinical outcome.
    encounter_id: int | None = Field(default=None, gt=0)


class ConsultationCancelRequest(StrictSchema):
    """Patient or doctor cancels a scheduled/confirmed session."""

    reason: str | None = Field(default=None, max_length=500)


# ---------------------------------------------------------------------------
# Task 13: Queue lifecycle and hospital-resource schemas
# ---------------------------------------------------------------------------

class QueueActionRequest(StrictSchema):
    """Staff applies a lifecycle action to a queue token (13.2)."""

    action: Literal["call_next", "complete", "miss", "requeue", "cancel"]
    reason: str | None = Field(default=None, max_length=500)


class EmergencyEscalateRequest(StrictSchema):
    """Escalate a token to emergency priority and record the case (13.8)."""

    emergency_level: Literal["critical", "urgent", "high"]
    notes: str | None = Field(default=None, max_length=1000)
    response_time_minutes: int | None = Field(default=None, ge=0, le=1440)


class DoctorAvailabilityRequest(StrictSchema):
    """Hospital-admin sets a doctor's availability (13.10)."""

    availability: Literal["Available", "Busy", "Off Duty"]
    patients_today: int | None = Field(default=None, ge=0, le=500)
