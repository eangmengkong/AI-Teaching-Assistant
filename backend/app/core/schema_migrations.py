"""Lightweight, idempotent schema migrations.

``Base.metadata.create_all()`` only creates tables that are missing — it never
adds new *columns* to tables that already exist. When a model gains a column
after the shared/production database was created, every query touching that
column fails with "column X does not exist".

This module runs tiny guarded ``ALTER TABLE`` statements at startup so that a
deploy also syncs the schema. Every entry is checked against the database
catalog first and is therefore safe to run on every boot.
"""

import logging
from typing import List, Tuple

from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError, OperationalError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

logger = logging.getLogger(__name__)

# (table, column, column type SQL). Keep entries additive and idempotent so
# re-runs against an already-migrated database are no-ops.
_SCHEMA_MIGRATIONS: List[Tuple[str, str, str]] = [
    # The app stores uploaded file bytes in the DB so documents survive
    # redeploys on Render's ephemeral disk.
    ("documents", "file_data", "BYTEA"),
]


async def _column_exists(conn: AsyncConnection, table: str, column: str) -> bool:
    """Return True when ``table.column`` already exists in the database."""
    if conn.dialect.name == "sqlite":
        rows = (await conn.execute(text(f"PRAGMA table_info({table})"))).fetchall()
        return any(row[1] == column for row in rows)

    # Postgres and other information_schema databases
    rows = (
        await conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = :table AND column_name = :column"
            ),
            {"table": table, "column": column},
        )
    ).fetchall()
    return bool(rows)


async def run_schema_migrations(engine: AsyncEngine) -> None:
    """Add any columns introduced after the database was first created."""
    async with engine.begin() as conn:
        for table, column, column_type in _SCHEMA_MIGRATIONS:
            if await _column_exists(conn, table, column):
                continue
            try:
                await conn.execute(
                    text(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")
                )
                logger.info(
                    "Schema migration: added column %s.%s (%s)",
                    table,
                    column,
                    column_type,
                )
            except (ProgrammingError, OperationalError) as exc:
                # Another worker may have added the column between the
                # existence check and the ALTER. Treat duplicate-column as a
                # no-op and let any other error fail loudly.
                sqlstate = str(getattr(getattr(exc, "orig", None), "sqlstate", ""))
                detail = str(exc).lower()
                if (
                    sqlstate == "42701"
                    or "duplicate column" in detail
                    or "already exists" in detail
                ):
                    logger.warning(
                        "Column %s.%s already added by a concurrent process, skipping.",
                        table,
                        column,
                    )
                    continue
                raise