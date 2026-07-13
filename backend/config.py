"""Environment-specific configuration for MediFlow Secure."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
load_dotenv(PROJECT_ROOT / ".env")


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _normalize_database_url(url: str) -> str:
    """Select psycopg 3 for provider URLs that omit a SQLAlchemy driver.

    Render exposes ``postgresql://`` connection strings. SQLAlchemy otherwise
    treats that as the legacy psycopg2 driver, which this project deliberately
    does not install.
    """
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    return url


def _database_url(environment: str) -> str:
    if environment == "testing":
        configured = os.getenv("TEST_DATABASE_URL")
        if configured:
            return configured
        return "sqlite+pysqlite:///:memory:"

    configured = os.getenv("DATABASE_URL")
    if configured:
        return _normalize_database_url(configured)

    if _bool("MEDIFLOW_ALLOW_SQLITE"):
        return f"sqlite+pysqlite:///{(BASE_DIR / 'database.db').as_posix()}"

    return "postgresql+psycopg://mediflow:mediflow@localhost:5432/mediflow"


def _project_path(name: str, default: Path) -> str:
    configured = Path(os.getenv(name, str(default)))
    return str(configured if configured.is_absolute() else (PROJECT_ROOT / configured).resolve())


class BaseConfig:
    ENV_NAME = "base"
    SECRET_KEY = os.getenv("SECRET_KEY", "development-only-change-me")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "development-jwt-secret-change-me-32-bytes-minimum")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": int(os.getenv("DB_POOL_RECYCLE", "1800")),
    }
    CORS_ORIGINS = [
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
        if origin.strip()
    ]
    JSON_SORT_KEYS = False
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", str(25 * 1024 * 1024)))
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = False
    RATELIMIT_ENABLED = True
    RATELIMIT_STORAGE_URI = os.getenv("RATELIMIT_STORAGE_URI", "memory://")
    # Flask-Limiter reads this config key as a rate-limit expression. Passing
    # a list is stringified by newer releases and becomes an invalid value such
    # as "['200 per minute']" when rate limiting is enabled.
    RATELIMIT_DEFAULT = os.getenv("API_DEFAULT_RATE_LIMIT", "200 per minute")
    RATELIMIT_HEADERS_ENABLED = True
    ACCESS_TOKEN_MINUTES = int(os.getenv("ACCESS_TOKEN_MINUTES", "15"))
    REFRESH_TOKEN_DAYS = int(os.getenv("REFRESH_TOKEN_DAYS", "7"))
    PASSWORD_RESET_MINUTES = int(os.getenv("PASSWORD_RESET_MINUTES", "30"))
    ACCOUNT_ACTIVATION_MINUTES = int(os.getenv("ACCOUNT_ACTIVATION_MINUTES", "60"))
    REFRESH_COOKIE_NAME = os.getenv("REFRESH_COOKIE_NAME", "mediflow_refresh")
    MFA_REQUIRED_FOR_STAFF = _bool("MFA_REQUIRED_FOR_STAFF")

    # Task 15.14/15.16 — metrics and health checks
    # Set to a strong random value; used as Bearer token for internal endpoints.
    # Generate: python -c "import secrets; print(secrets.token_hex(32))"
    METRICS_SECRET_KEY = os.getenv("METRICS_SECRET_KEY", "")

    # Task 11: Telemedicine — Jitsi provider configuration
    # Generate key: python -c "import secrets; print(secrets.token_hex(32))"
    TELEMEDICINE_JITSI_DOMAIN = os.getenv("TELEMEDICINE_JITSI_DOMAIN", "meet.jit.si")
    TELEMEDICINE_JITSI_SECRET = os.getenv("TELEMEDICINE_JITSI_SECRET", "")
    TELEMEDICINE_JITSI_APP_ID = os.getenv("TELEMEDICINE_JITSI_APP_ID", "mediflow")
    # Path where encrypted document files are stored on the local filesystem.
    DOCUMENT_STORAGE_PATH = os.getenv("DOCUMENT_STORAGE_PATH", str(BASE_DIR / "document_store"))
    # Storage backend: "local" (dev) or "s3" (production with S3-compatible service).
    DOCUMENT_STORAGE_BACKEND = os.getenv("DOCUMENT_STORAGE_BACKEND", "local")
    # S3 settings (only required when DOCUMENT_STORAGE_BACKEND=s3)
    DOCUMENT_S3_BUCKET = os.getenv("DOCUMENT_S3_BUCKET", "")
    DOCUMENT_S3_REGION = os.getenv("DOCUMENT_S3_REGION", "us-east-1")
    DOCUMENT_S3_ENDPOINT_URL = os.getenv("DOCUMENT_S3_ENDPOINT_URL", "")  # override for MinIO/LocalStack
    DOCUMENT_S3_ACCESS_KEY = os.getenv("DOCUMENT_S3_ACCESS_KEY", "")
    DOCUMENT_S3_SECRET_KEY = os.getenv("DOCUMENT_S3_SECRET_KEY", "")
    # Envelope encryption: a URL-safe base64-encoded 32-byte Fernet key.
    # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # In production rotate via key versioning — keep old keys in DOCUMENT_ENCRYPTION_KEY_PREV.
    DOCUMENT_ENCRYPTION_KEY = os.getenv("DOCUMENT_ENCRYPTION_KEY", "")
    DOCUMENT_ENCRYPTION_KEY_PREV = os.getenv("DOCUMENT_ENCRYPTION_KEY_PREV", "")
    # 20 MiB hard limit for medical document uploads (separate from Flask MAX_CONTENT_LENGTH).
    MAX_DOCUMENT_SIZE_BYTES = int(os.getenv("MAX_DOCUMENT_SIZE_BYTES", str(20 * 1024 * 1024)))
    # Comma-separated list of allowed file extensions (without leading dot).
    ALLOWED_DOCUMENT_EXTENSIONS = {
        ext.strip().lower()
        for ext in os.getenv(
            "ALLOWED_DOCUMENT_EXTENSIONS",
            "pdf,jpg,jpeg,png,tiff,tif,bmp,webp",
        ).split(",")
        if ext.strip()
    }
    # Corresponding MIME types for allowed documents.
    ALLOWED_DOCUMENT_MIME_TYPES = {
        "application/pdf",
        "image/jpeg",
        "image/png",
        "image/tiff",
        "image/bmp",
        "image/webp",
    }

    # Task 8: asynchronous blockchain integrity proof layer.
    BLOCKCHAIN_ENABLED = _bool("BLOCKCHAIN_ENABLED")
    BLOCKCHAIN_RPC_URL = os.getenv("BLOCKCHAIN_RPC_URL", "http://127.0.0.1:8545")
    BLOCKCHAIN_CHAIN_ID = int(os.getenv("BLOCKCHAIN_CHAIN_ID", "31337"))
    BLOCKCHAIN_CONTRACT_ADDRESS = os.getenv("BLOCKCHAIN_CONTRACT_ADDRESS", "")
    BLOCKCHAIN_DEPLOYER_PRIVATE_KEY = os.getenv("BLOCKCHAIN_DEPLOYER_PRIVATE_KEY", "")
    BLOCKCHAIN_DEVELOPMENT_UNLOCKED_ACCOUNT = _bool("BLOCKCHAIN_DEVELOPMENT_UNLOCKED_ACCOUNT")
    BLOCKCHAIN_REFERENCE_SECRET = os.getenv("BLOCKCHAIN_REFERENCE_SECRET", SECRET_KEY)
    BLOCKCHAIN_CONFIRMATIONS = int(os.getenv("BLOCKCHAIN_CONFIRMATIONS", "1"))
    BLOCKCHAIN_RETRY_MAX_ATTEMPTS = int(os.getenv("BLOCKCHAIN_RETRY_MAX_ATTEMPTS", "8"))
    BLOCKCHAIN_RETRY_BASE_SECONDS = int(os.getenv("BLOCKCHAIN_RETRY_BASE_SECONDS", "30"))
    BLOCKCHAIN_AUDIT_PERIOD_MINUTES = int(os.getenv("BLOCKCHAIN_AUDIT_PERIOD_MINUTES", "60"))
    BLOCKCHAIN_ABI_PATH = _project_path(
        "BLOCKCHAIN_ABI_PATH",
        PROJECT_ROOT / "blockchain" / "artifacts" / "contracts" / "MediFlowIntegrity.sol" / "MediFlowIntegrity.json",
    )

    # Task 10: transient monitoring pub/sub. Durable records remain in PostgreSQL.
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # Task 12: security controls. Loopback stays recoverable by default.
    SECURITY_IP_ALLOWLIST = {
        value.strip() for value in os.getenv("SECURITY_IP_ALLOWLIST", "127.0.0.1,::1").split(",") if value.strip()
    }
    SECURITY_EVENT_RETENTION_DAYS = int(os.getenv("SECURITY_EVENT_RETENTION_DAYS", "365"))


class DevelopmentConfig(BaseConfig):
    ENV_NAME = "development"
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = _database_url("development")
    SQLALCHEMY_ENGINE_OPTIONS = {
        **BaseConfig.SQLALCHEMY_ENGINE_OPTIONS,
        "pool_size": int(os.getenv("DB_POOL_SIZE", "5")),
        "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", "10")),
        "pool_timeout": int(os.getenv("DB_POOL_TIMEOUT", "30")),
    }


class ProductionConfig(BaseConfig):
    ENV_NAME = "production"
    DEBUG = False
    TESTING = False
    SESSION_COOKIE_SECURE = True
    SQLALCHEMY_DATABASE_URI = _database_url("production")
    SQLALCHEMY_ENGINE_OPTIONS = {
        **BaseConfig.SQLALCHEMY_ENGINE_OPTIONS,
        "pool_size": int(os.getenv("DB_POOL_SIZE", "10")),
        "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", "20")),
        "pool_timeout": int(os.getenv("DB_POOL_TIMEOUT", "30")),
    }


class TestingConfig(BaseConfig):
    ENV_NAME = "testing"
    TESTING = True
    DEBUG = False
    RATELIMIT_ENABLED = False
    SQLALCHEMY_DATABASE_URI = _database_url("testing")
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}


CONFIGS = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}


def get_config(name: str | None = None):
    environment = name or os.getenv("FLASK_ENV", "development")
    return CONFIGS.get(environment, DevelopmentConfig)
