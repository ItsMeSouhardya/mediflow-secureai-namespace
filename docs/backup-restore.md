# MediFlow Secure — Backup and Restore Procedures

> Task 15.13 — database backups and documented restore procedures.

---

## 1. Backup strategy

| Type | Tool | Schedule | Retention |
|---|---|---|---|
| Full logical dump | `pg_dump --format=custom` | Daily at 02:00 UTC | 14 days local + 90 days S3 |
| WAL streaming (optional) | `pg_basebackup` / managed PG WAL | Continuous | 7 days |
| Document store | S3 versioning or `rsync` | Daily | 30 days |

Every backup is **SHA-256 checksummed** and the checksum file is stored alongside the dump.

---

## 2. Running a backup

```bash
# Local backup to ./backups/
DATABASE_URL="postgresql+psycopg://user:pass@localhost:5432/mediflow" \
  ./scripts/db/backup.sh

# With S3 upload
DATABASE_URL="..." \
BACKUP_S3_BUCKET="s3://my-company-backups/mediflow" \
  ./scripts/db/backup.sh

# Via Compose (runs against the postgres service)
docker compose -f compose.prod.yaml exec postgres \
  sh -c "pg_dump -U mediflow mediflow | gzip" > mediflow-$(date +%Y%m%d).pgdump.gz
```

Backups are stored in `./backups/mediflow-<TIMESTAMP>.pgdump.gz` and checksummed in the paired `.sha256` file.

---

## 3. Restoring from a backup

> **DESTRUCTIVE** — this replaces all data in the target database.

```bash
# Step 1: stop the API and worker so no writes occur during restore
docker compose -f compose.prod.yaml stop api worker

# Step 2: verify checksum (automatic in restore.sh)
sha256sum --check backups/mediflow-20260712T020000Z.pgdump.gz.sha256

# Step 3: restore (will prompt for confirmation)
DATABASE_URL="postgresql+psycopg://user:pass@localhost:5432/mediflow" \
  ./scripts/db/restore.sh backups/mediflow-20260712T020000Z.pgdump.gz

# Step 4: verify row counts
DATABASE_URL="..." ./scripts/db/verify_restore.sh

# Step 5: restart services
docker compose -f compose.prod.yaml start api worker
```

To skip the interactive prompt in automated pipelines:
```bash
MEDIFLOW_RESTORE_CONFIRM=yes DATABASE_URL="..." \
  ./scripts/db/restore.sh backups/mediflow-20260712T020000Z.pgdump.gz
```

---

## 4. Migration rollback

If a bad migration is deployed:

```bash
# Check current revision
flask db current

# Roll back one step
flask db downgrade -1

# Roll back to a specific revision
flask db downgrade <revision_id>
```

Every migration has a `downgrade()` function. Verify it on staging before rolling back production.

---

## 5. Disaster recovery (full loss)

1. Provision a fresh PostgreSQL instance.
2. Create the database and user:
   ```sql
   CREATE DATABASE mediflow;
   CREATE USER mediflow WITH PASSWORD '...';
   GRANT ALL ON DATABASE mediflow TO mediflow;
   ```
3. Run the restore script with the latest backup.
4. If the backup pre-dates the latest migration, run `flask db upgrade` afterwards
   (restore.sh does this automatically).
5. Restore the document store from S3 or your object storage backup.
6. Update `DATABASE_URL` in secrets manager to point to the new host.
7. Restart all services.
8. Run smoke tests: `python backend/scripts/smoke_api.py`.

---

## 6. Cron job example (server crontab)

```cron
# Daily backup at 02:00 UTC
0 2 * * * \
  DATABASE_URL="$(cat /run/secrets/DATABASE_URL)" \
  BACKUP_S3_BUCKET="s3://my-backups/mediflow" \
  /app/scripts/db/backup.sh >> /var/log/mediflow-backup.log 2>&1
```

---

## 7. Document store backup

Encrypted document files (`.enc`) in the `document_store` volume must be backed up
**together with the `DOCUMENT_ENCRYPTION_KEY`** stored in your secrets manager.
Without the key, the files cannot be decrypted even if restored.

```bash
# S3 sync (idempotent, only uploads changed files)
aws s3 sync /data/documents s3://my-backups/mediflow-docs/ --sse AES256

# Restore
aws s3 sync s3://my-backups/mediflow-docs/ /data/documents/
```
