"""The six per-board readers for boards that publish a schedule as nyc.gov HTML.

The fixtures under `tests/fixtures/board_html/` are real pages, trimmed to a window that
parses to exactly the same result the whole page did — a fixture that parses differently
from the thing it stands for is not a fixture.

Each test names the shape it is pinning, because these parsers exist precisely because the
six pages share a host and a CMS and nothing else, and the next person here will be here
because one of them changed.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from showup.sources.board_html import HTML_READERS, lines_of, parse_html

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "board_html"
TODAY = date(2026, 10, 31)


def page(code: str) -> str:
    return (FIXTURES / f"{code}.html").read_text(encoding="utf-8")


def read(code: str):
    return parse_html(code, page(code), on_or_after=TODAY)


class TestEveryBoardHasAReader:
    def test_the_six_boards_are_the_registry(self):
        assert set(HTML_READERS) == {
            "103",
            "304",
            "313",
            "315",
            "318",
            "401",
            "407",
            "411",
            "414",
        }

    def test_a_board_with_no_reader_yields_nothing_rather_than_raising(self):
        """A board that moves onto this path without a reader must fail quietly: the
        other 53 boards' schedules do not depend on it."""
        assert parse_html("999", page("103"), on_or_after=TODAY) == []

    @pytest.mark.parametrize("code", sorted(HTML_READERS))
    def test_each_reader_finds_dated_meetings_ahead_of_the_cutoff(self, code):
        found = read(code)
        assert found, code
        for meeting in found:
            assert meeting.day >= TODAY
            assert meeting.title

    @pytest.mark.parametrize("code", sorted(HTML_READERS))
    def test_each_reader_returns_them_in_order(self, code):
        days = [m.day for m in read(code)]
        assert days == sorted(days)


class TestManhattanCb3:
    """`Calendar of Meetings - November 2026`, then
    `Thursday, November 5 at 6:30pm -- Community Board 3 Office - 59 East 4th Street`.
    The year appears only in the heading."""

    def test_it_takes_the_year_from_the_heading(self):
        assert all(m.day.year == 2026 for m in read("103"))

    def test_it_reads_the_time_and_the_venue_after_the_dashes(self):
        first = read("103")[0]
        assert first.start_time == "6:30 PM"
        assert "59 East 4th Street" in (first.location or "")

    def test_it_does_not_invent_a_committee_name(self):
        """These lines name no committee, so the title stays generic rather than being
        guessed from the venue."""
        assert all("Community Board 3 Office" not in m.title for m in read("103"))


class TestBrooklynCb4:
    """A bare year on its own line, then `December 16th Public Hearing and Regular
    Meeting`. Ordinal suffixes, newest first, and no times anywhere on the page."""

    def test_it_reads_the_ordinal_dates(self):
        assert [m.day for m in read("304")] == [date(2026, 11, 18), date(2026, 12, 16)]

    def test_it_keeps_the_title_and_drops_the_date_from_it(self):
        first = read("304")[0]
        assert first.title == "Public Hearing and Regular Meeting"

    def test_it_reports_no_time_because_the_page_states_none(self):
        assert all(m.start_time is None for m in read("304"))


class TestBrooklynCb15:
    """`Tuesday, November 17, 2026` followed by the title, the time and the venue on the
    lines after it, so the details belong to the date line above them."""

    def test_it_pairs_the_details_with_the_date_above_them(self):
        [meeting] = read("315")
        assert meeting.day == date(2026, 11, 17)
        assert meeting.start_time == "7:00 PM"
        assert "Kingsborough" in (meeting.location or "")

    def test_the_title_does_not_swallow_the_time(self):
        [meeting] = read("315")
        assert meeting.title == "General Board Meeting (In Person)"
        assert "7:00" not in meeting.title


class TestBrooklynCb18:
    """A bare list of dates, some with ordinal suffixes, and the time only in prose."""

    def test_it_reads_every_date_in_the_list(self):
        assert len(read("318")) == 8

    def test_it_handles_an_ordinal_in_the_middle_of_the_list(self):
        """`February 24th, 2027` sits among plain `January 20, 2027` entries."""
        assert date(2027, 2, 24) in [m.day for m in read("318")]

    def test_it_does_not_attach_the_prose_time(self):
        """The page gives the hour in a sentence about the third Wednesday, and marks
        exceptions by colour. A colour is not something this can read."""
        assert all(m.start_time is None for m in read("318"))


