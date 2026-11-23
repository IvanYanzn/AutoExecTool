from __future__ import annotations

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from autoexectool.storage.models import Base
from autoexectool.storage.paths import DataPaths


def create_engine_for_paths(paths: DataPaths) -> Engine:
    url = f"sqlite:///{paths.db_file.as_posix()}"
    engine = create_engine(url, future=True)

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record):  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def _ensure_columns(engine: Engine) -> None:
    """开发期轻量迁移：为已有 SQLite 表补齐新增列。"""
    wanted: dict[str, list[tuple[str, str]]] = {
        "execution_sessions": [
            ("playbook_path", "TEXT DEFAULT ''"),
            ("playbook_json", "TEXT DEFAULT ''"),
            ("host_id", "VARCHAR(36)"),
            ("variables_json", "TEXT DEFAULT '{}'"),
            ("failed_step_key", "VARCHAR(128) DEFAULT ''"),
        ],
        "schedules": [
            ("mode", "VARCHAR(16) DEFAULT 'cron'"),
            ("run_at", "DATETIME"),
        ],
    }
    insp = inspect(engine)
    with engine.begin() as conn:
        for table, cols in wanted.items():
            if table not in insp.get_table_names():
                continue
            existing = {c["name"] for c in insp.get_columns(table)}
            for name, decl in cols:
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {decl}"))


def init_db(engine: Engine) -> None:
    Base.metadata.create_all(engine)
    _ensure_columns(engine)
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS schema_version ("
                "version INTEGER NOT NULL"
                ")"
            )
        )
        row = conn.execute(text("SELECT version FROM schema_version LIMIT 1")).fetchone()
        if row is None:
            conn.execute(text("INSERT INTO schema_version(version) VALUES (3)"))
        else:
            conn.execute(text("UPDATE schema_version SET version = 3"))


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
