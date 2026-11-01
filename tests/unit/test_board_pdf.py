"""The fifteen boards that publish a schedule as a PDF.

`tests/fixtures/board_pdf_text.json` holds what pypdf actually extracted from each board's
live document on 2026-10-31, in both modes, keyed by board code. It is the extracted text
rather than the PDFs themselves for the same reason the cache stores text: a fixture should
be something a reviewer can read, and `showup build` must not need a PDF parser to run.

Each test names the shape it is pinning. These parsers exist because fifteen boards share a
borough and a file format and nothing else, and the next person here will be here because
one of them redesigned its calendar.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import pytest

from showup.sources.board_pdf import (
    PDF_BOARDS,
    PDF_READERS,
    GridBoard,
    ListBoard,
    _cell_pieces,
    _looks_like_a_week,
    _month_offsets,
    _reassembled_month,
    _split_heading,
    _time_of,
    extract_pdf_text,
    grid_cells,
    parse_pdf,
)

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "board_pdf_text.json"

#: A one-entry October grid, for the tests that are about the envelope rather than about
#: any board's layout.
ONE_CELL_GRID = "11   12   13   14   15   16   17\n          Executive\n          6:30 pm"

#: The day the fixtures were captured. Most of these boards publish only the current
#: month, so a later cutoff would empty the fixture and pin nothing.
TODAY = date(2026, 10, 1)


@pytest.fixture(scope="module")
def documents() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def read(documents: dict, code: str, *, on_or_after: date = TODAY):
    return parse_pdf(code, json.dumps(documents[code]), on_or_after=on_or_after)


#: Every board the fixture covers, and what it must yield. Written down rather than
#: computed so that a board silently dropping to zero fails here.
EXPECTED = {
    "201": 13,
    "203": 0,  # stale: the newest PDF this board published is September 2026
    "204": 10,
    "205": 2,
    "207": 10,
    "209": 10,
    "210": 8,
    "211": 23,
    "301": 6,
    "408": 3,
    "409": 1,
    "412": 12,
    "501": 13,
    "502": 6,
    "503": 6,
}


class TestEveryBoardHasAReader:
    def test_the_registry_is_the_fifteen_pdf_boards(self):
        assert set(PDF_READERS) == set(EXPECTED)

    def test_the_fixture_covers_every_board_with_a_reader(self, documents):
        assert set(documents) == set(PDF_READERS)

    def test_a_board_with_no_reader_yields_nothing_rather_than_raising(self, documents):
        """A board moving onto this path without a reader must fail quietly: the other 44
        boards' schedules do not depend on it."""
        assert parse_pdf("999", json.dumps(documents["207"]), on_or_after=TODAY) == []

    @pytest.mark.parametrize(("code", "count"), sorted(EXPECTED.items()))
    def test_each_reader_yields_the_meetings_it_did_when_measured(self, documents, code, count):
        assert len(read(documents, code)) == count

    @pytest.mark.parametrize("code", sorted(EXPECTED))
    def test_every_meeting_is_dated_ahead_of_the_cutoff_and_titled(self, documents, code):
        for meeting in read(documents, code):
            assert meeting.day >= TODAY
            assert meeting.title
            assert meeting.title.strip() == meeting.title

    @pytest.mark.parametrize("code", sorted(EXPECTED))
    def test_every_reader_returns_them_in_order(self, documents, code):
        found = read(documents, code)
        assert found == sorted(found, key=lambda m: (m.day, m.start_time or ""))

    @pytest.mark.parametrize("code", sorted(EXPECTED))
    def test_no_reader_reports_a_holiday_or_a_closure_as_a_meeting(self, documents, code):
        """A closed office published as a meeting sends somebody to a locked door."""
        for meeting in read(documents, code):
            blob = f"{meeting.title} {meeting.location or ''}".lower()
            for closed in ("office is closed", "office closed", "no meeting", "cancelled"):
                assert closed not in blob, (code, meeting.title)

    @pytest.mark.parametrize("code", sorted(EXPECTED))
    def test_no_reader_leaks_a_contact_detail_into_a_title(self, documents, code):
        """These cells carry an organiser's email and the office phone number. Neither
        belongs in a meeting name, and `718-823-3034` parses as a time."""
        for meeting in read(documents, code):
            assert "@" not in meeting.title
            assert "http" not in meeting.title.lower()


