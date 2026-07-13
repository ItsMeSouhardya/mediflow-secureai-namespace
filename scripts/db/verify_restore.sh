#!/usr/bin/env bash
# MediFlow Secure — Post-restore verification — task 15.13
# Prints table row counts so you can confirm the restore matches expectations.

set -euo pipefail

if [[ -n "${DATABASE_URL:-}" && -z "${PGHOST:-}" ]]; then
  url="${DATABASE_URL#*://}"
  PGUSER="${url%%:*}"; url="${url#*:}"
  PGPASSWORD="${url%%@*}"; url="${url#*@}"
  host_port="${url%%/*}"
  PGHOST="${host_port%%:*}"; PGPORT="${host_port##*:}"
  PGDATABASE="${url##*/}"; PGDATABASE="${PGDATABASE%%\?*}"
  export PGHOST PGPORT PGUSER PGPASSWORD PGDATABASE
fi

echo "Row counts for database: ${PGDATABASE} on ${PGHOST}"
echo "────────────────────────────────────────────────────"

psql "${PGDATABASE}" <<'SQL'
SELECT
  schemaname,
  tablename,
  n_live_tup AS row_count
FROM pg_stat_user_tables
ORDER BY schemaname, tablename;
SQL
