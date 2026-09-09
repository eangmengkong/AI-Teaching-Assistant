"""Tests for the faster-upload path (client compression + background parsing).

Covers:
1. upload_codec.decompress_payload: accepts zlib and raw DEFLATE, and rejects
   garbage (invalid compressed upload -> readable 400, not a hung request).
2. process_pending_documents: a stored "pending" document gets parsed by the
   background worker into pages/chunks and flips to "processed" (idempotent,
   runs on worker threads so the API event loop is never blocked).
"""

import io
import zlib

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Base
import app.models.models  # noqa: F401  (register all tables on Base.metadata)
from app.models.models import Document, DocumentPage, DocumentChunk
from app.services.document_processing_service import process_pending_documents
from app.services.upload_codec import decompress_payload, InvalidCompressedUpload


# ---------------------------------------------------------------------------
# upload_codec
# ---------------------------------------------------------------------------

def test_decompress_payload_plain():
    payload = b"raw bytes"
    assert decompress_payload(payload, False) == payload


def test_decompress_payload_zlib():
    original = b"hello world" * 512
    assert decompress_payload(zlib.compress(original), True) == original


def test_decompress_payload_raw_deflate():
    original = b"raw deflate payload" * 256
    compressor = zlib.compressobj(6, zlib.DEFLATED, -15)
    compressed = compressor.compress(original) + compressor.flush()
    assert decompress_payload(compressed, True) == original


def test_decompress_payload_rejects_garbage():
    with pytest.raises(InvalidCompressedUpload):
        decompress_payload(b"\x00\x01\x02\x03 not deflate at all", True)


# ---------------------------------------------------------------------------
# background processing
# ---------------------------------------------------------------------------

def _tiny_pdf() -> bytes:
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_process_pending_document_builds_rows():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as db:
        doc = Document(
            course_id=1,
            document_type="textbook",
            filename="sample.pdf",
            file_data=_tiny_pdf(),
            total_pages=0,
            status="pending",
        )
        db.add(doc)
        await db.commit()
        doc_id = doc.id

    handled = await process_pending_documents(limit=2, session_factory=factory)
    assert handled == 1

    async with factory() as db:
        stored = (
            await db.execute(select(Document).where(Document.id == doc_id))
        ).scalars().one()
        assert stored.status == "processed"
        assert stored.total_pages == 1

        pages = (
            await db.execute(select(DocumentPage).where(DocumentPage.document_id == doc_id))
        ).scalars().all()
        chunks = (
            await db.execute(select(DocumentChunk).where(DocumentChunk.document_id == doc_id))
        ).scalars().all()
        assert len(pages) == 1
        assert len(chunks) == 1

    await engine.dispose()


@pytest.mark.asyncio
async def test_process_pending_document_without_bytes_is_marked_error():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as db:
        doc = Document(
            course_id=1,
            document_type="textbook",
            filename="broken.pdf",
            file_data=None,
            total_pages=0,
            status="pending",
        )
        db.add(doc)
        await db.commit()
        doc_id = doc.id

    handled = await process_pending_documents(limit=2, session_factory=factory)
    assert handled == 1

    async with factory() as db:
        stored = (
            await db.execute(select(Document).where(Document.id == doc_id))
        ).scalars().one()
        assert stored.status == "error"

    await engine.dispose()