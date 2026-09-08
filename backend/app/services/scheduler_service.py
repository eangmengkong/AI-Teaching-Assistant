from datetime import date, datetime, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, update
from app.models.models import (
    Course, Document, DocumentPage, LessonSchedule, LessonProgress,
    CalendarEvent, TelegramMessage, Homework, Review,
)

class SchedulerService:
    DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    @staticmethod
    async def _purge_course_schedules(db: AsyncSession, course_id: int) -> None:
        """Delete a course's schedules and every row referencing them."""
        schedule_ids = select(LessonSchedule.id).where(LessonSchedule.course_id == course_id).scalar_subquery()
        await db.execute(delete(LessonProgress).where(LessonProgress.lesson_schedule_id.in_(schedule_ids)))
        await db.execute(delete(CalendarEvent).where(CalendarEvent.lesson_schedule_id.in_(schedule_ids)))
        await db.execute(delete(TelegramMessage).where(TelegramMessage.lesson_schedule_id.in_(schedule_ids)))
        await db.execute(delete(Homework).where(Homework.lesson_schedule_id.in_(schedule_ids)))
        await db.execute(delete(Review).where(Review.lesson_schedule_id.in_(schedule_ids)))
        await db.execute(delete(LessonSchedule).where(LessonSchedule.course_id == course_id))

    @staticmethod
    async def generate_monthly_schedule(db: AsyncSession, course_id: int) -> List[LessonSchedule]:
        stmt = select(Course).where(Course.id == course_id)
        result = await db.execute(stmt)
        course = result.scalar_one_or_none()
        if not course:
            # Auto-create default course for local execution if missing
            course = Course(
                id=course_id,
                user_id=1,
                name="English 101",
                student_count=25,
                class_days=["Monday", "Wednesday", "Friday"],
                start_time="08:00",
                end_time="09:30",
                start_date=date.today(),
                end_date=date.today() + timedelta(days=30),
                holidays=[]
            )
            db.add(course)
            await db.commit()

        # Get documents
        doc_stmt = select(Document).where(Document.course_id == course_id)
        doc_res = await db.execute(doc_stmt)
        docs = doc_res.scalars().all()

        textbook = next((d for d in docs if d.document_type.lower() == 'textbook'), None)
        workbook = next((d for d in docs if d.document_type.lower() == 'workbook'), None)

        tb_total_pages = textbook.total_pages if textbook else 30
        wb_total_pages = workbook.total_pages if workbook else 20

        # Calculate teaching dates
        teaching_dates = SchedulerService._calculate_teaching_dates(
            start_date=course.start_date,
            end_date=course.end_date,
            class_days=course.class_days,
            holidays=[datetime.strptime(h, "%Y-%m-%d").date() if isinstance(h, str) else h for h in (course.holidays or [])],
            days_without_class=[datetime.strptime(d, "%Y-%m-%d").date() if isinstance(d, str) else d for d in (course.days_without_class or [])]
        )

        total_sessions = len(teaching_dates)
        if total_sessions == 0:
            raise ValueError("No valid teaching sessions available in date range with selected class days")

        # Reserve sessions:
        # Final Exam (last session)
        # Pre-exam Final Review (2nd to last session)
        # Exam Correction (or final recap)
        # Quizzes (approx every 4th/5th session)
        # Regular review sessions (approx every 3rd/4th session)

        reserved_indices = {} # index -> session_type
        reserved_indices[total_sessions - 1] = "final_exam"
        if total_sessions > 1:
            reserved_indices[total_sessions - 2] = "final_review"

        # Place quizzes & regular reviews
        for i in range(total_sessions):
            if i in reserved_indices:
                continue
            if (i + 1) % 5 == 0 and i != total_sessions - 1:
                reserved_indices[i] = "quiz"
            elif (i + 1) % 3 == 0:
                reserved_indices[i] = "review"

        content_sessions_count = total_sessions - len(reserved_indices)
        if content_sessions_count <= 0:
            content_sessions_count = total_sessions # fallback if short course

        # Distribute textbook and workbook pages
        tb_pages_per_session = max(1, round(tb_total_pages / max(1, content_sessions_count)))
        wb_pages_per_session = max(1, round(wb_total_pages / max(1, content_sessions_count)))

        # Clear existing schedule for this course (children first: the bulk
        # delete below bypasses ORM cascades, so calendar_events / lesson_progress
        # / telegram_messages / homework / reviews that still reference these
        # schedules must be removed first or PostgreSQL aborts the delete).
        await SchedulerService._purge_course_schedules(db, course_id)

        new_schedules = []
        tb_curr_page = 1
        wb_curr_page = 1
        lesson_counter = 1
        unit_counter = 1
        quiz_counter = 1

        for idx, s_date in enumerate(teaching_dates):
            week_num = ((s_date - course.start_date).days // 7) + 1
            session_type = reserved_indices.get(idx, "regular")

            if session_type == "final_exam":
                unit_str = f"Course Final"
                lesson_str = f"Final Examination"
                tb_pages_str = f"Pages 1–{tb_total_pages} (Comprehensive)"
                wb_pages_str = f"Pages 1–{wb_total_pages} (Comprehensive)"
                objectives_str = "Evaluate student mastery across all course units and lessons."
                activities = ["Final Examination Administration", "Submission Collection"]
                exercises = []
                homework = "None - Course Complete!"
                assessment = "Comprehensive Final Examination"

            elif session_type == "final_review":
                unit_str = f"Review"
                lesson_str = f"Comprehensive Final Review"
                tb_pages_str = f"Pages 1–{tb_total_pages}"
                wb_pages_str = f"Pages 1–{wb_total_pages}"
                objectives_str = "Review all key vocabulary, grammar, and core concepts prior to the final exam."
                activities = ["Q&A Session", "Key Concept Recap", "Practice Exam Sample"]
                exercises = ["Group Problem Solving", "Mock Quiz"]
                homework = "Study for Final Examination"
                assessment = "Practice Review Check"

            elif session_type == "quiz":
                unit_str = f"Unit {unit_counter}"
                lesson_str = f"Quiz #{quiz_counter} & Revision"
                tb_pages_str = f"Pages {max(1, tb_curr_page - tb_pages_per_session * 2)}–{tb_curr_page}"
                wb_pages_str = f"Pages {max(1, wb_curr_page - wb_pages_per_session * 2)}–{wb_curr_page}"
                objectives_str = f"Assess student understanding for recent material up to Unit {unit_counter}."
                activities = [f"Administer Quiz #{quiz_counter}", "Quiz Discussion & Correction"]
                exercises = ["Quiz Questions", "Self-Correction"]
                homework = f"Review Quiz #{quiz_counter} errors"
                assessment = f"Quiz #{quiz_counter}"
                quiz_counter += 1

            elif session_type == "review":
                unit_str = f"Unit {unit_counter}"
                lesson_str = f"Lesson Review & Practice"
                tb_pages_str = f"Pages {max(1, tb_curr_page - tb_pages_per_session)}–{tb_curr_page}"
                wb_pages_str = f"Pages {max(1, wb_curr_page - wb_pages_per_session)}–{wb_curr_page}"
                objectives_str = "Consolidate vocabulary, grammar structures, and workbook exercises."
                activities = ["Vocabulary Drill", "Grammar Warmup", "Workbook Exercise Review"]
                exercises = ["Workbook Practice", "Pair Activity"]
                homework = "Complete remaining workbook exercises"
                assessment = "In-class participation check"

            else:
                # Regular Content Lesson
                tb_next_page = min(tb_total_pages, tb_curr_page + tb_pages_per_session - 1)
                wb_next_page = min(wb_total_pages, wb_curr_page + wb_pages_per_session - 1)

                unit_str = f"Unit {unit_counter}"
                lesson_str = f"Lesson {lesson_counter}"
                tb_pages_str = f"Pages {tb_curr_page}–{tb_next_page}"
                wb_pages_str = f"Pages {wb_curr_page}–{wb_next_page}"
                objectives_str = f"Master content in Unit {unit_counter} Lesson {lesson_counter} (Textbook pp. {tb_curr_page}–{tb_next_page})."
                activities = ["Concept Explanation", "Textbook Guided Reading", "Workbook Practice"]
                exercises = [f"Textbook pp. {tb_curr_page} exercises", f"Workbook pp. {wb_curr_page} exercises"]
                homework = f"Workbook pages {wb_curr_page}–{wb_next_page}"
                assessment = "Short lesson check"

                tb_curr_page = min(tb_total_pages, tb_next_page + 1)
                wb_curr_page = min(wb_total_pages, wb_next_page + 1)
                lesson_counter += 1
                if lesson_counter > 3:
                    lesson_counter = 1
                    unit_counter += 1

            schedule_item = LessonSchedule(
                course_id=course_id,
                date=s_date,
                start_time=course.start_time,
                end_time=course.end_time,
                week_number=week_num,
                unit=unit_str,
                lesson=lesson_str,
                textbook_pages=tb_pages_str,
                workbook_pages=wb_pages_str,
                objectives=objectives_str,
                activities=activities,
                exercises=exercises,
                homework=homework,
                assessment=assessment,
                status="planned"
            )
            db.add(schedule_item)
            new_schedules.append(schedule_item)

        await db.commit()
        return new_schedules

    @staticmethod
    def _calculate_teaching_dates(start_date: date, end_date: date, class_days: List[str], holidays: List[date], days_without_class: List[date]) -> List[date]:
        dates = []
        curr = start_date
        class_days_normalized = [d.capitalize() for d in class_days]

        while curr <= end_date:
            day_name = SchedulerService.DAY_NAMES[curr.weekday()]
            if day_name in class_days_normalized:
                if curr not in holidays and curr not in days_without_class:
                    dates.append(curr)
            curr += timedelta(days=1)
        return dates

    @staticmethod
    async def reschedule_uncompleted_content(db: AsyncSession, course_id: int, skipped_lesson_id: int) -> Dict[str, Any]:
        # Fetch all planned future lessons after skipped_lesson_id
        skipped_stmt = select(LessonSchedule).where(LessonSchedule.id == skipped_lesson_id)
        skipped_res = await db.execute(skipped_stmt)
        skipped = skipped_res.scalar_one_or_none()

        if not skipped:
            raise ValueError(f"Lesson {skipped_lesson_id} not found")

        # Mark skipped lesson as skipped
        skipped.status = "skipped"

        # Fetch remaining planned lessons after this date
        future_stmt = (
            select(LessonSchedule)
            .where(LessonSchedule.course_id == course_id)
            .where(LessonSchedule.date > skipped.date)
            .where(LessonSchedule.status == "planned")
            .order_by(LessonSchedule.date.asc())
        )
        future_res = await db.execute(future_stmt)
        future_lessons = future_res.scalars().all()

        if not future_lessons:
            await db.commit()
            return {"status": "warning", "message": "No remaining teaching sessions to redistribute content into."}

        # Shift the content of skipped lesson into future lessons intelligently
        content_to_redistribute = {
            "unit": skipped.unit,
            "lesson": skipped.lesson,
            "textbook_pages": skipped.textbook_pages,
            "workbook_pages": skipped.workbook_pages,
            "objectives": skipped.objectives
        }

        # Append/merge content into the next content lesson
        next_lesson = future_lessons[0]
        next_lesson.objectives = f"{next_lesson.objectives}\n(Includes catch-up from skipped {skipped.unit} {skipped.lesson})"
        next_lesson.textbook_pages = f"{skipped.textbook_pages}, {next_lesson.textbook_pages}"
        next_lesson.workbook_pages = f"{skipped.workbook_pages}, {next_lesson.workbook_pages}"
        next_lesson.notes = f"Redistributed from skipped lesson on {skipped.date}"

        await db.commit()
        return {
            "status": "success",
            "message": f"Content from skipped lesson on {skipped.date} redistributed into lesson on {next_lesson.date}.",
            "updated_lesson_id": next_lesson.id,
            "updated_lesson_date": str(next_lesson.date)
        }
