import asyncio
import os
import tempfile
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, Response
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func, text

from app.core.database import get_db
from app.core.config import settings
from app.api.v1.auth import get_current_user
from app.models.models import User, Course, Document, DocumentUploadChunk
from app.schemas.schemas import DocumentResponse, UploadInitRequest, UploadCompleteRequest
from app.services.document_service import DocumentService
from app.services.document_processing_service import process_pending_documents
from app.services.study_material_service import StudyMaterialService
from app.services.upload_codec import StreamDecompressor, InvalidCompressedUpload, decompress_payload

router = APIRouter()

ALLOWED_DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt"}
MAX_UPLOAD_SIZE = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024


@router.post("/upload", response_model=DocumentResponse)
async def upload_document(
    course_id: int = Form(...),
    document_type: str = Form(...), # "textbook" or "workbook"
    file: UploadFile = File(...),
    compressed: int = Form(0), # 1 when the client deflated the payload (PDF/TXT)
    db: AsyncSession = Depends(get_db)
):
    if document_type.lower() not in ["textbook", "workbook"]:
        raise HTTPException(status_code=400, detail="document_type must be 'textbook' or 'workbook'")

    filename = file.filename or ""
    file_ext = os.path.splitext(filename)[1].lower()
    if file_ext not in ALLOWED_DOCUMENT_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{file_ext}'. Allowed: {', '.join(sorted(ALLOWED_DOCUMENT_EXTENSIONS))}",
        )

    # Read the body STREAMING to a temp file. Buffering the whole upload in
    # RAM (raw += chunk) OOM-kills the 512 MB free-tier instance on large
    # files, which shows up in the browser as a CORS/connection failure.
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=settings.UPLOAD_DIR, suffix=".upload")
    written = 0
    try:
        decompressor = StreamDecompressor() if compressed else None
        with os.fdopen(fd, "wb") as out:
            while chunk := await file.read(1024 * 1024):
                if decompressor is not None:
                    chunk = decompressor.feed(chunk)
                written += len(chunk)
                if written > MAX_UPLOAD_SIZE:
                    raise HTTPException(
                        status_code=413,
                        detail="File exceeds the 500 MB upload limit.",
                    )
                out.write(chunk)
            if decompressor is not None:
                tail = decompressor.finish()
                written += len(tail)
                if written > MAX_UPLOAD_SIZE:
                    raise HTTPException(
                        status_code=413,
                        detail="File exceeds the 500 MB upload limit.",
                    )
                out.write(tail)

        # Single read for the DB insert (one copy in memory, not three).
        with open(tmp_path, "rb") as stored:
            file_bytes = stored.read()
    except InvalidCompressedUpload:
        raise HTTPException(status_code=400, detail="Invalid compressed upload data.")
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
    if len(file_bytes) > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=413,
            detail="File exceeds the 500 MB upload limit.",
        )

    # Store the file immediately and return. Parsing pages/search chunks is
    # done by the background worker (status 'pending' -> 'processed'), so a
    # large upload only takes as long as the network transfer, never the
    # CPU-bound text extraction.
    doc = Document(
        course_id=course_id,
        document_type=document_type.lower(),
        filename=filename,
        # The production column is NOT NULL even though the model allows null,
        # so store an empty string (the bytes live in file_data).
        file_path="",
        file_data=file_bytes,
        mime_type=file.content_type,
        file_size=len(file_bytes),
        total_pages=0,
        status="pending",
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    asyncio.create_task(process_pending_documents())
    return doc

# ---------------------------------------------------------------------------
# Chunked (large file) upload: the client sends a few MB per request so the
# free-tier instance never buffers a whole 100 MB file in RAM (which OOM-kills
# it and shows up in the browser as a CORS/connection failure).
# ---------------------------------------------------------------------------

UPLOAD_CHUNK_MAX_BYTES = 8 * 1024 * 1024


@router.post("/upload/init")
async def upload_init(
    payload: UploadInitRequest,
    db: AsyncSession = Depends(get_db),
):
    document_type = payload.document_type.lower()
    if document_type not in ["textbook", "workbook"]:
        raise HTTPException(status_code=400, detail="document_type must be 'textbook' or 'workbook'")
    file_ext = os.path.splitext(payload.filename)[1].lower()
    if file_ext not in ALLOWED_DOCUMENT_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{file_ext}'. Allowed: {', '.join(sorted(ALLOWED_DOCUMENT_EXTENSIONS))}",
        )
    if payload.size > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail="File exceeds the 500 MB upload limit.")
    if payload.total_chunks < 1 or payload.size < 1:
        raise HTTPException(status_code=400, detail="Invalid upload size.")

    # Housekeeping: drop abandoned partial uploads (older than a day).
    cutoff = datetime.utcnow() - timedelta(days=1)
    stale = await db.execute(
        select(Document).where(Document.status == "uploading", Document.created_at < cutoff)
    )
    for stale_doc in stale.scalars().all():
        await db.execute(
            delete(DocumentUploadChunk).where(DocumentUploadChunk.document_id == stale_doc.id)
        )
        await db.delete(stale_doc)

    doc = Document(
        course_id=payload.course_id,
        document_type=document_type,
        filename=payload.filename,
        file_path="",  # production column is NOT NULL; bytes live in file_data
        file_data=b"",
        mime_type=payload.mime_type,
        file_size=payload.size,
        total_pages=0,
        status="uploading",
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    return {"document_id": doc.id, "chunk_size": UPLOAD_CHUNK_MAX_BYTES}


@router.post("/upload/{document_id}/chunk")
async def upload_chunk(
    document_id: int,
    seq: int = Form(...),
    chunk: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    doc = (
        await db.execute(select(Document).where(Document.id == document_id))
    ).scalars().first()
    if doc is None or doc.status != "uploading":
        raise HTTPException(status_code=409, detail="Upload session not found or already completed.")

    data = await chunk.read()
    if len(data) > UPLOAD_CHUNK_MAX_BYTES:
        raise HTTPException(status_code=413, detail="Chunk too large.")
    if not data:
        raise HTTPException(status_code=400, detail="Empty chunk.")

    # Idempotent per part so a client retry never duplicates bytes.
    await db.execute(
        delete(DocumentUploadChunk).where(
            DocumentUploadChunk.document_id == document_id,
            DocumentUploadChunk.seq == seq,
        )
    )
    db.add(DocumentUploadChunk(document_id=document_id, seq=seq, data=data))
    await db.commit()
    return {"received": seq}


@router.post("/upload/{document_id}/complete", response_model=DocumentResponse)
async def upload_complete(
    document_id: int,
    payload: UploadCompleteRequest,
    db: AsyncSession = Depends(get_db),
):
    doc = (
        await db.execute(select(Document).where(Document.id == document_id))
    ).scalars().first()
    if doc is None or doc.status != "uploading":
        raise HTTPException(status_code=409, detail="Upload session not found or already completed.")

    count_result = await db.execute(
        select(func.count()).select_from(DocumentUploadChunk).where(
            DocumentUploadChunk.document_id == document_id
        )
    )
    chunk_count = count_result.scalar_one()
    if chunk_count != payload.total_chunks:
        raise HTTPException(
            status_code=409,
            detail=f"Upload incomplete: received {chunk_count}/{payload.total_chunks} parts.",
        )

    # Assemble the parts INSIDE Postgres so the app never holds the whole
    # file in RAM (this is what keeps 100 MB uploads alive on 512 MB
    # free-tier instances).
    dialect_name = db.get_bind().dialect.name
    if dialect_name == "postgresql":
        await db.execute(
            text(
                """
                UPDATE documents SET
                    file_data = agg.data,
                    file_size = octet_length(agg.data),
                    status = 'pending',
                    total_pages = 0,
                    file_path = ''
                FROM (
                    SELECT document_id, string_agg(data, ''::bytea ORDER BY seq) AS data
                    FROM document_upload_chunks
                    WHERE document_id = :doc_id
                    GROUP BY document_id
                ) AS agg
                WHERE documents.id = agg.document_id AND documents.id = :doc_id
                """
            ),
            {"doc_id": document_id},
        )
    else:
        # SQLite (local dev/tests): small files, concat in Python.
        parts = (
            await db.execute(
                select(DocumentUploadChunk.data)
                .where(DocumentUploadChunk.document_id == document_id)
                .order_by(DocumentUploadChunk.seq)
            )
        ).scalars().all()
        doc.file_data = b"".join(parts)
        doc.file_size = len(doc.file_data)
        doc.status = "pending"
        doc.total_pages = 0

    await db.execute(
        delete(DocumentUploadChunk).where(DocumentUploadChunk.document_id == document_id)
    )
    await db.commit()
    await db.refresh(doc)

    # Decompress concatenated payload if client compressed it
    if payload.compressed and doc.file_data:
        try:
            decompressed = decompress_payload(doc.file_data, compressed=True)
            doc.file_data = decompressed
            doc.file_size = len(decompressed)
            await db.commit()
            await db.refresh(doc)
        except Exception:
            pass

    asyncio.create_task(process_pending_documents())
    return doc


@router.get("/{course_id}", response_model=List[DocumentResponse])
async def list_course_documents(
    course_id: int,
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Document).where(Document.course_id == course_id)
    res = await db.execute(stmt)
    return res.scalars().all()

@router.get("/search/{course_id}")
async def search_course_documents(
    course_id: int,
    query: str,
    document_type: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    chunks = await DocumentService.search_documents(db, course_id, query, document_type)
    return {"query": query, "results": chunks}


@router.get("/{course_id}/pages")
async def download_document_pages(
    course_id: int,
    document_type: str = Query("textbook", pattern="^(textbook|workbook)$"),
    page_spec: str = Query(..., min_length=1, max_length=200, description='Pages to extract, e.g. "10-20" or "10,12,15"'),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Build a study PDF containing exactly the requested pages of the uploaded
    textbook/workbook (page numbers match the printed page numbers)."""
    try:
        pdf_bytes, filename, pages_info = await StudyMaterialService.build_document_pages_pdf(
            db, course_id=course_id, document_type=document_type, page_spec=page_spec
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "X-Study-Pages": pages_info,
        },
    )
