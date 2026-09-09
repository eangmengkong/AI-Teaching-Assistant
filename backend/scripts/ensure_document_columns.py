# Ensure production schema columns           -*- coding: utf-8 -*-
"""Idempotently add columns that were introduced after the DB was created.

``Base.metadata.create_all()`` only creates missing tables; it never adds new
columns to existing tables. This script brings a live database up to date so
endpoints stop failing with "column documents.file_data does not exist".

Run from the ``backend`` folder:

    venv\\Scripts\\python.exe -m scripts.ensure_document_columns

It connects with ``SYNC_DATABASE_URL`` from .env (the same URL the deployed
app uses) and adds any missing column, then exits. Safe to re-run.
"""
import os
import sys

import psycopg2

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)

from app.core.config import settings  # noqa: E402  (imports .env)

# (table, column, column type). Keep additive & idempotent — the same list the
# app runs at startup (app.core.schema_migrations) so both stay in sync.
REQUIRED_COLUMNS = [
    ("documents", "file_data", "BYTEA"),
]


def column_exists(cur, table: str, column: str) -> bool:
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s AND column_name = %s
        """,
        (table, column),
    )
    return cur.fetchone() is not None


def main() -> int:
    conn = psycopg2.connect(settings.SYNC_DATABASE_URL)
    conn.autocommit = True  # each ALTER commits on success
    cur = conn.cursor()
    try:
        for table, column, column_type in REQUIRED_COLUMNS:
            if column_exists(cur, table, column):
                print(f"[ok]      {table}.{column} already present")
                continue
            cur.execute(
                f'ALTER TABLE "public"."{table}" ADD COLUMN "{column}" {column_type}'
            )
            print(f"[added]   {table}.{column} {column_type}")
    finally:
        cur.close()
        conn.close()
    print("\nSchema is up to date.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())