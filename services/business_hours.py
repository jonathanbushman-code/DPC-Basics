"""Business-hours helpers for the SPRUS weekly report.

Hours of operation:
- Monday-Thursday: 08:00-12:00 and 13:00-17:00
- Friday: 08:00-12:00 only (afternoons closed)
- 12:00-13:00 is lunch every business day
- Saturday and Sunday are closed
"""

from datetime import datetime, time

# Mon=0 ... Sun=6
_MORNING_START = time(8, 0)
_MORNING_END = time(12, 0)
_AFTERNOON_START = time(13, 0)
_AFTERNOON_END = time(17, 0)


def is_business_hours(dt: datetime) -> bool:
    """True if dt (in practice local time) falls inside business hours."""
    weekday = dt.weekday()
    if weekday > 4:
        return False
    t = dt.time()
    if _MORNING_START <= t < _MORNING_END:
        return True
    if weekday < 4 and _AFTERNOON_START <= t < _AFTERNOON_END:
        return True
    return False


def business_hour_slots() -> list[int]:
    """Hours-of-day that the dashboard chart should display (8..16)."""
    return list(range(8, 17))


def hour_label(hour_24: int) -> str:
    suffix = "AM" if hour_24 < 12 else "PM"
    h = hour_24 % 12 or 12
    return f"{h} {suffix}"


def is_open_in_hour(weekday: int, hour_24: int) -> bool:
    """Is the practice open for any minute of this hour on this weekday?"""
    if weekday > 4:
        return False
    if 8 <= hour_24 < 12:
        return True
    if weekday < 4 and 13 <= hour_24 < 17:
        return True
    return False
