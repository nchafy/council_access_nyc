"""Parsing the real Legistar calendar grid."""

from __future__ import annotations

from datetime import date, time

import pytest

from showup.sources.calendar import (
    CalendarParseError,
    parse_calendar,
    parse_clock,
    parse_us_date,
    upcoming,
)


class TestParseUsDate:
    def test_normal(self):
        assert parse_us_date("12/17/2026") == date(2026, 12, 17)

    def test_single_digits(self):
        assert parse_us_date("1/5/2026") == date(2026, 1, 5)

    def test_impossible_date_is_rejected_not_rolled_over(self):
        # A rolled-over 02/31 -> 03/03 would send someone on the wrong day.
        assert parse_us_date("02/31/2026") is None

    @pytest.mark.parametrize("value", ["", "not a date", "2026-12-17", "13/45/2026"])
    def test_junk(self, value):
        assert parse_us_date(value) is None


class TestParseClock:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("1:30 PM", time(13, 30)),
            ("10:00 AM", time(10, 0)),
            ("12:00 PM", time(12, 0)),
            ("12:00 AM", time(0, 0)),
            ("9:30 a.m.", time(9, 30)),
        ],
    )
    def test_variants(self, raw, expected):
        assert parse_clock(raw) == expected

    def test_deferred_is_not_a_time(self):
        # Never guess a start time — "Deferred" must not become 00:00.
        assert parse_clock("Deferred") is None

    @pytest.mark.parametrize("value", ["", "TBD", "25:00 PM", "noon"])
    def test_unparseable(self, value):
        assert parse_clock(value) is None


class TestParseCalendar:
    def test_parses_the_real_fixture(self, calendar_html):
        meetings = parse_calendar(calendar_html)
        assert len(meetings) == 60

    def test_rejects_a_document_that_is_not_the_calendar(self):
        # Legistar serves error bodies with HTTP 200, so a status check is not
        # enough; this must be a loud failure, not an empty list.
        with pytest.raises(CalendarParseError):
            parse_calendar("<html><body>Invalid feed</body></html>")

    def test_deferred_meetings_have_no_time_but_are_kept(self, calendar_html):
        meetings = parse_calendar(calendar_html)
        deferred = [m for m in meetings if m.time_state == "deferred"]
        assert deferred, "fixture should contain deferred rows"
        for meeting in deferred:
            assert meeting.start_time is None

    def test_every_meeting_has_a_venue_and_a_mode(self, calendar_html):
        for meeting in parse_calendar(calendar_html):
            assert meeting.venue is not None
            assert meeting.attendance_mode in {"in_person", "hybrid", "remote"}

    def test_deadlines_are_computed_for_every_meeting(self, calendar_html):
        for meeting in parse_calendar(calendar_html):
            assert meeting.written_safe_until is not None
            assert meeting.accommodation_by is not None
            assert meeting.accommodation_by < meeting.date

    def test_urls_are_allowlisted_or_none(self, calendar_html):
        for meeting in parse_calendar(calendar_html):
            for url in (meeting.detail_url, meeting.agenda_url, meeting.minutes_url):
                if url is not None:
                    assert url.startswith("https://nyc.legistar.com/")

    def test_placeholder_topic_becomes_none(self, calendar_html):
        # "Multiple meeting items, please see Meeting Details" is not a topic.
        for meeting in parse_calendar(calendar_html):
            if meeting.topic:
                assert not meeting.topic.lower().startswith("multiple meeting items")

    def test_committee_names_contain_no_markup(self, calendar_html):
        for meeting in parse_calendar(calendar_html):
            assert "<" not in meeting.committee
            assert "&lt;" not in meeting.committee


class TestUpcoming:
    def test_returns_five_soonest_in_order(self, calendar_html):
        meetings = parse_calendar(calendar_html)
        result = upcoming(meetings, date(2026, 1, 1), 5)
        assert len(result) == 5
        assert result == sorted(result, key=lambda m: m.date)

    def test_excludes_the_past(self, calendar_html):
        meetings = parse_calendar(calendar_html)
        horizon = date(2026, 11, 1)
        for meeting in upcoming(meetings, horizon, 5):
            assert meeting.date >= horizon

    def test_empty_when_nothing_ahead(self, calendar_html):
        meetings = parse_calendar(calendar_html)
        assert upcoming(meetings, date(2099, 1, 1), 5) == []
