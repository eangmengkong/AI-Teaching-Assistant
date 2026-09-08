"""
Source-grounded study content retrieval for the Telegram bot.

Priority for finding the ACTUAL exercise / quiz / exam content:
  1. Connected database   (Quiz / Exam / WorkbookExercise tables - real stored content)
  2. Uploaded textbook    (DocumentPage page text stored in DB; live pypdf fallback)
  3. Uploaded workbook    (DocumentPage / WorkbookExercise)
  4. Other connected sources (DocumentChunk keyword search)

Never invents content: every returned block is traced to its source page. If
nothing is found, callers reply "I couldn't find the actual ..." plus the
source location as a reference.
"""
import io
import os
import re
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    Course, Document, DocumentChunk, DocumentPage, Homework, LessonSchedule,
    Quiz, QuizQuestion, Exam, ExamQuestion, WorkbookExercise,
)
from app.services.document_service import DocumentService
from app.services.study_material_service import StudyMaterialService

# Max characters per Telegram message chunk (Telegram hard limit is 4096).
_CHUNK_SIZE = 3500



class StudyContentService:
    # ------------------------------------------------------------ lesson resolution

    @staticmethod
    async def resolve_course(db: AsyncSession, user_id: int) -> Optional[Course]:
        """First course owned by the user (matches the rest of the app)."""
        course = (
            await db.execute(
                select(Course).where(Course.user_id == user_id).order_by(Course.id).limit(1)
            )
        ).scalar_one_or_none()
        return course

    @staticmethod
    async def resolve_lesson(db: AsyncSession, course_id: int, lesson_id: Optional[int] = None) -> Optional[LessonSchedule]:
        """The requested lesson by id, else the current / next forthcoming lesson,
        else the last lesson of the course."""
        if lesson_id:
            return (
                await db.execute(select(LessonSchedule).where(LessonSchedule.id == lesson_id))
            ).scalar_one_or_none()

        lesson = (
            await db.execute(
                select(LessonSchedule)
                .where(LessonSchedule.course_id == course_id)
                .where(LessonSchedule.date >= date.today())
                .order_by(LessonSchedule.date.asc(), LessonSchedule.id.asc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if lesson:
            return lesson

        return (
            await db.execute(
                select(LessonSchedule)
                .where(LessonSchedule.course_id == course_id)
                .order_by(LessonSchedule.date.desc(), LessonSchedule.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    # ------------------------------------------------------------ page text

    @staticmethod
    async def get_document(db: AsyncSession, course_id: int, document_type: str) -> Optional[Document]:
        """Latest uploaded document of this type for the course."""
        return await StudyMaterialService.get_course_document(db, course_id, document_type)

    @staticmethod
    async def get_page_texts(db: AsyncSession, course_id: int, document_type: str, page_spec: Optional[str]) -> List[Dict[str, Any]]:
        """Fetch the ACTUAL page text for a page spec like 'Pages 1-35' or '10-20'.
        Returns [{'page': int, 'text': str}] using DocumentPage (stored at
        upload time); falls back to live pypdf extraction when DB pages are absent."""
        if not page_spec:
            return []
        doc = await StudyContentService.get_document(db, course_id, document_type)
        if not doc:
            return []

        total = doc.total_pages or 0
        try:
            pages = StudyMaterialService.parse_page_spec(page_spec, total)
        except ValueError:
            return []
        if not pages:
            return []

        page_rows = (
            await db.execute(
                select(DocumentPage.page_number, DocumentPage.clean_text, DocumentPage.content)
                .where(DocumentPage.document_id == doc.id)
                .where(DocumentPage.page_number.in_(pages))
                .order_by(DocumentPage.page_number)
            )
        ).all()
        if page_rows:
            by_page = {
                r.page_number: (r.clean_text or r.content or "")
                for r in page_rows
            }
            return [{"page": p, "text": by_page.get(p, "")} for p in pages if by_page.get(p)]

        return StudyContentService._extract_live_page_texts(doc, pages)

    @staticmethod
    def _extract_live_page_texts(doc: Document, pages: List[int]) -> List[Dict[str, Any]]:
        if not doc.file_path or not os.path.exists(doc.file_path):
            return []
        try:
            from pypdf import PdfReader
            reader = PdfReader(doc.file_path)
            out = []
            for page in pages:
                if 1 <= page <= len(reader.pages):
                    text = (reader.pages[page - 1].extract_text() or "").strip()
                    if not text:
                        # Scanned-image page: best-effort OCR when the optional
                        # pytesseract + Pillow stack is installed.
                        text = StudyContentService._ocr_page(doc, page)
                    out.append({"page": page, "text": text})
            return out
        except Exception:
            return []

    @staticmethod
    def _ocr_page(doc: Document, page_number: int) -> str:
        """OCR a scanned PDF page. Returns '' when OCR deps are unavailable
        (pytesseract + Pillow are optional; never a hard dependency)."""
        if not doc.file_path or not os.path.exists(doc.file_path):
            return ""
        try:
            import pytesseract  # noqa: F401  (optional)
            from PIL import Image
            from pypdf import PdfReader

            reader = PdfReader(doc.file_path)
            pdf_page = reader.pages[page_number - 1]
            text_out: List[str] = []
            for img in pdf_page.images:
                try:
                    pil_img = Image.open(io.BytesIO(img.data))
                    text_out.append(pytesseract.image_to_string(pil_img))
                except Exception:
                    continue
            return "\n".join(t for t in text_out if t).strip()
        except Exception:
            return ""


    # ------------------------------------------------------------ search

    @staticmethod
    async def search_content(
        db: AsyncSession, course_id: int, query: str, document_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Keyword / unit-lesson / exercise-number search across connected sources,
        ranked best first (textbook & workbook page text, then document chunks)."""
        matches: List[Dict[str, Any]] = []
        docs_stmt = select(Document).where(Document.course_id == course_id)
        if document_type:
            docs_stmt = docs_stmt.where(Document.document_type == document_type)
        docs = (await db.execute(docs_stmt)).scalars().all()

        query_lower = (query or "").lower().strip()
        for doc in docs:
            page_rows = (
                await db.execute(
                    select(DocumentPage.page_number, DocumentPage.clean_text)
                    .where(DocumentPage.document_id == doc.id)
                    .order_by(DocumentPage.page_number)
                )
            ).all()
            for row in page_rows:
                hay = (row.clean_text or "")
                if query_lower and query_lower in hay.lower():
                    matches.append({
                        "source": doc.document_type,
                        "document_name": doc.filename,
                        "page": row.page_number,
                        "text": hay[:2000],
                        "relevance": 2,
                    })

        # Structural chunk metadata search (Unit 3 / Lesson 2 / Exercise 5 ...)
        for chunk in await DocumentService.search_documents(db, course_id, query, document_type):
            if not any(m["page"] == chunk["page_number"] and m["source"] == chunk["document_type"] for m in matches):
                matches.append({
                    "source": chunk["document_type"],
                    "document_name": chunk["document_name"],
                    "page": chunk["page_number"],
                    "text": (chunk["content"] or "")[:2000],
                    "relevance": 1,
                })

        matches.sort(key=lambda m: m["relevance"], reverse=True)
        return matches[:12]

    @staticmethod
    async def get_workbook_exercises(
        db: AsyncSession, course_id: int, page_numbers: Optional[List[int]] = None
    ) -> List[WorkbookExercise]:
        """Structured exercises extracted from the workbook at upload time."""
        stmt = (
            select(WorkbookExercise)
            .where(WorkbookExercise.course_id == course_id)
            .order_by(WorkbookExercise.page_number.asc(), WorkbookExercise.id.asc())
        )
        if page_numbers:
            stmt = stmt.where(WorkbookExercise.page_number.in_(page_numbers))
        return (await db.execute(stmt)).scalars().all()

    # ------------------------------------------------------------ content formatting

    @staticmethod
    def extract_exercise_blocks(page_texts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Best-effort split of the ACTUAL page text into exercise blocks.
        Falls back to the whole page text verbatim (never invents anything).
        Unreadable pages (covers / scanned noise without OCR) are skipped so
        garbage is never presented as study content."""
        blocks: List[Dict[str, Any]] = []
        for item in page_texts:
            text = item.get("text", "")
            page = item.get("page")
            if not text.strip() or not StudyContentService._is_readable(text):
                continue
            lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
            starts = [
                i for i, ln in enumerate(lines)
                if re.search(r"(?i)^\s*(exercise|activity|task)\s*\d*[a-z]?\s*[:.)]", ln)
                or re.search(r"(?i)^\s*[1-9][0-9]?[.)]\s*\S", ln)
            ]
            if len(starts) >= 2:
                for idx, s in enumerate(starts):
                    end = starts[idx + 1] if idx + 1 < len(starts) else len(lines)
                    blocks.append({
                        "page": page,
                        "text": "\n".join(lines[s:end]).strip(),
                    })
            else:
                blocks.append({"page": page, "text": text.strip()})
        return blocks

    @staticmethod
    def _is_readable(text: str) -> bool:
        """Heuristic: does this page text contain real language content?
        Guards against cover-page noise / binary glyphs from PDF extraction."""
        cleaned = "".join(ch for ch in text if ch.isprintable())
        if len(cleaned) < 40:
            return False
        letters = sum(1 for ch in cleaned if ch.isalpha() or "\u4e00" <= ch <= "\u9fff")
        return letters / len(cleaned) >= 0.45

    # ------------------------------------------------------------ quiz / exam

    @staticmethod
    async def get_actual_quiz(db: AsyncSession, course_id: int) -> Optional[Dict[str, Any]]:
        """Latest ACTUAL quiz stored in the database (source priority #1).
        Placeholder-only AI quizzes (source_type == 'ai_generated' on every
        question) do NOT count as an actual quiz - returning them as
        'retrieved content' would be hallucination."""
        quiz = (
            await db.execute(
                select(Quiz)
                .where(Quiz.course_id == course_id)
                .where(Quiz.status != "practice")
                .order_by(Quiz.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if not quiz:
            return None
        questions = (
            await db.execute(
                select(QuizQuestion)
                .where(QuizQuestion.quiz_id == quiz.id)
                .order_by(QuizQuestion.question_number.asc())
            )
        ).scalars().all()
        real = [q for q in questions if (q.source_type or "ai_generated") != "ai_generated"]
        if not real:
            return None
        return {"quiz": quiz, "questions": real}


    @staticmethod
    async def get_actual_exam(db: AsyncSession, course_id: int) -> Optional[Dict[str, Any]]:
        """Latest ACTUAL exam stored in the database (source priority #1).
        Placeholder-only AI exams do not count (anti-hallucination rule)."""
        exam = (
            await db.execute(
                select(Exam)
                .where(Exam.course_id == course_id)
                .where(Exam.status != "practice")
                .order_by(Exam.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if not exam:
            return None
        questions = (
            await db.execute(
                select(ExamQuestion)
                .where(ExamQuestion.exam_id == exam.id)
                .order_by(ExamQuestion.question_number.asc())
            )
        ).scalars().all()
        real = [q for q in questions if (q.source_type or "ai_generated") != "ai_generated"]
        if not real:
            return None
        return {"exam": exam, "questions": real}

    # ------------------------------------------------------------ practice (AI-generated) helpers

    @staticmethod
    async def mark_quiz_practice(db: AsyncSession, quiz_id: int) -> None:
        """Tag an AI-generated practice quiz so it can never be presented
        later as an 'actual' quiz retrieved from the materials."""
        quiz = (
            await db.execute(select(Quiz).where(Quiz.id == quiz_id))
        ).scalar_one_or_none()
        if quiz:
            quiz.status = "practice"
            await db.commit()

    @staticmethod
    async def mark_exam_practice(db: AsyncSession, exam_id: int) -> None:
        """Tag an AI-generated practice exam (see mark_quiz_practice)."""
        exam = (
            await db.execute(select(Exam).where(Exam.id == exam_id))
        ).scalar_one_or_none()
        if exam:
            exam.status = "practice"
            await db.commit()

    @staticmethod
    async def format_quiz_by_id(db: AsyncSession, quiz_id: int) -> str:
        quiz = (
            await db.execute(select(Quiz).where(Quiz.id == quiz_id))
        ).scalar_one_or_none()
        if not quiz:
            return "Quiz not found."
        questions = (
            await db.execute(
                select(QuizQuestion)
                .where(QuizQuestion.quiz_id == quiz.id)
                .order_by(QuizQuestion.question_number.asc())
            )
        ).scalars().all()
        return StudyContentService.format_quiz_telegram({"quiz": quiz, "questions": questions})

    @staticmethod
    async def format_exam_by_id(db: AsyncSession, exam_id: int) -> str:
        exam = (
            await db.execute(select(Exam).where(Exam.id == exam_id))
        ).scalar_one_or_none()
        if not exam:
            return "Exam not found."
        questions = (
            await db.execute(
                select(ExamQuestion)
                .where(ExamQuestion.exam_id == exam.id)
                .order_by(ExamQuestion.question_number.asc())
            )
        ).scalars().all()
        return StudyContentService.format_exam_telegram({"exam": exam, "questions": questions})

    @staticmethod
    def format_generated_quiz_dict(res: Dict[str, Any]) -> str:
        """Format an in-memory generate_quiz() result (dict, not ORM)."""
        lines = [f"📝 {res.get('title', 'Practice Quiz')}", ""]
        units = res.get("covered_units") or []
        if units:
            lines.append("Covered: " + ", ".join(units))
            lines.append("")
        for q in res.get("questions", []):
            lines.append(f"{q.get('num')}. {q.get('q', '')}")
            for opt in q.get("options", []):
                lines.append(f"   {opt}")
            lines.append("")
        return "\n".join(lines).strip()

    @staticmethod
    def format_quiz_telegram(pack: Dict[str, Any]) -> str:
        quiz, questions = pack["quiz"], pack["questions"]
        lines = [f"📝 QUIZ: {quiz.title}", ""]
        if quiz.covered_units:
            lines.append(f"📚 Covered: {', '.join(map(str, quiz.covered_units))}")
        if quiz.quiz_date:
            lines.append(f"📅 Date: {quiz.quiz_date}")
        lines.append("")
        if not questions:
            lines.append("(No question content stored for this quiz.)")
        for q in questions:
            qtext = q.question_text or ""
            opts = q.options or []
            lines.append(f"Q{q.question_number}. {qtext}")
            for idx, opt in enumerate(opts):
                letter = "ABCDEFGH"[idx] if idx < len("ABCDEFGH") else f"{idx + 1}."
                lines.append(f"   {letter}. {opt}")
            lines.append("")
        return "\n".join(lines).strip()

    @staticmethod
    def format_exam_telegram(pack: Dict[str, Any]) -> str:
        exam, questions = pack["exam"], pack["questions"]
        lines = [f"🎓 EXAM: {exam.title}", ""]
        if exam.covered_content:
            lines.append(f"📚 Covered: {', '.join(map(str, exam.covered_content))}")
        if exam.exam_date:
            lines.append(f"📅 Date: {exam.exam_date}")
        lines.append("")
        if not questions:
            lines.append("(No question content stored for this exam.)")
        for q in questions:
            qtext = q.question_text or ""
            opts = q.options or []
            lines.append(f"Q{q.question_number}. {qtext}")
            for idx, opt in enumerate(opts):
                letter = "ABCDEFGH"[idx] if idx < len("ABCDEFGH") else f"{idx + 1}."
                lines.append(f"   {letter}. {opt}")
            lines.append("")
        return "\n".join(lines).strip()

    # ------------------------------------------------------------ telegram chunks

    @staticmethod
    def split_messages(text: str, chunk_size: int = _CHUNK_SIZE) -> List[str]:
        """Split long study content into Telegram-friendly messages, keeping
        blank lines and reasonable line grouping."""
        if len(text) <= chunk_size:
            return [text] if text.strip() else []
        parts: List[str] = []
        current = ""
        for line in text.splitlines():
            if len(current) + len(line) + 1 > chunk_size:
                if current.strip():
                    parts.append(current.rstrip())
                current = ""
                # very long single line: hard-split
                while len(line) > chunk_size:
                    parts.append(line[:chunk_size])
                    line = line[chunk_size:]
            current += line + "\n"
        if current.strip():
            parts.append(current.rstrip())
        return parts

    # ------------------------------------------------------------ lesson exercises (source-grounded)

    @staticmethod
    def _parse_pages(spec: Optional[str]) -> List[int]:
        """Extract page numbers from scheduler formats like 'Pages 1-35' or
        'Pages 1-209 (Comprehensive)' without needing a page-count clamp."""
        if not spec:
            return []
        norm = (spec or "").replace("–", "-").replace("—", "-")
        norm = re.sub(r"(?i)\bpages?\b", " ", norm)
        norm = re.sub(r"\([^)]*\)", " ", norm)
        nums: List[int] = []
        for part in norm.split(","):
            part = part.strip()
            m = re.fullmatch(r"(\d+)\s*-\s*(\d+)", part)
            if m:
                lo, hi = int(m.group(1)), int(m.group(2))
                if lo <= hi and hi - lo < 1000:
                    nums.extend(range(lo, hi + 1))
            elif part.isdigit():
                nums.append(int(part))
        return sorted(set(nums))

    @staticmethod
    async def get_lesson_exercises(
        db: AsyncSession, lesson: LessonSchedule, source: Optional[str] = None
    ) -> Dict[str, Any]:
        """Collect the ACTUAL exercises for a lesson from connected sources.
        Priority: (1) structured WorkbookExercise rows stored at upload time,
        (2) actual textbook/workbook page text (DocumentPage / pypdf / OCR),
        (3) keyword search fallback. Every block carries its source trace.
        Never invents content."""
        course_id = lesson.course_id
        refs: List[str] = []
        blocks: List[Dict[str, Any]] = []

        wb_pages = StudyContentService._parse_pages(lesson.workbook_pages)
        tb_pages = StudyContentService._parse_pages(lesson.textbook_pages)
        if lesson.textbook_pages:
            refs.append(f"📖 Textbook {lesson.textbook_pages}")
        if lesson.workbook_pages:
            refs.append(f"✏️ Workbook {lesson.workbook_pages}")

        src = (source or "").lower()
        want_tb = src in ("", "textbook", "tb")
        want_wb = src in ("", "workbook", "wb")

        # 1. Structured workbook exercises stored in the connected database
        structured = 0
        if want_wb and wb_pages:
            for w in await StudyContentService.get_workbook_exercises(db, course_id, wb_pages):
                header = f"Exercise {w.exercise_number}" + (f": {w.title}" if w.title else "")
                body = "\n".join(x for x in [header.strip(), (w.prompt or "").strip()] if x.strip())
                if not body:
                    continue
                blocks.append({
                    "page": w.page_number,
                    "source": "workbook",
                    "trace": f"✏️ Workbook p.{w.page_number}" + (f" — {w.title}" if w.title else ""),
                    "text": body,
                })
                structured += 1

        # 2. Actual textbook page text, split into exercise blocks
        if want_tb and tb_pages:
            page_texts = await StudyContentService.get_page_texts(
                db, course_id, "textbook", lesson.textbook_pages
            )
            for b in StudyContentService.extract_exercise_blocks(page_texts):
                blocks.append({
                    "page": b["page"],
                    "source": "textbook",
                    "trace": f"📖 Textbook p.{b['page']}",
                    "text": b["text"],
                })

        # 3. Actual workbook page text when no structured rows cover the lesson
        if want_wb and not structured and wb_pages:
            page_texts = await StudyContentService.get_page_texts(
                db, course_id, "workbook", lesson.workbook_pages
            )
            for b in StudyContentService.extract_exercise_blocks(page_texts):
                blocks.append({
                    "page": b["page"],
                    "source": "workbook",
                    "trace": f"✏️ Workbook p.{b['page']}",
                    "text": b["text"],
                })

        pack: Dict[str, Any] = {
            "found": bool(blocks),
            "lesson": lesson,
            "blocks": blocks,
            "refs": refs,
            "source": source,
        }
        if not blocks:
            query = f"{lesson.unit} {lesson.lesson}".strip()
            matches = await StudyContentService.search_content(db, course_id, query) if query else []
            pack["search_matches"] = matches[:3]
            pack["message"] = StudyContentService.exercise_not_found_text(lesson, refs, matches)
        return pack

    @staticmethod
    def exercise_not_found_text(
        lesson: LessonSchedule, refs: List[str], matches: List[Dict[str, Any]]
    ) -> str:
        lines = ["⚠️ I couldn't find the actual exercise in the connected materials.", ""]
        if refs:
            lines.append("📚 Source location for this lesson:")
            lines += [f"  • {r}" for r in refs]
        if matches:
            lines.append("")
            lines.append("🔎 Closest matches found in your materials:")
            for m in matches:
                icon = "📖" if m.get("source") == "textbook" else "✏️" if m.get("source") == "workbook" else "📄"
                lines.append(f"  • {icon} {m.get('document_name', '')} — p.{m.get('page')}")
            lines.append("")
            lines.append("Send /pages to open those pages as PDF.")
        lines.append("")
        lines.append("Tip: /exercise textbook or /exercise workbook searches one book only.")
        return "\n".join(lines)

    @staticmethod
    def format_exercise_telegram(
        pack: Dict[str, Any], page: int = 0, per_page: int = 3
    ) -> Tuple[str, int]:
        """Format the retrieved exercise blocks for Telegram. Returns
        (text, total_pages); blocks are paginated for the nav buttons."""
        lesson = pack["lesson"]
        blocks: List[Dict[str, Any]] = pack["blocks"]
        total_pages = max(1, (len(blocks) + per_page - 1) // per_page)
        page = max(0, min(page, total_pages - 1))
        chunk = blocks[page * per_page:(page + 1) * per_page]

        lines = [f"📚 EXERCISES — {lesson.unit} · {lesson.lesson}", f"📅 {lesson.date}", ""]
        if page == 0 and pack.get("refs"):
            lines.append(f"Source: {'  ·  '.join(pack['refs'])}")
            lines.append("")
        for i, b in enumerate(chunk, start=page * per_page + 1):
            lines.append(f"{i}. {b['trace']}")
            lines.append(b["text"])
            lines.append("")
        if total_pages > 1:
            lines.append(f"— Page {page + 1}/{total_pages} —")
        return "\n".join(lines).strip(), total_pages

    @staticmethod
    def lesson_summary_text(lesson: LessonSchedule) -> str:
        return "\n".join([
            f"📚 LESSON — {lesson.unit} · {lesson.lesson}",
            f"📅 {lesson.date}  ⏰ {lesson.start_time}-{lesson.end_time}",
            f"📖 Textbook: {lesson.textbook_pages or '—'}",
            f"✏️ Workbook: {lesson.workbook_pages or '—'}",
            f"Status: {lesson.status}",
            "",
            "Commands: /exercise · /quiz · /exam · /pages",
        ])

    @staticmethod
    def lesson_plan_text(lesson: LessonSchedule) -> str:
        """Full lesson-plan card used by /lesson (everything stored, verbatim)."""
        lines = [
            f"📚 LESSON PLAN — {lesson.unit} · {lesson.lesson}",
            f"📅 {lesson.date}  ⏰ {lesson.start_time}-{lesson.end_time}  (week {lesson.week_number})",
            f"📖 Textbook: {lesson.textbook_pages or '—'}   ✏️ Workbook: {lesson.workbook_pages or '—'}",
            f"Status: {lesson.status}",
        ]
        if lesson.objectives:
            lines += ["", "🎯 Objectives:", str(lesson.objectives)]
        acts = lesson.activities if isinstance(lesson.activities, list) else None
        if acts:
            lines += ["", "🗂 Activities:"]
            lines += [f"  {i}. {a}" for i, a in enumerate(acts, 1)]
        elif lesson.activities:
            lines += ["", "🗂 Activities:", str(lesson.activities)]
        if lesson.exercises:
            ex = lesson.exercises if isinstance(lesson.exercises, list) else [lesson.exercises]
            lines += ["", "📝 Exercises:"]
            lines += [f"  {i}. {a}" for i, a in enumerate(ex, 1)]
        if lesson.homework:
            lines += ["", "🏠 Homework:", str(lesson.homework)]
        if lesson.assessment:
            lines += ["", "🎓 Assessment:", str(lesson.assessment)]
        lines += ["", "Commands: /exercise · /quiz · /exam · /pages · /complete"]
        return "\n".join(lines)

    @staticmethod
    async def get_course_setup_text(db: AsyncSession, course_id: int) -> str:
        """Formatted materials summary for /setup (real data from the DB)."""
        docs = (
            await db.execute(
                select(Document).where(Document.course_id == course_id).order_by(Document.id)
            )
        ).scalars().all()
        lesson_count = len((
            await db.execute(
                select(LessonSchedule).where(LessonSchedule.course_id == course_id)
            )
        ).scalars().all())
        next_lesson = (
            await db.execute(
                select(LessonSchedule)
                .where(LessonSchedule.course_id == course_id, LessonSchedule.date >= date.today())
                .order_by(LessonSchedule.date.asc())
                .limit(1)
            )
        ).scalars().first()

        lines = ["⚙️ COURSE & MATERIALS SETUP", ""]
        lines.append(f"📚 Scheduled lessons: {lesson_count}")
        if next_lesson:
            lines.append(f"➡️ Next lesson: {next_lesson.date} — {next_lesson.unit} · {next_lesson.lesson}")
        lines.append("")
        if docs:
            lines.append("📄 Connected materials:")
            for d in docs:
                kind = {"textbook": "📖 Textbook", "workbook": "✏️ Workbook"}.get(d.document_type, "📄 " + str(d.document_type))
                lines.append(f"  • {kind}: {d.file_name}")
        else:
            lines.append("📄 No materials uploaded yet — upload a textbook/workbook PDF in the dashboard.")
        lines += [
            "",
            "Next steps:",
            "• Generate/refresh the plan: click ✨ in the dashboard",
            "• /exercise /quiz /exam — actual content from these materials",
            "• /pages — today's pages as PDF",
            "• /progress — completion status",
        ]
        return "\n".join(lines)

    @staticmethod
    async def generate_grounded_review(
        db: AsyncSession, course_id: int, unit: str
    ) -> Tuple[Optional[str], str]:
        """Review session built ONLY from the unit's actual page text.
        Returns (review_text, info). review_text is None when the unit is
        unknown or no readable source text exists (scanned book)."""
        lessons = (
            await db.execute(
                select(LessonSchedule)
                .where(LessonSchedule.course_id == course_id)
                .order_by(LessonSchedule.date.asc())
            )
        ).scalars().all()
        target = [l for l in lessons if unit.lower() in (l.unit or "").lower()]
        if not target:
            available = sorted({(l.unit or "") for l in lessons if l.unit})
            return None, (
                f"Unit not found. Available units: {', '.join(available) if available else '—'}."
            )

        pages: List[int] = []
        specs: List[str] = []
        for l in target:
            for spec, icon in ((l.textbook_pages, "📖"), (l.workbook_pages, "✏️")):
                nums = StudyContentService._parse_pages(spec)
                if nums:
                    pages.extend(nums)
                    specs.append(f"{icon} {spec}")
        pages = sorted(set(pages))[:40]  # keep the prompt bounded

        spec_str = ",".join(str(p) for p in pages)
        tb = await StudyContentService.get_page_texts(db, course_id, "textbook", spec_str)
        wb = await StudyContentService.get_page_texts(db, course_id, "workbook", spec_str)
        corpus_parts = [f"[Textbook p.{d['page']}]\n{d.get('text','')}" for d in tb]
        corpus_parts += [f"[Workbook p.{d['page']}]\n{d.get('text','')}" for d in wb]
        corpus_parts = [p for p in corpus_parts if StudyContentService._is_readable(p)]
        if not corpus_parts:
            return None, (
                "The pages for this unit are scanned images without extractable text, "
                "so I can't quote them inline. Send /pages to read the actual pages."
            )
        corpus = "\n\n".join(corpus_parts)[:12000]

        try:
            from app.core.ai_providers import chat_with_fallback
            prompt = (
                "You are a strict tutor. Create a review session for the unit below using "
                "ONLY the provided source pages. Copy real words, sentences and exercises "
                "from the source verbatim; never invent content. Cite each item as (p.X).\n\n"
                f"UNIT: {unit}\n\nSOURCE PAGES:\n{corpus}\n\n"
                "Format: '📖 REVIEW — <unit>' then sections: 1) Key vocabulary (from pages, "
                "with page cites) 2) Grammar/structures found in the pages 3) 5 practice items "
                "copied or adapted strictly from the pages (each with p.X) 4) Answers."
            )
            reply, provider_name = await chat_with_fallback(
                [{"role": "user", "content": prompt}]
            )
            text_out = ""
            try:
                text_out = (reply.choices[0].message.content or "") if reply else ""
            except Exception:
                text_out = ""
            if not text_out.strip():
                return None, "The AI chain is unavailable right now. Please retry later."
            header = (
                "📖 REVIEW (source-grounded)\n"
                f"Sources: {' · '.join(sorted(set(specs)))}\n\n"
            )
            return header + text_out.strip() + f"\n\n_ via {provider_name}_", "ok"
        except Exception as e:
            return None, f"AI chain error: {e}"

    @staticmethod
    def not_found_quiz_text(lesson: Optional[LessonSchedule]) -> str:
        lines = ["⚠️ I couldn't find an actual quiz in the connected materials.", ""]
        if lesson:
            lines.append(
                f"📚 This lesson's actual content: 📖 {lesson.textbook_pages or '—'} · "
                f"✏️ {lesson.workbook_pages or '—'}"
            )
            lines.append("Send /pages to study the source pages, or /exercise to see the real exercises.")
            lines.append("")
        lines.append(
            "Reply /quiz gen and I'll generate an AI practice quiz from this "
            "lesson's actual pages (clearly labeled as AI-generated)."
        )
        return "\n".join(lines)

    @staticmethod
    def not_found_exam_text(lesson: Optional[LessonSchedule]) -> str:
        lines = ["⚠️ I couldn't find an actual exam in the connected materials.", ""]
        if lesson:
            lines.append(
                f"📚 Covered content so far: 📖 {lesson.textbook_pages or '—'} · "
                f"✏️ {lesson.workbook_pages or '—'}"
            )
            lines.append("")
        lines.append(
            "Reply /exam gen and I'll generate an AI practice exam from your "
            "completed lessons' actual pages (clearly labeled as AI-generated)."
        )
        return "\n".join(lines)

    # ------------------------------------------------------------ command formatters (direct bot handlers)

    @staticmethod
    def format_lesson_brief(res: Dict[str, Any], label: str) -> str:
        if res.get("status") != "success":
            return f"📅 {label}: {res.get('message', 'No lesson found.')}"
        l = res["lesson"]
        lines = [
            f"📅 {label} — {l['unit']} · {l['lesson']}",
            f"🗓 {l['date']}  ⏰ {l['time']}",
            f"📖 Textbook: {l.get('textbook_pages') or '—'}",
            f"✏️ Workbook: {l.get('workbook_pages') or '—'}",
        ]
        if l.get("objectives"):
            lines.append(f"🎯 {l['objectives']}")
        lines.append(f"Status: {l.get('status', 'planned')}")
        lines.append("")
        lines.append("Commands: /lesson · /exercise · /pages · /complete")
        return "\n".join(lines)

    @staticmethod
    def format_lesson_plan_text(res: Dict[str, Any]) -> str:
        if res.get("status") != "success":
            return res.get("message", "Lesson plan not found.")
        p = res["lesson_plan"]
        lines = [
            f"📚 LESSON PLAN — {p['unit']} · {p['lesson']}",
            f"🗓 {p['date']}  ⏰ {p['time']}",
            f"📖 {p.get('textbook_content', '')}",
            f"✏️ {p.get('workbook_content', '')}",
        ]
        if p.get("objectives"):
            lines.append(f"🎯 Objectives: {p['objectives']}")
        acts = p.get("activities")
        if acts:
            lines.append("🧩 Activities:")
            lines += [f"  • {a}" for a in acts]
        if p.get("exercises"):
            lines.append(f"📝 Exercises: {p['exercises']}")
        if p.get("homework"):
            lines.append(f"🏠 Homework: {p['homework']}")
        if p.get("assessment"):
            lines.append(f"🎓 Assessment: {p['assessment']}")
        lines.append("")
        lines.append("Commands: /exercise · /pages · /quiz · /exam · /complete")
        return "\n".join(lines)

    @staticmethod
    def format_week_text(res: Dict[str, Any]) -> str:
        if res.get("status") != "success":
            return res.get("message", "No schedule found.")
        lines = [f"🗓 WEEK  {res.get('week_range', '')}"]
        for item in res.get("schedule", []):
            icon = {"completed": "✅", "skipped": "⏭️"}.get(item["status"], "•")
            lines.append(
                f"{icon} {item['day']} {item['date']} {item['time']} — {item['unit']} · {item['lesson']}"
            )
        if not res.get("schedule"):
            lines.append("(no lessons this week)")
        prog = res.get("progress_summary") or {}
        if prog:
            lines += [
                "",
                f"📈 Progress: {prog.get('completed_lessons', 0)}/{prog.get('total_lessons', 0)} lessons "
                f"· 📖 {prog.get('textbook_progress', '0%')} · ✏️ {prog.get('workbook_progress', '0%')}",
            ]
        return "\n".join(lines)

    @staticmethod
    def format_progress_text(res: Dict[str, Any]) -> str:
        if res.get("status") != "success":
            return res.get("message", "No progress data.")
        skipped = res.get("skipped_lessons", 0)
        return "\n".join([
            "📈 COURSE PROGRESS",
            f"✅ Lessons completed: {res.get('completed_lessons', 0)}/{res.get('total_lessons', 0)}"
            + (f"  (⏭️ {skipped} skipped)" if skipped else ""),
            f"📖 Textbook: {res.get('textbook_progress', '0%')}",
            f"✏️ Workbook: {res.get('workbook_progress', '0%')}",
            f"📝 Avg quiz score: {res.get('average_quiz_score', '—')}",
            f"🎓 Avg exam score: {res.get('average_exam_score', '—')}",
            f"Status: {res.get('status_summary', '—')}",
        ])

    @staticmethod
    async def get_homework_text(db: AsyncSession, course_id: int) -> str:
        """Actual homework stored in the connected database for today's lesson
        (or course-wide). Lists real rows only - never invents homework."""
        today_res = await CentralAgentTools.get_today_lesson(db, course_id)
        if today_res.get("status") != "success":
            return "No lesson found in your schedule — no homework to show."
        lesson_id = today_res["lesson"]["id"]
        rows = (
            await db.execute(
                select(Homework)
                .where(Homework.course_id == course_id)
                .where(
                    or_(
                        Homework.lesson_schedule_id == lesson_id,
                        Homework.lesson_schedule_id.is_(None),
                    )
                )
                .order_by(Homework.id.desc())
                .limit(10)
            )
        ).scalars().all()
        if not rows:
            l = today_res["lesson"]
            return (
                "⚠️ No homework recorded yet in the database for this lesson.\n\n"
                f"📚 Lesson content: 📖 {l.get('textbook_pages') or '—'} · "
                f"✏️ {l.get('workbook_pages') or '—'}\n"
                "The lesson plan itself lists assigned homework — send /lesson to see it."
            )
        lines = ["🏠 HOMEWORK"]
        for h in rows:
            lines.append("")
            lines.append(f"• {h.title}")
            if h.textbook_hw:
                lines.append(f"  📖 {h.textbook_hw}")
            if h.workbook_hw:
                lines.append(f"  ✏️ {h.workbook_hw}")
            if h.due_date:
                lines.append(f"  ⏳ Due: {h.due_date}")
        return "\n".join(lines)

    # ------------------------------------------------------------ telegram nav keyboard

    @staticmethod
    def nav_keyboard(
        kind: str, lesson_id: int, source: str, page: int, total_pages: int
    ) -> Dict[str, Any]:
        """Inline keyboard: ⬅️ Previous / Next ➡️ paging, 🏠 Back to Lesson,
        📚 cross-links. callback_data format: '<kind>|<lesson_id>|<source>|<page>'."""
        rows: List[List[Dict[str, str]]] = []
        nav: List[Dict[str, str]] = []
        if page > 0:
            nav.append({"text": "⬅️ Previous", "callback_data": f"{kind}|{lesson_id}|{source}|{page - 1}"})
        if page < total_pages - 1:
            nav.append({"text": "Next ➡️", "callback_data": f"{kind}|{lesson_id}|{source}|{page + 1}"})
        if nav:
            rows.append(nav)
        rows.append([
            {"text": "🏠 Back to Lesson", "callback_data": f"lesson|{lesson_id}||0"},
            {"text": "📚 Back to Exercises", "callback_data": f"ex|{lesson_id}||0"},
        ])
        rows.append([
            {"text": "📝 Quiz", "callback_data": f"qz|{lesson_id}||0"},
            {"text": "🎓 Exam", "callback_data": f"exm|{lesson_id}||0"},
        ])
        return {"inline_keyboard": rows}

