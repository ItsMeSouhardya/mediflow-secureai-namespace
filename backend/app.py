"""MediFlow Secure application factory with v1 and legacy-compatible APIs."""

from __future__ import annotations

from datetime import datetime, timezone

import click
from flask import Flask, g, jsonify, request
from flask_cors import CORS
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from ai_engine import (
    analyze_patient,
    compute_priority_score,
    elderly_mode,
    generate_ai_json,
    get_crowd_and_timing,
    get_dashboard_stats,
    get_position,
    get_wait_info,
    hospital_journey,
    suggest_doctor,
    suggest_hospital,
)
from audit import write_audit_event
from auth_routes import register_auth_commands, register_auth_routes
from auth_service import ROLE_DOCTOR, ROLE_HOSPITAL_ADMIN, ROLE_PATIENT, ROLE_SECURITY_ADMIN
from authorization import authorize_clinical_access, enforce_owner, enforce_tenant, require_auth, require_v1_auth
from blockchain_routes import register_blockchain_commands, register_blockchain_routes
from config import get_config
from errors import ApiProblem
from analysis_routes import register_analysis_routes
from consent_routes import register_consent_routes
from sharing_routes import register_sharing_routes
from queue_routes import register_queue_routes
from metrics import register_health_routes, register_metrics_hooks, ScrubFilter
from monitoring_routes import register_monitoring_routes
from security_routes import register_security_routes
from patient_audit_routes import register_patient_audit_routes
from telemedicine_routes import register_telemedicine_routes
from document_routes import register_document_routes
from document_storage import validate_storage_config
from ehr_routes import register_ehr_routes
from extensions import db, limiter, migrate
from idempotency import find_replay, request_hash, store_result, validate_key
from observability import configure_logging, is_v1_request, register_request_hooks
from rate_limits import (
    PREDICTION_RATE_LIMIT,
    SENSITIVE_WRITE_RATE_LIMIT,
    TOKEN_BOOKING_RATE_LIMIT,
    TOKEN_LOOKUP_RATE_LIMIT,
)
from repository import MediFlowRepository
from schemas import (
    AIReportQuery,
    AnalyzeQuery,
    AppointmentRequest,
    BookTokenRequest,
    DepartmentQuery,
    ElderlyQuery,
    FeedbackRequest,
    HospitalQuery,
    OptionalDepartmentQuery,
    PaginationQuery,
    PositionQuery,
    PriorityQuery,
    SymptomsHistoryRequest,
    UserPaginationQuery,
    validate_json,
    validate_query,
)
from tracking import generate_tracking_code, hash_tracking_code


def create_app(config_name: str | None = None, config_overrides: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_object(get_config(config_name))
    if config_overrides:
        app.config.update(config_overrides)

    _validate_security_configuration(app)
    _validate_document_storage_configuration(app)
    _validate_blockchain_configuration(app)
    db.init_app(app)
    migrate.init_app(app, db)
    limiter.init_app(app)
    CORS(
        app,
        resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}},
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID"],
        expose_headers=["Idempotent-Replayed", "Retry-After", "X-Request-ID", "X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset"],
        supports_credentials=True,
        max_age=600,
    )

    configure_logging(app)
    register_request_hooks(app)
    register_metrics_hooks(app)
    register_health_routes(app)
    register_error_handlers(app)
    register_routes(app)
    register_auth_routes(app)
    register_ehr_routes(app)
    register_document_routes(app)
    register_analysis_routes(app)
    register_consent_routes(app)
    register_sharing_routes(app)
    register_monitoring_routes(app)
    register_queue_routes(app)
    register_security_routes(app)
    register_patient_audit_routes(app)
    register_telemedicine_routes(app)
    register_blockchain_routes(app)
    register_task3_routes(app)
    register_versioned_routes(app)
    register_commands(app)
    register_auth_commands(app)
    register_blockchain_commands(app)
    return app


