"""Automated verification: simulates EVERY Telegram bot command through the
real handler against the real database. Telegram HTTP calls are intercepted
(nothing is actually sent to Telegram). Mutating commands run inside a
snapshot/restore so the schedule is left untouched.

Usage: python scripts/test_all_commands.py [safe|mutate|review]
"""
import asyncio
import contextlib
import io as _io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx

from app.core.database import AsyncSessionLocal
from sqlalchemy import text

MODE = sys.argv[1] if len(sys.argv) > 1 else "safe"

# ---- intercept every Telegram API call (record, fake 200, no network) ----
_real_post = httpx.AsyncClient.post
SENT = []


class _FakeResp:
    status_code = 200
    text = "ok"


async def _fake_post(self, url, **kw):
    if "api.telegram.org" in str(url):
        SENT.append((str(url).rsplit("/", 1)[-1], kw))
        return _FakeResp()
    return await _real_post(self, url, **kw)


httpx.AsyncClient.post = _fake_post

from app.telegram.bot import TelegramBotHandler  # noqa: E402

CHAT_ID = "703281574"  # the user's real linked chat


def cmd(t):
    return {"message": {"message_id": 1, "chat": {"id": int(CHAT_ID)}, "text": t}}


async def run_command(label, update, timeout=60):
    buf = _io.StringIO()
    SENT.clear()
    err = None
    with contextlib.redirect_stdout(buf):
        try:
            await asyncio.wait_for(TelegramBotHandler.handle_update(update), timeout)
        except Exception as e:  # timeout or crash
            err = f"{type(e).__name__}: {e}"
    captured = buf.getvalue()
    replies = [(m, k) for m, k in SENT if m == "sendMessage"]
    docs = [(m, k) for m, k in SENT if m == "sendDocument"]
    first = ""
    if replies:
        body = replies[0][1].get("json", {}).get("text", "")
        first = body.splitlines()[0][:90] if body else "(empty)"
    status = "ERROR" if err else ("OK" if (replies or docs) else "NO-REPLY")
    markup = " [buttons]" if replies and replies[0][1].get("json", {}).get("reply_markup") else ""
    docinfo = f" +{len(docs)} PDF(s)" if docs else ""
    print(f"[{status}] {label:26s} -> {first}{markup}{docinfo}")
    if err:
        print(f"       exception: {err}")
    if status != "OK":
        tail = captured.strip().splitlines()[-3:]
        for line in tail:
            print(f"       log| {line[:130]}")
    return status

# ---- snapshot / restore (INSERT_ORDER = parents before children;
# ---- DELETE_ORDER = exact reverse so FKs never block) ----
INSERT_ORDER = [
    "quizzes", "quiz_questions", "exams", "exam_questions",
    "lesson_schedule", "lesson_progress", "calendar_events",
    "telegram_messages", "homework", "reviews",
    "quiz_results", "exam_results",
]
DELETE_ORDER = list(reversed(INSERT_ORDER))
TABLES = INSERT_ORDER
SNAP = {}


async def snapshot(db):
    res = await db.execute(text(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='public'"))
    existing = {r[0] for r in res.fetchall()}
    for t in TABLES:
        if t not in existing:
            SNAP[t] = None  # table does not exist
            continue
        res = await db.execute(text(f'SELECT * FROM "{t}"'))
        cols = list(res.keys())
        SNAP[t] = [dict(zip(cols, r)) for r in res.fetchall()]


def _enc(v):
    if isinstance(v, (dict, list)):
        return json.dumps(v)
    return v


async def restore(db):
    # children first (DELETE_ORDER), then re-insert parents first (INSERT_ORDER)
    for t in DELETE_ORDER:
        if SNAP.get(t) is None:
            continue
        await db.execute(text(f'DELETE FROM "{t}"'))
    await db.flush()
    for t in INSERT_ORDER:
        rows = SNAP.get(t)
        if not rows:
            continue
        cols = list(rows[0].keys())
        collist = ", ".join(f'"{c}"' for c in cols)
        for r in rows:
            ph = ", ".join(f":p{i}" for i in range(len(cols)))
            params = {f"p{i}": _enc(r[c]) for i, c in enumerate(cols)}
            await db.execute(text(f'INSERT INTO "{t}" ({collist}) VALUES ({ph})'), params)
        if "id" in cols:
            await db.execute(
                text(f"SELECT setval(pg_get_serial_sequence('{t}','id'), "
                     f"(SELECT COALESCE(MAX(id),1) FROM \"{t}\"), true)")
            )
    await db.commit()


async def counts_match(db):
    for t, rows in SNAP.items():
        if rows is None:
            continue
        n = (await db.execute(text(f'SELECT COUNT(*) FROM "{t}"'))).scalar()
        if n != len(rows):
            return f"{t}: {len(rows)} -> {n}"
    return None


async def main():
    async with AsyncSessionLocal() as db:
        await snapshot(db)
        today = (await db.execute(text(
            "SELECT id FROM lesson_schedule ORDER BY date, id LIMIT 1"))).scalar()
        n_today = (await db.execute(text(
            "SELECT COUNT(*) FROM lesson_schedule"))).scalar()
    print(f"mode={MODE} | today's lesson id={today} | {n_today} scheduled lessons | chat={CHAT_ID}")

    results = {}
    if MODE == "safe":
        for c in ["/start", "/help", "/today", "/tomorrow", "/week", "/lesson",
                  "/exercise", "/exercise workbook", "/pages", "/quiz", "/exam",
                  "/homework", "/progress", "/setup", "/review", "/blah"]:
            results[c] = await run_command(c, cmd(c))
        results["btn:next"] = await run_command(
            "button Next (ex p2)",
            {"callback_query": {"id": "1", "data": f"ex|{today}||1",
                                "message": {"chat": {"id": int(CHAT_ID)}}}})
        results["btn:quiz"] = await run_command(
            "button Quiz",
            {"callback_query": {"id": "2", "data": f"qz|{today}||0",
                                "message": {"chat": {"id": int(CHAT_ID)}}}})
    elif MODE == "review":
        results["/review 1"] = await run_command("/review 1 (real AI)", cmd("/review 1"), timeout=170)
        results["/review Unit 1"] = await run_command("/review Unit 1 (fallback)", cmd("/review Unit 1"), timeout=170)
    elif MODE == "mutate":
        for c in ["/complete", "/skip", "/reschedule 2026-09-30", "/score 1 TestStudent 9"]:
            results[c] = await run_command(c, cmd(c))
        results["/quiz gen"] = await run_command("/quiz gen (real AI)", cmd("/quiz gen"), timeout=170)
        results["/exam gen"] = await run_command("/exam gen (real AI)", cmd("/exam gen"), timeout=170)
        results["/score after gen"] = await run_command("/score after gen", cmd("/score 1 TestStudent 9"))
        async with AsyncSessionLocal() as db:
            await restore(db)
        async with AsyncSessionLocal() as db2:
            diff = await counts_match(db2)
        print("RESTORE OK (all tables back to snapshot)" if not diff else f"RESTORE DIFF: {diff}")

    bad = [k for k, v in results.items() if v != "OK"]
    print(f"\n{MODE}: {len(results) - len(bad)}/{len(results)} OK" + (f" | problems: {bad}" if bad else ""))


if __name__ == "__main__":
    asyncio.run(main())