class TestQueensCb1:
    """Sections of dates where only the first entry states a time."""

    def test_it_reads_the_whole_listing(self):
        assert len(read("401")) == 41

    def test_it_does_not_carry_a_section_time_down_the_list(self):
        """This page states the hour once, on the first entry of a section, and leaves the
        rest bare. Carrying it down was tried and removed: the sections are not reliably
        delimited in the markup, so it risked putting the full board's hour on a
        committee's date. An absent time is a gap; a wrong one sends somebody to a room at
        the wrong hour.

        Every upcoming entry here is bare, because the one line that does state a time is
        dated September and falls before the cutoff.
        """
        assert all(m.start_time is None for m in read("401"))

    def test_it_still_reads_a_time_printed_on_the_line(self):
        found = parse_html("401", "<p>November 17, 2026 - 6:00 PM</p>", on_or_after=TODAY)
        assert [m.start_time for m in found] == ["6:00 PM"]


class TestQueensCb7:
    """One sentence naming the next meeting, with the venue beneath it."""

    def test_it_reads_the_single_meeting_the_board_publishes(self):
        [meeting] = read("407")
        assert meeting.day == date(2026, 11, 16)
        assert meeting.start_time == "7:00 PM"
        assert "Tosi" in (meeting.location or "")


class TestTheSharedHelpers:
    def test_lines_keep_block_boundaries(self):
        """`strip_tags` alone flattens a table to one line, which loses exactly the
        structure these readers need."""
        assert lines_of("<ul><li>one</li><li>two</li></ul>") == ["one", "two"]

    def test_entities_are_resolved(self):
        assert lines_of("<p>Regular &amp; Public Hearing</p>") == ["Regular & Public Hearing"]

    def test_script_and_style_contents_are_dropped(self):
        assert lines_of("<script>var d='November 5'</script><p>ok</p>") == ["ok"]

    @pytest.mark.parametrize("markup", ["", "   ", "<p></p>", "<div><span></span></div>"])
    def test_an_empty_page_yields_no_lines(self, markup):
        assert lines_of(markup) == []

    def test_a_page_with_no_dates_yields_no_meetings(self):
        for code in HTML_READERS:
            assert parse_html(code, "<p>Call the office.</p>", on_or_after=TODAY) == []

    def test_an_impossible_date_is_dropped_rather_than_clamped(self):
        """`February 30` is not a date, and must not become March 2."""
        assert parse_html("318", "<p>February 30, 2027</p>", on_or_after=TODAY) == []

    def test_a_past_date_is_dropped(self):
        assert parse_html("318", "<p>January 20, 2020</p>", on_or_after=TODAY) == []


class TestTheUncoveredEdges:
    """Branches the real pages happen not to exercise, pinned so they stay deliberate."""

    def test_an_out_of_range_hour_is_not_a_time(self):
        """`13:00 pm` is not a thing. Dropping it is better than reporting hour 13 with a
        meridiem, which would render as nonsense."""
        found = parse_html("401", "<p>November 17, 2026 - 13:00 PM</p>", on_or_after=TODAY)
        assert [m.start_time for m in found] == [None]

    def test_cb15_keeps_an_entry_whose_details_have_no_time(self):
        markup = "<p>Tuesday, November 17, 2026</p><p>General Board Meeting</p>"
        [meeting] = parse_html("315", markup, on_or_after=TODAY)
        assert (meeting.start_time, meeting.location) == (None, None)
        assert meeting.title == "General Board Meeting"

    def test_cb7_ignores_a_sentence_about_a_past_meeting(self):
        markup = "<p>Our Regular meeting will be January 5, 2020 at 7:00 p.m.</p>"
        assert parse_html("407", markup, on_or_after=TODAY) == []

    def test_cb7_reports_the_meeting_even_without_a_venue_line(self):
        markup = "<p>Our Regular meeting will be November 16, 2026 at 7:00 p.m.</p>"
        [meeting] = parse_html("407", markup, on_or_after=TODAY)
        assert meeting.location is None

    def test_cb18_ignores_prose_that_merely_mentions_a_date(self):
        """This board's list is one bare date per line. A long line carrying a date is the
        page explaining itself, not an entry — taking it would add a phantom meeting."""
        markup = (
            "<p>November 18, 2026</p>"
            "<p>Please note that the meeting scheduled for November 25, 2026 has been "
            "moved at the discretion of the chair.</p>"
        )
        assert [m.day for m in parse_html("318", markup, on_or_after=TODAY)] == [date(2026, 11, 18)]

    def test_cb4_without_a_year_heading_reports_nothing(self):
        """The year is only ever on a line of its own. Without it there is no date to be
        had, and guessing the current year would silently invent a schedule."""
        assert parse_html("304", "<p>December 16th Regular Meeting</p>", on_or_after=TODAY) == []


