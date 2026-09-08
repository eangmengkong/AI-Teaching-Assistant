"""Live audit of EVERY Telegram bot command against the real database.
Telegram sends and DB persistence are patched out (nothing is sent, nothing
is saved). Prints a PASS/FAIL line per command."""
import asyncio
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.models import LessonSchedule, User
from app.services import reminder_service, study_material_service
from app.telegram.bot import TelegramBotHandler
from app.agent import central_agent as agent_mod

SENT = []          # captured (chat_id, text) replies
PDFS = []          # captured (chat_id, filename, size)


async def _fake_send(chat_id, text, reply_markup=None):
    SENT.append((str(chat_id), str(text)))
    return True


async def _fake_pdf(chat_id, filename, pdf_bytes, caption=""):
    PDFS.append((str(chat_id), filename, len(pdf_bytes or b"")))
    return True


async def _fake_agent(db, course_id, user_message):
    return f"[AI-AGENT-OFFLINE-MODE] received: {user_message}"


async def _fake_commit(self):
    return None  # keep everything in-transaction; rolled back on session close


async def main():
    # patch senders / AI / persistence
    reminder_service.ReminderService.send_telegram_message = staticmethod(_fake_send)
    study_material_service.StudyMaterialService.send_study_pdf = staticmethod(_fake_pdf)
    agent_mod.CentralAITeachingAgent.process_user_request = staticmethod(_fake_agent)
    AsyncSession.commit = _fake_commit

    ok = True
    async with AsyncSessionLocal() as db:
        user = (
            await db.execute(select(User).where(User.telegram_chat_id.isnot(None)).limit(1))
        ).scalars().first()
        assert user, "no user with telegram_chat_id"
        chat_id = user.telegram_chat_id
        lesson = (
            await db.execute(select(LessonSchedule).order_by(LessonSchedule.date.asc()).limit(1))
        ).scalars().first()
        lid = lesson.id if lesson else 0

    def marker_text():
        return " || ".join(t for _, t in SENT[-3:])[-160:].replace("\n", " ⏎ ")

    async def run(label, text=None, callback=None):
        global ok
        n_msgs, n_pdfs = len(SENT), len(PDFS)
        if callback is not None:
            result = await TelegramBotHandler._handle_callback(callback)
        else:
            result = await TelegramBotHandler.handle_update(
                {"message": {"chat": {"id": int(chat_id)}, "text": text}}
            )
        got_msgs = len(SENT) - n_msgs
        got_pdfs = len(PDFS) - n_pdfs
        bad = (
            result == "ERROR"
            or (got_msgs == 0 and got_pdfs == 0)
            or any("Traceback" in t or "Internal Server Error" in t for _, t in SENT[n_msgs:])
        )
        status = "PASS" if not bad else "FAIL"
        if bad:
            ok = False
        extra = f" +{got_pdfs} pdf" if got_pdfs else ""
        print(f"{status:4} | {label:28} | rc={result} msgs={got_msgs}{extra} | {marker_text() if got_msgs else ''}")

    print(f"chat_id={chat_id} lesson_id={lid}\n")

    await run("/start", "/start")
    await run("/help", "/help")
    await run("/today", "/today")
    await run("/tomorrow", "/tomorrow")
    await run("/week", "/week")
    await run("/lesson", "/lesson")
    await run("/pages", "/pages")
    await run("/exercise", "/exercise")
    await run("/exercise workbook", "/exercise workbook")
    await run("/homework", "/homework")
    await run("/quiz (actual)", "/quiz")
    await run("/quiz gen", "/quiz gen")
    await run("/review Unit 1", "/review Unit 1")
    await run("/exam (actual)", "/exam")
    await run("/exam gen", "/exam gen")
    await run("/progress", "/progress")
    await run("/complete", "/complete")
    await run("/score", "/score 1 AuditTest 10")
    await run("/setup", "/setup")
    await run("unknown -> AI agent", "/what is for dinner")
    # destructive last (persisted changes are rolled back by the patched commit)
    await run("/reschedule", "/reschedule 2099-01-01")
    await run("/skip", "/skip")

    print("\n-- inline keyboard callbacks --")
    await run("cb: exercises", callback={"id": "t1", "data": f"ex|{lid}||0", "message": {"chat": {"id": int(chat_id)}}})
    await run("cb: next page", callback={"id": "t2", "data": f"ex|{lid}||1", "message": {"chat": {"id": int(chat_id)}}})
    await run("cb: quiz", callback={"id": "t3", "data": f"qz|{lid}||0", "message": {"chat": {"id": int(chat_id)}}})
    await run("cb: exam", callback={"id": "t4", "data": f"exm|{lid}||0", "message": {"chat": {"id": int(chat_id)}}})
    await run("cb: back to lesson", callback={"id": "t5", "data": f"lesson|{lid}||0", "message": {"chat": {"id": int(chat_id)}}})

    print(f"\ntotal replies captured: {len(SENT)} | PDFs prepared: {len(PDFS)} ({[f[1] for f in PDFS]})")
    print("ALL COMMANDS PASS" if ok else "FAILURES PRESENT — see lines above")


if __name__ == "__main__":
    asyncio.run(main())
