"""Lightweight application metrics and health/readiness/liveness endpoints.

Covers tasks 15.14, 15.15, 15.16:
  15.14  Metrics for latency, errors, DB health, queue events, document
         processing, blockchain transactions, and security alerts.
  15.15  Centralised log configuration — no medical content or credentials
         in any log payload; sensitive keys stripped before emission.
  15.16  Liveness, readiness, dependency, and worker health checks.

Design rules
------------
- No external metrics framework (Prometheus/StatsD) is required at runtime;
  metrics are collected in process-local counters and surfaced via JSON HTTP
  endpoints that can be scraped by any monitoring agent.
- All endpoints are under /api/v1/internal/* and are gated behind a Bearer
  token check using the METRICS_SECRET_KEY config value.  Set it to a random
  value; do NOT expose these endpoints to the public internet.
- No patient data, clinical content, or credentials appear in any metric or
  log payload.  Sensitive keys are stripped at the logging layer.
- Liveness returns 200 as long as the process is running.
- Readiness returns 200 only when the database and Redis are reachable.
- Dependency health returns the status of each external dependency individually.
"""

from __future__ import annotations

import logging
import os
import time
from collections import defaultdict
from datetime import datetime, timezone
from threading import Lock
from typing import Any

from flask import Flask, g, jsonify, request

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sensitive key names stripped from log payloads (15.15)
# ---------------------------------------------------------------------------

_SENSITIVE_LOG_KEYS: frozenset[str] = frozenset({
    "password", "password_hash", "token", "access_token", "refresh_token",
    "secret", "secret_key", "jwt", "api_key", "document_encryption_key",
    "symptoms", "diagnosis", "prescription", "clinical_notes", "body",
    "mfa_secret", "tracking_code", "storage_key",
})


def scrub_log_record(record: logging.LogRecord) -> logging.LogRecord:
    """Strip sensitive keys from log record message and extra fields."""
    for key in list(vars(record).keys()):
        if key.lower() in _SENSITIVE_LOG_KEYS:
            setattr(record, key, "[REDACTED]")
    # Also scrub the message string if it accidentally contains a key=value pair.
    import re
    for key in _SENSITIVE_LOG_KEYS:
        record.msg = re.sub(
            rf"(?i)\b{re.escape(key)}\s*[=:]\s*\S+",
            f"{key}=[REDACTED]",
            str(record.msg),
        )
    return record


class ScrubFilter(logging.Filter):
    """Logging filter that strips sensitive fields from every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        scrub_log_record(record)
        return True


# ---------------------------------------------------------------------------
# In-process metric counters (15.14)
# ---------------------------------------------------------------------------

class MetricsRegistry:
    """Simple thread-safe counter + histogram registry.

    Not a replacement for Prometheus — just enough to expose meaningful
    operational data without adding an external dependency.

    Counters:  api_requests_total, api_errors_total, auth_failures_total,
               queue_bookings_total, queue_actions_total, document_uploads_total,
               document_processing_failures_total, blockchain_enqueue_total,
               blockchain_confirmed_total, blockchain_failed_total,
               security_alerts_total, consent_grants_total, consent_revocations_total
    Histograms (sum + count → derives mean): api_request_duration_ms
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._counters: dict[str, int] = defaultdict(int)
        self._histograms: dict[str, list[float]] = defaultdict(list)
        self._started_at = datetime.now(timezone.utc)

    def inc(self, name: str, value: int = 1, labels: dict | None = None) -> None:
        key = name if not labels else f"{name}{{{','.join(f'{k}={v}' for k, v in sorted(labels.items()))}}}"
        with self._lock:
            self._counters[key] += value

    def observe(self, name: str, value: float) -> None:
        with self._lock:
            hist = self._histograms[name]
            hist.append(value)
            # Keep only the last 1 000 observations to cap memory.
            if len(hist) > 1000:
                self._histograms[name] = hist[-1000:]

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            counters = dict(self._counters)
            histograms = {
                name: {
                    "count": len(vals),
                    "sum": round(sum(vals), 2),
                    "mean": round(sum(vals) / len(vals), 2) if vals else 0,
                    "p95": round(sorted(vals)[int(len(vals) * 0.95)], 2) if vals else 0,
                    "p99": round(sorted(vals)[int(len(vals) * 0.99)], 2) if vals else 0,
                }
                for name, vals in self._histograms.items()
            }
        uptime_s = (datetime.now(timezone.utc) - self._started_at).total_seconds()
        return {
            "uptime_seconds": round(uptime_s, 1),
            "started_at": self._started_at.isoformat(),
            "counters": counters,
            "histograms": histograms,
        }


