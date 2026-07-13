#!/usr/bin/env bash
# MediFlow Secure — PostgreSQL backup script — task 15.13
#
# Creates a compressed, timestamped pg_dump and optionally uploads it to S3.
# Designed to be run as a cron job or a Docker one-shot container.
#
# Usage:
#   ./scripts/db/backup.sh
#
# Required environment variables:
#   DATABASE_URL     — PostgreSQL connection string
#     OR individually: PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE
#
# Optional:
#   BACKUP_DIR       — Local directory to store backups (default: ./backups)
#   BACKUP_S3_BUCKET — Upload to this S3 bucket if set (e.g. s3://my-bucket/mediflow-backups)
#   BACKUP_RETAIN_DAYS — Delete local backups older than N days (default: 14)
#
# Example cron (daily at 02:00 UTC):
#   0 2 * * * /app/scripts/db/backup.sh >> /var/log/mediflow-backup.log 2>&1

set -euo pipefail

TIMESTAMP=$(date -u +"%Y%m%dT%H%M%SZ")
BACKUP_DIR="${BACKUP_DIR:-./backups}"
RETAIN_DAYS="${BACKUP_RETAIN_DAYS:-14}"
BACKUP_FILE="${BACKUP_DIR}/mediflow-${TIMESTAMP}.pgdump.gz"

# ── Parse DATABASE_URL if individual variables not already set ─────────────
if [[ -n "${DATABASE_URL:-}" && -z "${PGHOST:-}" ]]; then
  # Strip scheme (postgresql+psycopg:// or postgresql://)
  url="${DATABASE_URL#*://}"
  PGUSER="${url%%:*}"
  url="${url#*:}"
  PGPASSWORD="${url%%@*}"
  url="${url#*@}"
  host_port="${url%%/*}"
  PGHOST="${host_port%%:*}"
  PGPORT="${host_port##*:}"
  PGDATABASE="${url##*/}"
  # Strip query string from database name
  PGDATABASE="${PGDATABASE%%\?*}"
  export PGHOST PGPORT PGUSER PGPASSWORD PGDATABASE
fi

# ── Validate ───────────────────────────────────────────────────────────────
: "${PGHOST:?PGHOST is required}"
: "${PGUSER:?PGUSER is required}"
: "${PGDATABASE:?PGDATABASE is required}"

mkdir -p "${BACKUP_DIR}"

echo "[$(date -u +%FT%TZ)] Starting backup: ${BACKUP_FILE}"

# ── Dump ──────────────────────────────────────────────────────────────────
pg_dump \
  --format=custom \
  --no-acl \
  --no-owner \
  --compress=9 \
  "${PGDATABASE}" \
  | gzip -9 > "${BACKUP_FILE}"

BACKUP_SIZE=$(du -h "${BACKUP_FILE}" | cut -f1)
echo "[$(date -u +%FT%TZ)] Backup complete: ${BACKUP_FILE} (${BACKUP_SIZE})"

# ── Checksum ──────────────────────────────────────────────────────────────
sha256sum "${BACKUP_FILE}" > "${BACKUP_FILE}.sha256"
echo "[$(date -u +%FT%TZ)] Checksum: $(cat "${BACKUP_FILE}.sha256")"

# ── Optional S3 upload ─────────────────────────────────────────────────────
if [[ -n "${BACKUP_S3_BUCKET:-}" ]]; then
  echo "[$(date -u +%FT%TZ)] Uploading to ${BACKUP_S3_BUCKET}…"
  aws s3 cp "${BACKUP_FILE}"       "${BACKUP_S3_BUCKET}/" --sse AES256
  aws s3 cp "${BACKUP_FILE}.sha256" "${BACKUP_S3_BUCKET}/"
  echo "[$(date -u +%FT%TZ)] Upload complete."
fi

# ── Prune old local backups ────────────────────────────────────────────────
find "${BACKUP_DIR}" -name "mediflow-*.pgdump.gz*" -mtime "+${RETAIN_DAYS}" -delete
echo "[$(date -u +%FT%TZ)] Pruned backups older than ${RETAIN_DAYS} days."

echo "[$(date -u +%FT%TZ)] Done."
