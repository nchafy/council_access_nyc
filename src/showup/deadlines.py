"""The two dates this product computes rather than repeats.

Everything else on the site is a fact copied from an official page with a link
back to it. These two are arithmetic, so they carry the risk of being confidently
wrong about a deadline — which is the worst thing this product can do. Both are
therefore computed conservatively and labelled with their basis.

1. `written_safe_until` — written testimony is accepted "up to 72 hours after
   [the] hearing has been adjourned" (council.nyc.gov/testify/). Adjournment time
   is published nowhere. But adjournment is always at or after the scheduled
   start, so `start + 72h` is provably *inside* the real window: filing before it
   is always safe. It is a lower bound, never presented as the deadline.

2. `accommodation_by` — ASL, CART and interpretation must be requested "at least
   three (3) business days before the hearing". Business days exclude weekends
   and holidays, so this needs a real calendar rather than `date - 3`.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

__all__ = ["HOLIDAYS", "WRITTEN_TESTIMONY_HOURS", "accommodation_deadline", "written_safe_until"]

WRITTEN_TESTIMONY_HOURS = 72
ACCOMMODATION_BUSINESS_DAYS = 3

#: Observed NYC government holidays. Committed as data rather than computed,
#: because Election Day, Juneteenth and the floating holidays are political
#: decisions and a rule that derives them will silently drift. Extend by hand.
#: Being wrong here makes an accommodation deadline too late to act on, so the
#: table is deliberately generous: a holiday listed in error only moves a
#: deadline earlier, which is safe.
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

    When the start time is unknown — the source said "Deferred", or published no
    time at all — we fall back to midnight at the *start* of the hearing day.
    That makes the bound earlier, i.e. more conservative, which is the correct
    direction for a deadline: it may tell someone to hurry more than strictly
    necessary, and will never tell them they have time they do not have.
    """
    anchor = datetime.combine(hearing_date, start_time or time(0, 0))
    return anchor + timedelta(hours=WRITTEN_TESTIMONY_HOURS)


def accommodation_deadline(
    hearing_date: date, business_days: int = ACCOMMODATION_BUSINESS_DAYS
) -> date:
    """The last business day that is at least `business_days` before the hearing.

    Counts backwards over business days only. The hearing day itself does not
    count, since "three business days before the hearing" excludes it.
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

    A passed deadline is a designed state: the UI still shows the contacts,
    because the Council may accommodate a late request and hiding the phone
    number guarantees they cannot.
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