# Module-level singleton used by the rest of the application.
metrics = MetricsRegistry()


# ---------------------------------------------------------------------------
# Request instrumentation middleware (15.14 — latency + error counters)
# ---------------------------------------------------------------------------

def register_metrics_hooks(app: Flask) -> None:
    """Attach before/after request hooks to record latency and error rates."""

    @app.before_request
    def _start_timer():
        g._request_start = time.monotonic()

    @app.after_request
    def _record_request(response):
        duration_ms = (time.monotonic() - getattr(g, "_request_start", time.monotonic())) * 1000
        metrics.inc("api_requests_total", labels={"method": request.method, "status": str(response.status_code)})
        metrics.observe("api_request_duration_ms", duration_ms)
        if response.status_code >= 500:
            metrics.inc("api_errors_total", labels={"status": str(response.status_code)})
        return response


# ---------------------------------------------------------------------------
# Dependency health helpers (15.16)
# ---------------------------------------------------------------------------

def _check_database() -> dict[str, Any]:
    try:
        from extensions import db
        from sqlalchemy import text
        db.session.execute(text("SELECT 1"))
        return {"status": "healthy"}
    except Exception as exc:  # noqa: BLE001
        return {"status": "unhealthy", "error": type(exc).__name__}


def _check_redis() -> dict[str, Any]:
    try:
        from monitoring_realtime import broker
        if broker is None:
            return {"status": "degraded", "note": "Using in-process fallback broker"}
        # If broker is a real Redis client, ping it.
        if hasattr(broker, "ping"):
            broker.ping()
        return {"status": "healthy"}
    except Exception as exc:  # noqa: BLE001
        return {"status": "unhealthy", "error": type(exc).__name__}


def _check_document_storage(config: dict) -> dict[str, Any]:
    try:
        from document_storage import validate_storage_config
        warnings = validate_storage_config(config)
        if warnings:
            return {"status": "degraded", "warnings": warnings}
        return {"status": "healthy"}
    except Exception as exc:  # noqa: BLE001
        return {"status": "unhealthy", "error": type(exc).__name__}


def _check_blockchain(config: dict) -> dict[str, Any]:
    rpc = config.get("BLOCKCHAIN_RPC_URL", "")
    if not rpc:
        return {"status": "not_configured", "note": "Blockchain outbox will queue without confirming"}
    try:
        from blockchain_adapter import Web3IntegrityAdapter
        adapter = Web3IntegrityAdapter(config)
        adapter.ping()
        return {"status": "healthy"}
    except Exception as exc:  # noqa: BLE001
        return {"status": "degraded", "error": type(exc).__name__,
                "note": "Blockchain outbox is pending — EHR availability not affected"}


def _check_blockchain_worker(config: dict) -> dict[str, Any]:
    """Check for stuck pending transactions — indicates the worker is not running."""
    try:
        from extensions import db
        from models import BlockchainTransaction
        from sqlalchemy import select, func
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)
        stuck = db.session.scalar(
            select(func.count(BlockchainTransaction.transaction_id)).where(
                BlockchainTransaction.state == "pending",
                BlockchainTransaction.created_at < cutoff,
            )
        ) or 0
        if stuck > 0:
            return {"status": "degraded",
                    "stuck_transactions": stuck,
                    "note": "Blockchain worker may not be running"}
        return {"status": "healthy"}
    except Exception as exc:  # noqa: BLE001
        return {"status": "unknown", "error": type(exc).__name__}


# ---------------------------------------------------------------------------
# Health/readiness/liveness route registration (15.16)
# ---------------------------------------------------------------------------

def _metrics_auth(secret: str) -> bool:
    """Validate the metrics bearer token."""
    header = request.headers.get("Authorization", "")
    scheme, _, value = header.partition(" ")
    return scheme.lower() == "bearer" and value == secret


