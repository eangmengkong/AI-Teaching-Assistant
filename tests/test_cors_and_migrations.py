"""Regression tests for the CORS + startup-schema fixes.

Covered scenarios (all taken from real production incidents):

1. A route that raises must still return 500 WITH the expected CORS headers —
   otherwise browsers report "blocked by CORS" and hide the real HTTP 500.
2. Origins outside the allow-list must keep getting no CORS headers.
3. Normal (200) cross-origin requests keep their CORS headers.
4. run_schema_migrations() adds the missing documents.file_data column and is
   idempotent (BEFORE the fix, prod 500'd with "column documents.file_data
   does not exist").
"""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.testclient import TestClient

import app.main as main
from app.core.schema_migrations import run_schema_migrations

FRONTEND_ORIGIN = "https://ai-teaching-assistant-eight.vercel.app"
FOREIGN_ORIGIN = "https://evil.example.com"


def _build_test_app() -> FastAPI:
    """A minimal app using the exact same CORS + exception-handler wiring as the
    real application (same settings, same CORSMiddleware options, same
    generic_exception_handler)."""
    app = FastAPI()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=main.settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Disposition", "X-Study-Pages"],
    )
    app.exception_handler(Exception)(main.generic_exception_handler)

    @app.get("/ok")
    def ok():
        return {"ok": True}

    @app.get("/boom")
    def boom():
        raise RuntimeError("boom")

    return app


def test_cors_allowlist_contains_vercel_frontend():
    assert FRONTEND_ORIGIN in main.settings.CORS_ORIGINS
    assert "*" not in main.settings.CORS_ORIGINS  # "*" is invalid with credentials


def test_success_response_still_has_cors_headers():
    with TestClient(_build_test_app()) as client:
        res = client.get("/ok", headers={"Origin": FRONTEND_ORIGIN})
    assert res.status_code == 200
    assert res.headers.get("access-control-allow-origin") == FRONTEND_ORIGIN
    assert res.headers.get("access-control-allow-credentials") == "true"


def test_500_response_includes_cors_headers():
    # raise_server_exceptions=False mirrors production: the framework's
    # ServerErrorMiddleware (outermost, OUTSIDE the CorSMiddleware) calls the
    # catch-all handler and serves its response to the client instead of
    # re-raising it for the test runner.
    with TestClient(_build_test_app(), raise_server_exceptions=False) as client:
        res = client.get("/boom", headers={"Origin": FRONTEND_ORIGIN})
    assert res.status_code == 500
    # A 500 must still be a valid CORS response so the browser shows the real
    # error instead of a misleading "blocked by CORS" failure.
    assert res.headers.get("access-control-allow-origin") == FRONTEND_ORIGIN
    assert res.headers.get("access-control-allow-credentials") == "true"
    assert "boom" in res.json()["detail"]


def test_foreign_origin_still_gets_no_cors_headers():
    with TestClient(_build_test_app(), raise_server_exceptions=False) as client:
        res = client.get("/boom", headers={"Origin": FOREIGN_ORIGIN})
    assert res.status_code == 500
    assert "access-control-allow-origin" not in res.headers


def test_build_cors_headers_allowlist():
    assert main.build_cors_headers(FRONTEND_ORIGIN)["Access-Control-Allow-Origin"] == FRONTEND_ORIGIN
    assert main.build_cors_headers("http://localhost:3000")["Access-Control-Allow-Origin"] == "http://localhost:3000"
    assert main.build_cors_headers(FOREIGN_ORIGIN) == {}


@pytest.mark.asyncio
async def test_run_schema_migrations_adds_column_idempotently():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        # Simulate the pre-fix production database: table exists, column does not.
        await conn.execute(
            text(
                "CREATE TABLE documents (id INTEGER PRIMARY KEY, "
                "course_id INTEGER, file_path TEXT)"
            )
        )

    await run_schema_migrations(engine)

    async with engine.begin() as conn:
        cols = (await conn.execute(text("PRAGMA table_info(documents)"))).fetchall()
    assert any(row[1] == "file_data" for row in cols), "file_data column was not added"

    # Second run must be a no-op (deploys run migrations on every boot).
    await run_schema_migrations(engine)
    await engine.dispose()