"""
Study material service: turn "Textbook pages 10-20" into real PDFs.

- Parses page specs like "10-20", "10,12,15", "10-20, 25" (en dash supported).
- Extracts those pages from the uploaded textbook/workbook PDF (pypdf) into a
  smaller "study PDF" that keeps a bookmark per original page number.
- Delivers study PDFs to Telegram (sendDocument) so the teacher can read or
  study the exact material for lessons, quizzes and exams on the phone.
"""
import io
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.models import Course, Document, LessonSchedule

try:
    from pypdf import PdfReader, PdfWriter
except ImportError:  # pragma: no cover
    PdfReader = None
    PdfWriter = None


class StudyMaterialService:
    # ------------------------------------------------------------- page specs

    @staticmethod
    def parse_page_spec(spec: str, total_pages: int) -> List[int]:
        """Parse '10-20', '10,12,15' or '10-20, 25' (en dash supported) into a
        sorted, unique 1-based page list clamped to [1, total_pages].

        Tolerates the formats the scheduler stores, e.g. 'Pages 1-35' and
        'Pages 1-209 (Comprehensive)' (the Pages prefix and any trailing
        parenthetical are stripped)."""
        if PdfReader is None:
            raise ValueError("pypdf is not installed on the server.")
        spec = (spec or "").strip()
        if not spec:
            raise ValueError("No pages specified.")
        # Normalize scheduler-style strings anywhere in the spec:
        # "Pages 1-35", "Page 3", "Pages 1-209 (Comprehensive)" and compound
        # specs like "Pages 1-35, Pages 36-70" (repeated prefix per part).
        spec = re.sub(r"[\(\[][^\)\]]*[\)\]]", " ", spec)      # drop "(Comprehensive)" etc.
        spec = re.sub(r"(?i)\bpages?\b", " ", spec)             # strip every Pages/Page token
        spec = re.sub(r"(?i)\band\b|&|;", ",", spec)            # treat and/&/; as separators
        spec = spec.replace("\u2013", "-").replace("\u2014", "-")  # en/em dash -> hyphen
        if not spec.strip():
            raise ValueError("No pages specified.")
        pages: set = set()
        for part in re.split(r"[,\s]+", spec):
            if not part:
                continue
            m = re.fullmatch(r"(\d+)(?:\s*-\s*(\d+))?", part)
            if not m:
                raise ValueError(f"Invalid page range part: '{part}' (use e.g. '10-20' or '10,12,15').")
            start, end = int(m.group(1)), int(m.group(2) or m.group(1))
            if start > end:
                start, end = end, start
            for p in range(start, end + 1):
                if 1 <= p <= total_pages:
                    pages.add(p)
        if not pages:
            raise ValueError(f"No valid pages in '{spec}' (the document has {total_pages} pages).")
        return sorted(pages)

    # ------------------------------------------------------------ PDF building

    @staticmethod
    def extract_pages_pdf(source_path: str, pages: List[int]) -> bytes:
        """Build a new PDF containing only `pages` (1-based), with a bookmark
        per original page number so navigation is easy while studying."""
        if PdfReader is None or PdfWriter is None:
            raise ValueError("pypdf is not installed on the server.")
        try:
            reader = PdfReader(source_path)
        except Exception as e:  # corrupted / encrypted file
            raise ValueError(f"Could not read the PDF file: {e}")
        writer = PdfWriter()
        for index, page_number in enumerate(pages):
            writer.add_page(reader.pages[page_number - 1])
            try:
                writer.add_outline_item(f"Page {page_number}", index)
            except Exception:  # bookmarks are a nice-to-have
                pass
        buffer = io.BytesIO()
        writer.write(buffer)
        return buffer.getvalue()

    @staticmethod
    def _pdf_filename(course_name: str, document_type: str, pages: List[int]) -> str:
        slug = re.sub(r"[^A-Za-z0-9]+", "_", course_name or "").strip("_")[:40] or "course"
        spec = f"{pages[0]}" if len(pages) == 1 else f"{pages[0]}-{pages[-1]}"
        return f"{slug}_{document_type.capitalize()}_p{spec}.pdf"

    @staticmethod
    def _is_pdf_file(doc: Document) -> bool:
        if doc.file_path and doc.file_path.lower().endswith(".pdf"):
            return True
        return bool(doc.mime_type and "pdf" in doc.mime_type.lower())

    # ------------------------------------------------------ document resolution

    @staticmethod
    async def get_course_document(db: AsyncSession, course_id: int, document_type: str) -> Optional[Document]:
        stmt = (
            select(Document)
            .where(Document.course_id == course_id, Document.document_type == document_type)
            .order_by(Document.id.desc())
        )
        res = await db.execute(stmt)
        return res.scalars().first()

    @staticmethod
    async def build_document_pages_pdf(
        db: AsyncSession, course_id: int, document_type: str, page_spec: str
    ) -> Tuple[bytes, str, str]:
        """Resolve the uploaded document, parse the spec and extract the pages.
        Returns (pdf_bytes, filename, pages_info).
        Raises LookupError (missing document/file) or ValueError (bad input)."""
        doc = await StudyMaterialService.get_course_document(db, course_id, document_type)
        if not doc:
            raise LookupError(
                f"No {document_type} uploaded for course {course_id}. Upload it in the Documents section first."
            )
        if not doc.file_path or not os.path.exists(doc.file_path):
            raise LookupError(f"The {document_type} file is missing on disk ({doc.file_path}).")
        if not StudyMaterialService._is_pdf_file(doc):
            raise ValueError(
                f"Page extraction works on PDF files only, but the uploaded {document_type} is "
                f"'{doc.filename}'. Re-upload it as a PDF."
            )

        course = (await db.execute(select(Course).where(Course.id == course_id))).scalar_one_or_none()
        course_name = course.name if course else f"course{course_id}"

        total = doc.total_pages or 0
        if not total:
            try:
                total = len(PdfReader(doc.file_path).pages)
            except Exception:
                total = 0

        pages = StudyMaterialService.parse_page_spec(page_spec, total)
        pdf_bytes = StudyMaterialService.extract_pages_pdf(doc.file_path, pages)
        info = f"pages={','.join(map(str, pages))};total={total}"
        filename = StudyMaterialService._pdf_filename(course_name, document_type, pages)
        return pdf_bytes, filename, info

    # ---------------------------------------------------------- lesson bundles

    @staticmethod
    async def prepare_lesson_pdfs(
        db: AsyncSession, lesson_id: int, include: str = "textbook,workbook"
    ) -> Dict[str, Any]:
        """Build the study PDFs for one lesson (textbook and/or workbook pages).
        Returns {"prepared": [...], "skipped": [...], "lesson": {...}}."""
        lesson = (
            await db.execute(select(LessonSchedule).where(LessonSchedule.id == lesson_id))
        ).scalar_one_or_none()
        if not lesson:
            raise LookupError(f"Lesson {lesson_id} not found.")

        course = (
            await db.execute(select(Course).where(Course.id == lesson.course_id))
        ).scalar_one_or_none()
        course_name = course.name if course else f"course{lesson.course_id}"

        kinds = [
            k.strip().lower()
            for k in (include or "").split(",")
            if k.strip().lower() in ("textbook", "workbook")
        ] or ["textbook", "workbook"]

        prepared: List[Dict[str, Any]] = []
        skipped: List[Dict[str, str]] = []
        for kind in kinds:
            spec = lesson.textbook_pages if kind == "textbook" else lesson.workbook_pages
            if not spec:
                skipped.append({"kind": kind, "reason": f"No {kind} pages set for this lesson."})
                continue
            doc = await StudyMaterialService.get_course_document(db, lesson.course_id, kind)
            if not doc:
                skipped.append({"kind": kind, "reason": f"No {kind} uploaded for this course yet."})
                continue
            if not doc.file_path or not os.path.exists(doc.file_path):
                skipped.append({"kind": kind, "reason": f"The {kind} file is missing on disk."})
                continue
            if not StudyMaterialService._is_pdf_file(doc):
                skipped.append(
                    {"kind": kind, "reason": f"{kind.capitalize()} is not a PDF ('{doc.filename}')."}
                )
                continue
            total = doc.total_pages or 0
            if not total:
                try:
                    total = len(PdfReader(doc.file_path).pages)
                except Exception:
                    total = 0
            try:
                pages = StudyMaterialService.parse_page_spec(spec, total)
            except ValueError as e:
                skipped.append({"kind": kind, "reason": str(e)})
                continue

            prepared.append(
                {
                    "kind": kind,
                    "pages": pages,
                    "filename": StudyMaterialService._pdf_filename(course_name, kind, pages),
                    "caption": (
                        f"{'📖' if kind == 'textbook' else '✏️'} {course_name} — "
                        f"{kind.capitalize()} pages {spec}\n"
                        f"{lesson.unit} – {lesson.lesson} ({lesson.date.isoformat()})"
                    ),
                    "pdf": StudyMaterialService.extract_pages_pdf(doc.file_path, pages),
                }
            )

        return {
            "prepared": prepared,
            "skipped": skipped,
            "lesson": {"id": lesson.id, "unit": lesson.unit, "lesson": lesson.lesson},
        }

    # -------------------------------------------------------- telegram delivery

    @staticmethod
    async def send_study_pdf(chat_id: str, filename: str, pdf: bytes, caption: str = "") -> bool:
        """Send one PDF document to a Telegram chat via sendDocument."""
        token = settings.TELEGRAM_BOT_TOKEN
        if not chat_id:
            return False
        if not token:
            print(f"[Simulation Mode] Chat: {chat_id} | would send PDF '{filename}' ({len(pdf)} bytes) | Caption: {caption}")
            return True
        url = f"https://api.telegram.org/bot{token}/sendDocument"
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    url,
                    data={"chat_id": chat_id, "caption": caption[:1000]},
                    files={"document": (filename, pdf, "application/pdf")},
                )
                if resp.status_code != 200:
                    print(f"[Telegram sendDocument] {resp.status_code}: {resp.text[:200]}")
                return resp.status_code == 200
        except Exception as e:
            print(f"[Telegram sendDocument error] {e}")
            return False

    @staticmethod
    async def deliver_lesson_pdfs(
        db: AsyncSession, lesson_id: int, chat_id: str, include: str = "textbook,workbook"
    ) -> Dict[str, Any]:
        """Prepare the lesson study PDFs and send each one to `chat_id`."""
        pack = await StudyMaterialService.prepare_lesson_pdfs(db, lesson_id, include)
        sent: List[Dict[str, Any]] = []
        for item in pack["prepared"]:
            ok = await StudyMaterialService.send_study_pdf(chat_id, item["filename"], item["pdf"], item["caption"])
            if ok:
                sent.append({"kind": item["kind"], "filename": item["filename"], "pages": item["pages"]})
            else:
                pack["skipped"].append(
                    {"kind": item["kind"], "reason": "Telegram delivery failed (check the bot token / chat)."}
                )
        return {
            "status": "success" if sent else "nothing_sent",
            "lesson_id": lesson_id,
            "sent": sent,
            "skipped": pack["skipped"],
            "sent_count": len(sent),
        }