# Phase 0 Baseline

## Source snapshot

- Snapshot date: 2026-07-11
- Legacy database: `backend/database.db`
- Backup: `backend/backups/database-pre-postgres-20260711.sqlite3` (intentionally ignored by Git)
- Source and backup SHA-256: `AD94BD10E79A4B49095C3AA1C166568471C49FC6A65BA399F439B75093788CDB`
- Source size: 77,824 bytes

## Legacy data counts

| Table | Rows |
|---|---:|
| users | 27 |
| hospitals | 3 |
| departments | 18 |
| doctors | 36 |
| tokens | 105 |
| queue_logs | 54 |
| symptoms_history | 9 |
| emergency_cases | 0 |
| appointments | 2 |
| feedback | 2 |

Token statuses: 67 waiting, 30 completed, and 8 missed.

Token priorities: 63 normal, 20 elderly, and 22 emergency.

## Frontend route baseline

| Route | Page |
|---|---|
| `/` | Landing |
| `/dashboard` | Hospital dashboard |
| `/queue` | Queue tracker |
| `/bookings` | Token booking |
| `/emergency` | Emergency analyzer |
| `/ai-report` | AI smart report |

## Compatibility API groups

- AI/reporting: `/api/ai-report`, `/api/wait-time`, `/api/crowd-info`, `/api/analyze`, `/api/doctor`, `/api/navigation`, `/api/hospital-suggestion`, `/api/elderly`, `/api/priority`
- Queue: `/api/tokens/book`, `/api/tokens/<token>`, `/api/position`, `/api/live-status`, `/api/alerts`
- Hospital: `/api/dashboard/stats`, `/api/hospitals`, `/api/departments`, `/api/departments/overview`, `/api/doctors`
- Prototype records: `/api/symptoms-history`, `/api/emergency-cases`, `/api/appointments`, `/api/feedback`

## Health conventions

- `GET /api/health` is process liveness and does not query dependencies.
- `GET /api/ready` verifies database connectivity and returns HTTP 503 when unavailable.
- The frontend may show dependency status, but a failed readiness response must not be represented as a successful live-data state.

## Restore procedure

1. Stop the backend.
2. Verify the backup checksum against the value above.
3. Copy the ignored backup over `backend/database.db` only if rollback to the legacy prototype is required.
4. Run `backend/scripts/export_sqlite_baseline.py` and compare counts before using the restored file.

## Migration invariant

The PostgreSQL migration is accepted only when the source and destination counts match for every legacy table, all foreign keys are valid, token status/priority totals match, and representative API smoke tests pass.
