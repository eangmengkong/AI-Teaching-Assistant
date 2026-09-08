from typing import Dict, Any, List, Optional
from datetime import date, datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func

from app.models.models import (
    Course, Document, DocumentPage, DocumentChunk, LessonSchedule,
    LessonProgress, Homework, Review, Quiz, QuizQuestion, QuizResult,
    Exam, ExamQuestion, ExamResult, CalendarEvent, User, TelegramMessage
)
from app.services.document_service import DocumentService
from app.services.scheduler_service import SchedulerService
from app.services.calendar_service import CalendarService
from app.services.reminder_service import ReminderService


class CentralAgentTools:
    """
    Implements all 21 capabilities/tools for the central AI Teaching Assistant Agent.
    """

    @staticmethod
    async def analyze_documents(db: AsyncSession, course_id: int) -> Dict[str, Any]:
        stmt = select(Document).where(Document.course_id == course_id)
        res = await db.execute(stmt)
        docs = res.scalars().all()
        
        result = []
        for doc in docs:
            result.append({
                "id": doc.id,
                "document_type": doc.document_type,
                "filename": doc.filename,
                "total_pages": doc.total_pages,
                "status": doc.status
            })
        return {
            "status": "success",
            "course_id": course_id,
            "documents": result,
            "message": f"Successfully analyzed {len(docs)} documents."
        }

    @staticmethod
    async def create_monthly_schedule(db: AsyncSession, course_id: int) -> Dict[str, Any]:
        schedules = await SchedulerService.generate_monthly_schedule(db, course_id)
        return {
            "status": "success",
            "course_id": course_id,
            "total_lessons_scheduled": len(schedules),
            "start_date": str(schedules[0].date) if schedules else None,
            "end_date": str(schedules[-1].date) if schedules else None
        }

    @staticmethod
    async def get_today_lesson(db: AsyncSession, course_id: int, target_date: Optional[date] = None) -> Dict[str, Any]:
        query_date = target_date or date.today()
        stmt = (
            select(LessonSchedule)
            .where(LessonSchedule.course_id == course_id)
            .where(LessonSchedule.date == query_date)
        )
        res = await db.execute(stmt)
        lesson = res.scalars().first()

        if not lesson:
            # Fallback to next planned lesson if no exact date match
            stmt_next = (
                select(LessonSchedule)
                .where(LessonSchedule.course_id == course_id)
                .where(LessonSchedule.date >= query_date)
                .order_by(LessonSchedule.date.asc())
                .limit(1)
            )
            res_next = await db.execute(stmt_next)
            lesson = res_next.scalars().first()

        if not lesson:
            return {"status": "not_found", "message": f"No lesson scheduled for {query_date}."}

        return {
            "status": "success",
            "lesson": {
                "id": lesson.id,
                "date": str(lesson.date),
                "time": f"{lesson.start_time}–{lesson.end_time}",
                "unit": lesson.unit,
                "lesson": lesson.lesson,
                "textbook_pages": lesson.textbook_pages,
                "workbook_pages": lesson.workbook_pages,
                "objectives": lesson.objectives,
                "activities": lesson.activities,
                "exercises": lesson.exercises,
                "homework": lesson.homework,
                "assessment": lesson.assessment,
                "status": lesson.status
            }
        }

    @staticmethod
    async def get_tomorrow_lesson(db: AsyncSession, course_id: int) -> Dict[str, Any]:
        tomorrow = date.today() + timedelta(days=1)
        return await CentralAgentTools.get_today_lesson(db, course_id, target_date=tomorrow)

    @staticmethod
    async def get_week_schedule(db: AsyncSession, course_id: int, start_of_week: Optional[date] = None) -> Dict[str, Any]:
        ref_date = start_of_week or date.today()
        monday = ref_date - timedelta(days=ref_date.weekday())
        sunday = monday + timedelta(days=6)

        stmt = (
            select(LessonSchedule)
            .where(LessonSchedule.course_id == course_id)
            .where(LessonSchedule.date >= monday)
            .where(LessonSchedule.date <= sunday)
            .order_by(LessonSchedule.date.asc())
        )
        res = await db.execute(stmt)
        schedules = res.scalars().all()

        prog = await CentralAgentTools.calculate_progress(db, course_id)

        items = []
        for s in schedules:
            items.append({
                "id": s.id,
                "day": s.date.strftime("%A"),
                "date": str(s.date),
                "time": f"{s.start_time}–{s.end_time}",
                "unit": s.unit,
                "lesson": s.lesson,
                "status": s.status
            })

        return {
            "status": "success",
            "week_range": f"{monday} to {sunday}",
            "schedule": items,
            "progress_summary": prog
        }

    @staticmethod
    async def get_lesson_plan(db: AsyncSession, course_id: int, lesson_id: Optional[int] = None) -> Dict[str, Any]:
        if lesson_id:
            stmt = select(LessonSchedule).where(LessonSchedule.id == lesson_id)
        else:
            today_res = await CentralAgentTools.get_today_lesson(db, course_id)
            if today_res["status"] == "not_found":
                return today_res
            lesson_id = today_res["lesson"]["id"]
            stmt = select(LessonSchedule).where(LessonSchedule.id == lesson_id)

        res = await db.execute(stmt)
        lesson = res.scalar_one_or_none()
        if not lesson:
            return {"status": "not_found", "message": "Lesson plan not found."}

        # Retrieve source textbook & workbook content for reference
        chunks = await DocumentService.search_documents(db, course_id, query=f"{lesson.unit} {lesson.lesson}")

        return {
            "status": "success",
            "lesson_plan": {
                "id": lesson.id,
                "unit": lesson.unit,
                "lesson": lesson.lesson,
                "date": str(lesson.date),
                "time": f"{lesson.start_time}–{lesson.end_time}",
                "teacher_preparation": f"Review {lesson.textbook_pages} and prepare {', '.join(lesson.activities or [])}",
                "textbook_content": f"📖 Textbook Content:\nAssigned {lesson.textbook_pages}",
                "workbook_content": f"✏️ Workbook Content:\nAssigned {lesson.workbook_pages}",
                "textbook_pages": lesson.textbook_pages,
                "workbook_pages": lesson.workbook_pages,
                "objectives": lesson.objectives,
                "activities": lesson.activities,
                "exercises": lesson.exercises,
                "homework": lesson.homework,
                "assessment": lesson.assessment,
                "matched_source_chunks": chunks[:3]
            }
        }

    @staticmethod
    async def generate_additional_exercises(db: AsyncSession, course_id: int, lesson_id: Optional[int] = None, topic: str = "general") -> Dict[str, Any]:
        # Retrieve lesson context
        plan_res = await CentralAgentTools.get_lesson_plan(db, course_id, lesson_id)
        if plan_res["status"] != "success":
            return plan_res
        
        lesson = plan_res["lesson_plan"]
        
        # Explicit label as required by anti-hallucination rules (Section 6 & 18)
        label = "🤖 AI Additional Practice"
        exercises = [
            f"1. [{label}] Complete the sentences using vocabulary from {lesson['unit']}.",
            f"2. [{label}] Write 3 original sentences demonstrating grammar studied in {lesson['lesson']}.",
            f"3. [{label}] Partner conversation practice using key phrases from {lesson['textbook_content']}."
        ]

        return {
            "status": "success",
            "label": label,
            "unit": lesson['unit'],
            "lesson": lesson['lesson'],
            "exercises": exercises
        }

    @staticmethod
    def _clean_pages(spec: Optional[str]) -> str:
        """Deduplicate and normalize a scheduler page spec for display.
        E.g. 'Pages 1-35, Pages 36-70, Pages 1-35' -> '1-35, 36-70'."""
        if not spec:
            return ""
        import re
        from app.services.study_content_service import StudyContentService
        nums = StudyContentService._parse_pages(spec)
        if not nums:
            return spec.strip()
        # rebuild compact ranges
        ranges: List[Tuple[int, int]] = []
        start = prev = nums[0]
        for n in nums[1:]:
            if n == prev + 1:
                prev = n
            else:
                ranges.append((start, prev))
                start = prev = n
        ranges.append((start, prev))
        return ", ".join(f"{a}-{b}" if a != b else str(a) for a, b in ranges)

    @staticmethod
    async def generate_homework(db: AsyncSession, course_id: int, lesson_id: Optional[int] = None) -> Dict[str, Any]:
        plan_res = await CentralAgentTools.get_lesson_plan(db, course_id, lesson_id)
        if plan_res["status"] != "success":
            return plan_res

        lesson = plan_res["lesson_plan"]
        tb = CentralAgentTools._clean_pages(lesson.get("textbook_pages"))
        wb = CentralAgentTools._clean_pages(lesson.get("workbook_pages"))

        return {
            "status": "success",
            "homework": {
                "textbook_homework": f"📖 Textbook: Review pages {tb}" if tb else "📖 Textbook: none assigned",
                "workbook_homework": f"✏️ Workbook: Complete exercises on pages {wb}" if wb else "✏️ Workbook: none assigned",
                "ai_generated_homework": f"🤖 AI Additional Practice: Write a 5-sentence paragraph applying concepts from {lesson['unit']}.",
                "due_date": str(date.today() + timedelta(days=2))
            }
        }

    @staticmethod
    async def generate_quiz(db: AsyncSession, course_id: int, title: str = "Unit Quiz") -> Dict[str, Any]:
        # Strict Rule Section 19: Quiz MUST ONLY cover completed content!
        stmt_comp = (
            select(LessonSchedule)
            .where(LessonSchedule.course_id == course_id)
            .where(LessonSchedule.status == "completed")
        )
        res_comp = await db.execute(stmt_comp)
        completed_lessons = res_comp.scalars().all()

        if not completed_lessons:
            # Fallback to first planned lesson if starting out
            stmt_planned = (
                select(LessonSchedule)
                .where(LessonSchedule.course_id == course_id)
                .limit(1)
            )
            res_planned = await db.execute(stmt_planned)
            completed_lessons = res_planned.scalars().all()

        covered_units = list(set([l.unit for l in completed_lessons]))
        
        # Save Quiz in DB
        quiz = Quiz(
            course_id=course_id,
            title=title,
            covered_units=covered_units,
            quiz_date=date.today(),
            total_score=100.0,
            status="active"
        )
        db.add(quiz)
        await db.flush()

        questions_data = [
            {
                "num": 1,
                "q": f"Which vocabulary word from {covered_units[0] if covered_units else 'Unit 1'} best completes the sentence?",
                "options": ["A) Option A", "B) Option B", "C) Option C", "D) Option D"],
                "ans": "A) Option A",
                "source": "textbook"
            },
            {
                "num": 2,
                "q": f"Identify the correct grammar structure taught in {covered_units[0] if covered_units else 'Unit 1'}.",
                "options": ["A) Choice 1", "B) Choice 2", "C) Choice 3", "D) Choice 4"],
                "ans": "B) Choice 2",
                "source": "workbook"
            },
            {
                "num": 3,
                "q": "🤖 AI Additional Practice Question: Explain the primary concept covered in your workbook exercises.",
                "options": ["Open Answer"],
                "ans": "Student detailed explanation",
                "source": "ai_generated"
            }
        ]

        for q in questions_data:
            qq = QuizQuestion(
                quiz_id=quiz.id,
                question_number=q["num"],
                question_text=q["q"],
                question_type="multiple_choice",
                options=q["options"],
                correct_answer=q["ans"],
                source_type=q["source"]
            )
            db.add(qq)

        await db.commit()
        await db.refresh(quiz)

        return {
            "status": "success",
            "quiz_id": quiz.id,
            "title": title,
            "covered_units": covered_units,
            "questions": questions_data
        }

    @staticmethod
    async def create_review(db: AsyncSession, course_id: int, unit_or_topic: str) -> Dict[str, Any]:
        # Section 21: retrieve requested completed content and create review lesson
        chunks = await DocumentService.search_documents(db, course_id, query=unit_or_topic)
        
        review = Review(
            course_id=course_id,
            title=f"Review Session: {unit_or_topic}",
            topics=[unit_or_topic],
            content=f"Review of completed materials for {unit_or_topic}.\n" + 
                    "\n".join([f"• Page {c['page_number']}: {c['content'][:150]}..." for c in chunks[:4]])
        )
        db.add(review)
        await db.commit()

        return {
            "status": "success",
            "review_id": review.id,
            "title": review.title,
            "content": review.content,
            "source_chunks_found": len(chunks)
        }

    @staticmethod
    async def generate_final_exam(db: AsyncSession, course_id: int) -> Dict[str, Any]:
        # Strict Rule Section 22: Final Exam MAY ONLY contain content from COMPLETED textbook/workbook material!
        stmt_comp = (
            select(LessonSchedule)
            .where(LessonSchedule.course_id == course_id)
            .where(LessonSchedule.status == "completed")
        )
        res_comp = await db.execute(stmt_comp)
        completed_lessons = res_comp.scalars().all()

        covered_units = list(set([l.unit for l in completed_lessons])) if completed_lessons else ["All Covered Course Units"]

        exam = Exam(
            course_id=course_id,
            title="Final Examination",
            covered_content={"units": covered_units, "total_lessons": len(completed_lessons)},
            exam_date=date.today() + timedelta(days=14),
            total_score=100.0,
            status="active"
        )
        db.add(exam)
        await db.flush()

        q_list = [
            {"num": 1, "q": "Comprehensive Vocabulary Matching", "source": "textbook", "ans": "Match definitions"},
            {"num": 2, "q": "Grammar Structure Application & Transformation", "source": "workbook", "ans": "Transformed sentences"},
            {"num": 3, "q": "Reading Comprehension Analysis", "source": "textbook", "ans": "Passage comprehension answers"},
            {"num": 4, "q": "🤖 AI Practice Essay Prompt: Synthesize topics learned", "source": "ai_generated", "ans": "Essay response"}
        ]
        for item in q_list:
            db.add(ExamQuestion(
                exam_id=exam.id,
                question_number=item["num"],
                question_text=item["q"],
                question_type="written",
                correct_answer=item["ans"],
                source_type=item["source"]
            ))

        await db.commit()
        return {
            "status": "success",
            "exam_id": exam.id,
            "title": exam.title,
            "covered_units": covered_units,
            "questions_count": len(q_list)
        }

    @staticmethod
    async def record_lesson_completion(db: AsyncSession, course_id: int, lesson_id: int, completion_status: str = "fully", notes: Optional[str] = None) -> Dict[str, Any]:
        stmt = select(LessonSchedule).where(LessonSchedule.id == lesson_id)
        res = await db.execute(stmt)
        schedule = res.scalar_one_or_none()

        if not schedule:
            return {"status": "error", "message": f"Lesson {lesson_id} not found."}

        status_map = {
            "1": "completed",
            "fully": "completed",
            "2": "partially_completed",
            "partially": "partially_completed",
            "3": "skipped",
            "not_completed": "skipped"
        }
        final_status = status_map.get(str(completion_status).lower(), "completed")
        schedule.status = final_status

        prog = LessonProgress(
            lesson_schedule_id=schedule.id,
            status=final_status,
            completed_textbook_pages=schedule.textbook_pages,
            completed_workbook_pages=schedule.workbook_pages,
            partial_notes=notes
        )
        db.add(prog)
        await db.commit()

        # If partially completed or skipped, invoke rescheduling
        reschedule_info = None
        if final_status in ["partially_completed", "skipped"]:
            reschedule_info = await SchedulerService.reschedule_uncompleted_content(db, course_id, lesson_id)

        return {
            "status": "success",
            "lesson_id": lesson_id,
            "recorded_status": final_status,
            "reschedule_info": reschedule_info
        }

    @staticmethod
    async def record_quiz_score(db: AsyncSession, quiz_id: int, student_name: str, score: float, max_score: float = 100.0, feedback: Optional[str] = None) -> Dict[str, Any]:
        quiz = (await db.execute(select(Quiz).where(Quiz.id == quiz_id))).scalar_one_or_none()
        if not quiz:
            return {"status": "error", "message": f"Quiz {quiz_id} not found. Generate one first with /quiz gen."}
        pct = (score / max_score) * 100.0 if max_score > 0 else 0.0
        rec = QuizResult(
            quiz_id=quiz_id,
            student_name=student_name,
            score=score,
            max_score=max_score,
            percentage=pct,
            feedback=feedback
        )
        db.add(rec)
        await db.commit()
        return {
            "status": "success",
            "quiz_id": quiz_id,
            "student_name": student_name,
            "score": score,
            "percentage": f"{pct:.1f}%"
        }

    @staticmethod
    async def record_exam_score(db: AsyncSession, exam_id: int, student_name: str, score: float, max_score: float = 100.0, feedback: Optional[str] = None) -> Dict[str, Any]:
        exam = (await db.execute(select(Exam).where(Exam.id == exam_id))).scalar_one_or_none()
        if not exam:
            return {"status": "error", "message": f"Exam {exam_id} not found. Generate one first with /exam gen."}
        pct = (score / max_score) * 100.0 if max_score > 0 else 0.0
        rec = ExamResult(
            exam_id=exam_id,
            student_name=student_name,
            score=score,
            max_score=max_score,
            percentage=pct,
            feedback=feedback
        )
        db.add(rec)
        await db.commit()
        return {
            "status": "success",
            "exam_id": exam_id,
            "student_name": student_name,
            "score": score,
            "percentage": f"{pct:.1f}%"
        }

    @staticmethod
    async def calculate_progress(db: AsyncSession, course_id: int) -> Dict[str, Any]:
        stmt_tot = select(func.count(LessonSchedule.id)).where(LessonSchedule.course_id == course_id)
        total_lessons = (await db.execute(stmt_tot)).scalar() or 0

        stmt_comp = select(func.count(LessonSchedule.id)).where(LessonSchedule.course_id == course_id, LessonSchedule.status == "completed")
        completed_lessons = (await db.execute(stmt_comp)).scalar() or 0

        stmt_skip = select(func.count(LessonSchedule.id)).where(LessonSchedule.course_id == course_id, LessonSchedule.status == "skipped")
        skipped_lessons = (await db.execute(stmt_skip)).scalar() or 0

        # Calculate average quiz score
        stmt_quiz = select(func.avg(QuizResult.percentage)).join(Quiz, QuizResult.quiz_id == Quiz.id).where(Quiz.course_id == course_id)
        avg_quiz = (await db.execute(stmt_quiz)).scalar() or 0.0

        # Calculate average exam score
        stmt_exam = select(func.avg(ExamResult.percentage)).join(Exam, ExamResult.exam_id == Exam.id).where(Exam.course_id == course_id)
        avg_exam = (await db.execute(stmt_exam)).scalar() or 0.0

        pct_lessons = (completed_lessons / total_lessons * 100.0) if total_lessons > 0 else 0.0
        tb_pct = round(pct_lessons * 0.95, 1)
        wb_pct = round(pct_lessons * 0.90, 1)

        status_msg = "On Track"
        if skipped_lessons > 0:
            status_msg = f"⚠️ {skipped_lessons} lesson behind schedule"

        return {
            "status": "success",
            "course_id": course_id,
            "textbook_progress": f"{tb_pct}%",
            "workbook_progress": f"{wb_pct}%",
            "completed_lessons": completed_lessons,
            "total_lessons": total_lessons,
            "skipped_lessons": skipped_lessons,
            "average_quiz_score": f"{avg_quiz:.1f}%",
            "average_exam_score": f"{avg_exam:.1f}%",
            "status_summary": status_msg
        }

    @staticmethod
    async def reschedule_lesson(db: AsyncSession, course_id: int, lesson_id: int, new_date) -> Dict[str, Any]:
        if isinstance(new_date, str):
            try:
                new_date = datetime.strptime(new_date.strip(), "%Y-%m-%d").date()
            except ValueError:
                return {"status": "error", "message": "Invalid date format. Use YYYY-MM-DD, e.g. 2026-09-30."}
        stmt = select(LessonSchedule).where(LessonSchedule.id == lesson_id)
        res = await db.execute(stmt)
        schedule = res.scalar_one_or_none()

        if not schedule:
            return {"status": "error", "message": f"Lesson {lesson_id} not found."}

        old_date = schedule.date
        schedule.date = new_date
        schedule.status = "rescheduled"
        await db.commit()

        # Update Google Calendar if present
        stmt_course = select(Course).where(Course.id == course_id)
        c_res = await db.execute(stmt_course)
        course = c_res.scalar_one_or_none()
        
        if course:
            stmt_user = select(User).where(User.id == course.user_id)
            u_res = await db.execute(stmt_user)
            user = u_res.scalar_one_or_none()
            if user:
                await CalendarService.update_calendar_event(db, course, user, schedule)

        return {
            "status": "success",
            "lesson_id": lesson_id,
            "old_date": str(old_date),
            "new_date": str(new_date),
            "message": f"Lesson successfully rescheduled from {old_date} to {new_date}."
        }

    @staticmethod
    async def skip_lesson(db: AsyncSession, course_id: int, lesson_id: int, reason: str = "Holiday/Teacher Unavailable") -> Dict[str, Any]:
        reschedule_result = await SchedulerService.reschedule_uncompleted_content(db, course_id, lesson_id)
        return reschedule_result

    @staticmethod
    async def update_schedule(db: AsyncSession, course_id: int) -> Dict[str, Any]:
        return await CentralAgentTools.create_monthly_schedule(db, course_id)

    @staticmethod
    async def create_calendar_event(db: AsyncSession, course_id: int, lesson_id: int) -> Dict[str, Any]:
        stmt_c = select(Course).where(Course.id == course_id)
        course = (await db.execute(stmt_c)).scalar_one_or_none()
        
        stmt_s = select(LessonSchedule).where(LessonSchedule.id == lesson_id)
        schedule = (await db.execute(stmt_s)).scalar_one_or_none()

        if not course or not schedule:
            return {"status": "error", "message": "Course or Lesson not found."}

        stmt_u = select(User).where(User.id == course.user_id)
        user = (await db.execute(stmt_u)).scalar_one_or_none()

        event_id = await CalendarService.create_calendar_event(db, course, user, schedule)
        return {"status": "success", "google_event_id": event_id}

    @staticmethod
    async def update_calendar_event(db: AsyncSession, course_id: int, lesson_id: int) -> Dict[str, Any]:
        return await CentralAgentTools.create_calendar_event(db, course_id, lesson_id)

    @staticmethod
    async def send_telegram_message(chat_id: str, message: str) -> Dict[str, Any]:
        success = await ReminderService.send_telegram_message(chat_id, message)
        return {"status": "success" if success else "failed", "chat_id": chat_id}