def _validate_security_configuration(app: Flask) -> None:
    origins = app.config.get("CORS_ORIGINS", [])
    if not origins or "*" in origins:
        raise RuntimeError("CORS_ORIGINS must be an explicit non-empty allowlist")
    if app.config.get("ENV_NAME") == "production" and app.config.get("SECRET_KEY") == "development-only-change-me":
        raise RuntimeError("A production SECRET_KEY must be configured")
    if app.config.get("ENV_NAME") == "production" and app.config.get("JWT_SECRET_KEY") in {
        None,
        "development-jwt-secret-change-me-32-bytes-minimum",
    }:
        raise RuntimeError("A production JWT_SECRET_KEY must be configured")


def _validate_document_storage_configuration(app: Flask) -> None:
    """Warn loudly in logs when the document storage config is incomplete.

    Raises RuntimeError in production; logs warnings in development so the
    app can still start for non-document workflows.
    """
    warnings = validate_storage_config(app.config)
    for warning in warnings:
        if app.config.get("ENV_NAME") == "production":
            raise RuntimeError(f"Document storage misconfiguration: {warning}")
        app.logger.warning("document_storage_config_warning: %s", warning)


def _validate_blockchain_configuration(app: Flask) -> None:
    if not app.config.get("BLOCKCHAIN_ENABLED"):
        return
    required = (
        "BLOCKCHAIN_RPC_URL",
        "BLOCKCHAIN_CONTRACT_ADDRESS",
        "BLOCKCHAIN_REFERENCE_SECRET",
    )
    if not app.config.get("BLOCKCHAIN_DEVELOPMENT_UNLOCKED_ACCOUNT"):
        required = (*required, "BLOCKCHAIN_DEPLOYER_PRIVATE_KEY")
    missing = [name for name in required if not app.config.get(name)]
    if missing:
        message = f"Blockchain configuration is incomplete: {', '.join(missing)}"
        if app.config.get("ENV_NAME") == "production":
            raise RuntimeError(message)
        app.logger.warning(message)
    if (
        app.config.get("ENV_NAME") == "production"
        and app.config.get("BLOCKCHAIN_DEVELOPMENT_UNLOCKED_ACCOUNT")
    ):
        raise RuntimeError("Unlocked blockchain accounts are forbidden in production")
    if (
        app.config.get("ENV_NAME") == "production"
        and app.config.get("BLOCKCHAIN_REFERENCE_SECRET") == app.config.get("SECRET_KEY")
    ):
        raise RuntimeError("BLOCKCHAIN_REFERENCE_SECRET must be separate from SECRET_KEY in production")


def _repo() -> MediFlowRepository:
    return MediFlowRepository(db.session)


def _error(message: str, status: int = 400, code: str = "bad_request", details: list | None = None):
    return jsonify(
        {
            "status": "error",
            "code": code,
            "message": message,
            "details": details or [],
        }
    ), status