class TestTheTwoExtractionModes:
    """The whole design rests on each mode carrying what the other drops."""

    def test_layout_mode_drops_the_heading_bronx_cb7_needs(self, documents):
        """This is the measurement that decided the dependency, pinned so that a future
        pypdf including the heading is reported rather than silently changing behaviour.

        If this test fails because `OCTOBER 2026` now appears in layout mode, nothing is
        broken — `_heading_month` reads plain mode either way. Update the test.
        """
        [cb7] = documents["207"]
        assert "OCTOBER 2026" not in cb7["layout"]
        assert "OCTOBER 2026" in cb7["plain"]

    def test_plain_mode_flattens_the_grid_that_layout_mode_keeps(self, documents):
        """Plain mode loses the columns, which is the other half of why both are stored."""
        [cb7] = documents["207"]
        assert "SUNDAY        MONDAY" not in cb7["plain"]
        assert any("SUNDAY" in line and "MONDAY" in line for line in cb7["layout"].splitlines())

    def test_extraction_returns_both_modes_and_a_page_count(self):
        """Covers the pypdf call itself, on a document built here rather than committed."""
        from pypdf import PdfWriter

        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        buffer = __import__("io").BytesIO()
        writer.write(buffer)

        extracted = extract_pdf_text(buffer.getvalue())
        assert set(extracted) == {"layout", "plain", "pages"}
        assert extracted["pages"] == "1"


class TestTheGridSkeleton:
    def test_the_day_numbers_are_the_columns_not_the_weekday_headers(self):
        """Bronx CB7 prints `TUESDAY` at column 52 and the `13` under it at column 33.
        Bucketing against the headers put days 12 and 13 in one column and lost one."""
        layout = "\n".join(
            [
                "SUNDAY        MONDAY                       TUESDAY",
                "11       12                13",
                "               HOLIDAY     Housing, Land Use & Economic Development",
                "                                       6:30 pm",
            ]
        )
        cells = {number: lines for number, _offset, lines in grid_cells(layout)}
        assert cells[12] == ["HOLIDAY"]
        assert cells[13] == ["Housing, Land Use & Economic Development", "6:30 pm"]

    def test_a_cell_is_not_merged_with_its_neighbour_across_a_wide_gap(self):
        """The piece regex once used a greedy optional group, so `N` and `7:00PM` 21 spaces
        apart matched as one piece — which merged whole adjacent columns on five boards."""
        assert _cell_pieces("      N                     7:00PM") == [(6, "N"), (28, "7:00PM")]

    def test_a_single_space_is_a_word_break_not_a_cell_boundary(self):
        assert _cell_pieces("   211 East 203rd Street") == [(3, "211 East 203rd Street")]

    def test_two_spaces_are_a_cell_boundary(self):
        assert _cell_pieces("Parks  Housing") == [(0, "Parks"), (7, "Housing")]

    def test_an_empty_line_yields_no_pieces(self):
        assert _cell_pieces("      ") == []

    @pytest.mark.parametrize(
        ("days", "first_row", "expected"),
        [
            # A grid's first row opens with the previous month's tail.
            ([27, 28, 29, 30, 1, 2, 3], True, [-1, -1, -1, -1, 0, 0, 0]),
            # Its last row closes with the next month's head.
            ([29, 30, 31, 1, 2, 3, 4], False, [0, 0, 0, 1, 1, 1, 1]),
            # A whole week inside the month belongs to it.
            ([11, 12, 13, 14, 15, 16, 17], False, [0] * 7),
        ],
    )
    def test_an_edge_row_is_attributed_to_its_own_month(self, days, first_row, expected):
        assert _month_offsets(days, first_row=first_row) == expected

    def test_a_neighbouring_months_entry_is_dropped_rather_than_misdated(self):
        """Without this, an entry printed under September 28 in October's grid would be
        published as October 28 — a wrong date, which is worse than a missing one."""
        layout = "\n".join(
            [
                "27       28         29        30        1         2         3",
                "         Land Use                       Executive",
                "         6:30 pm                        7:00 pm",
            ]
        )
        reader = PDF_READERS["207"]
        found = reader(layout, "OCTOBER 2026", on_or_after=date(2026, 9, 1), url=None)
        assert [(m.day, m.title) for m in found] == [(date(2026, 10, 1), "Executive")]

    @pytest.mark.parametrize(
        ("numbers", "expected"),
        [
            ([(0, "1"), (10, "2"), (20, "3")], True),
            # One reset, at the month boundary.
            ([(0, "30"), (10, "31"), (20, "1")], True),
            # Two resets is not a week.
            ([(0, "30"), (10, "1"), (20, "29"), (30, "2")], False),
            # No day number exceeds 31.
            ([(0, "1"), (10, "2"), (20, "99")], False),
        ],
    )
    def test_a_run_of_numbers_is_only_a_week_if_it_reads_like_one(self, numbers, expected):
        assert _looks_like_a_week(numbers) is expected

    def test_text_before_any_week_row_is_not_assigned_to_a_day(self):
        """A letterhead sits above the grid and belongs to no cell."""
        assert grid_cells("BRONX COMMUNITY BOARD 9\nbx09@cb.nyc.gov") == []

    def test_an_eighth_column_is_a_sidebar_not_a_saturday(self):
        """Bronx CB1 prints a `Community Events` column whose rows carry their own dates.
        Read as Saturday, it would attach other events to a Saturday.

        The cut has to be made on horizontal position: there are only ever seven day
        numbers, so no column *index* can express an eighth column, and an earlier
        `columns_cap` of 7 was dead code that never excluded anything.
        """
        layout = "\n".join(
            [
                "1    2    3    4    5    6    7         Community Events",
                "                                        Wed, Nov 4 Expo",
            ]
        )
        assert grid_cells(layout, sidebar=True) == []
        bled = grid_cells(layout, sidebar=False)
        assert [lines for _, _, lines in bled] == [["Wed, Nov 4 Expo"]]

    def test_a_lone_number_does_not_open_a_week(self):
        """Three is the floor: a grid's last row can be `29 30 31`, but one number is a
        street address or a page number."""
        assert grid_cells("5\n   Land Use") == []

    def test_a_day_the_month_does_not_have_is_dropped(self):
        """A grid's last row can print a 31 under a 30-day month, as part of the next
        month's first week. November has no 31st, and it must not become December 1."""
        layout = "\n".join(
            [
                "29   30   31",
                "     Land Use      Executive",
                "     6:30 pm       7:00 pm",
            ]
        )
        found = PDF_READERS["210"](layout, "November 2026", on_or_after=TODAY, url=None)
        assert [(m.day, m.title) for m in found] == [(date(2026, 11, 30), "Land Use")]


