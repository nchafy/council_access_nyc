"""The two dates this product computes rather than copies. Both are deliberately conservative.

`written_safe_until` is `start + 72h`: a provable lower bound on the window
council.nyc.gov/testify/ states, because adjournment time is published nowhere.
`accommodation_by` counts three business days against `HOLIDAYS`, not `date - 3`.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

__all__ = ["HOLIDAYS", "WRITTEN_TESTIMONY_HOURS", "accommodation_deadline", "written_safe_until"]

WRITTEN_TESTIMONY_HOURS = 72
ACCOMMODATION_BUSINESS_DAYS = 3

#: Committed as data and extended by hand, because the floating holidays are political
#: decisions a derivation would drift from. Generous on purpose: a holiday listed in error
#: only moves a deadline earlier, which is the safe direction.
HOLIDAYS: frozenset[date] = frozenset(
    {
        date(2026, 1, 1),  # New Year's Day
        date(2026, 1, 19),  # Martin Luther King Jr. Day
        date(2026, 2, 16),  # Presidents' Day
        date(2026, 5, 25),  # Memorial Day
        date(2026, 6, 19),  # Juneteenth
        date(2026, 7, 3),  # Independence Day (observed)
        date(2026, 9, 7),  # Labor Day
        date(2026, 10, 12),  # Indigenous Peoples' / Columbus Day
        date(2026, 11, 3),  # Election Day
        date(2026, 11, 11),  # Veterans Day
        date(2026, 11, 26),  # Thanksgiving
        date(2026, 11, 27),  # Day after Thanksgiving
        date(2026, 12, 25),  # Christmas
        date(2027, 1, 1),
        date(2027, 1, 18),
        date(2027, 2, 15),
        date(2027, 5, 31),
        date(2027, 6, 18),  # Juneteenth (observed)
        date(2027, 7, 5),  # Independence Day (observed)
        date(2027, 9, 6),
        date(2027, 10, 11),
        date(2027, 11, 2),
        date(2027, 11, 11),
        date(2027, 11, 25),
        date(2027, 11, 26),
        date(2027, 12, 24),  # Christmas (observed)
    }
)


def is_business_day(day: date) -> bool:
    """Monday-Friday and not in the committed holiday table."""
    return day.weekday() < 5 and day not in HOLIDAYS


def written_safe_until(hearing_date: date, start_time: time | None) -> datetime:
    """A timestamp before which filing written testimony is certainly in time.

    An unknown start time falls back to midnight at the start of the hearing day, which
    moves the bound earlier and never tells someone they have time they do not have.
    """
    anchor = datetime.combine(hearing_date, start_time or time(0, 0))
    return anchor + timedelta(hours=WRITTEN_TESTIMONY_HOURS)


def accommodation_deadline(
    hearing_date: date, business_days: int = ACCOMMODATION_BUSINESS_DAYS
) -> date:
    """The last business day at least `business_days` before the hearing.

    The hearing day itself does not count, since "before the hearing" excludes it.
    """
    remaining = business_days
    day = hearing_date
    while remaining > 0:
        day -= timedelta(days=1)
        if is_business_day(day):
            remaining -= 1
    return day


def accommodation_state(hearing_date: date, today: date | None = None) -> str:
    """ "open" while an accommodation can still be requested, else "too_late".

    "too_late" is a designed state: the page keeps the contacts, because the Council may
    still accommodate a late request.
    """
    now = today or date.today()
    return "open" if now <= accommodation_deadline(hearing_date) else "too_late"


def written_state(safe_until: datetime, now: datetime | None = None) -> str:
    """ "open" | "closing" (under 24h left) | "closed"."""
    moment = now or datetime.now()
    if moment >= safe_until:
        return "closed"
    if safe_until - moment <= timedelta(hours=24):
        return "closing"
    return "open"
