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
    # Attempt DB setup with retry so temporary network/database cold-start delays
    # do not crash the container and trigger a Render deployment failure.
    for attempt in range(1, 4):
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            await run_schema_migrations(engine)
            print(f"[Startup] Database schema initialized successfully (attempt {attempt})")
            break
        except Exception as exc:
            print(f"[Startup Warning] Database initialization attempt {attempt} failed: {exc}")
            if attempt < 3:
                await asyncio.sleep(2)

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
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "X-Study-Pages"],
)


def is_allowed_origin(origin: str) -> bool:
    if not origin:
        return False
    clean_origin = origin.rstrip("/")
    if clean_origin in [o.rstrip("/") for o in settings.CORS_ORIGINS]:
        return True
    if clean_origin.endswith(".vercel.app") or clean_origin.startswith("http://localhost"):
        return True
    return False


def build_cors_headers(origin: str) -> dict:
    """CORS headers to echo for ``origin`` (empty when the origin is not allowed).

    Starlette's CORSMiddleware normally adds these, but responses produced by
    the catch-all exception handler below can escape the middleware before its
    header-writing wrapper runs (the exception is re-raised out of the CORS
    middleware into Starlette's outer ServerErrorMiddleware). Without them an
    unexpected 5xx would reach browsers as a confusing "blocked by CORS" error
    instead of the real HTTP 500 status and body.
    """
    if is_allowed_origin(origin):
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
