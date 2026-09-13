# Backfill file bytes into Cloudflare R2      -*- coding: utf-8 -*-
"""One-shot backfill: move existing ``documents.file_data`` rows into R2.

Run from the ``backend`` folder (with the ``R2_*`` env vars set and boto3
installed):

    venv\\Scripts\\python.exe -m scripts.backfill_documents_to_r2

For every row that still has its bytes in the database (``file_data`` IS NOT
NULL and ``file_path`` is empty / not already an ``r2://`` key) it:

 * streams the BYTEA out a bounded batch at a time,
 * uploads it to Cloudflare R2 (key ``r2://documents/<course>/<type>/<uuid><ext>``),
 * updates the row: ``file_path = r2://...``, ``file_data = NULL``.

Safe and idempotent: rows already pointing at R2 are skipped, and every batch
is committed before the next one starts, so a crash never loses progress.
"""
import os
import sys

import psycopg2
import psycopg2.extras

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)

from app.core.config import settings  # noqa: E402
from app.services import file_store  # noqa: E402

BATCH_SIZE = 50

QUERY = """
    SELECT id, course_id, document_type, filename, mime_type, file_data
    FROM documents
    WHERE file_data IS NOT NULL
      AND (file_path IS NULL OR file_path = '' OR file_path NOT LIKE 'r2://%')
      AND id > %s
    ORDER BY id
    LIMIT %s
"""


def main() -> int:
    if not file_store.r2_enabled():
        print(
            "Cloudflare R2 is not configured. Set R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, "
            "R2_SECRET_ACCESS_KEY and R2_BUCKET first."
        )
        return 1

    conn = psycopg2.connect(settings.SYNC_DATABASE_URL)
    migrated = 0
    failed = 0
    last_id = 0

    while True:
        # Named (server-side) cursor keeps large BYTEA values out of memory,
        # and it is closed before the batch UPDATE so commit() is safe.
        cur = conn.cursor("backfill_r2", cursor_factory=psycopg2.extras.RealDictCursor)
        cur.itersize = BATCH_SIZE
        cur.execute(QUERY, (last_id, BATCH_SIZE))
        rows = cur.fetchall()
        cur.close()

        if not rows:
            break

        updates = []
        for row in rows:
            doc_id = row["id"]
            last_id = doc_id
            try:
                data = bytes(row["file_data"])
            except Exception as exc:  # noqa: BLE001 - report and continue
                print(f"  ! doc {doc_id}: cannot read bytea: {exc}")
                failed += 1
                continue
            if not data:
                continue
            remote_path = file_store.store_document_bytes(
                row["course_id"],
                row["document_type"],
                row["filename"],
                data,
                row["mime_type"] or "application/octet-stream",
            )
            updates.append((remote_path, doc_id))
            print(
                f"  ✓ doc {doc_id}: {row['filename']} -> {remote_path} "
                f"({len(data) / (1024 * 1024):.1f} MB)"
            )

        if updates:
            with conn.cursor() as upd:
                upd.executemany(
                    "UPDATE documents SET file_path = %s, file_data = NULL WHERE id = %s",
                    updates,
                )
            conn.commit()
            migrated += len(updates)

    conn.close()
    print(f"\nDone: {migrated} documents moved to R2, {failed} failed.")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())