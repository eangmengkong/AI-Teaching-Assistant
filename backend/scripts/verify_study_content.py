"""Offline verification of the source-grounded exercise/quiz/exam retrieval.
Runs against the real database and real uploaded documents. Sends nothing
to Telegram."""
import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.models.models import Course, LessonSchedule
from app.services.study_content_service import StudyContentService


async def main():
    ok = True
    # 1. page-spec parsing for scheduler formats
    cases = {
        "Pages 1-35": list(range(1, 36)),
        "Pages 1\u2013209 (Comprehensive)": list(range(1, 210)),
        "Page 3": [3],
    }
    for spec, expected in cases.items():
        got = StudyContentService._parse_pages(spec)
        if got != expected:
            ok = False
            print(f"FAIL parse {spec!r}: got {len(got)} pages")
    print("PASS page-spec parsing (scheduler formats)" if ok else "parse failures above")

    async with AsyncSessionLocal() as db:
        course = (await db.execute(select(Course).order_by(Course.id).limit(1))).scalars().first()
        lessons = (
            await db.execute(
                select(LessonSchedule)
                .where(LessonSchedule.course_id == course.id)
                .order_by(LessonSchedule.date.asc())
            )
        ).scalars().all()
        print(f"course={course.id} {course.name!r} — {len(lessons)} scheduled lessons")

        # 2. real exercise retrieval across sample lessons (first / middle / last)
        sample = [lessons[0], lessons[len(lessons) // 2], lessons[-1]]
        readable_found = False
        for lesson in sample:
            pack = await StudyContentService.get_lesson_exercises(db, lesson)
            print(f"\n— lesson={lesson.id} {lesson.unit} {lesson.lesson} TB={lesson.textbook_pages} WB={lesson.workbook_pages}")
            print(f"  blocks: {len(pack['blocks'])}")
            for b in pack["blocks"][:2]:
                snippet = " ".join(b["text"].split())[:100]
                if not StudyContentService._is_readable(b["text"]):
                    ok = False
                    print(f"  FAIL: garbage block slipped through: {snippet}")
                else:
                    readable_found = True
                    print(f"  {b['trace']} :: {snippet}")
            if not pack["found"]:
                msg = (pack.get("message") or "").splitlines()[0]
                print(f"  honest fallback: {msg}")

        if not readable_found:
            print("NOTE: no lesson pages have a text layer (scanned book) — OCR would be needed")

        # 2b. simulate the full /exercise flow for the scanned-book case
        # (token neutralized -> sendStudyPdf runs in simulation mode, sends nothing)
        import app.telegram.bot as bot_mod
        from app.core.config import settings as cfg
        real_token = cfg.TELEGRAM_BOT_TOKEN
        cfg.TELEGRAM_BOT_TOKEN = ""
        try:
            lesson = lessons[0]
            pack = await StudyContentService.get_lesson_exercises(db, lesson)
            assert not pack["found"], "expected honest not-found for scanned pages"
            sent = await bot_mod.TelegramBotHandler._deliver_page_fallback(
                db, lesson, "0", None
            )
            print(f"scanned-book fallback: {sent} actual-page PDF(s) prepared+sim-sent (expect 2)")
            if sent != 2:
                ok = False
        finally:
            cfg.TELEGRAM_BOT_TOKEN = real_token

        # 3. quiz/exam retrieval (honest result expected)
        q = await StudyContentService.get_actual_quiz(db, course.id)
        e = await StudyContentService.get_actual_exam(db, course.id)
        print(f"actual quiz in DB: {'YES' if q else 'none (bot will say so honestly)'}")
        print(f"actual exam in DB: {'YES' if e else 'none (bot will say so honestly)'}")

        # 4. not-found texts render
        t1 = StudyContentService.not_found_quiz_text(lesson)
        t2 = StudyContentService.not_found_exam_text(lesson)
        assert "couldn't find an actual quiz" in t1 and "quiz gen" in t1
        assert "couldn't find an actual exam" in t2 and "exam gen" in t2
        print("PASS not-found fallback texts")

    # 5. bot module imports cleanly
    import app.telegram.bot as bot_mod
    assert hasattr(bot_mod.TelegramBotHandler, "_handle_callback")
    print("PASS bot.py imports + callback handler present")

    print("ALL PASS" if ok else "FAILURES PRESENT")


if __name__ == "__main__":
    asyncio.run(main())
