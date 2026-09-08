from fastapi import APIRouter, Depends, HTTPException
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.api.v1.auth import get_current_user
from app.models.models import User, Course
from app.schemas.schemas import CourseCreate, CourseUpdate, CourseResponse

router = APIRouter()

@router.post("/", response_model=CourseResponse)
async def create_course(
    course_in: CourseCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    course = Course(
        user_id=current_user.id,
        name=course_in.name,
        description=course_in.description,
        student_count=course_in.student_count,
        class_days=course_in.class_days,
        start_time=course_in.start_time,
        end_time=course_in.end_time,
        start_date=course_in.start_date,
        end_date=course_in.end_date,
        teaching_frequency=course_in.teaching_frequency,
        holidays=course_in.holidays,
        days_without_class=course_in.days_without_class,
        teacher_timezone=course_in.teacher_timezone,
        status="active"
    )
    db.add(course)
    await db.commit()
    await db.refresh(course)
    return course

@router.get("/", response_model=List[CourseResponse])
async def list_courses(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Course).where(Course.user_id == current_user.id)
    res = await db.execute(stmt)
    return res.scalars().all()

@router.get("/{course_id}", response_model=CourseResponse)
async def get_course(
    course_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Course).where(Course.id == course_id, Course.user_id == current_user.id)
    res = await db.execute(stmt)
    course = res.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    return course

@router.put("/{course_id}", response_model=CourseResponse)
async def update_course(
    course_id: int,
    course_in: CourseUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Course).where(Course.id == course_id, Course.user_id == current_user.id)
    res = await db.execute(stmt)
    course = res.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    update_data = course_in.dict(exclude_unset=True)
    for field, val in update_data.items():
        setattr(course, field, val)

    await db.commit()
    await db.refresh(course)
    return course