class TestTheTimes:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("6:30 pm", "6:30 PM"),
            ("6PM", "6:00 PM"),
            ("6:30pm", "6:30 PM"),
            ("6.45PM", "6:45 PM"),
            ("7:00 p.m.", "7:00 PM"),
            ("6:30 P.M.", "6:30 PM"),
            ("10:00AM", "10:00 AM"),
            ("7 p.m.", "7:00 PM"),
            ("6PM.", "6:00 PM"),
        ],
    )
    def test_every_form_these_boards_write(self, text, expected):
        assert _time_of(text) == expected

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            # Bronx CB4 writes ranges. The meeting starts at the FIRST hour; matching the
            # plain time pattern alone published the end of the meeting as its start.
            ("6:30-    8:00PM", "6:30 PM"),
            ("7:00PM    -8:30PM", "7:00 PM"),
            ("6:30PM-8:30PM", "6:30 PM"),
        ],
    )
    def test_a_range_reports_the_hour_the_meeting_starts(self, text, expected):
        assert _time_of(text) == expected

    def test_an_ambiguous_hour_reports_no_time_at_all(self):
        """Bronx CB5 writes `5/6PM.`, meaning five or six o'clock. Picking one would send
        somebody to a room an hour early or an hour late."""
        assert _time_of("Public Hearing. 5/6PM.") is None

    @pytest.mark.parametrize("text", ["no time here", "", "13:00 PM", "0:30 pm"])
    def test_text_with_no_usable_hour(self, text):
        assert _time_of(text) is None


