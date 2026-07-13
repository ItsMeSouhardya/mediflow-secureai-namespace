"""Request tracing, safe JSON logs, v1 envelopes, and security headers."""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from datetime import datetime, timezone

from flask import Flask, Response, g, request

from schemas import ApiMeta, ErrorBody, ErrorEnvelope, SuccessEnvelope


REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in ("request_id", "method", "path", "status", "duration_ms", "remote_addr"):
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["exception"] = record.exc_info[0].__name__
        return json.dumps(payload, separators=(",", ":"), default=str)


def configure_logging(app: Flask) -> None:
    from metrics import ScrubFilter
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler.addFilter(ScrubFilter())
    app.logger.handlers.clear()
    app.logger.addHandler(handler)
    app.logger.setLevel(app.config.get("LOG_LEVEL", "INFO"))
    # Also install the scrub filter on the root logger so all modules benefit.
    logging.getLogger().addFilter(ScrubFilter())


def is_v1_request() -> bool:
    return request.path == "/api/v1" or request.path.startswith("/api/v1/")


def _request_id() -> str:
    """Return a request ID even when an earlier before-request hook aborted."""
    value = getattr(g, "request_id", None)
    if value is None:
        supplied = request.headers.get("X-Request-ID", "")
        value = supplied if REQUEST_ID_PATTERN.fullmatch(supplied) else str(uuid.uuid4())
        g.request_id = value
    return value


def _meta(existing: dict | None = None) -> ApiMeta:
    values = {
        "request_id": _request_id(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **(existing or {}),
    }
    values["request_id"] = _request_id()
    return ApiMeta.model_validate(values)


def _wrap_v1(response: Response, app: Flask) -> Response:
    if not is_v1_request() or not response.is_json:
        return response
    body = response.get_json(silent=True)
    if body is None:
        return response

    if response.status_code < 400:
        if isinstance(body, dict) and body.get("status") == "success" and "data" in body:
            data = body["data"]
            existing_meta = body.get("meta") or {}
        else:
            data = body
            existing_meta = {}
        envelope = SuccessEnvelope(data=data, meta=_meta(existing_meta)).model_dump(mode="json")
    else:
        if isinstance(body, dict) and "error" in body and isinstance(body["error"], dict):
            error_body = body["error"]
        else:
            error_body = {
                "code": body.get("code", "request_failed") if isinstance(body, dict) else "request_failed",
                "message": body.get("message", "Request failed") if isinstance(body, dict) else "Request failed",
                "details": body.get("details", []) if isinstance(body, dict) else [],
            }
        envelope = ErrorEnvelope(error=ErrorBody.model_validate(error_body), meta=_meta()).model_dump(mode="json")

    response.set_data(app.json.dumps(envelope))
    response.content_type = "application/json"
    return response


def register_request_hooks(app: Flask) -> None:
    @app.before_request
    def begin_request():
        supplied = request.headers.get("X-Request-ID", "")
        g.request_id = supplied if REQUEST_ID_PATTERN.fullmatch(supplied) else str(uuid.uuid4())
        g.request_started_at = time.perf_counter()

    @app.after_request
    def finish_request(response: Response):
        request_id = _request_id()
        response = _wrap_v1(response, app)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        if app.config.get("ENV_NAME") == "production":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        started_at = getattr(g, "request_started_at", time.perf_counter())
        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
        app.logger.info(
            "api_request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.path,
                "status": response.status_code,
                "duration_ms": duration_ms,
                "remote_addr": request.remote_addr,
            },
        )
        return response
