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
async def test_chunked_upload_end_to_end():
    """init -> parts -> complete assembles file_data server-side and flips
    the document to 'pending' without ever buffering a whole file per part."""
    from httpx import ASGITransport, AsyncClient
    from app.core.database import get_db
    from app.main import app
    from app.models.models import DocumentUploadChunk

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        payload = b"chunked pdf body " * 4096  # ~64 KB -> 3 parts at 32 KB
        part_size = 32 * 1024
        total_chunks = 3
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            init = await client.post(
                "/api/v1/documents/upload/init",
                json={
                    "course_id": 1,
                    "document_type": "textbook",
                    "filename": "big.pdf",
                    "mime_type": "application/pdf",
                    "size": len(payload),
                    "total_chunks": total_chunks,
                },
            )
            assert init.status_code == 200, init.text
            doc_id = init.json()["document_id"]

            for seq in range(total_chunks):
                part = payload[seq * part_size : (seq + 1) * part_size]
                res = await client.post(
                    f"/api/v1/documents/upload/{doc_id}/chunk",
                    data={"seq": str(seq)},
                    files={"chunk": ("part", part, "application/octet-stream")},
                )
                assert res.status_code == 200, res.text

            done = await client.post(
                f"/api/v1/documents/upload/{doc_id}/complete",
                json={"size": len(payload), "total_chunks": total_chunks},
            )
            assert done.status_code == 200, done.text
            body = done.json()
            assert body["status"] == "pending"

        async with factory() as db:
            stored = (
                await db.execute(select(Document).where(Document.id == doc_id))
            ).scalars().one()
            assert stored.file_data == payload
            assert stored.file_size == len(payload)
            leftovers = (
                await db.execute(select(DocumentUploadChunk))
            ).scalars().all()
            assert leftovers == []
    finally:
        app.dependency_overrides.pop(get_db, None)
        await engine.dispose()


@pytest.mark.asyncio
async def test_chunked_upload_complete_rejects_missing_parts():
    from httpx import ASGITransport, AsyncClient
    from app.core.database import get_db
    from app.main import app

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            init = await client.post(
                "/api/v1/documents/upload/init",
                json={
                    "course_id": 1,
                    "document_type": "workbook",
                    "filename": "wb.pdf",
                    "size": 100000,
                    "total_chunks": 2,
                },
            )
            doc_id = init.json()["document_id"]
            await client.post(
                f"/api/v1/documents/upload/{doc_id}/chunk",
                data={"seq": "0"},
                files={"chunk": ("part", b"a" * 1000, "application/octet-stream")},
            )
            done = await client.post(
                f"/api/v1/documents/upload/{doc_id}/complete",
                json={"size": 100000, "total_chunks": 2},
            )
            assert done.status_code == 409
            assert "1/2" in done.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_db, None)
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