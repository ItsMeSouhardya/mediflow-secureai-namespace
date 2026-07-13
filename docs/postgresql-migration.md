# PostgreSQL Migration Runbook

The application now targets PostgreSQL by default. SQLite is retained only as an ignored legacy source and as an isolated test backend.

## Prerequisites

- PostgreSQL 15+ or Docker Compose
- The dependencies from `backend/requirements.txt`
- A copied `.env` based on `.env.example`
- The verified legacy backup described in `phase-0-baseline.md`

## Provision PostgreSQL

With Docker available:

```powershell
docker compose up -d postgres
```

Alternatively, create `mediflow` and `mediflow_test` databases in an existing PostgreSQL service and update `DATABASE_URL` and `TEST_DATABASE_URL`.

## Apply the schema

From `backend`:

```powershell
.venv\Scripts\python.exe -m flask --app app db upgrade
```

## Migrate the legacy data

From the project root:

```powershell
backend\.venv\Scripts\python.exe backend\scripts\migrate_sqlite_to_postgres.py `
  --source backend\database.db `
  --target $env:DATABASE_URL
```

The target must be empty. The command never truncates or overwrites a populated target.

## Verify

```powershell
backend\.venv\Scripts\python.exe -m flask --app backend\app.py verify-db
backend\.venv\Scripts\python.exe backend\scripts\smoke_api.py --database-url $env:DATABASE_URL
```

Compare all output counts with `docs/phase-0-baseline.md`.

Run the guarded online acceptance verifier against `TEST_DATABASE_URL` (the
database name must end in `_test`):

```powershell
Set-Location backend
.venv\Scripts\python.exe scripts\verify_postgres_tasks_1_2.py
Set-Location ..
```

This applies pending migrations to the test database, seeds deterministic test
data when empty, performs 20 concurrent bookings in independent PostgreSQL
transactions, and verifies request IDs, safe validation errors, CORS,
idempotency replay, and rate limiting. It refuses to modify the operational
database.

### Local verification record (2026-07-12)

- Alembic online head: `e6a1c9f42b70`
- Migrated counts: 27 users, 3 hospitals, 18 departments, 36 doctors, 105 tokens
- Token statuses: 67 waiting, 30 completed, 8 missed
- Token priorities: 63 normal, 20 elderly, 22 emergency
- Checked orphan/mismatched references: 0
- Concurrent booking result: 20 committed, 20 unique token numbers, one queue session
- API foundation: request ID, validation, CORS, idempotency, and rate limiting passed

## Fresh demo database

For an empty development database without legacy records:

```powershell
backend\.venv\Scripts\python.exe -m flask --app backend\app.py db upgrade
backend\.venv\Scripts\python.exe -m flask --app backend\app.py seed-demo
```

The seed is deterministic and exits without duplicating existing hospital data.

## Rollback boundary

Do not remove the ignored legacy database or backup until:

1. PostgreSQL counts match the baseline.
2. Foreign-key checks pass.
3. Compatibility API smoke checks pass.
4. A PostgreSQL backup and restore has been tested.
