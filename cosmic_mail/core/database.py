from __future__ import annotations

import logging

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from cosmic_mail.domain.models import Base

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Incremental schema migrations
#
# SQLAlchemy's create_all() only creates *missing tables* — it never alters
# existing tables to add new columns.  We manage that gap here with a simple
# inspect-and-ALTER approach so deployments on existing databases are fully
# automatic.
#
# Each entry: (table, column, postgres_ddl, sqlite_ddl)
# Add a new row whenever a column is added to an existing model.
# ---------------------------------------------------------------------------
_COLUMN_MIGRATIONS: list[tuple[str, str, str, str]] = [
    # bounce detection fields added to MailMessage
    ("messages", "is_bounce",   "BOOLEAN NOT NULL DEFAULT FALSE", "BOOLEAN NOT NULL DEFAULT 0"),
    ("messages", "bounce_type", "VARCHAR(32)",                    "VARCHAR(32)"),
]


def build_engine(database_url: str) -> Engine:
    if database_url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
        if database_url.endswith(":memory:"):
            return create_engine(
                database_url,
                connect_args=connect_args,
                poolclass=StaticPool,
            )
        return create_engine(database_url, connect_args=connect_args, pool_pre_ping=True)
    return create_engine(database_url, pool_pre_ping=True)


def build_session_factory(engine: Engine) -> sessionmaker:
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def _run_column_migrations(engine: Engine) -> None:
    """Add any columns that exist in the model but are missing from the live DB.

    Idempotent — safe to run on every startup.
    """
    dialect = engine.dialect.name
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    with engine.begin() as conn:
        for table, column, pg_ddl, sqlite_ddl in _COLUMN_MIGRATIONS:
            if table not in existing_tables:
                continue  # table will be created by create_all below
            existing_cols = {c["name"] for c in inspector.get_columns(table)}
            if column in existing_cols:
                continue
            ddl = pg_ddl if dialect == "postgresql" else sqlite_ddl
            logger.info("Schema migration: ALTER TABLE %s ADD COLUMN %s %s", table, column, ddl)
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))


def init_db(engine: Engine) -> None:
    _run_column_migrations(engine)
    Base.metadata.create_all(bind=engine)
