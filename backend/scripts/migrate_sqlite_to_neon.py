# Migrate local SQLite                       -*- coding: utf-8 -*-
"""One-shot migration: copy every row from the local SQLite DB into Neon.

Run from the ``backend`` folder:

    venv\\Scripts\\python.exe -m scripts.migrate_sqlite_to_neon

Behaviour
---------
* Each table that exists in SQLite *and* in PostgreSQL is truncated and
  re-filled with the same row ids (so ``course_id=1`` references keep
  working), then PostgreSQL sequences are advanced past the max id.
* Everything runs inside a single transaction - if one table fails the
  whole migration rolls back and Neon is left untouched.
* The old fallback user (``teacher@local.com`` with the placeholder hash)
  gets a real bcrypt password hash for ``admin123`` so the new login flow
  works out of the box. Change it from the dashboard or the DB afterwards.
"""
import json
import os
import sqlite3
import sys

import psycopg2
from psycopg2.extras import Json

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)

from app.core.config import settings  # noqa: E402
from app.core.security import get_password_hash  # noqa: E402

SQLITE_PATH = os.path.join(BACKEND_DIR, "ai_teaching_assistant.db")
DEFAULT_PASSWORD = "admin123"
PLACEHOLDER_HASH = "default_hashed_password_123"

# Tables owned by the app (skip sqlite internals like sqlite_sequence).
APP_TABLES = {
    "users", "courses", "students", "documents", "document_pages",
    "document_chunks", "units", "lessons", "workbook_exercises",
    "lesson_schedule", "lesson_progress", "homework", "reviews",
    "quizzes", "quiz_questions", "quiz_results",
    "exams", "exam_questions", "exam_results",
    "calendar_events", "telegram_messages", "holidays", "settings",
}


def sqlite_tables(con: sqlite3.Connection) -> list[str]:
    rows = con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name != 'alembic_version'"
    ).fetchall()
    return [r[0] for r in rows]


def pg_columns(cur, table: str) -> dict[str, str]:
    cur.execute(
        """
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        """,
        (table,),
    )
    return {name: dtype for name, dtype in cur.fetchall()}


def convert_value(raw, pg_type: str):
    """Adapt a sqlite value to the PostgreSQL type."""
    if raw is None:
        return None
    if pg_type in ("json", "jsonb", "jsonarray"):
        return Json(raw if isinstance(raw, (dict, list)) else json.loads(raw or "null"))
    if pg_type == "boolean":
        return bool(raw)
    if pg_type == "integer":
        return int(raw)
    if pg_type == "bigint":
        return int(raw)
    return raw


def main() -> int:
    if not os.path.exists(SQLITE_PATH):
        print(f"[error] SQLite database not found: {SQLITE_PATH}")
        return 1

    sqlite = sqlite3.connect(SQLITE_PATH)
    sqlite.row_factory = sqlite3.Row

    conn = psycopg2.connect(settings.SYNC_DATABASE_URL)
    conn.autocommit = False
    cur = conn.cursor()

    try:
        tables = [t for t in sqlite_tables(sqlite) if t in APP_TABLES]
        print(f"SQLite tables to migrate ({len(tables)}): {', '.join(tables)}")

        # Truncate existing rows only for tables we will actually copy.
        existing = [t for t in tables if pg_columns(cur, t)]
        if existing:
            quoted = ", ".join(f'"public"."{t}"' for t in existing)
            cur.execute(f"TRUNCATE {quoted} RESTART IDENTITY CASCADE")
            print("Truncated:", ", ".join(existing))

        total_rows = 0
        for table in tables:
            cols = pg_columns(cur, table)
            if not cols:
                print(f"  [skip] {table}: not present in PostgreSQL")
                continue

            sqlite_cols = [r[1] for r in sqlite.execute(f'PRAGMA table_info("{table}")').fetchall()]
            common = [c for c in sqlite_cols if c in cols]

            col_list = ", ".join(f'"{c}"' for c in sqlite_cols)
            rows = sqlite.execute(f'SELECT {col_list} FROM "{table}"').fetchall()

            if not rows:
                print(f"  {table}: 0 rows (nothing to copy)")
                continue

            values = []
            for row in rows:
                if table == "users":
                    # Replace the placeholder password hash so login works.
                    row_vals = dict(row)
                    if row_vals.get("hashed_password") == PLACEHOLDER_HASH:
                        row_vals["hashed_password"] = get_password_hash(DEFAULT_PASSWORD)
                    row = row_vals

                packed = [convert_value(dict(row).get(c), cols.get(c)) for c in common]
                values.append(packed)

            placeholders = ", ".join(["%s"] * len(common))
            cols_sql = ", ".join(f'"{c}"' for c in common)
            cur.executemany(
                f'INSERT INTO "public"."{table}" ({cols_sql}) VALUES ({placeholders})',
                values,
            )
            print(f"  {table}: {len(values)} rows copied")

            # Advance the id sequence so new inserts don't collide.
            if "id" in common:
                cur.execute("SELECT pg_get_serial_sequence(%s, 'id')", (table,))
                seq = cur.fetchone()[0]
                if seq:
                    cur.execute(f"SELECT COALESCE(MAX(id), 0) FROM \"{table}\"")
                    max_id = cur.fetchone()[0]
                    cur.execute(f"SELECT setval('{seq}', {max_id + 1}, false)")
            total_rows += len(values)

        conn.commit()
        print(f"\nMigration committed. {total_rows} rows total.")
        if any('users' == t for t in tables):
            print(f"Default login for '{DEFAULT_PASSWORD}' was set on the migrated fallback user.")
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()
        sqlite.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())