class TestTheHeadings:
    def test_a_month_and_year_printed_apart_are_still_one_heading(self):
        """Bronx CB3 centres the month and right-aligns the year, so plain mode puts them
        on different lines with the board's name between them."""
        assert _split_heading("September\nBronx Community Board 3\n2026") == (9, 2026)

    def test_a_month_with_no_year_near_it_is_not_a_heading(self):
        assert _split_heading("September\n\n\n\n\n\n2026") is None

    def test_a_document_with_no_month_has_no_heading(self):
        assert _split_heading("Bronx Community Board 3\nbx03@cb.nyc.gov") is None

    def test_a_vertically_printed_month_is_reassembled(self):
        """Bronx CB9 sets `NOVEMBER` down the left margin, one letter per line. Layout mode
        scatters those letters into the grid rows they are level with, so this reads plain
        mode, where they arrive consecutively."""
        assert _reassembled_month("N\nO\nV\nE\nM\nB\nE\nR\n2026") == (11, 2026)

    def test_stray_letters_that_spell_no_month_are_not_one(self):
        assert _reassembled_month("X\nY\nZ\n2026") is None

    def test_letters_with_no_year_after_them_are_not_a_heading(self):
        assert _reassembled_month("N\nO\nV\nE\nM\nB\nE\nR\nCalendar") is None

    def test_a_grid_with_no_heading_yields_nothing_rather_than_guessing(self):
        """A grid prints only day numbers. Without the heading there is no year, and
        assuming the current month would invent a schedule for whenever the build ran."""
        layout = "1   2   3   4   5   6   7\n    Land Use\n    6:30 pm"
        assert PDF_READERS["207"](layout, "no month here", on_or_after=TODAY, url=None) == []

    def test_the_year_may_come_before_the_month(self, documents):
        """Bronx CB4 heads its grid `2026   OCTOBER`."""
        assert PDF_BOARDS["204"].year_first is True
        assert read(documents, "204")[0].day.year == 2026


class TestHolidaysAndClosures:
    def test_a_holiday_sharing_a_cell_with_a_meeting_keeps_the_meeting(self, documents):
        """Bronx CB9 prints `Veterans Day` in the same Wednesday cell as a 7:00pm NYPD
        precinct council meeting. Dropping the cell would lose a real meeting; keeping the
        marker would publish a public holiday as one."""
        on_the_day = [m for m in read(documents, "209") if m.day == date(2026, 11, 11)]
        assert [m.title for m in on_the_day] == ["NYPD 43rd Pct Council"]

    def test_a_cell_that_is_only_a_closure_is_dropped(self):
        """Bronx CB7 writes `HOLIDAY / (OFFICE IS / CLOSED)`. Removing the first line
        leaves `(OFFICE IS CLOSED)`, which is still not a meeting."""
        layout = "\n".join(
            [
                "11       12                13",
                "               HOLIDAY",
                "              (OFFICE IS",
                "               CLOSED)",
            ]
        )
        found = PDF_READERS["207"](layout, "OCTOBER 2026", on_or_after=TODAY, url=None)
        assert found == []

    def test_a_bare_office_line_is_not_a_meeting(self):
        """Bronx CB11 writes `OFFICE / CLOSED: / Veterans Day` down one cell. Removing the
        closure lines leaves a bare `OFFICE`."""
        layout = "8   9   10   11   12   13   14\n        OFFICE\n        CLOSED:\n   Veterans Day"
        found = PDF_READERS["211"](layout, "November 2026", on_or_after=TODAY, url=None)
        assert found == []

    def test_a_curly_apostrophe_does_not_hide_a_holiday(self):
        """A curly apostrophe (U+2019) slipped past a pattern spelling only the straight
        one, and the holiday was published as a meeting."""
        layout = "8   9   10   11   12   13   14\n        Veterans’ Day"
        assert PDF_READERS["210"](layout, "November 2026", on_or_after=TODAY, url=None) == []

    def test_the_documents_own_footer_is_not_a_meeting(self):
        """Several of these grids print their footer inside the last week's row. Bronx
        CB10's `Call the Board Office at 718-892-1161 to confirm all meetings` was
        published as an 11:09 AM meeting on 30 November."""
        layout = "\n".join(
            [
                "22   23   24   25   26   27   28",
                "     Call the Board Office at 718-892-1161 to confirm all meetings.",
            ]
        )
        assert PDF_READERS["210"](layout, "November 2026", on_or_after=TODAY, url=None) == []

    def test_an_organisers_email_does_not_disqualify_a_real_meeting(self):
        """The footer filter once matched any email, which would have dropped a real Bronx
        CB3 meeting whose cell carries the organiser's address."""
        layout = "\n".join(
            [
                "6   7   8   9   10   11   12",
                "    PSA 7 Community Council",
                "    Meeting 5:00 PM",
                "    Jesus.Correa@nypd.org",
            ]
        )
        [meeting] = PDF_READERS["203"](layout, "October 2026", on_or_after=TODAY, url=None)
        assert meeting.start_time == "5:00 PM"
        assert "@" not in meeting.title