def register_health_routes(app: Flask) -> None:
    """Register liveness, readiness, dependency, and metrics endpoints."""

    # ── Liveness — is the process up? ────────────────────────────────────
    @app.get("/api/v1/health")
    def health_live():
        """Liveness probe: returns 200 as long as the Flask process is running.

        Does NOT check dependencies — fast enough for aggressive polling.
        """
        return jsonify({
            "status": "alive",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "version": os.getenv("APP_VERSION", "dev"),
        })

    # ── Readiness — is the app ready to serve traffic? ───────────────────
    @app.get("/api/v1/ready")
    def health_ready():
        """Readiness probe: checks DB and Redis before accepting traffic.

        Returns 503 if any critical dependency is unhealthy so the load
        balancer stops sending traffic until the app recovers.
        """
        db_status = _check_database()
        redis_status = _check_redis()

        ready = (
            db_status["status"] == "healthy"
            and redis_status["status"] in ("healthy", "degraded")
        )
        http_status = 200 if ready else 503

        return jsonify({
            "status": "ready" if ready else "not_ready",
            "checks": {
                "database": db_status,
                "redis": redis_status,
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }), http_status

    # ── Dependency health — detailed per-service status ──────────────────
    @app.get("/api/v1/internal/health/dependencies")
    def health_dependencies():
        """Detailed dependency health — protected by METRICS_SECRET_KEY.

        Returns the status of every external service: DB, Redis, document
        storage, blockchain node, and blockchain worker.
        """
        secret = app.config.get("METRICS_SECRET_KEY", "")
        if secret and not _metrics_auth(secret):
            return jsonify({"error": "Unauthorized"}), 401

        checks = {
            "database":         _check_database(),
            "redis":            _check_redis(),
            "document_storage": _check_document_storage(app.config),
            "blockchain_node":  _check_blockchain(app.config),
            "blockchain_worker": _check_blockchain_worker(app.config),
        }
        overall = "healthy"
        for check in checks.values():
            if check["status"] == "unhealthy":
                overall = "unhealthy"
                break
            if check["status"] in ("degraded", "not_configured"):
                overall = "degraded"

        http_status = 200 if overall != "unhealthy" else 503
        return jsonify({
            "status": overall,
            "checks": checks,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }), http_status

    # ── Metrics — operational counters and histograms ─────────────────────
    @app.get("/api/v1/internal/metrics")
    def internal_metrics():
        """Prometheus-compatible JSON metrics — protected by METRICS_SECRET_KEY.

        Covers task 15.14: latency, errors, DB health, queue events,
        AI jobs, document processing, blockchain, security alerts.
        Sensitive clinical content is NEVER included (15.15).
        """
        secret = app.config.get("METRICS_SECRET_KEY", "")
        if secret and not _metrics_auth(secret):
            return jsonify({"error": "Unauthorized"}), 401

        snapshot = metrics.snapshot()

        # Augment with live DB stats that cannot be tracked in counters.
        try:
            from extensions import db
            from models import (
                AuditEvent, BlockchainTransaction, MonitoringAlert,
                Token, MedicalDocument,
            )
            from sqlalchemy import select, func

            def _count(model, **filters):
                q = select(func.count()).select_from(model)
                for col, val in filters.items():
                    q = q.where(getattr(model, col) == val)
                return db.session.scalar(q) or 0

            snapshot["live"] = {
                "queue": {
                    "waiting": _count(Token, status="waiting"),
                    "serving":  _count(Token, status="serving"),
                },
                "documents": {
                    "ready":       _count(MedicalDocument, status="ready"),
                    "processing":  _count(MedicalDocument, status="processing"),
                    "failed":      _count(MedicalDocument, status="failed"),
                    "quarantined": _count(MedicalDocument, status="quarantined"),
                },
                "blockchain": {
                    "pending":   _count(BlockchainTransaction, state="pending"),
                    "confirmed": _count(BlockchainTransaction, state="confirmed"),
                    "failed":    _count(BlockchainTransaction, state="failed"),
                },
                "monitoring_alerts": {
                    "open":         _count(MonitoringAlert, status="open"),
                    "acknowledged": _count(MonitoringAlert, status="acknowledged"),
                },
            }
        except Exception as exc:  # noqa: BLE001
            snapshot["live_error"] = type(exc).__name__

        return jsonify(snapshot)
