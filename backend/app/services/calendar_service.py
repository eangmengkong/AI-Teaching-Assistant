from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.models.models import LessonSchedule, CalendarEvent, Course, User
from app.core.config import settings

try:
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
except ImportError:
    Credentials = None
    build = None


class CalendarService:
    @staticmethod
    def get_auth_url() -> str:
        if not settings.GOOGLE_CLIENT_ID:
            return "https://accounts.google.com/o/oauth2/auth?mock=true"
        redirect_uri = settings.GOOGLE_REDIRECT_URI
        scope = "https://www.googleapis.com/auth/calendar"
        return (
            f"https://accounts.google.com/o/oauth2/v2/auth?"
            f"response_type=code&client_id={settings.GOOGLE_CLIENT_ID}&"
            f"redirect_uri={redirect_uri}&scope={scope}&access_type=offline&prompt=consent"
        )

    @staticmethod
    async def create_calendar_event(db: AsyncSession, course: Course, user: User, schedule: LessonSchedule) -> Optional[str]:
        # Build description format required by spec Section 11
        event_title = f"{course.name} – {schedule.unit} – {schedule.lesson}"
        description = (
            f"📚 TEACHING LESSON\n\n"
            f"Unit:\n{schedule.unit}\n\n"
            f"Lesson:\n{schedule.lesson}\n\n"
            f"📖 Textbook:\n{schedule.textbook_pages or 'N/A'}\n\n"
            f"✏️ Workbook:\n{schedule.workbook_pages or 'N/A'}\n\n"
            f"🎯 Objectives:\n{schedule.objectives or 'N/A'}\n\n"
            f"📝 Classroom Activities:\n{', '.join(schedule.activities) if schedule.activities else 'N/A'}\n\n"
            f"✏️ Exercises:\n{', '.join(schedule.exercises) if schedule.exercises else 'N/A'}\n\n"
            f"🏠 Homework:\n{schedule.homework or 'N/A'}\n\n"
            f"🧪 Assessment:\n{schedule.assessment or 'N/A'}"
        )

        start_dt_str = f"{schedule.date}T{schedule.start_time}:00"
        end_dt_str = f"{schedule.date}T{schedule.end_time}:00"

        # Check if calendar event already exists in DB to prevent duplicates.
        # NOTE: IDs prefixed with "evt_" are LOCAL placeholders created when no
        # Google token was available yet - they are not real Google Calendar IDs,
        # so they must be pushed with an INSERT (updating a non-existent Google
        # event would 404 silently and the lesson would never reach the calendar).
        if schedule.calendar_event_id and not str(schedule.calendar_event_id).startswith("evt_"):
            return await CalendarService.update_calendar_event(db, course, user, schedule)

        event_id = f"evt_{course.id}_{schedule.id}_{int(datetime.utcnow().timestamp())}"

        # If Google credentials exist, execute actual Google API call
        if user.google_refresh_token and Credentials and build:
            try:
                creds = Credentials(
                    token=None,
                    refresh_token=user.google_refresh_token,
                    token_uri="https://oauth2.googleapis.com/token",
                    client_id=settings.GOOGLE_CLIENT_ID,
                    client_secret=settings.GOOGLE_CLIENT_SECRET
                )
                service = build('calendar', 'v3', credentials=creds)
                event_body = {
                    'summary': event_title,
                    'description': description,
                    'start': {'dateTime': f"{start_dt_str}Z", 'timeZone': course.teacher_timezone},
                    'end': {'dateTime': f"{end_dt_str}Z", 'timeZone': course.teacher_timezone},
                    'reminders': {
                        'useDefault': False,
                        'overrides': [
                            {'method': 'popup', 'minutes': 24 * 60}, # 24 hours
                            {'method': 'popup', 'minutes': 60},      # 1 hour
                            {'method': 'popup', 'minutes': 15},      # 15 minutes
                        ],
                    },
                }
                created_evt = service.events().insert(calendarId='primary', body=event_body).execute()
                event_id = created_evt.get('id', event_id)
            except Exception as e:
                print(f"Google Calendar API execution note/fallback: {str(e)}")

        # Store in database - update the existing row for this lesson when one
        # is present (prevents duplicate calendar_event rows after a placeholder
        # is replaced with the real Google event id).
        schedule.calendar_event_id = event_id
        
        start_dt = datetime.strptime(f"{schedule.date} {schedule.start_time}", "%Y-%m-%d %H:%M")
        end_dt = datetime.strptime(f"{schedule.date} {schedule.end_time}", "%Y-%m-%d %H:%M")

        existing = (
            await db.execute(
                select(CalendarEvent).where(CalendarEvent.lesson_schedule_id == schedule.id)
            )
        ).scalar_one_or_none()
        if existing:
            existing.google_event_id = event_id
            existing.title = event_title
            existing.description = description
            existing.start_datetime = start_dt
            existing.end_datetime = end_dt
            existing.status = "created"
            existing.last_synced_at = datetime.utcnow()
        else:
            db.add(CalendarEvent(
                lesson_schedule_id=schedule.id,
                course_id=course.id,
                google_event_id=event_id,
                title=event_title,
                start_datetime=start_dt,
                end_datetime=end_dt,
                description=description,
                status="created",
                last_synced_at=datetime.utcnow()
            ))
        await db.commit()

        return event_id

    @staticmethod
    async def update_calendar_event(db: AsyncSession, course: Course, user: User, schedule: LessonSchedule) -> str:
        if not schedule.calendar_event_id:
            return await CalendarService.create_calendar_event(db, course, user, schedule)

        event_title = f"{course.name} – {schedule.unit} – {schedule.lesson}"
        description = f"📚 TEACHING LESSON (Updated)\nUnit: {schedule.unit}\nLesson: {schedule.lesson}\n📖 Textbook: {schedule.textbook_pages}\n✏️ Workbook: {schedule.workbook_pages}"

        if user.google_refresh_token and Credentials and build:
            try:
                creds = Credentials(
                    token=None,
                    refresh_token=user.google_refresh_token,
                    token_uri="https://oauth2.googleapis.com/token",
                    client_id=settings.GOOGLE_CLIENT_ID,
                    client_secret=settings.GOOGLE_CLIENT_SECRET
                )
                service = build('calendar', 'v3', credentials=creds)
                start_dt_str = f"{schedule.date}T{schedule.start_time}:00"
                end_dt_str = f"{schedule.date}T{schedule.end_time}:00"
                
                event_body = {
                    'summary': event_title,
                    'description': description,
                    'start': {'dateTime': f"{start_dt_str}Z", 'timeZone': course.teacher_timezone},
                    'end': {'dateTime': f"{end_dt_str}Z", 'timeZone': course.teacher_timezone},
                }
                service.events().update(calendarId='primary', eventId=schedule.calendar_event_id, body=event_body).execute()
            except Exception as e:
                print(f"Google Calendar update exception: {str(e)}")

        start_dt = datetime.strptime(f"{schedule.date} {schedule.start_time}", "%Y-%m-%d %H:%M")
        end_dt = datetime.strptime(f"{schedule.date} {schedule.end_time}", "%Y-%m-%d %H:%M")

        await db.execute(
            update(CalendarEvent)
            .where(CalendarEvent.google_event_id == schedule.calendar_event_id)
            .values(
                title=event_title,
                description=description,
                start_datetime=start_dt,
                end_datetime=end_dt,
                last_synced_at=datetime.utcnow()
            )
        )
        await db.commit()
        return schedule.calendar_event_id