class TestBrooklynCb13:
    """A centred block on the **home page**, pasted out of Outlook.

    `Wednesday, September 23, @ 7 PM (2601 Ocean Pkwy-South Brooklyn Hospital, 2nd floor
    Auditorium)`. The earlier record said this board published minutes only; it does not.
    """

    def test_it_takes_the_year_from_the_heading(self):
        """`Upcoming Brooklyn Community Board 13 Meetings for 2026 Calendar` is the only
        place the year appears — no row carries one."""
        assert [m.day for m in read("313")] == [date(2026, 11, 18), date(2026, 12, 16)]

    def test_it_reads_the_hour_and_the_venue_in_brackets(self):
        first = read("313")[0]
        assert first.start_time == "7:00 PM"
        assert "South Brooklyn Hospital" in (first.location or "")
        assert "(" not in (first.location or "")

    def test_it_requires_the_weekday_that_opens_every_row(self):
        """These rows sit on the home page among everything else a board puts there.
        Without the weekday as an anchor, a sentence naming a month becomes a meeting."""
        markup = "<p>Meetings for 2026 Calendar</p><p>Our October 28 vote was postponed.</p>"
        assert parse_html("313", markup, on_or_after=TODAY) == []

    def test_without_the_heading_it_reports_nothing(self):
        """The year is only in the heading. Assuming the current one would invent a
        schedule for whatever year the build ran in."""
        markup = "<p>Wednesday, November 18, @ 7 PM (Somewhere)</p>"
        assert parse_html("313", markup, on_or_after=TODAY) == []

    def test_a_row_with_no_bracketed_venue_still_reports_the_meeting(self):
        markup = "<p>Meetings for 2026 Calendar</p><p>Wednesday, November 18, @ 7 PM</p>"
        [meeting] = parse_html("313", markup, on_or_after=TODAY)
        assert meeting.location is None


class TestQueensCb11:
    """A flat `<ul>` of full dates, with the hour in one sentence beneath it."""

    def test_it_reads_the_dates(self):
        assert [m.day for m in read("411")] == [date(2026, 11, 2), date(2026, 12, 7)]

    def test_it_takes_the_hour_the_page_states_for_the_whole_list(self):
        """`**Meetings are held at 7:30 pm` governs this one flat list, and the page names
        no exception. That is reading what the page says — unlike Brooklyn CB18, whose
        exceptions are marked by colour, and Queens CB1, whose sections the markup does not
        delimit."""
        assert [m.start_time for m in read("411")] == ["7:30 PM", "7:30 PM"]

    def test_without_the_sentence_no_hour_is_invented(self):
        markup = "<ul><li>November 2, 2026</li></ul>"
        [meeting] = parse_html("411", markup, on_or_after=TODAY)
        assert meeting.start_time is None

    def test_prose_naming_a_date_is_not_an_entry(self):
        """A row here is a date and nothing else."""
        markup = "<p>Please register to speak by November 2, 2026 at the latest.</p>"
        assert parse_html("411", markup, on_or_after=TODAY) == []


class TestQueensCb14:
    """A year's full-board dates, plus one dated label per agenda link."""

    def test_it_reads_the_ordinal_dates_in_the_year_list(self):
        assert date(2026, 12, 8) in [m.day for m in read("414")]

    def test_it_reads_the_committee_off_each_agenda_label(self):
        found = {m.day: m.title for m in read("414")}
        assert found[date(2026, 11, 2)] == "Housing and Land Use Committee"

    def test_a_day_whose_agenda_is_posted_is_not_published_twice(self):
        """The year's list and the agenda labels describe the same board meetings. The
        label is the better of the two because it names the committee, so the generic
        entry yields to it."""
        days = [m.day for m in read("414")]
        assert len(days) == len(set(days))
        assert {m.title for m in read("414") if m.day == date(2026, 11, 10)} == {
            "Monthly Board Meeting"
        }

    def test_it_reports_no_time_and_no_venue(self):
        """The page names two alternating locations in prose and says to check the agenda
        for which; the agendas are scanned images. The prose hour covers the monthly board
        meetings and not the committees, which share this page."""
        for meeting in read("414"):
            assert meeting.start_time is None
            assert meeting.location is None

    def test_an_impossible_agenda_label_date_is_dropped(self):
        markup = "<p><a>Monthly Board Agenda, February 30, 2027</a></p>"
        assert parse_html("414", markup, on_or_after=TODAY) == []

    def test_prose_naming_its_two_venues_is_not_an_entry(self):
        markup = "<p>Meetings alternate between the two locations listed below for 2026.</p>"
        assert parse_html("414", markup, on_or_after=TODAY) == []
