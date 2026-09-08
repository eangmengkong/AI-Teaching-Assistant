from pydantic import BaseModel, EmailStr
from typing import List, Optional, Any, Dict
from datetime import date, datetime

# Auth / User schemas
class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None
    telegram_chat_id: Optional[str] = None

class UserResponse(BaseModel):
    id: int
    email: EmailStr
    full_name: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse

# Course Setup Schemas
class CourseCreate(BaseModel):
    name: str
    description: Optional[str] = None
    student_count: int
    class_days: List[str] # ["Monday", "Wednesday", "Friday"]
    start_time: str # "08:00"
    end_time: str # "09:30"
    start_date: date
    end_date: date
    teaching_frequency: str = "weekly"
    holidays: List[str] = [] # ["2026-09-24"]
    days_without_class: List[str] = []
    teacher_timezone: str = "UTC"

class CourseUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    student_count: Optional[int] = None
    class_days: Optional[List[str]] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    holidays: Optional[List[str]] = None
    days_without_class: Optional[List[str]] = None
    teacher_timezone: Optional[str] = None

class CourseResponse(CourseCreate):
    id: int
    user_id: int
    status: str
    created_at: datetime

    class Config:
        from_attributes = True

# Document schemas
class DocumentResponse(BaseModel):
    id: int
    course_id: int
    document_type: str # "textbook" | "workbook"
    filename: str
    total_pages: int
    status: str
    created_at: datetime

    class Config:
        from_attributes = True

# Schedule schemas
class LessonScheduleResponse(BaseModel):
    id: int
    course_id: int
    date: date
    start_time: str
    end_time: str
    week_number: int
    unit: str
    lesson: str
    textbook_pages: Optional[str] = None
    workbook_pages: Optional[str] = None
    objectives: Optional[str] = None
    activities: Optional[List[Any]] = None
    exercises: Optional[List[Any]] = None
    homework: Optional[str] = None
    assessment: Optional[str] = None
    status: str
    calendar_event_id: Optional[str] = None
    notes: Optional[str] = None

    class Config:
        from_attributes = True

class RescheduleRequest(BaseModel):
    lesson_id: int
    new_date: date
    reason: Optional[str] = None

class SkipRequest(BaseModel):
    lesson_id: int
    reason: Optional[str] = None

class CompleteLessonRequest(BaseModel):
    lesson_id: int
    completion_status: str # "fully", "partially", "not_completed"
    completed_textbook_pages: Optional[str] = None
    completed_workbook_pages: Optional[str] = None
    notes: Optional[str] = None

# Assessment schemas
class QuizQuestionSchema(BaseModel):
    question_number: int
    question_text: str
    question_type: str = "multiple_choice"
    options: Optional[List[str]] = None
    correct_answer: str
    source_type: str # "textbook", "workbook", "ai_generated"

class QuizCreate(BaseModel):
    course_id: int
    title: str
    covered_units: List[str]
    quiz_date: Optional[date] = None

class ScoreRecordRequest(BaseModel):
    quiz_or_exam_id: int
    is_exam: bool = False
    student_name: str
    score: float
    max_score: float = 100.0
    feedback: Optional[str] = None

# Progress schemas
class ProgressReport(BaseModel):
    course_name: str
    textbook_progress_percentage: float
    workbook_progress_percentage: float
    completed_lessons: int
    total_lessons: int
    skipped_lessons: int
    completed_quizzes: int
    average_quiz_score: float
    completed_exams: int
    average_exam_score: float
    status_summary: str
