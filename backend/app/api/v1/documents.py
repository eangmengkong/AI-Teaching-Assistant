import os
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

router = APIRouter()

ALLOWED_DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt"}
MAX_UPLOAD_SIZE = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024


@router.post("/upload", response_model=DocumentResponse)
async def upload_document(
    course_id: int = Form(...),
    document_type: str = Form(...), # "textbook" or "workbook"
    file: UploadFile = File(...),
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

    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    file_location = os.path.join(settings.UPLOAD_DIR, f"c{course_id}_{document_type}_{filename}")

    file_bytes = b""
    written = 0
    try:
        with open(file_location, "wb") as buffer:
            while chunk := await file.read(1024 * 1024):
                written += len(chunk)
                file_bytes += chunk
                if written > MAX_UPLOAD_SIZE:
                    raise HTTPException(
                        status_code=413,
                        detail="File exceeds the 500 MB upload limit.",
                    )
                buffer.write(chunk)
    except HTTPException:
        if os.path.exists(file_location):
            os.remove(file_location)
        raise

    try:
        doc = await DocumentService.process_document(
            db=db,
            course_id=course_id,
            document_type=document_type.lower(),
            filename=filename,
            file_path=file_location,
            file_data=file_bytes
        )
        if os.path.exists(file_location):
            os.remove(file_location)
        return doc
    except Exception as e:
        if os.path.exists(file_location):
            os.remove(file_location)
        raise HTTPException(status_code=500, detail=f"Failed to process document: {str(e)}")

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
