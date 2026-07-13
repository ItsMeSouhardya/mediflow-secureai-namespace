#!/usr/bin/env bash
# MediFlow Secure — PostgreSQL restore script — task 15.13
#
# Restores from a pg_dump file created by backup.sh.
# DESTRUCTIVE — drops all existing tables before restoring.
#
# Usage:
#   ./scripts/db/restore.sh <path-to-backup.pgdump.gz>
#
# Required environment variables: same as backup.sh
#
# Safety:
#   - Prompts for confirmation unless MEDIFLOW_RESTORE_CONFIRM=yes is set.
#   - Verifies the SHA-256 checksum before restoring if a .sha256 file exists.

set -euo pipefail

BACKUP_FILE="${1:?Usage: $0 <backup.pgdump.gz>}"

# ── Parse DATABASE_URL ─────────────────────────────────────────────────────
if [[ -n "${DATABASE_URL:-}" && -z "${PGHOST:-}" ]]; then
  url="${DATABASE_URL#*://}"
  PGUSER="${url%%:*}"; url="${url#*:}"
  PGPASSWORD="${url%%@*}"; url="${url#*@}"
  host_port="${url%%/*}"
  PGHOST="${host_port%%:*}"; PGPORT="${host_port##*:}"
  PGDATABASE="${url##*/}"; PGDATABASE="${PGDATABASE%%\?*}"
  export PGHOST PGPORT PGUSER PGPASSWORD PGDATABASE
fi

: "${PGHOST:?PGHOST is required}"
: "${PGUSER:?PGUSER is required}"
: "${PGDATABASE:?PGDATABASE is required}"

if [[ ! -f "${BACKUP_FILE}" ]]; then
  echo "ERROR: backup file not found: ${BACKUP_FILE}" >&2
  exit 1
fi

# ── Checksum verification ──────────────────────────────────────────────────
CHECKSUM_FILE="${BACKUP_FILE}.sha256"
if [[ -f "${CHECKSUM_FILE}" ]]; then
  echo "Verifying checksum…"
  sha256sum --check "${CHECKSUM_FILE}"
  echo "Checksum OK."
else
  echo "WARNING: No checksum file found at ${CHECKSUM_FILE} — skipping integrity check."
fi

# ── Confirmation prompt ────────────────────────────────────────────────────
if [[ "${MEDIFLOW_RESTORE_CONFIRM:-}" != "yes" ]]; then
  echo ""
  echo "⚠️  WARNING: This will DROP ALL TABLES in database '${PGDATABASE}' on ${PGHOST}"
  echo "   and replace them with the contents of: ${BACKUP_FILE}"
  echo ""
  read -r -p "Type 'RESTORE' to continue: " CONFIRM
  if [[ "${CONFIRM}" != "RESTORE" ]]; then
    echo "Aborted."
    exit 1
  fi
fi

echo "[$(date -u +%FT%TZ)] Starting restore to ${PGDATABASE} on ${PGHOST}…"

# ── Drop and recreate schema ───────────────────────────────────────────────
psql -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;" "${PGDATABASE}"

# ── Restore ───────────────────────────────────────────────────────────────
gunzip -c "${BACKUP_FILE}" | pg_restore \
  --format=custom \
  --no-acl \
  --no-owner \
  --dbname="${PGDATABASE}" \
  --single-transaction

echo "[$(date -u +%FT%TZ)] Restore complete."

# ── Run migrations to apply any pending schema changes ────────────────────
echo "[$(date -u +%FT%TZ)] Running flask db upgrade…"
flask db upgrade

echo "[$(date -u +%FT%TZ)] Done. Verify row counts with scripts/db/verify_restore.sh"
