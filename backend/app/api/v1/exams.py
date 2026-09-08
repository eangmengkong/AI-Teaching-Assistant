from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.api.v1.auth import get_current_user
from app.models.models import User, Exam
from app.schemas.schemas import ScoreRecordRequest
from app.agent.tools import CentralAgentTools

router = APIRouter()

@router.post("/generate/{course_id}")
async def generate_exam_api(
    course_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    return await CentralAgentTools.generate_final_exam(db, course_id)

@router.get("/{course_id}")
async def list_exams(
    course_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Exam).where(Exam.course_id == course_id)
    res = await db.execute(stmt)
    return res.scalars().all()

@router.post("/score")
async def record_exam_score_api(
    req: ScoreRecordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    return await CentralAgentTools.record_exam_score(
        db, exam_id=req.quiz_or_exam_id, student_name=req.student_name, score=req.score, max_score=req.max_score, feedback=req.feedback
    )
