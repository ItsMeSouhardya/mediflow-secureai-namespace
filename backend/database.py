"""Compatibility exports for the SQLAlchemy database extension.

Runtime code must use repositories/services rather than direct connections.
Schema creation is handled by Alembic; `init_db` exists only for isolated tests.
"""

from extensions import db


def init_db() -> None:
    """Create tables for isolated tests only; production uses Alembic migrations."""
    db.create_all()