def _collection(items: list, query: PaginationQuery, total: int):
    if not is_v1_request():
        return jsonify(items)
    total_pages = (total + query.per_page - 1) // query.per_page if total else 0
    return jsonify(
        {
            "status": "success",
            "data": items,
            "meta": {
                "pagination": {
                    "page": query.page,
                    "per_page": query.per_page,
                    "total": total,
                    "total_pages": total_pages,
                }
            },
        }
    )


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(ApiProblem)
    def handle_api_problem(error: ApiProblem):
        suspicious_upload = request.path.endswith("/documents") and error.code in {
            "file_quarantined", "file_type_not_allowed", "mime_type_not_allowed",
            "file_too_large", "invalid_file_content",
        }
        if error.status_code in (401, 403, 423) or suspicious_upload:
            from security_service import collect_security_event
            db.session.rollback()
            collect_security_event(
                db.session,
                event_type="upload.suspicious_rejected" if suspicious_upload else "access.denied",
                outcome="failure" if suspicious_upload else "denied",
                actor_user_id=getattr(getattr(g, "current_user", None), "user_id", None),
                auth_session_id=getattr(getattr(g, "auth_session", None), "auth_session_id", None),
                resource_type="api_route", resource_id=request.path,
                remote_addr=request.remote_addr,
                user_agent=request.user_agent.string if request.user_agent else None,
                metadata={"code": error.code, "status": error.status_code},
            )
            db.session.commit()
        return _error(error.message, error.status_code, error.code, error.details)

    @app.errorhandler(404)
    def handle_not_found(_error_value):
        return _error("Resource not found", 404, "not_found")

    @app.errorhandler(405)
    def handle_method_not_allowed(_error_value):
        return _error("Method not allowed", 405, "method_not_allowed")

    @app.errorhandler(413)
    def handle_payload_too_large(_error_value):
        return _error("Request payload is too large", 413, "payload_too_large")

    @app.errorhandler(429)
    def handle_rate_limit(_error_value):
        from security_service import collect_security_event
        db.session.rollback()
        collect_security_event(
            db.session, event_type="rate_limit.violation", outcome="denied",
            actor_user_id=getattr(getattr(g, "current_user", None), "user_id", None),
            resource_type="api_route", resource_id=request.path,
            remote_addr=request.remote_addr,
            user_agent=request.user_agent.string if request.user_agent else None,
            metadata={"status": 429},
        )
        db.session.commit()
        return _error("Rate limit exceeded", 429, "rate_limit_exceeded")

    @app.errorhandler(SQLAlchemyError)
    def handle_database_error(error: SQLAlchemyError):
        db.session.rollback()
        app.logger.exception("database_operation_failed", exc_info=error)
        return _error("A database operation failed", 500, "database_error")

    @app.errorhandler(Exception)
    def handle_unexpected_error(error: Exception):
        db.session.rollback()
        app.logger.exception("unhandled_api_error", exc_info=error)
        return _error("An unexpected server error occurred", 500, "internal_error")


def register_versioned_routes(app: Flask) -> None:
    """Expose the same protected view functions under `/api/v1` during migration."""
    for rule in list(app.url_map.iter_rules()):
        if not rule.rule.startswith("/api/") or rule.rule.startswith("/api/v1/"):
            continue
        versioned_rule = f"/api/v1{rule.rule[4:]}"
        methods = sorted(rule.methods - {"HEAD", "OPTIONS"})
        app.add_url_rule(
            versioned_rule,
            endpoint=f"v1_{rule.endpoint}",
            view_func=app.view_functions[rule.endpoint],
            methods=methods,
        )


