import asyncio

from app.core.database import AsyncSessionLocal
from app.services.daily_maintenance_service import DailyMaintenanceService
from app.services.reminder_service import ReminderService
from app.telegram.bot import TelegramBotHandler

async def start_background_worker():
    print("[Server-Side Reminder, Daily Digest & Scheduler Background Worker Started]")
    # Start Telegram polling background task for local execution
    asyncio.create_task(TelegramBotHandler.poll_updates())

    while True:
        try:
            async with AsyncSessionLocal() as db:
                # 1. Schedule upcoming 24h/1h reminders into telegram_messages table
                await ReminderService.schedule_upcoming_reminders(db)
                
                # 2. Process due telegram messages and send them
                await ReminderService.process_due_reminders(db)

                # 3. Daily jobs (idempotent, safe to call every cycle):
                #    - morning "today's lessons" Telegram digest per timezone
                #    - keep Google Calendar in sync with planned lessons
                await DailyMaintenanceService.run_daily(db)
        except Exception as e:
            print(f"[Worker Exception] {str(e)}")
            
        await asyncio.sleep(30) # Run cycle every 30 seconds

if __name__ == "__main__":
    asyncio.run(start_background_worker())
