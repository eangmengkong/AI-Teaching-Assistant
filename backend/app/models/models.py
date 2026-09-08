from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, Date, Time, Float, ForeignKey, JSON
)
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    telegram_chat_id = Column(String(100), nullable=True, unique=True, index=True)
    google_refresh_token = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    courses = relationship("Course", back_populates="owner", cascade="all, delete-orphan")


class Course(Base):
    __tablename__ = "courses"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    student_count = Column(Integer, default=0)
    class_days = Column(JSON, nullable=False) # e.g. ["Monday", "Wednesday", "Friday"]
    start_time = Column(String(10), nullable=False) # e.g. "08:00"
    end_time = Column(String(10), nullable=False) # e.g. "09:30"
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    teaching_frequency = Column(String(50), default="weekly") # "weekly", "daily", etc.
    holidays = Column(JSON, default=[]) # e.g. ["2026-09-24"]
    days_without_class = Column(JSON, default=[]) # e.g. ["2026-09-15"]
    teacher_timezone = Column(String(100), default="UTC")
    status = Column(String(50), default="active")
    created_at = Column(DateTime, default=datetime.utcnow)

    owner = relationship("User", back_populates="courses")
    documents = relationship("Document", back_populates="course", cascade="all, delete-orphan")
    schedules = relationship("LessonSchedule", back_populates="course", cascade="all, delete-orphan")
    students = relationship("Student", back_populates="course", cascade="all, delete-orphan")
    quizzes = relationship("Quiz", back_populates="course", cascade="all, delete-orphan")
    exams = relationship("Exam", back_populates="course", cascade="all, delete-orphan")


class Student(Base):
    __tablename__ = "students"

    id = Column(Integer, primary_key=True, index=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=True)
    details = Column(JSON, nullable=True)

    course = relationship("Course", back_populates="students")


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)
    document_type = Column(String(50), nullable=False) # "textbook" or "workbook"
    filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    mime_type = Column(String(100), nullable=True)
    file_size = Column(Integer, nullable=True)
    total_pages = Column(Integer, default=0)
    status = Column(String(50), default="processed")
    created_at = Column(DateTime, default=datetime.utcnow)

    course = relationship("Course", back_populates="documents")
    pages = relationship("DocumentPage", back_populates="document", cascade="all, delete-orphan")
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")


class DocumentPage(Base):
    __tablename__ = "document_pages"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    page_number = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    clean_text = Column(Text, nullable=True)

    document = relationship("Document", back_populates="pages")


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    page_number = Column(Integer, nullable=False)
    unit = Column(String(100), nullable=True)
    chapter = Column(String(100), nullable=True)
    lesson = Column(String(100), nullable=True)
    section = Column(String(100), nullable=True)
    content = Column(Text, nullable=False)
    metadata_json = Column(JSON, nullable=True)

    document = relationship("Document", back_populates="chunks")


class Unit(Base):
    __tablename__ = "units"

    id = Column(Integer, primary_key=True, index=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)
    unit_number = Column(String(50), nullable=False)
    title = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)


class Lesson(Base):
    __tablename__ = "lessons"

    id = Column(Integer, primary_key=True, index=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)
    unit_id = Column(Integer, ForeignKey("units.id"), nullable=True)
    lesson_number = Column(String(50), nullable=False)
    title = Column(String(255), nullable=True)
    objectives = Column(Text, nullable=True)


