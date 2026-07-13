"""Print a deterministic JSON baseline from the legacy SQLite database."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path


TABLES = [
    "users",
    "hospitals",
    "departments",
    "doctors",
    "tokens",
    "queue_logs",
    "symptoms_history",
    "emergency_cases",
    "appointments",
    "feedback",
]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def export(path: Path) -> dict:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        counts = {table: connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] for table in TABLES}
        token_statuses = dict(connection.execute("SELECT status, COUNT(*) FROM tokens GROUP BY status"))
        token_priorities = dict(connection.execute("SELECT priority, COUNT(*) FROM tokens GROUP BY priority"))
        samples = {
            "hospitals": [dict(row) for row in connection.execute("SELECT * FROM hospitals ORDER BY hospital_id LIMIT 3")],
            "departments": [dict(row) for row in connection.execute("SELECT * FROM departments ORDER BY dept_id LIMIT 3")],
            "tokens": [dict(row) for row in connection.execute("SELECT * FROM tokens ORDER BY token_id LIMIT 3")],
        }
        return {
            "source": str(path.resolve()),
            "sha256": file_sha256(path),
            "counts": counts,
            "token_statuses": token_statuses,
            "token_priorities": token_priorities,
            "samples": samples,
        }
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1] / "database.db")
    args = parser.parse_args()
    print(json.dumps(export(args.source), indent=2, default=str))


if __name__ == "__main__":
    main()
