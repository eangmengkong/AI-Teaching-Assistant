import asyncio
import json
import httpx
from typing import Any, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import AsyncSessionLocal
from app.agent.central_agent import CentralAITeachingAgent
from app.agent.tools import CentralAgentTools
from app.models.models import Course, User, LessonSchedule, Document, Quiz
from app.core.config import settings
from app.services.study_material_service import StudyMaterialService
from app.services.study_content_service import StudyContentService
from app.services.reminder_service import ReminderService
from sqlalchemy import select
from datetime import datetime

class TelegramBotHandler:
    # Command menu registered with Telegram so the client's Menu button
    # lists every supported command (also enables command autocomplete).
    BOT_COMMANDS = [
        {"command": "start", "description": "Register & show all commands"},
        {"command": "help", "description": "Show all available commands"},
        {"command": "today", "description": "View today's lesson plan"},
        {"command": "tomorrow", "description": "View tomorrow's lesson plan"},
        {"command": "week", "description": "View current week schedule & progress"},
        {"command": "lesson", "description": "Full lesson plan for today"},
        {"command": "pages", "description": "Send today's textbook & workbook pages as PDF"},
        {"command": "exercise", "description": "Show ACTUAL exercises for today's lesson (from your books)"},
        {"command": "homework", "description": "Today's homework assignments"},
        {"command": "quiz", "description": "Show ACTUAL quiz from your materials ('gen' = AI practice)"},
        {"command": "review", "description": "Generate review session, e.g. /review 1"},
        {"command": "exam", "description": "Show ACTUAL exam from your materials ('gen' = AI practice)"},
        {"command": "progress", "description": "Course, textbook & workbook progress"},
        {"command": "complete", "description": "Record lesson completion"},
        {"command": "skip", "description": "Skip lesson & recalculate schedule"},
        {"command": "reschedule", "description": "Reschedule lesson, e.g. /reschedule 2026-09-20"},
        {"command": "score", "description": "Record quiz score: /score <quiz_id> <name> <score> (or /score <name> <score> for latest)"},
        {"command": "examscore", "description": "Record exam score: /examscore <exam_id> <name> <score>"},
        {"command": "setup", "description": "Configure course & materials"},
    ]

    @staticmethod
    async def _send_chat_action(chat_id: str, action: str = "typing") -> None:
        """Send a Telegram chat action (typing / upload_document) so the user
        sees a 'typing…' or 'sending file…' indicator while we work. Best-effort:
        failures are silently ignored."""
        if not settings.TELEGRAM_BOT_TOKEN:
            return
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(
                    f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendChatAction",
                    json={"chat_id": int(chat_id), "action": action},
                )
        except Exception:
            pass

    @staticmethod
    async def _send_loading(chat_id: str, text: str) -> None:
        """Send a short status message (e.g. '⏳ Building your study pages…')
        so the user knows something is happening. Best-effort."""
        if not settings.TELEGRAM_BOT_TOKEN:
            return
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(
                    f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage",
                    json={"chat_id": int(chat_id), "text": text},
                )
        except Exception:
            pass

    @staticmethod
    async def register_commands() -> bool:
        """Push the command menu to Telegram (setMyCommands). Best-effort:
        failures never block the bot."""
        token = settings.TELEGRAM_BOT_TOKEN
        if not token:
            return False
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"https://api.telegram.org/bot{token}/setMyCommands",
                    json={"commands": TelegramBotHandler.BOT_COMMANDS},
                )
                ok = resp.status_code == 200 and resp.json().get("ok", False)
                print(f"[Telegram Bot] setMyCommands -> {'OK' if ok else resp.text[:200]}")
                return ok
        except Exception as e:
            print(f"[Telegram Bot] setMyCommands failed (non-fatal): {e}")
            return False

    @staticmethod
    async def poll_updates():
        token = settings.TELEGRAM_BOT_TOKEN
        if not token:
            return
        offset = 0
        print(f"[Telegram Bot Polling Started for token {token[:10]}...]")
        await TelegramBotHandler.register_commands()
        while True:
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    url = f"https://api.telegram.org/bot{token}/getUpdates?offset={offset}&timeout=5"
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        data = resp.json()
                        for update in data.get("result", []):
                            offset = update["update_id"] + 1
                            try:
                                await TelegramBotHandler.handle_update(update)
                            except Exception as e:
                                # A single bad update must NEVER kill the loop
                                print(f"[Telegram Update Error] {type(e).__name__}: {e}")
            except Exception as e:
                print(f"[Telegram Poll Exception] {e}")
            await asyncio.sleep(2)

    @staticmethod
    async def handle_update(update_data: Dict[str, Any]) -> str:
        """Top-level guard: a crashing command must NEVER escape silently —
        the user always gets a reply."""
        try:
            return await TelegramBotHandler._handle_update_impl(update_data)
        except Exception as e:
            print(f"[Telegram Handle Error] {type(e).__name__}: {e}")
            msg = update_data.get("message") or {}
            chat = str(msg.get("chat", {}).get("id", "") or "")
            if chat:
                try:
                    await ReminderService.send_telegram_message(
                        chat,
                        "⚠️ Something went wrong while processing that command. Please try again in a moment.",
                    )
                except Exception:
                    pass
            return "ERROR"

    @staticmethod
    async def _handle_update_impl(update_data: Dict[str, Any]) -> str:
        """Handle one Telegram update. ONE DB session wraps the whole flow
        (lookup + command logic + reply) so the session is never used after
        it has closed (that bug made every command silently fail)."""
        try:
            callback = update_data.get("callback_query")
            if callback:
                return await TelegramBotHandler._handle_callback(callback)

            message = update_data.get("message", {})
            chat_id = str(message.get("chat", {}).get("id", ""))
            text = message.get("text", "").strip()

            if not chat_id or not text:
                return "OK"

            print(f"[Telegram Incoming] Chat {chat_id}: {text}")

            async with AsyncSessionLocal() as db:
                # Find user by telegram_chat_id or attach the default user.
                # telegram_chat_id is unique, but guard against any legacy
                # duplicates: take the first match and null out the extras.
                stmt = select(User).where(User.telegram_chat_id == chat_id).order_by(User.id)
                res = await db.execute(stmt)
                users = res.scalars().all()
                user = users[0] if users else None
                if len(users) > 1:
                    for extra in users[1:]:
                        extra.telegram_chat_id = None
                    await db.commit()

                if not user:
                    # Auto-register default user with this telegram_chat_id
                    stmt_first = select(User).limit(1)
                    res_first = await db.execute(stmt_first)
                    user = res_first.scalar_one_or_none()
                    if user:
                        user.telegram_chat_id = chat_id
                        await db.commit()

                course_id = 1
                if user:
                    c_stmt = select(Course).where(Course.user_id == user.id).order_by(Course.id)
                    c_res = await db.execute(c_stmt)
                    course = c_res.scalars().first()  # first owned course (user may own several)
                    if course:
                        course_id = course.id

                reply_text = ""
                reply_markup = None

                if text.startswith("/start") or text.startswith("/help"):
                    reply_text = (
                        "🤖 *AI TEACHING ASSISTANT BOT*\n\n"
                        "Available Commands:\n"
                        "• /today – View today's lesson plan\n"
                        "• /tomorrow – View tomorrow's lesson plan\n"
                        "• /week – View current week schedule & progress\n"
                        "• /lesson – Full lesson plan for today\n"
                        "• /pages – Send today's textbook & workbook pages as PDF\n"
                        "• /exercise [textbook|workbook] – Show the ACTUAL exercises for today's lesson (retrieved from your books)\n"
                        "• /homework – Today's homework assignments\n"
                        "• /quiz [gen] – Show the ACTUAL quiz from your materials (or 'gen' for AI practice)\n"
                        "• /review <unit> – Generate review session\n"
                        "• /exam [gen] – Show the ACTUAL exam from your materials (or 'gen' for AI practice)\n"
                        "• /progress – Course, textbook & workbook progress\n"
                        "• /complete – Record lesson completion\n"
                        "• /skip – Skip lesson & recalculate schedule\n"
                        "• /reschedule <date> – Reschedule lesson\n"
                        "• /score <quiz_id> <name> <score> – Record score\n"
                        "• /setup – Configure course & materials"
                    )

                elif text.startswith("/complete"):
                    # Interactive lesson completion prompt
                    today_res = await CentralAgentTools.get_today_lesson(db, course_id)
                    if today_res["status"] == "success":
                        lid = today_res["lesson"]["id"]
                        comp_res = await CentralAgentTools.record_lesson_completion(db, course_id, lid, completion_status="fully")
                        reply_text = f"✅ Lesson #{lid} marked as fully completed!\nProgress recorded."
                    else:
                        reply_text = "No active lesson found to mark completed today."

                elif text.startswith("/score"):
                    parts = text.split()
                    # Forms: /score <quiz_id> <name> <score>
                    #        /score <name> <score>            (uses the latest quiz)
                    qid = None
                    sname = None
                    score_val = None
                    if len(parts) >= 4 and parts[1].lstrip("-").isdigit():
                        qid = int(parts[1])
                        sname = parts[2]
                        try:
                            score_val = float(parts[3])
                        except ValueError:
                            score_val = None
                    elif len(parts) == 3:
                        sname = parts[1]
                        try:
                            score_val = float(parts[2])
                        except ValueError:
                            score_val = None
                    if score_val is None or not sname:
                        reply_text = "Usage: /score <quiz_id> <name> <score>  (example: /score 1 Mengkong 85)\nOr: /score <name> <score> to use your latest quiz."
                    else:
                        sres = await CentralAgentTools.record_quiz_score(db, qid, sname, score_val)
                        if sres.get("status") == "success":
                            reply_text = f"✅ Score recorded for {sname}: {sres['percentage']}"
                        elif qid is None or "not found" in str(sres.get("message", "")).lower():
                            # No explicit id (or id not found) → fall back to the latest quiz for this course.
                            latest = (
                                await db.execute(
                                    select(Quiz).where(Quiz.course_id == course_id).order_by(Quiz.id.desc()).limit(1)
                                )
                            ).scalar_one_or_none()
                            if not latest:
                                reply_text = "⚠️ No quiz exists yet. Generate one first with /quiz gen."
                            elif qid is not None and latest.id != qid:
                                sres2 = await CentralAgentTools.record_quiz_score(db, latest.id, sname, score_val)
                                if sres2.get("status") == "success":
                                    reply_text = f"⚠️ Quiz {qid} not found. Used your latest quiz #{latest.id} instead.\n✅ Score recorded for {sname}: {sres2['percentage']}"
                                else:
                                    reply_text = f"⚠️ {sres2.get('message', 'Could not record the score.')}"
                            else:
                                reply_text = f"⚠️ {sres.get('message', 'Could not record the score.')}"
                        else:
                            reply_text = f"⚠️ {sres.get('message', 'Could not record the score.')}"

                elif text.startswith("/examscore"):
                    parts = text.split()
                    if len(parts) >= 4 and parts[1].lstrip("-").isdigit():
                        try:
                            eid = int(parts[1])
                            sname = parts[2]
                            score_val = float(parts[3])
                            sres = await CentralAgentTools.record_exam_score(db, eid, sname, score_val)
                            if sres.get("status") == "success":
                                reply_text = f"✅ Exam score recorded for {sname}: {sres['percentage']}"
                            else:
                                reply_text = f"⚠️ {sres.get('message', 'Could not record the score.')}"
                        except ValueError:
                            reply_text = "Usage: /examscore <exam_id> <name> <score>  (example: /examscore 1 Mengkong 90)"
                    else:
                        reply_text = "Usage: /examscore <exam_id> <name> <score>  (example: /examscore 1 Mengkong 90)"

                elif text.startswith("/pages"):
                    # Send today's lesson study pages (textbook/workbook PDFs)
                    today_res = await CentralAgentTools.get_today_lesson(db, course_id)
                    if today_res.get("status") != "success":
                        reply_text = "No active lesson found to send pages for."
                    else:
                        lesson = today_res["lesson"]
                        await TelegramBotHandler._send_chat_action(chat_id, "upload_document")
                        await TelegramBotHandler._send_loading(
                            chat_id,
                            f"⏳ Building study pages for {lesson.get('unit', '')} – {lesson.get('lesson', '')}…",
                        )
                        pack = await StudyMaterialService.prepare_lesson_pdfs(db, lesson["id"])
                        if not pack["prepared"]:
                            reasons = "; ".join(s["reason"] for s in pack["skipped"]) or "no study pages configured"
                            reply_text = f"Could not build study pages: {reasons}"
                        else:
                            await CentralAgentTools.send_telegram_message(
                                chat_id,
                                f"📚 Study material for {lesson.get('unit', '')} – {lesson.get('lesson', '')}:",
                            )
                            sent_any = False
                            total = len(pack["prepared"])
                            for idx, item in enumerate(pack["prepared"], start=1):
                                await TelegramBotHandler._send_loading(
                                    chat_id,
                                    f"📤 Sending {item['caption'].split(' — ')[-1].split(' (')[0]} pages ({idx}/{total})…",
                                )
                                ok = await StudyMaterialService.send_study_pdf(
                                    chat_id, item["filename"], item["pdf"], item["caption"]
                                )
                                sent_any = sent_any or ok
                                if ok:
                                    await TelegramBotHandler._send_loading(
                                        chat_id, f"✅ File {idx}/{total} sent",
                                    )
                            reply_text = (
                                f"✅ Study PDFs sent above 👆 ({total} file{'s' if total != 1 else ''})"
                                if sent_any
                                else "⚠️ PDF delivery failed — check the bot token on the server."
                            )

                elif text.startswith("/reschedule"):
                    parts = text.split(maxsplit=1)
                    if len(parts) > 1:
                        try:
                            new_date = datetime.strptime(parts[1].strip(), "%Y-%m-%d").date()
                        except ValueError:
                            new_date = None
                        if not new_date:
                            reply_text = "Usage: /reschedule <YYYY-MM-DD>  (example: /reschedule 2026-09-30)"
                        else:
                            today_res = await CentralAgentTools.get_today_lesson(db, course_id)
                            if today_res["status"] == "success":
                                lid = today_res["lesson"]["id"]
                                resch_res = await CentralAgentTools.reschedule_lesson(db, course_id, lid, new_date)
                                if resch_res.get("status") == "success":
                                    reply_text = f"📅 {resch_res.get('message', 'Lesson rescheduled.')}"
                                else:
                                    reply_text = f"⚠️ {resch_res.get('message', 'Could not reschedule.')}"
                            else:
                                reply_text = "No lesson found to reschedule."
                    else:
                        reply_text = "Usage: /reschedule <YYYY-MM-DD>  (example: /reschedule 2026-09-30)"

                elif (
                    text.startswith("/exercise")
                    or text.startswith("/quiz")
                    or text.startswith("/exam")
                ):
                    # Source-grounded retrieval: show the ACTUAL exercises /
                    # quiz / exam from the connected materials. The AI agent is
                    # only used when the user explicitly asks for generated
                    # practice ('gen') - never as silent replacement.
                    cmd, _, arg = text.partition(" ")
                    arg = (arg or "").strip().lower()
                    today_res = await CentralAgentTools.get_today_lesson(db, course_id)
                    if today_res.get("status") != "success":
                        reply_text = "No lesson found in your schedule. Generate one in the dashboard first."
                    else:
                        lesson_orm = (
                            await db.execute(
                                select(LessonSchedule).where(
                                    LessonSchedule.id == today_res["lesson"]["id"]
                                )
                            )
                        ).scalar_one_or_none()
                        if not lesson_orm:
                            reply_text = "Lesson not found in the database."
                        elif cmd == "/exercise":
                            await TelegramBotHandler._send_chat_action(chat_id, "typing")
                            await TelegramBotHandler._send_loading(
                                chat_id,
                                f"🔍 Searching for actual exercises in {lesson_orm.unit} · {lesson_orm.lesson}…",
                            )
                            src = arg if arg in ("textbook", "workbook", "tb", "wb") else None
                            pack = await StudyContentService.get_lesson_exercises(db, lesson_orm, source=src)
                            if not pack["found"]:
                                reply_text = pack.get("message") or "No exercises found."
                                sent = await TelegramBotHandler._deliver_page_fallback(
                                    db, lesson_orm, chat_id, src
                                )
                                if sent:
                                    reply_text += (
                                        "\n\n📄 Your book pages are scanned images (no extractable text), "
                                        f"so I sent the actual lesson pages as {sent} PDF(s) instead."
                                    )
                            else:
                                ex_text, total_pages = StudyContentService.format_exercise_telegram(pack, 0)
                                reply_markup = StudyContentService.nav_keyboard(
                                    "ex", lesson_orm.id, src or "", 0, total_pages
                                )
                                chunks = StudyContentService.split_messages(ex_text)
                                for c in chunks[:-1]:
                                    await ReminderService.send_telegram_message(chat_id, c)
                                reply_text = chunks[-1]
                        elif cmd == "/quiz":
                            if arg == "gen":
                                await TelegramBotHandler._send_chat_action(chat_id, "typing")
                                await TelegramBotHandler._send_loading(
                                    chat_id,
                                    f"🤖 Generating a practice quiz for {lesson_orm.unit} · {lesson_orm.lesson}…",
                                )
                                res = await CentralAgentTools.generate_quiz(
                                    db, course_id,
                                    title=f"Practice Quiz - {lesson_orm.unit} {lesson_orm.lesson}",
                                )
                                await StudyContentService.mark_quiz_practice(db, res["quiz_id"])
                                reply_text = (
                                    "🤖 AI-GENERATED practice quiz (no actual quiz found in your "
                                    "materials):\n\n" + StudyContentService.format_generated_quiz_dict(res)
                                    + f"\n\n🆔 Quiz ID: {res['quiz_id']} — record a score with "
                                    + f"/score {res['quiz_id']} <name> <score>"
                                )
                            else:
                                actual = await StudyContentService.get_actual_quiz(db, course_id)
                                if actual:
                                    reply_text = StudyContentService.format_quiz_telegram(actual)
                                else:
                                    reply_text = StudyContentService.not_found_quiz_text(lesson_orm)
                        else:  # /exam
                            if arg == "gen":
                                await TelegramBotHandler._send_chat_action(chat_id, "typing")
                                await TelegramBotHandler._send_loading(
                                    chat_id,
                                    "🤖 Generating a practice exam from your completed lessons…",
                                )
                                res = await CentralAgentTools.generate_final_exam(db, course_id)
                                await StudyContentService.mark_exam_practice(db, res["exam_id"])
                                body = await StudyContentService.format_exam_by_id(db, res["exam_id"])
                                reply_text = (
                                    "🤖 AI-GENERATED practice exam (no actual exam found in your "
                                    "materials):\n\n" + body
                                    + f"\n\n🆔 Exam ID: {res['exam_id']} — record a score with "
                                    + f"/examscore {res['exam_id']} <name> <score>"
                                )
                            else:
                                actual = await StudyContentService.get_actual_exam(db, course_id)
                                if actual:
                                    reply_text = StudyContentService.format_exam_telegram(actual)
                                else:
                                    reply_text = StudyContentService.not_found_exam_text(lesson_orm)

                elif text.startswith("/lesson"):
                    # Full lesson plan for today, formatted straight from the DB
                    # (previously fell through to raw agent tool output).
                    today_res = await CentralAgentTools.get_today_lesson(db, course_id)
                    if today_res.get("status") != "success":
                        reply_text = "No lesson scheduled for today. 📅 Try /tomorrow or /week."
                    else:
                        l = today_res["lesson"]

                        def _fmt(v):
                            if isinstance(v, list):
                                return "\n".join(f"  • {x}" for x in v) if v else "  —"
                            return f"  {v}" if v else "  —"

                        reply_text = "\n".join([
                            f"📚 FULL LESSON PLAN — {l.get('unit', '')} · {l.get('lesson', '')}",
                            f"📅 {l.get('date', '')}  ⏰ {l.get('start_time', '')}-{l.get('end_time', '')}",
                            f"📖 Textbook: {l.get('textbook_pages') or '—'}   ✏️ Workbook: {l.get('workbook_pages') or '—'}",
                            f"Status: {l.get('status', 'planned')}",
                            "",
                            "🎯 Objectives:",
                            _fmt(l.get("objectives")),
                            "",
                            "📋 Activities:",
                            _fmt(l.get("activities")),
                            "",
                            "✏️ Exercises:",
                            _fmt(l.get("exercises")),
                            "",
                            f"🏠 Homework: {l.get('homework') or '—'}",
                            f"📝 Assessment: {l.get('assessment') or '—'}",
                            "",
                            "Deep dive: /exercise · study pages: /pages · /quiz · /exam",
                        ])

                elif text.startswith("/review"):
                    # /review <unit> -> source-grounded review of that unit's
                    # ACTUAL material; bare /review shows usage + available units
                    # (previously mis-routed to the progress tool).
                    unit_arg = text[len("/review"):].strip()
                    if not unit_arg:
                        units = (
                            await db.execute(
                                select(LessonSchedule.unit)
                                .where(LessonSchedule.course_id == course_id)
                                .distinct()
                                .order_by(LessonSchedule.unit)
                            )
                        ).scalars().all()
                        unit_list = ", ".join(units) if units else "none yet (generate a schedule first)"
                        reply_text = (
                            "Usage: /review <unit> — builds a grounded review of that "
                            "unit's actual material.\n"
                            f"Units in your schedule: {unit_list}\n"
                            "Example: /review Unit 1"
                        )
                    else:
                        await TelegramBotHandler._send_chat_action(chat_id, "typing")
                        await TelegramBotHandler._send_loading(
                            chat_id,
                            f"📖 Building a grounded review of {unit_arg}…",
                        )
                        review_text, meta = await StudyContentService.generate_grounded_review(
                            db, course_id, unit_arg
                        )
                        if review_text:
                            reply_text = review_text
                        else:
                            reply_text = f"⚠️ Couldn't build a review for '{unit_arg}': {meta}"
                            # Scanned book? Fall back to the unit's ACTUAL pages as PDFs.
                            unit_lesson = (
                                await db.execute(
                                    select(LessonSchedule)
                                    .where(LessonSchedule.course_id == course_id)
                                    .where(LessonSchedule.unit.ilike(f"%{unit_arg}%"))
                                    .order_by(LessonSchedule.date.asc())
                                )
                            ).scalars().first()
                            if unit_lesson:
                                sent = await TelegramBotHandler._deliver_page_fallback(
                                    db, unit_lesson, chat_id, None
                                )
                                if sent:
                                    reply_text += (
                                        f"\n\n📄 Instead, I sent the unit's actual pages "
                                        f"as {sent} PDF(s) above 👆"
                                    )

                elif text.startswith("/setup"):
                    # Setup status instead of raw agent tool output.
                    course = (
                        (await db.execute(select(Course).where(Course.id == course_id)))
                        .scalars().first()
                    )
                    docs = (
                        (await db.execute(select(Document).where(Document.course_id == course_id)))
                        .scalars().all()
                    )
                    schedules = (
                        (
                            await db.execute(
                                select(LessonSchedule).where(LessonSchedule.course_id == course_id)
                            )
                        )
                        .scalars().all()
                    )
                    tb = [d for d in docs if d.document_type == "textbook"]
                    wb = [d for d in docs if d.document_type == "workbook"]
                    reply_text = "\n".join([
                        "⚙️ SETUP STATUS",
                        f"📚 Course: {course.name if course else '—'}"
                        + (f"  ({course.start_date} → {course.end_date})" if course else ""),
                        f"📖 Textbook: {tb[0].filename if tb else 'not uploaded'}",
                        f"✏️ Workbook: {wb[0].filename if wb else 'not uploaded'}",
                        f"📅 Scheduled lessons: {len(schedules)}",
                        f"📱 Telegram: linked to chat {chat_id}",
                        "",
                        "Add/replace materials and (re)generate the schedule in the web dashboard.",
                        "Then use /today · /lesson · /exercise · /pages · /quiz · /exam here.",
                    ])

                else:
                    # Delegate query to Central AI Teaching Agent
                    await TelegramBotHandler._send_chat_action(chat_id, "typing")
                    reply_text = await CentralAITeachingAgent.process_user_request(db, course_id, text)

                # Send response back to Telegram (inside the same open session,
                # then the context manager closes it cleanly)
                await ReminderService.send_telegram_message(chat_id, reply_text, reply_markup)

            return "OK"
        except Exception as e:
            print(f"[Telegram Handle Error] {e}")
            return "ERROR"

    @staticmethod
    async def _handle_callback(cb: Dict[str, Any]) -> str:
        """Handle inline-keyboard presses: exercise paging (⬅️/➡️),
        🏠 Back to Lesson, 📚 Back to Exercises, quiz/exam cross-links.
        Opens its own DB session (never reuses a closed one)."""
        data = cb.get("data") or ""
        chat_id = str((cb.get("message") or {}).get("chat", {}).get("id", ""))
        try:
            async with httpx.AsyncClient(timeout=5.0) as hc:
                await hc.post(
                    f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/answerCallbackQuery",
                    json={"callback_query_id": cb.get("id")},
                )
        except Exception:
            pass
        if not chat_id or "|" not in data:
            return "OK"

        # Show a typing indicator while we build/retrieve the answer
        await TelegramBotHandler._send_chat_action(chat_id, "typing")

        kind, _, rest = data.partition("|")
        lid_s, _, rest2 = rest.partition("|")
        source, _, page_s = rest2.partition("|")
        try:
            lesson_id = int(lid_s)
            page = int(page_s or 0)
        except ValueError:
            return "OK"

        try:
            text_out, markup = "", None
            async with AsyncSessionLocal() as db:
                lesson = (
                    await db.execute(
                        select(LessonSchedule).where(LessonSchedule.id == lesson_id)
                    )
                ).scalar_one_or_none()
                if not lesson:
                    text_out = "Lesson not found."
                elif kind == "lesson":
                    text_out = StudyContentService.lesson_summary_text(lesson)
                elif kind == "ex":
                    pack = await StudyContentService.get_lesson_exercises(
                        db, lesson, source=source or None
                    )
                    if pack["found"]:
                        text_out, total_pages = StudyContentService.format_exercise_telegram(pack, page)
                        markup = StudyContentService.nav_keyboard(
                            "ex", lesson_id, source, page, total_pages
                        )
                    else:
                        text_out = pack.get("message") or "No exercises found."
                        sent = await TelegramBotHandler._deliver_page_fallback(
                            db, lesson, chat_id, source or None
                        )
                        if sent:
                            text_out += (
                                "\n\n📄 Your book pages are scanned images (no extractable text), "
                                f"so I sent the actual lesson pages as {sent} PDF(s) instead."
                            )
                elif kind == "qz":
                    actual = await StudyContentService.get_actual_quiz(db, lesson.course_id)
                    if actual:
                        text_out = StudyContentService.format_quiz_telegram(actual)
                    else:
                        text_out = StudyContentService.not_found_quiz_text(lesson)
                elif kind == "exm":
                    actual = await StudyContentService.get_actual_exam(db, lesson.course_id)
                    if actual:
                        text_out = StudyContentService.format_exam_telegram(actual)
                    else:
                        text_out = StudyContentService.not_found_exam_text(lesson)
            if text_out:
                await ReminderService.send_telegram_message(chat_id, text_out, markup)
        except Exception as e:
            print(f"[Telegram Callback Error] {e}")
        return "OK"

    @staticmethod
    async def _deliver_page_fallback(
        db, lesson: LessonSchedule, chat_id: str, src: Optional[str]
    ) -> int:
        """When the lesson's book pages are scanned images (no text layer),
        text extraction cannot show the exercises inline - so send the ACTUAL
        lesson pages as PDF documents instead (never a text description only).
        Returns the number of PDFs sent."""
        wants: list = []
        if src in (None, "", "textbook", "tb") and lesson.textbook_pages:
            wants.append(("textbook", lesson.textbook_pages))
        if src in (None, "", "workbook", "wb") and lesson.workbook_pages:
            wants.append(("workbook", lesson.workbook_pages))
        if not wants:
            return 0
        await TelegramBotHandler._send_chat_action(chat_id, "upload_document")
        await TelegramBotHandler._send_loading(
            chat_id,
            f"📄 Preparing {len(wants)} study page PDF(s) for {lesson.unit} · {lesson.lesson}…",
        )
        sent = 0
        total = len(wants)
        for idx, (dtype, spec) in enumerate(wants, start=1):
            progress = f"📤 Sending {dtype} pages ({idx}/{total})…"
            await TelegramBotHandler._send_loading(chat_id, progress)
            try:
                pdf_bytes, filename, _info = await StudyMaterialService.build_document_pages_pdf(
                    db, lesson.course_id, dtype, spec
                )
                caption = f"📖 {lesson.unit} · {lesson.lesson} — {dtype} {spec} (actual pages)"
                if await StudyMaterialService.send_study_pdf(chat_id, filename, pdf_bytes, caption):
                    sent += 1
                    await TelegramBotHandler._send_loading(
                        chat_id, f"✅ {dtype} pages sent ({idx}/{total})",
                    )
            except Exception as e:
                print(f"[Page fallback skipped] {dtype}: {e}")
                await TelegramBotHandler._send_loading(
                    chat_id, f"❌ {dtype} pages failed: {e}",
                )
        return sent