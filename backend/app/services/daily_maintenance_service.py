"""
Daily automation jobs that run inside the always-on backend worker.

1. send_daily_digests   - every morning (per course timezone) the teacher gets a
                          Telegram digest of today's lessons. No PC required.
2. sync_google_calendar - continuously makes sure every planned lesson exists in
                          the teacher's Google Calendar (inserts new/placeholder
                          events, pushes updates for modified lessons).

Both are idempotent: the worker calls run_daily() every 30 seconds, so any
crash/restart simply continues where it left off without duplicating messages
or events.
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.models import CalendarEvent, Course, LessonSchedule, TelegramMessage, User
from app.services.calendar_service import CalendarService

try:
    from zoneinfo import ZoneInfo
except ImportError:  # Python < 3.9
    ZoneInfo = None


def _get_tz(name: Optional[str]):
    """Resolve a course's IANA timezone, falling back to UTC on any error."""
    if ZoneInfo and name:
        try:
            return ZoneInfo(name)
        except Exception:
            pass
    return timezone.utc


class DailyMaintenanceService:
    @staticmethod
    async def run_daily(db: AsyncSession):
        """Entry point called by the worker every cycle. Each job is wrapped
        separately so one failing integration never blocks the other."""
        if settings.DAILY_DIGEST_ENABLED:
            try:
                await DailyMaintenanceService.send_daily_digests(db)
            except Exception as e:
                print(f"[Daily Digest Error] {e}")

        if settings.GOOGLE_CALENDAR_SYNC_ENABLED:
            try:
                await DailyMaintenanceService.sync_google_calendar(db)
            except Exception as e:
                print(f"[Calendar Auto-Sync Error] {e}")

    # ------------------------------------------------------------------
    # 1. Morning Telegram digest ("today's lessons")
    # ------------------------------------------------------------------
    @staticmethod
    async def send_daily_digests(db: AsyncSession):
        """Queue one "today's lessons" Telegram message per user+timezone once
        the local clock passes DAILY_DIGEST_HOUR (default 07:00). The message
        is delivered by the existing process_due_reminders() dispatcher, so it
        inherits retries and delivery tracking for free."""
        stmt = (
            select(User, Course)
            .join(Course, Course.user_id == User.id)
            .where(User.telegram_chat_id.isnot(None))
            .where(Course.status == "active")
        )
        rows = (await db.execute(stmt)).all()
        if not rows:
            return

        # Group courses by (chat_id, timezone) so a user with several courses
        # in the same timezone gets ONE combined digest.
        groups: Dict[Tuple[str, str], dict] = {}
        for user, course in rows:
            key = (user.telegram_chat_id, course.teacher_timezone or "UTC")
            group = groups.setdefault(key, {"user": user, "courses": []})
            group["courses"].append(course)

        for (chat_id, tz_name), group in groups.items():
            tz = _get_tz(tz_name)
            local_now = datetime.now(tz)

            # Wait until the configured local morning hour
            if local_now.hour < settings.DAILY_DIGEST_HOUR:
                continue

            target_date = local_now.date()
            message_type = f"daily_digest_{target_date.isoformat()}"

            # Idempotency: at most one digest per chat per local day. Checked
            # in the DB so it survives worker restarts and redeploys.
            existing = (
                await db.execute(
                    select(TelegramMessage).where(
                        TelegramMessage.telegram_chat_id == chat_id,
                        TelegramMessage.message_type == message_type,
                        TelegramMessage.status.in_(["pending", "sent", "failed"]),
                    )
                )
            ).scalar_one_or_none()
            if existing:
                continue

            courses = group["courses"]
            lessons = (
                await db.execute(
                    select(LessonSchedule)
                    .where(LessonSchedule.course_id.in_([c.id for c in courses]))
                    .where(LessonSchedule.date == target_date)
                    .where(LessonSchedule.status == "planned")
                    .order_by(LessonSchedule.start_time)
                )
            ).scalars().all()

            content = DailyMaintenanceService._build_digest_content(
                group["user"], courses, lessons, target_date
            )

            db.add(
                TelegramMessage(
                    lesson_schedule_id=None,
                    course_id=courses[0].id,
                    telegram_chat_id=chat_id,
                    message_type=message_type,
                    content=content,
                    scheduled_at=datetime.utcnow(),
                    status="pending",
                    retry_count=0,
                )
            )
            await db.commit()
            print(f"[Daily Digest] Queued {message_type} for chat {chat_id} ({tz_name})")

    @staticmethod
    def _build_digest_content(
        user: User, courses: List[Course], lessons: List[LessonSchedule], target_date
    ) -> str:
        greeting = user.full_name or "Teacher"
        header = (
            f"🌅 GOOD MORNING, {greeting}!\n\n"
            f"📅 {target_date.strftime('%A, %B %d')}"
        )
        if not lessons:
            return f"{header}\n\n🎉 No lessons scheduled today — enjoy your free day!"

        lines = [header, ""]
        for lesson in lessons:
            course_name = next((c.name for c in courses if c.id == lesson.course_id), "Lesson")
            lines.append(
                f"📚 {course_name}\n"
                f"⏰ {lesson.start_time}–{lesson.end_time}  |  {lesson.unit} – {lesson.lesson}\n"
                f"📖 Textbook: {lesson.textbook_pages or '—'}  |  ✏️ Workbook: {lesson.workbook_pages or '—'}"
            )
            if lesson.homework:
                hw = lesson.homework if len(lesson.homework) <= 160 else lesson.homework[:157] + "..."
                lines.append(f"🏠 Homework: {hw}")
            lines.append("")
        lines.append("Good luck with your classes! 🍎")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # 2. Automatic Google Calendar sync
    # ------------------------------------------------------------------
    @staticmethod
    async def sync_google_calendar(db: AsyncSession):
        """Push every planned lesson (yesterday -> +60 days) to Google Calendar.

        - Lessons with no event id (or a LOCAL 'evt_...' placeholder created
          before Google was connected) are INSERTED.
        - Lessons modified since their last sync are UPDATED.
        Already-synced, unchanged lessons cost zero Google API calls, so this
        is safe to run on every worker cycle.
        """
        if not settings.GOOGLE_CLIENT_ID:
            return

        stmt = (
            select(LessonSchedule, Course, User, CalendarEvent)
            .join(Course, LessonSchedule.course_id == Course.id)
            .join(User, Course.user_id == User.id)
            .outerjoin(CalendarEvent, CalendarEvent.lesson_schedule_id == LessonSchedule.id)
            .where(Course.status == "active")
            .where(LessonSchedule.status.in_(["planned", "rescheduled"]))
            .where(User.google_refresh_token.isnot(None))
        )
        rows = (await db.execute(stmt)).all()
        if not rows:
            return

        touched: Dict[int, dict] = {}
        for schedule, course, user, cal_event in rows:
            bundle = touched.setdefault(course.id, {"course": course, "user": user, "rows": []})
            bundle["rows"].append((schedule, cal_event))

        inserted = updated = 0
        for bundle in touched.values():
            course, user = bundle["course"], bundle["user"]
            tz = _get_tz(course.teacher_timezone)
            today = datetime.now(tz).date()
            window_start = today - timedelta(days=1)
            window_end = today + timedelta(days=60)
            try:
                for schedule, cal_event in bundle["rows"]:
                    if not (window_start <= schedule.date <= window_end):
                        continue
                    event_id = str(schedule.calendar_event_id or "")
                    if not event_id or event_id.startswith("evt_"):
                        # Never pushed to Google yet (missing or local placeholder)
                        await CalendarService.create_calendar_event(db, course, user, schedule)
                        inserted += 1
                    elif (
                        cal_event
                        and cal_event.last_synced_at
                        and schedule.updated_at
                        # 2-minute grace window prevents an update loop when
                        # updated_at and last_synced_at land in the same flush
                        and schedule.updated_at > cal_event.last_synced_at + timedelta(minutes=2)
                    ):
                        # Lesson changed since the last push -> update the event
                        await CalendarService.update_calendar_event(db, course, user, schedule)
                        updated += 1
            except Exception as e:
                # One bad Google token / quota error must not stop other courses
                print(f"[Calendar Auto-Sync] Course '{course.name}' failed: {e}")

        if inserted or updated:
            print(f"[Calendar Auto-Sync] {inserted} event(s) created, {updated} updated")