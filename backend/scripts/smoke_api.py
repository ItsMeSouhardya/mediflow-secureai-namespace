"""Read-only smoke checks for a migrated MediFlow database."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app import create_app  # noqa: E402


PATHS = [
    "/api/health",
    "/api/ready",
    "/api/hospitals",
    "/api/departments?hospital_id=1",
    "/api/dashboard/stats?hospital_id=1",
    "/api/analyze?symptoms=chest%20pain&dept_id=1",
    "/api/ai-report?dept_id=1&token=A001&symptoms=fever&age=45",
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    args = parser.parse_args()
    app = create_app(
        "testing",
        {
            "SQLALCHEMY_DATABASE_URI": args.database_url,
            "SQLALCHEMY_ENGINE_OPTIONS": {"pool_pre_ping": True},
        },
    )
    client = app.test_client()
    failures = []
    for path in PATHS:
        response = client.get(path)
        print(f"{response.status_code} {path}")
        if response.status_code != 200:
            failures.append(path)
    if failures:
        raise SystemExit(f"Smoke checks failed: {', '.join(failures)}")


if __name__ == "__main__":
    main()
