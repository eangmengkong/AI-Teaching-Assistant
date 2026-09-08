from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.v1.auth import get_current_user
from app.models.models import User
from app.agent.tools import CentralAgentTools

router = APIRouter()

@router.get("/{course_id}")
async def get_progress_api(
    course_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    return await CentralAgentTools.calculate_progress(db, course_id)
