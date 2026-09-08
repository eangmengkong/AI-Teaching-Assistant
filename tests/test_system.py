import pytest
from datetime import date, timedelta
from app.services.scheduler_service import SchedulerService

def test_calculate_teaching_dates():
    start = date(2026, 9, 7)
    end = date(2026, 10, 2)
    class_days = ["Monday", "Wednesday", "Friday"]
    holidays = [date(2026, 9, 24)]
    days_without_class = []

    dates = SchedulerService._calculate_teaching_dates(start, end, class_days, holidays, days_without_class)
    assert len(dates) == 12
    assert start in dates
    assert date(2026, 9, 24) not in dates # Holiday excluded
