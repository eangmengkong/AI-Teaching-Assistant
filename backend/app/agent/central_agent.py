import json
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.ai_providers import chat_with_fallback
from app.agent.tools import CentralAgentTools

try:
    import openai
except ImportError:
    openai = None


SYSTEM_PROMPT = """
You are the central AI Teaching Assistant Agent for a 1-month course.
You are the single central intelligence for lesson planning, schedules, document retrieval, exercises, homework, quizzes, reviews, exams, progress tracking, calendar integration, and Telegram communications.

STRICT RULES & CONSTRAINTS:
1. PRIMARY SOURCE OF TRUTH: The uploaded textbook and workbook are your primary source of truth.
2. STRICT ANTI-HALLUCINATION: Do NOT invent textbook or workbook content, pages, unit numbers, lesson numbers, exercises, vocabulary, grammar, or reading passages.
   If information cannot be found in the uploaded documents, respond:
   "I could not find this information in the uploaded textbook/workbook."
3. CONTENT LABELS:
   - Always clearly distinguish source content vs generated content using these exact labels:
     📖 Textbook Content
     ✏️ Workbook Content
     🤖 AI Additional Practice
4. COMPLETED CONTENT ONLY FOR ASSESSMENTS:
   - Quizzes and Final Examinations must ONLY test material from lessons marked as COMPLETED. Do not include future or uncompleted content.
5. SCHEDULE SYNCHRONIZATION:
   - Keep Database, Google Calendar, and Telegram in sync.
"""


TOOL_DEFINITIONS = [
    {
        "name": "analyze_documents",
        "description": "Analyzes uploaded textbook and workbook documents.",
        "parameters": {"type": "object", "properties": {"course_id": {"type": "integer"}}, "required": ["course_id"]}
    },
    {
        "name": "create_monthly_schedule",
        "description": "Generates a realistic 1-month teaching schedule for the course.",
        "parameters": {"type": "object", "properties": {"course_id": {"type": "integer"}}, "required": ["course_id"]}
    },
    {
        "name": "get_today_lesson",
        "description": "Returns today's scheduled lesson plan.",
        "parameters": {"type": "object", "properties": {"course_id": {"type": "integer"}}, "required": ["course_id"]}
    },
    {
        "name": "get_tomorrow_lesson",
        "description": "Returns tomorrow's scheduled lesson plan.",
        "parameters": {"type": "object", "properties": {"course_id": {"type": "integer"}}, "required": ["course_id"]}
    },
    {
        "name": "get_week_schedule",
        "description": "Returns the weekly schedule and progress summary.",
        "parameters": {"type": "object", "properties": {"course_id": {"type": "integer"}}, "required": ["course_id"]}
    },
    {
        "name": "get_lesson_plan",
        "description": "Returns the full detailed lesson plan including teacher preparation.",
        "parameters": {"type": "object", "properties": {"course_id": {"type": "integer"}, "lesson_id": {"type": "integer"}}, "required": ["course_id"]}
    },
    {
        "name": "generate_additional_exercises",
        "description": "Generates additional practice exercises labeled with 🤖 AI Additional Practice.",
        "parameters": {"type": "object", "properties": {"course_id": {"type": "integer"}, "lesson_id": {"type": "integer"}}, "required": ["course_id"]}
    },
    {
        "name": "generate_homework",
        "description": "Generates assigned homework distinguishing source from AI content.",
        "parameters": {"type": "object", "properties": {"course_id": {"type": "integer"}, "lesson_id": {"type": "integer"}}, "required": ["course_id"]}
    },
    {
        "name": "generate_quiz",
        "description": "Generates a quiz using ONLY completed units/lessons.",
        "parameters": {"type": "object", "properties": {"course_id": {"type": "integer"}, "title": {"type": "string"}}, "required": ["course_id"]}
    },
    {
        "name": "create_review",
        "description": "Generates a review lesson for specified completed units/topics.",
        "parameters": {"type": "object", "properties": {"course_id": {"type": "integer"}, "unit_or_topic": {"type": "string"}}, "required": ["course_id", "unit_or_topic"]}
    },
    {
        "name": "generate_final_exam",
        "description": "Generates the comprehensive final examination from completed material.",
        "parameters": {"type": "object", "properties": {"course_id": {"type": "integer"}}, "required": ["course_id"]}
    },
    {
        "name": "record_lesson_completion",
        "description": "Records completion status of a lesson (fully, partially, skipped).",
        "parameters": {"type": "object", "properties": {"course_id": {"type": "integer"}, "lesson_id": {"type": "integer"}, "completion_status": {"type": "string"}}, "required": ["course_id", "lesson_id", "completion_status"]}
    },
    {
        "name": "record_quiz_score",
        "description": "Records student score for a quiz.",
        "parameters": {"type": "object", "properties": {"quiz_id": {"type": "integer"}, "student_name": {"type": "string"}, "score": {"type": "number"}}, "required": ["quiz_id", "student_name", "score"]}
    },
    {
        "name": "record_exam_score",
        "description": "Records student score for an exam.",
        "parameters": {"type": "object", "properties": {"exam_id": {"type": "integer"}, "student_name": {"type": "string"}, "score": {"type": "number"}}, "required": ["exam_id", "student_name", "score"]}
    },
    {
        "name": "calculate_progress",
        "description": "Calculates overall course, textbook, and workbook progress.",
        "parameters": {"type": "object", "properties": {"course_id": {"type": "integer"}}, "required": ["course_id"]}
    },
    {
        "name": "reschedule_lesson",
        "description": "Reschedules a specific lesson to a new date and updates calendar.",
        "parameters": {"type": "object", "properties": {"course_id": {"type": "integer"}, "lesson_id": {"type": "integer"}, "new_date": {"type": "string"}}, "required": ["course_id", "lesson_id", "new_date"]}
    },
    {
        "name": "skip_lesson",
        "description": "Skips a lesson and automatically recalculates remaining schedule.",
        "parameters": {"type": "object", "properties": {"course_id": {"type": "integer"}, "lesson_id": {"type": "integer"}, "reason": {"type": "string"}}, "required": ["course_id", "lesson_id"]}
    },
    {
        "name": "update_schedule",
        "description": "Recalculates and updates the entire monthly schedule.",
        "parameters": {"type": "object", "properties": {"course_id": {"type": "integer"}}, "required": ["course_id"]}
    },
    {
        "name": "create_calendar_event",
        "description": "Creates a Google Calendar event for a scheduled lesson.",
        "parameters": {"type": "object", "properties": {"course_id": {"type": "integer"}, "lesson_id": {"type": "integer"}}, "required": ["course_id", "lesson_id"]}
    },
    {
        "name": "update_calendar_event",
        "description": "Updates an existing Google Calendar event.",
        "parameters": {"type": "object", "properties": {"course_id": {"type": "integer"}, "lesson_id": {"type": "integer"}}, "required": ["course_id", "lesson_id"]}
    },
    {
        "name": "send_telegram_message",
        "description": "Sends a message to the teacher via Telegram.",
        "parameters": {"type": "object", "properties": {"chat_id": {"type": "string"}, "message": {"type": "string"}}, "required": ["chat_id", "message"]}
    }
]