class TestTheCellSplit:
    def test_the_time_divides_the_name_from_the_venue(self, documents):
        """Layout mode breaks a cell's name across as many lines as the column is narrow,
        so taking the first line produced titles like `& Ethics`."""
        [meeting] = [m for m in read(documents, "207") if m.day == date(2026, 10, 13)]
        assert meeting.title == "Housing, Land Use & Economic Development"
        assert meeting.location == "The Bedford Community Room 211 East 203rd Street"

    def test_a_name_split_over_two_lines_is_rejoined(self, documents):
        [meeting] = [m for m in read(documents, "502") if m.day == date(2026, 10, 4)]
        assert meeting.title == "Traffic/Transportation / Public Service"

    def test_a_cell_whose_hour_comes_first_keeps_its_whole_name(self, documents):
        """Bronx CB11 leads with the hour, so there is nothing before the divider and the
        whole cell becomes the name — longer than the others, and never wrong."""
        [meeting] = [m for m in read(documents, "211") if m.day == date(2026, 11, 10)]
        assert meeting.start_time == "7:00 PM"
        assert meeting.title == "Health & Social Services Committee"

    def test_a_hyperlink_label_is_not_part_of_the_name(self, documents):
        for meeting in read(documents, "211"):
            assert "click here" not in meeting.title.lower()

    def test_a_cell_with_no_time_becomes_its_own_name(self):
        layout = "1   2   3   4   5   6   7\n    Executive Board Committee"
        [meeting] = PDF_READERS["412"](layout, "October 2026", on_or_after=TODAY, url=None)
        assert meeting.title == "Executive Board Committee"
        assert meeting.start_time is None

    def test_a_name_that_cleans_away_to_digits_falls_back_to_the_whole_cell(self):
        """Bronx CB4 writes `6:30-` on one line and `8:00PM` on the next, so the divider
        lands below the start time and everything above it is the digits of a range."""
        layout = "\n".join(
            [
                "5    6    7    8    9    10   11",
                "6:30-",
                "     8:00PM",
                "HOUSING & LAND USE",
                "COMMITTEE MEETING",
            ]
        )
        [meeting] = PDF_READERS["204"](layout, "2026 OCTOBER", on_or_after=TODAY, url=None)
        assert "HOUSING & LAND USE" in meeting.title
        assert meeting.title.strip(" 0123456789:.-") == meeting.title.lstrip(" 0123456789:.-")


class TestTheQuirkyDayNumbers:
    def test_a_trailing_period_on_a_day_number(self, documents):
        """Staten Island CB2 writes `1.` `2.` `4.` `10.`"""
        assert any(m.day == date(2026, 10, 4) for m in read(documents, "502"))

    def test_a_zero_padded_day_number(self, documents):
        """Queens CB12 writes `01 02 03`."""
        assert any(m.day == date(2026, 10, 5) for m in read(documents, "412"))

    def test_a_grid_with_no_weekday_header_row_at_all(self, documents):
        """Bronx CB4 prints no Sunday-to-Saturday labels, which is why a week is opened by
        a row of day numbers and never by a header."""
        [cb4] = documents["204"]
        assert "SUNDAY" not in cb4["layout"].upper()
        assert read(documents, "204")

    def test_an_abbreviated_weekday_header_row(self, documents):
        """Queens CB12 writes `SUN MON TUE WED THU FRI SAT`."""
        [cb12] = documents["412"]
        assert "SUN" in cb12["layout"] and "SUNDAY" not in cb12["layout"].upper()
        assert read(documents, "412")

    def test_a_vertically_printed_month_does_not_pollute_a_cell(self, documents):
        """CB9's margin letters land in whichever cell they are level with. No committee is
        named in one or two letters, so they are dropped as pieces."""
        for meeting in read(documents, "209"):
            assert len(meeting.title) > 2
            assert meeting.title not in {"N", "O", "V", "E", "M", "B", "RE"}

    def test_a_generation_stamp_is_not_a_meeting(self, documents):
        """Bronx CB10 prints `10/22/2026` inside the last week's row. It was published as
        an 11:09 AM meeting on 28 November — a date nobody can attend."""
        for code in ("210", "211"):
            for meeting in read(documents, code):
                assert not re.search(r"\d{1,2}/\d{1,2}/\d{2,4}", meeting.title), meeting.title

    def test_a_stamp_sharing_a_cell_leaves_nothing_behind(self):
        layout = "22   23   24   25   26   27   28\n                              10/22/2026"
        assert PDF_READERS["210"](layout, "November 2026", on_or_after=TODAY, url=None) == []


