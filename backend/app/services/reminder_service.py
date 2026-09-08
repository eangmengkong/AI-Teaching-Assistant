from datetime import datetime, timedelta
import asyncio
import httpx
from typing import Any, Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.models.models import LessonSchedule, TelegramMessage, Course, User
from app.core.config import settings

class ReminderService:
    @staticmethod
    async def schedule_upcoming_reminders(db: AsyncSession):
        """
        Scans planned lessons in the next 7 days and inserts 24h & 1h Telegram reminder jobs into DB.
        """
        now = datetime.utcnow()
        upcoming_window = now + timedelta(days=7)

        # Select planned lessons in the upcoming window
        stmt = (
            select(LessonSchedule, Course, User)
            .join(Course, LessonSchedule.course_id == Course.id)
            .join(User, Course.user_id == User.id)
            .where(LessonSchedule.status == "planned")
            .where(User.telegram_chat_id.isnot(None))
        )
        result = await db.execute(stmt)
        rows = result.all()

        for schedule, course, user in rows:
            lesson_dt = datetime.strptime(f"{schedule.date} {schedule.start_time}", "%Y-%m-%d %H:%M")
            
            # 24 hour reminder time
            rem_24h = lesson_dt - timedelta(hours=24)
            # 1 hour reminder time
            rem_1h = lesson_dt - timedelta(hours=1)

            # Check if 24h reminder already exists
            stmt_24h = select(TelegramMessage).where(
                TelegramMessage.lesson_schedule_id == schedule.id,
                TelegramMessage.message_type == "reminder_24h"
            )
            res_24h = await db.execute(stmt_24h)
            if not res_24h.scalar_one_or_none():
                msg_content = (
                    f"🔔 TOMORROW'S LESSON\n\n"
                    f"📚 {course.name}\n"
                    f"📖 {schedule.unit} – {schedule.lesson}\n\n"
                    f"📅 {schedule.date.strftime('%B %d')}\n"
                    f"⏰ {schedule.start_time}–{schedule.end_time}\n\n"
                    f"📖 Textbook:\n{schedule.textbook_pages or 'N/A'}\n\n"
                    f"✏️ Workbook:\n{schedule.workbook_pages or 'N/A'}\n\n"
                    f"🎯 Objectives:\n{schedule.objectives or 'N/A'}\n\n"
                    f"📝 Prepare:\nRead assigned pages and prepare classroom activities."
                )
                db.add(TelegramMessage(
                    lesson_schedule_id=schedule.id,
                    course_id=course.id,
                    telegram_chat_id=user.telegram_chat_id,
                    message_type="reminder_24h",
                    content=msg_content,
                    scheduled_at=rem_24h,
                    status="pending"
                ))

            # Check if 1h reminder already exists
            stmt_1h = select(TelegramMessage).where(
                TelegramMessage.lesson_schedule_id == schedule.id,
                TelegramMessage.message_type == "reminder_1h"
            )
            res_1h = await db.execute(stmt_1h)
            if not res_1h.scalar_one_or_none():
                msg_content = (
                    f"⏰ LESSON REMINDER\n\n"
                    f"Your {course.name} lesson starts in 1 hour.\n\n"
                    f"📚 {schedule.unit} – {schedule.lesson}\n"
                    f"⏰ {schedule.start_time}–{schedule.end_time}\n\n"
                    f"📖 Textbook: {schedule.textbook_pages or 'N/A'}\n"
                    f"✏️ Workbook: {schedule.workbook_pages or 'N/A'}"
                )
                db.add(TelegramMessage(
                    lesson_schedule_id=schedule.id,
                    course_id=course.id,
                    telegram_chat_id=user.telegram_chat_id,
                    message_type="reminder_1h",
                    content=msg_content,
                    scheduled_at=rem_1h,
                    status="pending"
                ))

        await db.commit()

    @staticmethod
    async def process_due_reminders(db: AsyncSession):
        """
        Server-side scheduler task: checks pending telegram messages due for delivery, sends them, and handles retries.
        """
        now = datetime.utcnow()
        stmt = (
            select(TelegramMessage)
            .where(TelegramMessage.status.in_(["pending", "failed"]))
            .where(TelegramMessage.retry_count < 3)
            .where(TelegramMessage.scheduled_at <= now)
        )
        result = await db.execute(stmt)
        messages = result.scalars().all()

        for msg in messages:
            success = await ReminderService.send_telegram_message(msg.telegram_chat_id, msg.content)
            if success:
                msg.status = "sent"
                msg.sent_at = datetime.utcnow()
                msg.error = None
            else:
                msg.retry_count += 1
                msg.status = "failed"
                msg.error = "Telegram API delivery error or token missing"

        await db.commit()

    @staticmethod
    async def send_telegram_message(chat_id: str, text: str, reply_markup: Optional[dict] = None) -> bool:
        if not settings.TELEGRAM_BOT_TOKEN:
            print(f"[Offline Server Reminder Dispatcher - Simulation Mode] Chat: {chat_id} | Message:\n{text}")
            return True

        url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
        payload: Dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(url, json=payload)
                if res.status_code == 200:
                    return True
                else:
                    # Retry without parse_mode in case markdown formatting caused a parse error
                    payload.pop("parse_mode", None)
                    res_retry = await client.post(url, json=payload)
                    if res_retry.status_code == 200:
                        return True
                    print(f"Telegram API response error: {res_retry.status_code} - {res_retry.text}")
                    return False
        except Exception as e:
            print(f"Telegram API exception: {str(e)}")
            return False