class WorkbookExercise(Base):
    __tablename__ = "workbook_exercises"

    id = Column(Integer, primary_key=True, index=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    page_number = Column(Integer, nullable=False)
    unit = Column(String(100), nullable=True)
    exercise_number = Column(String(50), nullable=False)
    title = Column(String(255), nullable=True)
    prompt = Column(Text, nullable=False)
    metadata_json = Column(JSON, nullable=True)


class LessonSchedule(Base):
    __tablename__ = "lesson_schedule"

    id = Column(Integer, primary_key=True, index=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)
    date = Column(Date, nullable=False)
    start_time = Column(String(10), nullable=False)
    end_time = Column(String(10), nullable=False)
    week_number = Column(Integer, nullable=False)
    unit = Column(String(100), nullable=False)
    lesson = Column(String(100), nullable=False)
    textbook_pages = Column(String(100), nullable=True)
    workbook_pages = Column(String(100), nullable=True)
    objectives = Column(Text, nullable=True)
    activities = Column(JSON, nullable=True)
    exercises = Column(JSON, nullable=True)
    homework = Column(Text, nullable=True)
    assessment = Column(Text, nullable=True)
    status = Column(String(50), default="planned") # planned, in_progress, completed, partially_completed, skipped, rescheduled
    calendar_event_id = Column(String(255), nullable=True)
    notes = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    course = relationship("Course", back_populates="schedules")
    progress = relationship("LessonProgress", back_populates="schedule", uselist=False, cascade="all, delete-orphan")


class LessonProgress(Base):
    __tablename__ = "lesson_progress"

    id = Column(Integer, primary_key=True, index=True)
    lesson_schedule_id = Column(Integer, ForeignKey("lesson_schedule.id"), nullable=False)
    status = Column(String(50), nullable=False)
    completed_textbook_pages = Column(String(100), nullable=True)
    completed_workbook_pages = Column(String(100), nullable=True)
    completed_exercises = Column(JSON, nullable=True)
    partial_notes = Column(Text, nullable=True)
    completed_at = Column(DateTime, default=datetime.utcnow)

    schedule = relationship("LessonSchedule", back_populates="progress")


class Homework(Base):
    __tablename__ = "homework"

    id = Column(Integer, primary_key=True, index=True)
    lesson_schedule_id = Column(Integer, ForeignKey("lesson_schedule.id"), nullable=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    textbook_hw = Column(Text, nullable=True)
    workbook_hw = Column(Text, nullable=True)
    ai_generated_hw = Column(Text, nullable=True)
    due_date = Column(Date, nullable=True)
    is_submitted = Column(Boolean, default=False)


class Review(Base):
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True, index=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)
    lesson_schedule_id = Column(Integer, ForeignKey("lesson_schedule.id"), nullable=True)
    title = Column(String(255), nullable=False)
    topics = Column(JSON, nullable=True)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Quiz(Base):
    __tablename__ = "quizzes"

    id = Column(Integer, primary_key=True, index=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)
    title = Column(String(255), nullable=False)
    covered_units = Column(JSON, nullable=True)
    quiz_date = Column(Date, nullable=True)
    total_score = Column(Float, default=100.0)
    status = Column(String(50), default="active")

    course = relationship("Course", back_populates="quizzes")
    questions = relationship("QuizQuestion", back_populates="quiz", cascade="all, delete-orphan")
    results = relationship("QuizResult", back_populates="quiz", cascade="all, delete-orphan")


class QuizQuestion(Base):
    __tablename__ = "quiz_questions"

    id = Column(Integer, primary_key=True, index=True)
    quiz_id = Column(Integer, ForeignKey("quizzes.id"), nullable=False)
    question_number = Column(Integer, nullable=False)
    question_text = Column(Text, nullable=False)
    question_type = Column(String(50), default="multiple_choice")
    options = Column(JSON, nullable=True)
    correct_answer = Column(Text, nullable=False)
    source_type = Column(String(50), default="ai_generated") # textbook, workbook, ai_generated

    quiz = relationship("Quiz", back_populates="questions")


class QuizResult(Base):
    __tablename__ = "quiz_results"

    id = Column(Integer, primary_key=True, index=True)
    quiz_id = Column(Integer, ForeignKey("quizzes.id"), nullable=False)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=True)
    student_name = Column(String(255), nullable=True)
    score = Column(Float, nullable=False)
    max_score = Column(Float, default=100.0)
    percentage = Column(Float, nullable=False)
    feedback = Column(Text, nullable=True)
    recorded_at = Column(DateTime, default=datetime.utcnow)

    quiz = relationship("Quiz", back_populates="results")


class Exam(Base):
    __tablename__ = "exams"

    id = Column(Integer, primary_key=True, index=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)
    title = Column(String(255), nullable=False)
    covered_content = Column(JSON, nullable=True)
    exam_date = Column(Date, nullable=True)
    total_score = Column(Float, default=100.0)
    status = Column(String(50), default="active")

    course = relationship("Course", back_populates="exams")
    questions = relationship("ExamQuestion", back_populates="exam", cascade="all, delete-orphan")
    results = relationship("ExamResult", back_populates="exam", cascade="all, delete-orphan")


class ExamQuestion(Base):
    __tablename__ = "exam_questions"

    id = Column(Integer, primary_key=True, index=True)
    exam_id = Column(Integer, ForeignKey("exams.id"), nullable=False)
    question_number = Column(Integer, nullable=False)
    question_text = Column(Text, nullable=False)
    question_type = Column(String(50), default="multiple_choice")
    options = Column(JSON, nullable=True)
    correct_answer = Column(Text, nullable=False)
    source_type = Column(String(50), default="ai_generated")

    exam = relationship("Exam", back_populates="questions")


class ExamResult(Base):
    __tablename__ = "exam_results"

    id = Column(Integer, primary_key=True, index=True)
    exam_id = Column(Integer, ForeignKey("exams.id"), nullable=False)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=True)
    student_name = Column(String(255), nullable=True)
    score = Column(Float, nullable=False)
    max_score = Column(Float, default=100.0)
    percentage = Column(Float, nullable=False)
    feedback = Column(Text, nullable=True)
    recorded_at = Column(DateTime, default=datetime.utcnow)

    exam = relationship("Exam", back_populates="results")


class CalendarEvent(Base):
    __tablename__ = "calendar_events"

    id = Column(Integer, primary_key=True, index=True)
    lesson_schedule_id = Column(Integer, ForeignKey("lesson_schedule.id"), nullable=False)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)
    google_event_id = Column(String(255), unique=True, index=True, nullable=False)
    title = Column(String(255), nullable=False)
    start_datetime = Column(DateTime, nullable=False)
    end_datetime = Column(DateTime, nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(50), default="created")
    last_synced_at = Column(DateTime, default=datetime.utcnow)


class TelegramMessage(Base):
    __tablename__ = "telegram_messages"

    id = Column(Integer, primary_key=True, index=True)
    lesson_schedule_id = Column(Integer, ForeignKey("lesson_schedule.id"), nullable=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)
    telegram_chat_id = Column(String(100), nullable=False)
    message_type = Column(String(50), nullable=False) # "reminder_24h", "reminder_1h", "schedule_update", etc.
    content = Column(Text, nullable=False)
    scheduled_at = Column(DateTime, nullable=False)
    sent_at = Column(DateTime, nullable=True)
    status = Column(String(50), default="pending") # pending, sent, failed
    retry_count = Column(Integer, default=0)
    error = Column(Text, nullable=True)


class Holiday(Base):
    __tablename__ = "holidays"

    id = Column(Integer, primary_key=True, index=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)
    holiday_date = Column(Date, nullable=False)
    name = Column(String(255), nullable=True)


class Settings(Base):
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=True)
    key = Column(String(100), nullable=False)
    value = Column(Text, nullable=False)
