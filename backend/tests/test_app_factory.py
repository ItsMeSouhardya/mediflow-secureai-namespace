from __future__ import annotations

from sqlalchemy import create_engine, inspect

from app import create_app


def test_create_app_does_not_create_schema(tmp_path):
    database_path = tmp_path / "factory.db"
    database_url = f"sqlite+pysqlite:///{database_path.as_posix()}"
    create_app(
        "testing",
        {
            "SQLALCHEMY_DATABASE_URI": database_url,
            "SQLALCHEMY_ENGINE_OPTIONS": {},
        },
    )
    engine = create_engine(database_url)
    try:
        assert inspect(engine).get_table_names() == []
    finally:
        engine.dispose()