class TestTheListBoards:
    def test_brooklyn_cb1_reads_slash_dates_under_a_bare_year_header(self, documents):
        """`2026` on its own line, then `Tuesday 01/13`. The list spans two years."""
        found = read(documents, "301")
        assert {m.day.year for m in found} == {2026, 2027}
        assert date(2027, 1, 12) in [m.day for m in found]

    def test_brooklyn_cb1s_duplicated_list_is_read_once(self, documents):
        """This document's schedule appears twice in the extracted text."""
        days = [m.day for m in read(documents, "301")]
        assert len(days) == len(set(days))

    def test_queens_cb8_takes_its_year_from_the_title(self, documents):
        """`2026 BOARD MEETING SCHEDULE`, then `January 7th` — no year on any row."""
        assert all(m.day.year == 2026 for m in read(documents, "408"))

    def test_queens_cb8_reports_no_time_because_the_document_states_none(self, documents):
        assert all(m.start_time is None for m in read(documents, "408"))

    def test_an_ordinal_suffix_is_read(self):
        reader = PDF_READERS["408"]
        found = reader(
            "", "2026 BOARD MEETING SCHEDULE\nNovember 18th", on_or_after=TODAY, url=None
        )
        assert [m.day for m in found] == [date(2026, 11, 18)]

    def test_a_list_row_with_no_year_anywhere_is_dropped(self):
        assert PDF_READERS["408"]("", "January 7th", on_or_after=TODAY, url=None) == []

    def test_prose_that_merely_mentions_a_date_is_not_an_entry(self):
        """Brooklyn CB1's closing paragraph names a date in a sentence."""
        plain = (
            "2026\n"
            "Tuesday 01/13\n"
            "Please note that the meeting scheduled for 02/10 may be moved at the "
            "discretion of the chair, who will advise the board in due course.\n"
        )
        found = PDF_READERS["301"]("", plain, on_or_after=date(2026, 1, 1), url=None)
        assert [m.day for m in found] == [date(2026, 1, 13)]

    def test_an_impossible_date_is_dropped_rather_than_clamped(self):
        """`02/30` is not a date, and must not become March 2."""
        found = PDF_READERS["301"]("", "2027\nTuesday 02/30", on_or_after=TODAY, url=None)
        assert found == []

    def test_an_impossible_named_date_is_dropped(self):
        found = PDF_READERS["408"]("", "2027 SCHEDULE\nFebruary 30th", on_or_after=TODAY, url=None)
        assert found == []

    def test_a_row_naming_its_own_year_overrides_the_section(self):
        found = PDF_READERS["301"]("", "2026\nTuesday 01/13/2027", on_or_after=TODAY, url=None)
        assert [m.day for m in found] == [date(2027, 1, 13)]

    def test_a_past_row_is_dropped(self):
        assert PDF_READERS["301"]("", "2020\nTuesday 01/13", on_or_after=TODAY, url=None) == []

    def test_a_cancelled_row_is_not_a_meeting(self):
        plain = "2027\nTuesday 01/12 CANCELLED"
        assert PDF_READERS["301"]("", plain, on_or_after=TODAY, url=None) == []

    def test_a_row_with_no_date_is_skipped(self):
        assert (
            PDF_READERS["408"]("", "2027 SCHEDULE\nCall the office", on_or_after=TODAY, url=None)
            == []
        )

    def test_an_empty_document_yields_nothing(self):
        for code in ("301", "408"):
            assert PDF_READERS[code]("", "", on_or_after=TODAY, url=None) == []


