"""Database engine, session management, and migration runner.

Source: docs/DB_SCHEMA.md §4 (Migrations)
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlmodel import SQLModel, create_engine, select
from sqlmodel.orm.session import Session

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def _get_db_path() -> Path:
    """Resolve the SQLite database path from settings."""
    return get_settings().database_path


def get_engine(db_path: Optional[Path] = None) -> Engine:
    """Return a synchronous SQLAlchemy engine for SQLite.

    Uses WAL mode + check_same_thread disabled for concurrent access.
    """
    db_path = db_path or _get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    url = f"sqlite:///{db_path}"
    engine = create_engine(url, echo=False, connect_args={
        "check_same_thread": False,
    })
    return engine


def init_db(engine: Optional[Engine] = None) -> Engine:
    """Create all tables (for development/first-run).

    In production, use ``run_migrations`` instead to apply migrations sequentially.
    """
    if engine is None:
        engine = get_engine()
    SQLModel.metadata.create_all(engine)
    _enable_wal(engine)
    logger.info("Database initialized at %s", _get_db_path())
    return engine


def _enable_wal(engine: Engine) -> None:
    """Enable WAL mode for concurrent read/write access."""
    with engine.connect() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL"))
        conn.execute(text("PRAGMA foreign_keys=ON"))


def get_session(engine: Optional[Engine] = None) -> Session:
    """Return a SQLModel Session for the given (or default) engine."""
    if engine is None:
        engine = get_engine()
    return Session(engine)


def run_migrations(migrations_dir: Optional[Path] = None) -> list[str]:
    """Run all SQL migration files in order.

    Migration files must be named ``NNN_description.sql``.
    Each file is applied exactly once — tracked in an internal ``_migrations`` table.
    """
    if migrations_dir is None:
        migrations_dir = get_settings().projects_dir.parent / "database" / "migrations"

    if not migrations_dir.exists():
        logger.warning("No migrations directory found at %s", migrations_dir)
        return []

    engine = get_engine()

    # Create migration tracking table
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS _migrations (
                filename TEXT PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.commit()

    applied = []
    migration_files = sorted(migrations_dir.glob("*.sql"))

    with engine.connect() as conn:
        for mig_file in migration_files:
            # Check if already applied
            result = conn.execute(
                text("SELECT 1 FROM _migrations WHERE filename = :fname"),
                {"fname": mig_file.name}
            )
            if result.fetchone():
                logger.debug("Migration %s already applied, skipping", mig_file.name)
                continue

            logger.info("Applying migration: %s", mig_file.name)
            sql = mig_file.read_text()
            conn.execute(text(sql))
            conn.execute(
                text("INSERT INTO _migrations (filename) VALUES (:fname)"),
                {"fname": mig_file.name}
            )
            conn.commit()
            applied.append(mig_file.name)

    return applied
