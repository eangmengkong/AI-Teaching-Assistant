from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.v1.auth import get_current_user
from app.models.models import User
from app.schemas.schemas import CompleteLessonRequest
from app.agent.tools import CentralAgentTools

router = APIRouter()

@router.get("/today/{course_id}")
async def get_today_lesson_api(
    course_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    return await CentralAgentTools.get_today_lesson(db, course_id)

@router.get("/tomorrow/{course_id}")
async def get_tomorrow_lesson_api(
    course_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    return await CentralAgentTools.get_tomorrow_lesson(db, course_id)

@router.get("/week/{course_id}")
async def get_week_schedule_api(
    course_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    return await CentralAgentTools.get_week_schedule(db, course_id)

@router.get("/plan/{course_id}")
async def get_lesson_plan_api(
    course_id: int,
    lesson_id: int = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    return await CentralAgentTools.get_lesson_plan(db, course_id, lesson_id)

@router.post("/complete")
async def complete_lesson_api(
    req: CompleteLessonRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    return await CentralAgentTools.record_lesson_completion(
        db, course_id=1, lesson_id=req.lesson_id, completion_status=req.completion_status, notes=req.notes
    )

@router.get("/exercises/{course_id}")
async def get_exercises_api(
    course_id: int,
    lesson_id: int = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    return await CentralAgentTools.generate_additional_exercises(db, course_id, lesson_id)

@router.get("/homework/{course_id}")
async def get_homework_api(
    course_id: int,
    lesson_id: int = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    return await CentralAgentTools.generate_homework(db, course_id, lesson_id)