class TestQueensCb9:
    """One agenda PDF per monthly meeting, on labelled lines. This board's page links
    agendas rather than a schedule, so each document yields exactly one meeting."""

    def test_it_reads_the_date_time_and_place(self, documents):
        [meeting] = read(documents, "409")
        assert meeting.day == date(2026, 11, 10)
        assert meeting.start_time == "7:15 PM"
        assert "Queens Borough Hall" in (meeting.location or "")

    def test_a_document_with_no_date_field_yields_nothing(self):
        layout = "TIME:   7:15 PM\nPLACE:  Queens Borough Hall"
        assert PDF_READERS["409"](layout, "", on_or_after=TODAY, url=None) == []

    def test_an_unparseable_date_field_yields_nothing(self):
        assert PDF_READERS["409"]("DATE:   sometime soon", "", on_or_after=TODAY, url=None) == []

    def test_a_past_agenda_is_dropped(self):
        layout = "DATE:   Tuesday, November 10, 2020\nTIME:   7:15 PM"
        assert PDF_READERS["409"](layout, "", on_or_after=TODAY, url=None) == []

    def test_only_the_first_value_of_a_repeated_label_is_taken(self):
        layout = "DATE:   Tuesday, November 10, 2026\nDATE:   Wednesday, December 9, 2026"
        [meeting] = PDF_READERS["409"](layout, "", on_or_after=TODAY, url=None)
        assert meeting.day == date(2026, 11, 10)


class TestStatenIslandCb1:
    """A month grid on page 1, then one agenda per meeting on the pages after it."""

    def test_it_reads_the_middot_headers_on_the_agenda_pages(self, documents):
        found = {(m.day, m.start_time): m.title for m in read(documents, "501")}
        assert found[(date(2026, 11, 4), "6:30 PM")] == "Land Use"

    def test_it_also_reads_the_full_board_meeting_off_the_grid(self, documents):
        """The committee agendas do not cover the full board, so the grid is read too."""
        titles = [m.title for m in read(documents, "501")]
        assert "Full Board Meeting" in titles

    def test_a_meeting_in_both_halves_is_published_once(self, documents):
        keys = [(m.day, m.start_time) for m in read(documents, "501")]
        assert len(keys) == len(set(keys))

    def test_decorative_prose_is_not_a_meeting(self, documents):
        """This board writes `Set clocks back 1 hour at 2 AM` in a cell. The `2 AM` is not
        a meeting, and `Fall back, sleepyheads!` is not a committee."""
        for meeting in read(documents, "501"):
            assert "sleepyhead" not in meeting.title.lower()
            assert "clocks back" not in meeting.title.lower()
            assert meeting.start_time != "2:00 AM"

    def test_a_document_with_no_heading_yields_nothing(self):
        layout = "WED  ·  NOV 4  ·  6:30 PM  ·  Land Use"
        assert PDF_READERS["501"](layout, "no month", on_or_after=TODAY, url=None) == []

    def test_an_unknown_month_abbreviation_is_skipped(self):
        layout = "WED  ·  XXX 4  ·  6:30 PM  ·  Land Use"
        assert PDF_READERS["501"](layout, "November 2026", on_or_after=TODAY, url=None) == []

    def test_an_impossible_agenda_date_is_skipped(self):
        layout = "WED  ·  NOV 31  ·  6:30 PM  ·  Land Use"
        assert PDF_READERS["501"](layout, "November 2026", on_or_after=TODAY, url=None) == []

    def test_a_past_agenda_header_is_dropped(self):
        layout = "WED  ·  NOV 4  ·  6:30 PM  ·  Land Use"
        assert PDF_READERS["501"](layout, "November 2020", on_or_after=TODAY, url=None) == []

    def test_a_repeated_agenda_header_is_read_once(self):
        layout = "\n".join(
            [
                "WED  ·  NOV 4  ·  6:30 PM  ·  Land Use",
                "WED  ·  NOV 4  ·  6:30 PM  ·  Land Use",
            ]
        )
        found = PDF_READERS["501"](layout, "November 2026", on_or_after=TODAY, url=None)
        assert len(found) == 1