def register_routes(app: Flask) -> None:
    @app.get("/api/ai-report")
    @limiter.limit(PREDICTION_RATE_LIMIT)
    @require_v1_auth(ROLE_PATIENT, ROLE_DOCTOR)
    def ai_report():
        query = validate_query(AIReportQuery)
        data = generate_ai_json(_repo(), query.dept_id, query.token, query.symptoms, query.age)
        return jsonify(
            {
                "status": "success",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "meta": {"model": "MediFlow rules v1.0", "decision_support_only": True},
                "data": data,
            }
        )

    @app.get("/api/wait-time")
    def wait_time():
        query = validate_query(DepartmentQuery)
        wait, advice, queue_len, consult_time = get_wait_info(_repo(), query.dept_id)
        return jsonify({"wait_time": wait, "advice": advice, "queue_length": queue_len, "consult_time": consult_time})

    @app.get("/api/crowd-info")
    def crowd_info():
        query = validate_query(DepartmentQuery)
        peak, crowd, suggestion, color = get_crowd_and_timing(_repo(), query.dept_id)
        return jsonify({"peak_hour": peak, "crowd": crowd, "best_time": suggestion, "color": color})

    @app.get("/api/analyze")
    @limiter.limit(PREDICTION_RATE_LIMIT)
    def analyze():
        query = validate_query(AnalyzeQuery)
        result = analyze_patient(_repo(), query.symptoms, query.dept_id)
        return jsonify(
            {
                "emergency": result.emergency,
                "is_emergency": result.is_emergency,
                "recommended_department": result.department,
                "hospital_status": result.hospital_status,
                "escalation_reason": result.escalation_reason,
                "disclaimer": result.disclaimer,
                "emergency_guidance": result.emergency_guidance,
            }
        )

    @app.get("/api/doctor")
    def doctor():
        # 13.5 — use least-loaded available doctor from PostgreSQL
        query = validate_query(OptionalDepartmentQuery)
        repo = _repo()
        best = repo.best_doctor_for_dept(query.dept_id) if query.dept_id else None
        name = best.doctor_name if best else "Doctor assignment pending"
        return jsonify({"suggested_doctor": name})

    @app.get("/api/navigation")
    def navigation():
        query = validate_query(DepartmentQuery)
        wait, _, _, _ = get_wait_info(_repo(), query.dept_id)
        journey, total = hospital_journey(_repo(), query.dept_id, wait)
        return jsonify({"journey": journey, "total_time": total})

    @app.get("/api/hospital-suggestion")
    def hospital_suggestion():
        # 13.5 — replaced random/hardcoded with PostgreSQL-backed live queue data
        return jsonify({"suggestion": _repo().recommend_hospital()})

    @app.get("/api/elderly")
    def elderly():
        query = validate_query(ElderlyQuery)
        return jsonify({"mode": elderly_mode(query.age)})

    @app.post("/api/tokens/book")
    @limiter.limit(TOKEN_BOOKING_RATE_LIMIT)
    @require_v1_auth(ROLE_PATIENT)
    def book_token():
        body = validate_json(BookTokenRequest)
        payload = body.model_dump(mode="json", exclude_none=True)
        idempotency_key = validate_key(
            request.headers.get("Idempotency-Key"),
            required=is_v1_request(),
        )
        payload_hash = request_hash(payload)
        if idempotency_key:
            replay = find_replay(
                db.session,
                scope="token_booking",
                key=idempotency_key,
                payload_hash=payload_hash,
            )
            if replay:
                response = jsonify(replay.response_json)
                response.status_code = replay.status_code
                response.headers["Idempotent-Replayed"] = "true"
                return response

        repo = _repo()
        _analysis = analyze_patient(repo, body.symptoms, body.dept_id)
        priority = "emergency" if _analysis.is_emergency else "elderly" if body.age >= 60 else "normal"
        doctors = repo.available_doctors(body.dept_id)
        tracking_code, tracking_code_hash, tracking_code_last4 = generate_tracking_code()
        current_user = g.current_user if is_v1_request() else None
        token = repo.book_token(
            dept_id=body.dept_id,
            patient_name=body.patient_name,
            age=body.age,
            phone=current_user.phone if current_user else body.phone,
            gender=current_user.gender if current_user and current_user.gender else body.gender,
            symptoms=body.symptoms,
            priority=priority,
            doctor_id=doctors[0].doctor_id if doctors else None,
            user_id=current_user.user_id if current_user else None,
            tracking_code_hash=tracking_code_hash,
            tracking_code_last4=tracking_code_last4,
        )
        hospital = repo.get_hospital(token.hospital_id)
        response_payload = {
            "token_id": token.token_id,
            "token_number": token.token_number,
            "token_code": token.token_number,
            "tracking_code": tracking_code,
            "priority": priority,
            "patient_name": token.booked_patient_name,
            "age": token.booked_patient_age,
            "hospital_id": token.hospital_id,
            "hospital_name": hospital.hospital_name if hospital else None,
            "ai_report": generate_ai_json(repo, body.dept_id, token.token_number, body.symptoms, body.age),
        }
        if idempotency_key:
            store_result(
                db.session,
                scope="token_booking",
                key=idempotency_key,
                payload_hash=payload_hash,
                response_json=response_payload,
                status_code=201,
            )
        write_audit_event(
            db.session,
            action="token.booked",
            resource_type="token",
            resource_id=token.token_id,
            actor_user_id=token.user_id,
            details={"hospital_id": token.hospital_id, "department_id": token.dept_id, "priority": priority},
        )
        try:
            db.session.commit()
        except IntegrityError as error:
            db.session.rollback()
            raise ApiProblem("conflict", "The booking could not be committed safely", 409) from error
        return jsonify(response_payload), 201

    @app.get("/api/tokens/<token_value>")
    @limiter.limit(TOKEN_LOOKUP_RATE_LIMIT)
    @require_v1_auth(ROLE_PATIENT, ROLE_DOCTOR)
    def get_token(token_value: str):
        if not token_value or len(token_value) > 128:
            raise ApiProblem("validation_error", "Token identifier is invalid", 422)
        repo = _repo()
        token = repo.get_token(token_value)
        if token is None:
            raise ApiProblem("token_not_found", "Token not found", 404)
        if is_v1_request():
            authorize_clinical_access(owner_user_id=token.user_id, hospital_id=token.hospital_id)
        payload = repo.token_payload(token)
        payload["ai_report"] = generate_ai_json(
            repo,
            token.dept_id,
            token.token_number,
            token.symptoms or "",
            payload.get("age") or 30,
        )
        write_audit_event(
            db.session,
            action="token.viewed",
            resource_type="token",
            resource_id=token.token_id,
            actor_user_id=token.user_id,
            details={"hospital_id": token.hospital_id, "department_id": token.dept_id},
        )
        db.session.commit()
        return jsonify(payload)

    @app.get("/api/dashboard/stats")
    @require_v1_auth(ROLE_DOCTOR, ROLE_HOSPITAL_ADMIN, ROLE_SECURITY_ADMIN)
    def dashboard_stats():
        query = validate_query(HospitalQuery)
        if is_v1_request():
            enforce_tenant(query.hospital_id)
        return jsonify(get_dashboard_stats(_repo(), query.hospital_id))

    @app.get("/api/hospitals")
    def list_hospitals():
        return jsonify(_repo().list_hospitals())

    @app.get("/api/departments")
    def list_departments():
        query = validate_query(HospitalQuery)
        return jsonify(_repo().list_departments(query.hospital_id))

    @app.get("/api/departments/overview")
    def departments_overview():
        query = validate_query(HospitalQuery)
        return jsonify(_repo().departments_overview(query.hospital_id))

    @app.get("/api/doctors")
    def list_doctors():
        query = validate_query(HospitalQuery)
        return jsonify(_repo().list_doctors(query.hospital_id))

    @app.get("/api/live-status")
    def live_status():
        query = validate_query(DepartmentQuery)
        wait, _, queue_len, _ = get_wait_info(_repo(), query.dept_id)
        _, crowd, _, _ = get_crowd_and_timing(_repo(), query.dept_id)
        return jsonify(
            {
                "wait_time": wait,
                "queue_length": queue_len,
                "crowd": crowd,
                "status": "Live",
                "last_updated": datetime.now(timezone.utc).isoformat(),
            }
        )

    @app.get("/api/alerts")
    def alerts():
        query = validate_query(DepartmentQuery)
        wait, _, _, _ = get_wait_info(_repo(), query.dept_id)
        alert = "High waiting time. Consider visiting later." if wait > 60 else "Moderate crowd. Plan accordingly." if wait > 30 else "Low crowd. Good time to visit."
        return jsonify({"alert": alert, "wait_time": wait})

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok", "service": "mediflow-api", "timestamp": datetime.now(timezone.utc).isoformat()})

    @app.get("/api/ready")
    def ready():
        try:
            db.session.execute(text("SELECT 1"))
            return jsonify({"status": "ready", "database": "connected"})
        except SQLAlchemyError:
            db.session.rollback()
            return _error("Service dependency unavailable", 503, "not_ready")

    @app.get("/api/priority")
    @limiter.limit(PREDICTION_RATE_LIMIT)
    def priority():
        query = validate_query(PriorityQuery)
        wait, _, _, _ = get_wait_info(_repo(), query.dept_id)
        _analysis = analyze_patient(_repo(), query.symptoms, query.dept_id)
        return jsonify({"priority_score": compute_priority_score(query.age, query.symptoms, wait, _analysis.emergency)})

    @app.get("/api/position")
    def token_position():
        query = validate_query(PositionQuery)
        position = get_position(_repo(), query.dept_id, query.token)
        return jsonify({"position": position, "found": position != -1})

    @app.route("/api/symptoms-history", methods=["GET", "POST"])
    @limiter.limit(SENSITIVE_WRITE_RATE_LIMIT, methods=["POST"])
    @require_v1_auth(ROLE_PATIENT)
    def symptoms_history():
        repo = _repo()
        if request.method == "GET":
            query = validate_query(UserPaginationQuery)
            if is_v1_request():
                query.user_id = g.current_user.user_id
            items, total = repo.symptoms_history(
                query.user_id,
                page=query.page,
                per_page=query.per_page,
                sort_order=query.sort_order,
                search=query.search,
                date_from=query.date_from,
                date_to=query.date_to,
            )
            return _collection(items, query, total)
        body = validate_json(SymptomsHistoryRequest)
        payload = body.model_dump()
        if is_v1_request():
            payload["user_id"] = g.current_user.user_id
        record = repo.add_symptoms_history(payload)
        write_audit_event(db.session, action="symptoms_history.created", resource_type="symptoms_history", resource_id=record.history_id, actor_user_id=record.user_id)
        db.session.commit()
        return jsonify({"status": "ok", "id": record.history_id}), 201

    @app.get("/api/emergency-cases")
    @require_v1_auth(ROLE_DOCTOR, ROLE_HOSPITAL_ADMIN)
    def emergency_cases():
        query = validate_query(PaginationQuery)
        if query.date_from or query.date_to:
            raise ApiProblem("unsupported_filter", "Emergency cases do not yet expose a date field", 422)
        items, total = _repo().emergency_cases(
            page=query.page,
            per_page=query.per_page,
            sort_order=query.sort_order,
            search=query.search,
        )
        return _collection(items, query, total)

    @app.route("/api/appointments", methods=["GET", "POST"])
    @limiter.limit(SENSITIVE_WRITE_RATE_LIMIT, methods=["POST"])
    @require_v1_auth(ROLE_PATIENT)
    def appointments():
        repo = _repo()
        if request.method == "GET":
            query = validate_query(UserPaginationQuery)
            if is_v1_request():
                query.user_id = g.current_user.user_id
            items, total = repo.appointments(
                query.user_id,
                page=query.page,
                per_page=query.per_page,
                sort_order=query.sort_order,
                search=query.search,
                date_from=query.date_from,
                date_to=query.date_to,
            )
            return _collection(items, query, total)
        body = validate_json(AppointmentRequest)
        payload = body.model_dump()
        if is_v1_request():
            payload["user_id"] = g.current_user.user_id
        appointment = repo.add_appointment(payload)
        write_audit_event(db.session, action="appointment.created", resource_type="appointment", resource_id=appointment.appointment_id, actor_user_id=appointment.user_id)
        db.session.commit()
        return jsonify({"status": "ok", "appointment_id": appointment.appointment_id}), 201

    @app.route("/api/feedback", methods=["GET", "POST"])
    @limiter.limit(SENSITIVE_WRITE_RATE_LIMIT, methods=["POST"])
    @require_v1_auth(ROLE_PATIENT)
    def feedback():
        repo = _repo()
        if request.method == "GET":
            query = validate_query(PaginationQuery)
            items, total = repo.feedback(
                page=query.page,
                per_page=query.per_page,
                sort_order=query.sort_order,
                search=query.search,
                date_from=query.date_from,
                date_to=query.date_to,
            )
            return _collection(items, query, total)
        body = validate_json(FeedbackRequest)
        payload = body.model_dump()
        if is_v1_request():
            payload["user_id"] = g.current_user.user_id
        record = repo.add_feedback(payload)
        write_audit_event(db.session, action="feedback.created", resource_type="feedback", resource_id=record.feedback_id, actor_user_id=record.user_id)
        db.session.commit()
        return jsonify({"status": "ok", "feedback_id": record.feedback_id}), 201

    @app.get("/")
    def home():
        return jsonify(
            {
                "project": "MediFlow Secure",
                "version": "2.0-foundation",
                "status": "Running",
                "database_target": "PostgreSQL",
                "api_version": "/api/v1",
                "legacy_api": "/api",
            }
        )