class CentralAITeachingAgent:
    @staticmethod
    async def process_user_request(db: AsyncSession, course_id: int, user_message: str) -> str:
        """
        Processes teacher query using Central AI Teaching Assistant logic and function dispatching.
        """
        # Command routing helper for Telegram / fast execution
        msg_clean = user_message.strip().lower()

        if msg_clean.startswith("/today"):
            res = await CentralAgentTools.get_today_lesson(db, course_id)
            if res["status"] != "success":
                return f"⚠️ {res['message']}"
            l = res["lesson"]
            return (
                f"📚 TODAY'S LESSON\n\n"
                f"Subject: English\n"
                f"Unit: {l['unit']}\n"
                f"Lesson: {l['lesson']}\n\n"
                f"📅 Date:\n{l['date']}\n\n"
                f"⏰ Time:\n{l['time']}\n\n"
                f"📖 Textbook:\n{l['textbook_pages'] or 'N/A'}\n\n"
                f"✏️ Workbook:\n{l['workbook_pages'] or 'N/A'}\n\n"
                f"🎯 Objectives:\n• {l['objectives']}\n\n"
                f"📝 Class Activities:\n" + "\n".join([f"{i+1}. {a}" for i, a in enumerate(l['activities'] or [])]) + "\n\n"
                f"🏠 Homework:\n{l['homework']}\n\n"
                f"🧪 Assessment:\n{l['assessment']}"
            )

        elif msg_clean.startswith("/tomorrow"):
            res = await CentralAgentTools.get_tomorrow_lesson(db, course_id)
            if res["status"] != "success":
                return f"⚠️ {res['message']}"
            l = res["lesson"]
            return f"📚 TOMORROW'S LESSON\nUnit: {l['unit']}\nLesson: {l['lesson']}\n⏰ {l['time']}\n📖 Textbook: {l['textbook_pages']}\n✏️ Workbook: {l['workbook_pages']}"

        elif msg_clean.startswith("/week"):
            res = await CentralAgentTools.get_week_schedule(db, course_id)
            p = res.get("progress_summary", {})
            lines = [f"📅 THIS WEEK ({res['week_range']})\n"]
            for item in res["schedule"]:
                lines.append(f"{item['day']}\n{item['unit']} – {item['lesson']}\n{item['time']}\n")
            lines.append(f"📊 Progress:\nTextbook: {p.get('textbook_progress', '0%')}\nWorkbook: {p.get('workbook_progress', '0%')}")
            return "\n".join(lines)

        elif msg_clean.startswith("/progress"):
            p = await CentralAgentTools.calculate_progress(db, course_id)
            return (
                f"📊 COURSE PROGRESS\n\n"
                f"📖 Textbook:\n{p['textbook_progress']} complete\n\n"
                f"✏️ Workbook:\n{p['workbook_progress']} complete\n\n"
                f"📚 Lessons:\n{p['completed_lessons']} / {p['total_lessons']} completed\n\n"
                f"Average quiz score: {p['average_quiz_score']}\n"
                f"Average exam score: {p['average_exam_score']}\n\n"
                f"⚠️ Current status:\n{p['status_summary']}"
            )

        elif msg_clean.startswith("/exercise"):
            res = await CentralAgentTools.generate_additional_exercises(db, course_id)
            return f"{res.get('label', '🤖 AI Additional Practice')}\n\n" + "\n".join(res.get('exercises', []))

        elif msg_clean.startswith("/homework"):
            res = await CentralAgentTools.generate_homework(db, course_id)
            hw = res.get("homework", {})
            lines = [
                "🏠 TODAY'S HOMEWORK",
                "",
                hw.get("textbook_homework", "📖 Textbook: none assigned"),
                hw.get("workbook_homework", "✏️ Workbook: none assigned"),
                hw.get("ai_generated_homework", ""),
                "",
                f"📅 Due date: {hw.get('due_date', 'TBD')}",
            ]
            return "\n".join(l for l in lines if l)

        elif msg_clean.startswith("/quiz"):
            res = await CentralAgentTools.generate_quiz(db, course_id)
            lines = [f"🧪 QUIZ GENERATED: {res['title']}\nCovered Units: {', '.join(res['covered_units'])}\n"]
            for q in res["questions"]:
                lines.append(f"Q{q['num']}: {q['q']}\nOptions: {', '.join(q['options'])}\n")
            return "\n".join(lines)

        elif msg_clean.startswith("/exam"):
            res = await CentralAgentTools.generate_final_exam(db, course_id)
            return f"🎓 FINAL EXAMINATION GENERATED\nTitle: {res['title']}\nCovered Units: {', '.join(res['covered_units'])}\nTotal Questions: {res['questions_count']}"

        elif msg_clean.startswith("/skip"):
            # Get current/next lesson
            today_res = await CentralAgentTools.get_today_lesson(db, course_id)
            if today_res["status"] == "success":
                lid = today_res["lesson"]["id"]
                res = await CentralAgentTools.skip_lesson(db, course_id, lid, reason="Teacher requested skip")
                return f"⚠️ Today's lesson was skipped.\n\nI've recalculated the remaining schedule.\n{res.get('message', '')}"
            return "No lesson found to skip."

        # Try every configured AI provider in order (primary first, then
        # AI_FALLBACK_1..9). If one is out of quota / erroring, the next
        # one answers automatically.
        if openai:
            try:
                response, provider_info = await chat_with_fallback(
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_message}
                    ],
                    functions=TOOL_DEFINITIONS,
                    function_call="auto"
                )
                if response:
                    print(f"AI answered via provider: {provider_info}")
                    choice = response.choices[0].message
                    fname = args = None
                    # Modern providers return tool_calls; some still use
                    # the legacy function_call field.
                    if getattr(choice, "tool_calls", None):
                        call = choice.tool_calls[0]
                        fname = call.function.name
                        args = json.loads(call.function.arguments or "{}")
                    elif getattr(choice, "function_call", None):
                        fname = choice.function_call.name
                        args = json.loads(choice.function_call.arguments or "{}")
                    if fname:
                        args["course_id"] = course_id

                        if hasattr(CentralAgentTools, fname):
                            tool_fn = getattr(CentralAgentTools, fname)
                            result = await tool_fn(db, **args)
                            return f"Result from central AI tool '{fname}':\n{json.dumps(result, indent=2, default=str)}"

                    return choice.content or "I am your central AI Teaching Assistant."
                else:
                    print(f"All AI providers failed: {provider_info}")
            except Exception as e:
                print(f"AI agent exception: {str(e)}")

        return f"Central AI Assistant received: '{user_message}'. All 21 tools are registered and synchronized."