class TestTheEnvelopeAndTheDispatch:
    def test_several_pdfs_are_read_and_their_overlap_collapsed(self, documents):
        """Bronx CB11 links November and December at once, and the two overlap."""
        assert len(documents["211"]) == 2
        keys = [(m.day, m.title, m.start_time) for m in read(documents, "211")]
        assert len(keys) == len(set(keys))

    def test_the_same_meeting_in_two_pdfs_is_published_once(self):
        """These pages link overlapping months, so a meeting genuinely arrives twice."""
        document = {
            "layout": ONE_CELL_GRID,
            "plain": "OCTOBER 2026",
        }
        once = parse_pdf("207", json.dumps([document]), on_or_after=TODAY)
        twice = parse_pdf("207", json.dumps([document, dict(document)]), on_or_after=TODAY)
        assert len(once) == len(twice) == 1

    def test_the_url_of_the_pdf_a_meeting_came_from_is_kept(self, documents):
        for meeting in read(documents, "207"):
            assert meeting.url and meeting.url.endswith(".pdf")

    def test_an_envelope_that_is_not_json_yields_nothing(self):
        assert parse_pdf("207", "{not json", on_or_after=TODAY) == []

    def test_an_envelope_that_is_not_an_array_yields_nothing(self):
        assert parse_pdf("207", '{"layout": "x"}', on_or_after=TODAY) == []

    def test_an_entry_that_is_not_an_object_is_skipped(self):
        assert parse_pdf("207", '["not an object"]', on_or_after=TODAY) == []

    def test_an_entry_missing_both_modes_is_not_an_error(self):
        assert parse_pdf("207", "[{}]", on_or_after=TODAY) == []

    def test_an_entry_with_no_url_is_still_read(self):
        envelope = json.dumps(
            [
                {
                    "layout": ONE_CELL_GRID,
                    "plain": "OCTOBER 2026",
                }
            ]
        )
        [meeting] = parse_pdf("207", envelope, on_or_after=TODAY)
        assert meeting.url is None

    def test_the_kind_is_dispatched_from_the_shared_reader(self):
        """`parse_feed` is what the cache loader calls, so the PDF branch must be wired."""
        from showup.sources.board_meetings import parse_feed

        envelope = json.dumps(
            [
                {
                    "layout": ONE_CELL_GRID,
                    "plain": "OCTOBER 2026",
                }
            ]
        )
        found = parse_feed("nyc-pdf", envelope, on_or_after=TODAY, code="207")
        assert [m.title for m in found] == ["Executive"]


class TestTheConfiguration:
    def test_every_board_is_a_grid_or_a_list_or_has_its_own_function(self):
        bespoke = set(PDF_READERS) - set(PDF_BOARDS)
        assert bespoke == {"409", "501"}
        for code, board in PDF_BOARDS.items():
            assert isinstance(board, GridBoard | ListBoard), code

    def test_only_bronx_cb1_has_a_sidebar_column(self):
        with_sidebar = {c for c, b in PDF_BOARDS.items() if getattr(b, "sidebar", False)}
        assert with_sidebar == {"201"}

    def test_only_bronx_cb9_reassembles_a_vertical_month(self):
        reassembling = {c for c, b in PDF_BOARDS.items() if getattr(b, "month_from_letters", False)}
        assert reassembling == {"209"}

    def test_only_bronx_cb4_reads_a_year_first_heading(self):
        year_first = {c for c, b in PDF_BOARDS.items() if getattr(b, "year_first", False)}
        assert year_first == {"204"}


class TestWhatItRefusesToClaim:
    def test_a_pdf_meeting_carries_no_attendance_mode_or_deadline(self, documents):
        """A grid cell says none of this, and `model.Meeting` has it only because Legistar
        publishes it. Inventing it here would be the worst failure available."""
        [meeting] = read(documents, "409")
        for invented in ("attendance_mode", "written_safe_until", "topic", "time_state"):
            assert not hasattr(meeting, invented), invented

    def test_a_recurrence_stated_in_prose_is_not_expanded(self):
        """Queens CB8's memo says the board meets monthly. Only the printed dates are
        read: a date we did not list is a gap, a date we invented is a wrong answer."""
        plain = "2027 SCHEDULE\nThe board meets on the second Wednesday of every month."
        assert PDF_READERS["408"]("", plain, on_or_after=TODAY, url=None) == []
