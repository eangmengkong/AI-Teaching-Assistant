import asyncio
from fastapi import APIRouter, Depends, HTTPException
from typing import List

# pyrefly: ignore [missing-import]
from sqlalchemy import select
# pyrefly: ignore [missing-import]
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user
from app.agent.tools import CentralAgentTools
from app.core.database import AsyncSessionLocal, get_db
from app.models.models import LessonSchedule, User
from app.schemas.schemas import LessonScheduleResponse, RescheduleRequest, SkipRequest

router = APIRouter()

# ---------------------------------------------------------------------------
# Schedule generation job store.
# Holds the latest job state per course in memory so the dashboard can poll
# GET /status/{course_id} while the AI agent builds the schedule in the
# background (instead of the frontend faking progress). Process-local is fine
# for this single-process self-study app; a multi-worker deployment would use
# Redis or a DB table instead.
# ---------------------------------------------------------------------------
SCHEDULE_JOBS: dict[int, dict] = {}


@router.post("/generate/{course_id}")
async def generate_schedule(course_id: int, current_user: User = Depends(get_current_user)):
    job = SCHEDULE_JOBS.get(course_id)
    if job and job.get("state") in {"analyzing", "building"}:
        raise HTTPException(
            status_code=409,
            detail="A schedule generation is already running for this course",
        )

    SCHEDULE_JOBS[course_id] = {
        "state": "analyzing",
        "progress": 15,
        "message": "Analyzing course materials…",
        "course_id": course_id,
    }
    asyncio.create_task(_run_schedule_generation(course_id))
    return {"status": "started", "course_id": course_id}


async def _run_schedule_generation(course_id: int):
    """Background work: run the scheduler and update the job store."""
    async with AsyncSessionLocal() as db:
        try:
            SCHEDULE_JOBS[course_id].update(
                {"state": "building", "progress": 40, "message": "Building the 1-month lesson plan…"}
            )
            res = await CentralAgentTools.create_monthly_schedule(db, course_id)
            SCHEDULE_JOBS[course_id].update(
                {
                    "state": "done",
                    "progress": 100,
                    "message": "Schedule generated",
                    "result": res,
                }
            )
        except Exception as e:  # noqa: BLE001 - report any failure to the UI
            SCHEDULE_JOBS[course_id].update({"state": "error", "message": str(e)})


@router.get("/status/{course_id}")
async def get_schedule_status(course_id: int):
    """Polled by the dashboard while generation is running."""
    job = SCHEDULE_JOBS.get(course_id)
    if not job:
        return {
            "state": "idle",
            "course_id": course_id,
            "progress": 0,
            "message": "No generation in progress",
        }
    return job


@router.get("/{course_id}", response_model=List[LessonScheduleResponse])
async def get_schedule(
    course_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(LessonSchedule)
        .where(LessonSchedule.course_id == course_id)
        .order_by(LessonSchedule.date.asc())
    )
    res = await db.execute(stmt)
    return res.scalars().all()


@router.post("/reschedule")
async def reschedule_lesson_api(
    req: RescheduleRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(LessonSchedule).where(LessonSchedule.id == req.lesson_id)
    s_res = await db.execute(stmt)
    schedule = s_res.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="Lesson schedule not found")

    res = await CentralAgentTools.reschedule_lesson(db, schedule.course_id, req.lesson_id, req.new_date)
    return res


@router.post("/skip")
async def skip_lesson_api(
    req: SkipRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(LessonSchedule).where(LessonSchedule.id == req.lesson_id)
    s_res = await db.execute(stmt)
    schedule = s_res.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="Lesson schedule not found")

    res = await CentralAgentTools.skip_lesson(db, schedule.course_id, req.lesson_id, req.reason or "Skipped")
    return res