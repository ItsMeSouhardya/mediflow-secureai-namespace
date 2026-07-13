# MediFlow Secure — Deployment and Secrets Management Guide

> Task 15.12 — environment-specific configuration and secrets management.

---

## 1. Environment overview

| Environment | Config file         | Database              | Secret storage        |
|-------------|---------------------|-----------------------|-----------------------|
| Development | `.env` (gitignored) | SQLite or local PG    | Plain `.env` file     |
| CI          | GitHub Actions vars | PostgreSQL service    | GitHub encrypted secrets |
| Staging     | `.env.staging`      | PostgreSQL            | GitHub / Vault        |
| Production  | Environment only    | PostgreSQL (managed)  | HashiCorp Vault / AWS Secrets Manager |

---

## 2. Required environment variables

Generate each secret exactly once and store it in your secrets manager.
**Never commit real values to version control.**

### 2.1 Core Flask / Auth

```bash
# At least 32 random bytes (base64-encoded or hex)
SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
JWT_SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
```

| Variable | Purpose | Example |
|---|---|---|
| `SECRET_KEY` | Flask session signing | 64-char hex |
| `JWT_SECRET_KEY` | Access/refresh token signing (separate key) | 64-char hex |
| `CORS_ORIGINS` | Comma-separated allowed frontend origins | `https://app.mediflow.example` |

### 2.2 Database

```bash
DATABASE_URL=postgresql+psycopg://mediflow:STRONG_PW@db-host:5432/mediflow
```

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | SQLAlchemy connection string |
| `POSTGRES_DB` | Database name (Compose only) |
| `POSTGRES_USER` | Database user (Compose only) |
| `POSTGRES_PASSWORD` | Database password (Compose only) |
| `TEST_DATABASE_URL` | Separate database for CI test runs |

### 2.3 Document encryption

```bash
# Generate a Fernet key (URL-safe base64, 32 bytes):
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

| Variable | Purpose |
|---|---|
| `DOCUMENT_ENCRYPTION_KEY` | Primary KEK for new document uploads |
| `DOCUMENT_ENCRYPTION_KEY_PREV` | Previous KEK (kept during rotation) |
| `DOCUMENT_STORAGE_BACKEND` | `local` or `s3` |
| `DOCUMENT_STORAGE_PATH` | Absolute path for local backend |
| `DOCUMENT_S3_BUCKET` | S3 bucket name |
| `DOCUMENT_S3_REGION` | AWS region |
| `DOCUMENT_S3_ACCESS_KEY` | AWS access key ID |
| `DOCUMENT_S3_SECRET_KEY` | AWS secret access key |

### 2.4 Telemedicine

```bash
TELEMEDICINE_JITSI_SECRET=$(python -c "import secrets; print(secrets.token_hex(32))")
TELEMEDICINE_JITSI_DOMAIN=meet.jit.si
TELEMEDICINE_JITSI_APP_ID=mediflow
```

### 2.5 Blockchain

| Variable | Purpose |
|---|---|
| `BLOCKCHAIN_RPC_URL` | Ethereum RPC endpoint (e.g. Alchemy/Infura or local Hardhat) |
| `BLOCKCHAIN_CONTRACT_ADDRESS` | Deployed MediFlow integrity contract address |
| `BLOCKCHAIN_SIGNER_KEY` | Private key for signing transactions (never the mnemonic) |
| `BLOCKCHAIN_REFERENCE_SECRET` | HMAC key for opaque reference generation |

### 2.6 Redis

```bash
REDIS_PASSWORD=$(python -c "import secrets; print(secrets.token_hex(24))")
```

---

## 3. Generating secrets in bulk

```bash
# Run once and paste into your secrets manager:
python - <<'EOF'
import secrets
from cryptography.fernet import Fernet

keys = {
    "SECRET_KEY":                   secrets.token_hex(32),
    "JWT_SECRET_KEY":               secrets.token_hex(32),
    "DOCUMENT_ENCRYPTION_KEY":      Fernet.generate_key().decode(),
    "TELEMEDICINE_JITSI_SECRET":    secrets.token_hex(32),
    "BLOCKCHAIN_REFERENCE_SECRET":  secrets.token_hex(32),
    "REDIS_PASSWORD":               secrets.token_hex(24),
}
for k, v in keys.items():
    print(f"{k}={v}")
EOF
```

---

## 4. Key rotation procedure

### Document encryption key rotation

1. Generate a new Fernet key: `DOCUMENT_ENCRYPTION_KEY_NEW`.
2. Set `DOCUMENT_ENCRYPTION_KEY_PREV` to the **current** primary key value.
3. Set `DOCUMENT_ENCRYPTION_KEY` to `DOCUMENT_ENCRYPTION_KEY_NEW`.
4. Deploy. New uploads use the new key; existing downloads decrypt with the old key
   (MultiFernet tries both in order).
5. After all documents have been re-uploaded or re-encrypted, clear
   `DOCUMENT_ENCRYPTION_KEY_PREV`.

### JWT key rotation

1. Set `JWT_SECRET_KEY` to the new value.
2. All existing access tokens are immediately invalidated (short TTL — 15 min).
3. Refresh tokens stored as revocable DB sessions continue to work until they expire or are
   revoked. Users will need to log in again after their current access token expires.

---

## 5. Production deployment checklist

- [ ] All secrets generated and stored in Vault / AWS Secrets Manager / GitHub secrets
- [ ] `DOCUMENT_ENCRYPTION_KEY` set and backed up offline (loss = unrecoverable documents)
- [ ] `DATABASE_URL` points to managed PostgreSQL with SSL required (`?sslmode=require`)
- [ ] `CORS_ORIGINS` lists only the production frontend hostname — no wildcards
- [ ] `MFA_REQUIRED_FOR_STAFF=true` set
- [ ] `SESSION_COOKIE_SECURE=true` confirmed (production config class already sets this)
- [ ] Alembic migrations applied: `docker compose -f compose.prod.yaml exec api flask db upgrade`
- [ ] Demo seed data NOT loaded (seed command is explicit CLI; never auto-runs)
- [ ] Blockchain worker service healthy: `docker compose -f compose.prod.yaml ps worker`
- [ ] Backup cron job configured (see `docs/backup-restore.md`)
- [ ] Health endpoints verified: `curl https://app.example/api/v1/health`
- [ ] TLS certificate installed on the load balancer / reverse proxy

---

## 6. Environment-specific .env files

```
.env              ← developer local (gitignored by .gitignore)
.env.example      ← committed; safe placeholders only
.env.staging      ← gitignored; deployed via CI secrets injection
```

Production containers receive all secrets via `docker compose --env-file` or
the orchestrator's secret injection (ECS task definitions, Kubernetes secrets, etc.).
No `.env` file is present inside production containers.
