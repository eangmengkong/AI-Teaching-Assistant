from fastapi import APIRouter, Request, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.v1.auth import get_current_user
from app.models.models import User
from app.services.study_material_service import StudyMaterialService
from app.telegram.bot import TelegramBotHandler

router = APIRouter()

@router.post("/webhook")
async def telegram_webhook(request: Request):
    update_data = await request.json()
    status = await TelegramBotHandler.handle_update(update_data)
    return {"status": status}


@router.post("/send-pages/{lesson_id}")
async def send_lesson_study_pages(
    lesson_id: int,
    include: str = Query("textbook,workbook", description="Comma-separated list: textbook,workbook"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Build the lesson's textbook/workbook page PDFs and send them to the
    current user's Telegram chat so they can read/study them on the phone."""
    if not current_user.telegram_chat_id:
        raise HTTPException(
            status_code=400,
            detail="No Telegram chat linked yet. Open Telegram and send /start to your bot once, then retry.",
        )
    try:
        return await StudyMaterialService.deliver_lesson_pdfs(
            db, lesson_id=lesson_id, chat_id=current_user.telegram_chat_id, include=include
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
