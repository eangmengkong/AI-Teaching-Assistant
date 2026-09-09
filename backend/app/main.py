import asyncio
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager

from app.core.config import settings
from app.core.database import engine, Base
from app.core.schema_migrations import run_schema_migrations
from app.api.v1 import (
    auth, courses, documents, schedule, lessons, calendar, quizzes, exams, progress, telegram
)
from app.worker import start_background_worker

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # create_all only creates missing tables - it never adds columns that were
    # introduced after the database was first created. Sync those here so the
    # docs/upload endpoints do not fail with "column X does not exist" in prod.
    await run_schema_migrations(engine)

    worker_task = asyncio.create_task(start_background_worker())

    yield

    worker_task.cancel()

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "X-Study-Pages"],
)


def build_cors_headers(origin: str) -> dict:
    """CORS headers to echo for ``origin`` (empty when the origin is not allowed).

    Starlette's CORSMiddleware normally adds these, but responses produced by
    the catch-all exception handler below can escape the middleware before its
    header-writing wrapper runs (the exception is re-raised out of the CORS
    middleware into Starlette's outer ServerErrorMiddleware). Without them an
    unexpected 5xx would reach browsers as a confusing "blocked by CORS" error
    instead of the real HTTP 500 status and body.
    """
    if origin and origin in settings.CORS_ORIGINS:
        return {
            "Access-Control-Allow-Origin": origin,
            "Vary": "Origin",
            "Access-Control-Allow-Credentials": "true",
        }
    return {}


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    import traceback
    tb = traceback.format_exc()
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {str(exc)}", "traceback": tb},
        headers=build_cors_headers(request.headers.get("origin", "")),
    )

app.include_router(auth.router, prefix=f"{settings.API_V1_STR}/auth", tags=["auth"])
app.include_router(courses.router, prefix=f"{settings.API_V1_STR}/courses", tags=["courses"])
app.include_router(documents.router, prefix=f"{settings.API_V1_STR}/documents", tags=["documents"])
app.include_router(schedule.router, prefix=f"{settings.API_V1_STR}/schedule", tags=["schedule"])
app.include_router(lessons.router, prefix=f"{settings.API_V1_STR}/lessons", tags=["lessons"])
app.include_router(calendar.router, prefix=f"{settings.API_V1_STR}/calendar", tags=["calendar"])
app.include_router(quizzes.router, prefix=f"{settings.API_V1_STR}/quizzes", tags=["quizzes"])
app.include_router(exams.router, prefix=f"{settings.API_V1_STR}/exams", tags=["exams"])
app.include_router(progress.router, prefix=f"{settings.API_V1_STR}/progress", tags=["progress"])
app.include_router(telegram.router, prefix=f"{settings.API_V1_STR}/telegram", tags=["telegram"])

@app.get("/")
async def root():
    return {
        "message": "AI Teaching Assistant API active",
        "central_ai_agent": "Active (1 Central AI Agent)",
        "offline_reminders": "Server-side scheduler running"
    }
