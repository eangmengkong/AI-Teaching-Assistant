"""Background processing of uploaded documents.

Uploads are now stored instantly with ``status='pending'`` and parsed by the
already-running background worker. This keeps the upload HTTP request short
(just the network transfer), so big PDFs no longer risk proxy timeouts — the
browser just waits for the document's status to flip to ``processed``.
"""

import logging
from typing import Type

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.database import AsyncSessionLocal
from app.models.models import Document
from app.services.document_service import DocumentService

logger = logging.getLogger(__name__)


async def process_pending_documents(
    limit: int = 10,
    session_factory: Type[async_sessionmaker] = None,
    retry_errored: bool = False,
) -> int:
    """Process documents whose status is 'pending'.

    Returns the number of documents that were handled (success or error).
    The default session factory targets the app database; tests inject their
    own in-memory factory.
    """
    if session_factory is None:
        session_factory = AsyncSessionLocal

    handled = 0
    async with session_factory() as db:
        # A restart may have interrupted an in-flight parse; reset those.
        await db.execute(
            update(Document).where(Document.status == "processing").values(status="pending")
        )
        if retry_errored:
            await db.execute(
                update(Document)
                .where(Document.status == "error", Document.file_data.isnot(None))
                .values(status="pending")
            )
        await db.commit()

        while True:
            stmt = (
                select(Document)
                .where(Document.status == "pending")
                .order_by(Document.id)
                .limit(limit)
            )
            docs = (await db.execute(stmt)).scalars().all()
            if not docs:
                break

            for doc in docs:
                handled += 1
                doc_id = doc.id
                if not doc.file_data:
                    doc.status = "error"
                    await db.commit()
                    logger.warning("Pending document %s has no file_data; marked error", doc_id)
                    continue

                doc.status = "processing"
                await db.commit()
                try:
                    await DocumentService.process_uploaded_document(db, doc)
                    await db.commit()
                    logger.info("Processed pending document %s (%s) -> %d pages", doc_id, doc.filename, doc.total_pages)
                except Exception as exc:  # keep the worker alive on a bad file
                    await db.rollback()
                    await db.execute(
                        update(Document)
                        .where(Document.id == doc_id)
                        .values(status="error", total_pages=0)
                    )
                    await db.commit()
                    logger.exception("Failed to process document %s: %s", doc_id, exc)

    return handled