import os
import tempfile
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, Response
from typing import List, Optional
# pyrefly: ignore [missing-import]
from sqlalchemy.ext.asyncio import AsyncSession
# pyrefly: ignore [missing-import]
from sqlalchemy import select

from app.core.database import get_db
from app.core.config import settings
from app.api.v1.auth import get_current_user
from app.models.models import User, Course, Document
from app.schemas.schemas import DocumentResponse
from app.services.document_service import DocumentService
from app.services.study_material_service import StudyMaterialService
from app.services.upload_codec import StreamDecompressor, InvalidCompressedUpload

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
