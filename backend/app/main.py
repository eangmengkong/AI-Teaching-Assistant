import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.core.config import settings
from app.core.database import engine, Base
from app.api.v1 import (
    auth, courses, documents, schedule, lessons, calendar, quizzes, exams, progress, telegram
)
from app.worker import start_background_worker

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create DB tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Start background server-side reminder worker task
    worker_task = asyncio.create_task(start_background_worker())
    
    yield
    
    worker_task.cancel()

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan
)

# Enable CORS for Next.js web dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
