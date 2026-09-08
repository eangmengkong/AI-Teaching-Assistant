"""
Verification for the study-material feature.

Run:  backend\\venv\\Scripts\\python.exe scripts\\verify_study_material.py

1) Offline: page-spec parsing (clamping, en dash, lists, invalid input) and
   PDF extraction on a generated 5-page temp file.
2) Live (read-only): if a real textbook PDF exists in the database, smoke-test
   GET /api/v1/documents/{course_id}/pages through FastAPI's TestClient.
"""
import io
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
os.chdir(BASE)

from pypdf import PdfReader, PdfWriter  # noqa: E402

from app.services.study_material_service import StudyMaterialService as S  # noqa: E402

TMP = os.path.join("uploads", "_verify_tmp.pdf")


def test_parsing():
    assert S.parse_page_spec("10-20", 15) == list(range(10, 16)), "clamping failed"
    assert S.parse_page_spec("10,12,5", 20) == [5, 10, 12], "list parsing failed"
    assert S.parse_page_spec("10\u201312", 20) == [10, 11, 12], "en dash failed"
    assert S.parse_page_spec("3", 20) == [3]
    # Scheduler-style stored values now tolerated
    assert S.parse_page_spec("Pages 1\u201335", 209) == list(range(1, 36)), "Pages prefix failed"
    assert S.parse_page_spec("Pages 1\u2013209 (Comprehensive)", 209) == list(range(1, 210)), "Pages + suffix failed"
    assert S.parse_page_spec("Page 3", 20) == [3], "Page (singular) prefix failed"
    for bad in ["abc", "500-600", ""]:
        try:
            S.parse_page_spec(bad, 100)
            raise AssertionError(f"expected ValueError for {bad!r}")
        except ValueError:
            pass
    print("PASS  page-spec parsing (clamping / en dash / lists / invalid / scheduler formats)")


def test_extraction():
    os.makedirs("uploads", exist_ok=True)
    w = PdfWriter()
    for _ in range(5):
        w.add_blank_page(width=612, height=792)
    with open(TMP, "wb") as f:
        w.write(f)
    pdf = S.extract_pages_pdf(TMP, [2, 4])
    assert pdf[:5] == b"%PDF-", "output is not a PDF"
    r = PdfReader(io.BytesIO(pdf))
    assert len(r.pages) == 2, f"expected 2 pages, got {len(r.pages)}"
    os.remove(TMP)
    print("PASS  page extraction (pages 2 & 4 of 5 -> valid 2-page PDF)")


def test_live():
    """Smoke-test the endpoint via TestClient. Everything runs inside
    TestClient's own event loop (context manager) so pooled DB connections
    stay on one loop; the background telegram/reminder worker is patched out
    to keep the test read-only."""
    import app.main as main_module
    from fastapi.testclient import TestClient

    async def _noop_worker():
        return None

    main_module.start_background_worker = _noop_worker

    with TestClient(main_module.app) as client:
        docs = client.get("/api/v1/documents/1").json()
        print(f"documents for course 1: {len(docs)}")
        target = next(
            (d for d in docs
             if d.get("document_type") == "textbook"
             and str(d.get("filename", "")).lower().endswith(".pdf")),
            None,
        )
        if not target:
            print("SKIP  live endpoint test (no textbook PDF uploaded for course 1)")
            return
        print(f"  - textbook: {target['filename']} pages={target.get('total_pages')}")

        r = client.get(
            "/api/v1/documents/1/pages",
            params={"document_type": "textbook", "page_spec": "1-2"},
        )
        print(f"GET /documents/1/pages?page_spec=1-2 -> {r.status_code} "
              f"({r.headers.get('content-type')}, {len(r.content)} bytes)")
        assert r.status_code == 200 and r.content[:5] == b"%PDF-", r.text[:200]

        r2 = client.get(
            "/api/v1/documents/1/pages",
            params={"document_type": "textbook", "page_spec": "zz"},
        )
        print(f"GET with invalid page_spec -> {r2.status_code} (expected 400)")
        assert r2.status_code == 400

    print("PASS  live endpoint smoke test (read-only)")


def main():
    test_parsing()
    test_extraction()
    test_live()
    print("\nAll study-material checks passed")


if __name__ == "__main__":
    main()