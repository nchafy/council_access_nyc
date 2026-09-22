"""The two computed dates.

A wrong deadline is the worst output this product has, so these tests assert the
*direction* of every approximation as well as its value: an error must always make
a deadline earlier (telling someone to hurry unnecessarily), never later (telling
them they have time they do not have).
"""

from __future__ import annotations

from datetime import date, datetime, time

from showup.deadlines import (
    accommodation_deadline,
    accommodation_state,
    is_business_day,
    written_safe_until,
    written_state,
)


class TestWrittenSafeUntil:
    def test_is_start_plus_72_hours(self):
        result = written_safe_until(date(2026, 10, 20), time(13, 30))
        assert result == datetime(2026, 10, 23, 13, 30)

    def test_unknown_time_falls_back_to_midnight_which_is_earlier(self):
        # Conservative direction: the bound must not drift later than the real
        # window when we know less.
        known = written_safe_until(date(2026, 10, 20), time(13, 30))
        unknown = written_safe_until(date(2026, 10, 20), None)
        assert unknown < known
        assert unknown == datetime(2026, 10, 23, 0, 0)

    def test_bound_is_inside_the_real_window(self):
        # The real deadline is 72h after adjournment, and adjournment >= start.
        # So our bound is always <= the real deadline: filing before it is safe.
        hearing = date(2026, 10, 20)
        start = time(10, 0)
        ours = written_safe_until(hearing, start)
        adjourned_late = datetime.combine(hearing, time(18, 0))
        real_deadline = adjourned_late.replace(day=23) + (datetime.min - datetime.min)
        assert ours <= real_deadline.replace(hour=18)


class TestWrittenState:
    def test_open_when_far_out(self):
        until = datetime(2026, 10, 23, 13, 30)
        assert written_state(until, datetime(2026, 10, 21, 9, 0)) == "open"

    def test_closing_within_24_hours(self):
        until = datetime(2026, 10, 23, 13, 30)
        assert written_state(until, datetime(2026, 10, 22, 18, 0)) == "closing"

    def test_closed_after(self):
        until = datetime(2026, 10, 23, 13, 30)
        assert written_state(until, datetime(2026, 10, 24, 0, 1)) == "closed"


class TestBusinessDays:
    def test_weekend_is_not_a_business_day(self):
        assert not is_business_day(date(2026, 10, 24))  # Saturday
        assert not is_business_day(date(2026, 10, 25))  # Sunday

    def test_weekday_is(self):
        assert is_business_day(date(2026, 10, 22))  # Thursday

    def test_committed_holiday_is_not(self):
        assert not is_business_day(date(2026, 11, 26))  # Thanksgiving


class TestAccommodationDeadline:
    def test_three_business_days_before_a_midweek_hearing(self):
        # Thursday 22 Oct -> Wed 21, Tue 20, Mon 19.
        assert accommodation_deadline(date(2026, 10, 22)) == date(2026, 10, 19)

    def test_skips_a_weekend(self):
        # Tuesday 20 Oct -> Mon 19, Fri 16, Thu 15.
        assert accommodation_deadline(date(2026, 10, 20)) == date(2026, 10, 15)

    def test_skips_thanksgiving_week(self):
        # Monday 30 Nov, counting back over business days only:
        #   Sun 29 and Sat 28 are weekend, Fri 27 and Thu 26 are holidays,
        #   Wed 25 = 1, Tue 24 = 2, Mon 23 = 3.
        # A naive `date - 3 days` would land on Friday 27, a holiday.
        result = accommodation_deadline(date(2026, 11, 30))
        assert result == date(2026, 11, 23)
        assert is_business_day(result)

    def test_hearing_day_itself_does_not_count(self):
        result = accommodation_deadline(date(2026, 10, 22))
        assert result < date(2026, 10, 22)


class TestAccommodationState:
    def test_open_before_the_deadline(self):
        assert accommodation_state(date(2026, 10, 22), date(2026, 10, 18)) == "open"

    def test_too_late_after(self):
        assert accommodation_state(date(2026, 10, 22), date(2026, 10, 21)) == "too_late"

    def test_deadline_day_is_still_open(self):
        assert accommodation_state(date(2026, 10, 22), date(2026, 10, 19)) == "open"