def register_task3_routes(app: Flask) -> None:
    """Register identity-aware endpoints that intentionally have no legacy alias."""

    @app.get("/api/v1/public/tokens/<tracking_code>")
    @limiter.limit(TOKEN_LOOKUP_RATE_LIMIT)
    def public_token_status(tracking_code: str):
        if len(tracking_code) < 24 or len(tracking_code) > 128:
            raise ApiProblem("tracking_not_found", "Tracking code not found", 404)
        token = _repo().get_token_by_tracking_hash(hash_tracking_code(tracking_code))
        if token is None:
            raise ApiProblem("tracking_not_found", "Tracking code not found", 404)
        return jsonify(_repo().public_token_payload(token))

    @app.get("/api/v1/patients/me/tokens/<int:token_id>/ai-report")
    @limiter.limit(PREDICTION_RATE_LIMIT)
    @require_auth(ROLE_PATIENT, ROLE_DOCTOR)
    def patient_ai_report(token_id: int):
        repo = _repo()
        token = repo.get_token(str(token_id))
        if token is None:
            raise ApiProblem("token_not_found", "Token not found", 404)
        authorize_clinical_access(owner_user_id=token.user_id, hospital_id=token.hospital_id)
        user = token.user
        data = generate_ai_json(
            repo,
            token.dept_id,
            token.token_number,
            token.symptoms or "",
            token.booked_patient_age if token.booked_patient_age is not None else (user.age if user and user.age is not None else 30),
        )
        department = repo.get_department(token.dept_id)
        data.update({
            "token_number": token.token_number,
            "patient_name": token.booked_patient_name or (user.name if user else None),
            "age": token.booked_patient_age if token.booked_patient_age is not None else (user.age if user and user.age is not None else 30),
            "booked_department": department.dept_name if department else data.get("department"),
        })
        write_audit_event(
            db.session,
            action="ai_report.viewed",
            resource_type="token",
            resource_id=token.token_id,
            actor_user_id=g.current_user.user_id,
            details={"hospital_id": token.hospital_id, "department_id": token.dept_id},
        )
        db.session.commit()
        return jsonify(
            {
                "status": "success",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "meta": {"model": "MediFlow rules v1.0", "decision_support_only": True},
                "data": data,
            }
        )


def register_commands(app: Flask) -> None:
    @app.cli.command("verify-db")
    def verify_db_command():
        from models import Department, Doctor, Hospital, Token, User

        counts = {
            "users": db.session.query(User).count(),
            "hospitals": db.session.query(Hospital).count(),
            "departments": db.session.query(Department).count(),
            "doctors": db.session.query(Doctor).count(),
            "tokens": db.session.query(Token).count(),
        }
        click.echo(counts)

    @app.cli.command("seed-demo")
    def seed_demo_command():
        from seed import seed_demo_data

        seed_demo_data(db.session)
        db.session.commit()
        click.echo("Deterministic demo data seeded.")


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=app.debug)
