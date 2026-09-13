"""OCR fallback for scanned/image-only PDFs.

Why
---
pypdf extracts **0 characters** from image-only pages (most Khmer/Chinese
textbooks are scans), so the whole teaching pipeline has nothing to read.
When a PDF is detected as textless and an AI vision provider is configured
(Gemini vision via the existing OpenAI-compatible provider chain), each page
is rendered to a PNG (pymupdf) and transcribed by the AI.

Design notes
------------
- Runs synchronously: callers already execute extraction in a worker thread
  (``asyncio.to_thread`` in ``document_service``), so the event loop is free.
- Per-page fault isolation: a page that fails (provider down, rate limit on
  every provider in the chain) yields "" instead of killing the document.
- Pacing: ``OCR_REQUEST_INTERVAL`` seconds between requests keeps us inside
  free-tier rate limits (the provider chain also cools down on 429s).
- Nothing is cached server-side beyond the DB pages; each vision request is
  paid for exactly once per page per parse.
"""
import base64
import logging
import time
from typing import List, Optional

from app.core.config import settings

logger = logging.getLogger("ocr_service")

try:
    import fitz  # pymupdf
except ImportError:  # pragma: no cover - optional dependency
    fitz = None

try:
    import openai as _openai
except ImportError:  # pragma: no cover
    _openai = None

from app.core.ai_providers import get_provider_chain, AIProvider

_TRANSCRIBE_PROMPT = (
    "You are an OCR engine. Transcribe ALL text visible on this scanned "
    "textbook page exactly as written (the text may be Khmer, Chinese, "
    "English or a mix). Output ONLY the transcription in natural reading "
    "order, preserving line breaks. No commentary, no markdown. If the page "
    "is blank or contains no text, output an empty string."
)


def ocr_enabled() -> bool:
    """True when OCR may run (setting on + pymupdf + openai + a provider)."""
    if not settings.OCR_ENABLED:
        return False
    if fitz is None or _openai is None:
        return False
    try:
        chain = get_provider_chain()
    except Exception:
        return False
    return bool(chain)


def needs_ocr(pages: List[str]) -> bool:
    """True when extracted pages are effectively textless (scanned images)."""
    if not pages:
        return False
    threshold = settings.OCR_MIN_CHARS_PER_PAGE * len(pages)
    return sum(len((p or "").strip()) for p in pages) < threshold


def parse_timeout_seconds() -> int:
    """Extraction timeout that grows to fit the OCR budget (or 10 min)."""
    base = 600  # 10 minutes, the pre-OCR cap
    if not ocr_enabled():
        return base
    budget = int(settings.OCR_MAX_PAGES * (settings.OCR_REQUEST_INTERVAL + 10))
    return base + budget + 300


def _transcribe_png(png: bytes, provider: AIProvider, timeout: float = 120.0) -> str:
    """One vision request: transcribe a page PNG through ``provider``."""
    client = _openai.OpenAI(
        api_key=provider.api_key,
        base_url=provider.base_url or None,
        timeout=timeout,
    )
    data_url = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
    resp = client.chat.completions.create(
        model=provider.model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": _TRANSCRIBE_PROMPT},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
        max_tokens=4000,
        temperature=0.0,
    )
    return (resp.choices[0].message.content or "").strip()


def ocr_pdf(pdf_bytes: bytes, max_pages: Optional[int] = None) -> List[str]:
    """Render every page of ``pdf_bytes`` and transcribe it. Returns per-page text.

    Bounded by ``OCR_MAX_PAGES`` (or explicit ``max_pages``); pages past the
    cap come back as "" so document structure still matches the real PDF.
    """
    if fitz is None:
        raise RuntimeError("pymupdf is not installed; run pip install -r requirements.txt")
    chain = get_provider_chain()
    if not chain:
        raise RuntimeError("OCR enabled but no AI provider is configured.")

    cap = int(max_pages if max_pages is not None else settings.OCR_MAX_PAGES)
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    zoom = settings.OCR_IMAGE_DPI / 72.0
    matrix = fitz.Matrix(zoom, zoom)
    pages: List[str] = []

    try:
        for index in range(doc.page_count):
            if index >= cap:
                pages.append("")
                continue
            png = doc[index].get_pixmap(matrix=matrix).tobytes("png")
            text = ""
            for provider in chain:
                try:
                    text = _transcribe_png(png, provider)
                    break
                except Exception as exc:
                    logger.warning(
                        "OCR page %d failed via %s: %s", index + 1, provider.name, exc
                    )
            pages.append(text)
            # Pace between *requests* (not after the very last one).
            if index < min(doc.page_count, cap) - 1:
                time.sleep(settings.OCR_REQUEST_INTERVAL)
    finally:
        doc.close()

    logger.info("OCR finished: %d pages transcribed", len(pages))
    return pages
