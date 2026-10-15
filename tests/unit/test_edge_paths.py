"""The defensive branches: malformed input that reaches a guard rather than a parser.

Each is here because the branch is genuinely reachable from real upstream data, not to
touch a line for the 100% floor. An unreachable branch is deleted instead.
"""

from __future__ import annotations

import json
from datetime import date

from showup.sources.boards import _board_website, _board_website_hostname, load_boards
from showup.sources.calendar import parse_calendar
from showup.sources.members import current_by_district, load_members
from showup.urls import absolutize, safe_url


class TestUrlGuards:
    def test_absolutize_rejects_empty_input(self):
        assert absolutize(None, "https://nyc.legistar.com/") is None
        assert absolutize("", "https://nyc.legistar.com/") is None
        assert absolutize("   ", "https://nyc.legistar.com/") is None

    def test_safe_url_rejects_a_value_that_is_only_control_characters(self):
        assert safe_url("\x00\x01\x02") is None

    def test_safe_url_survives_a_string_urlsplit_rejects(self):
        # An unclosed IPv6-looking bracket makes urlsplit raise.
        assert safe_url("https://[oops") is None

    def test_relative_href_with_a_base_that_strips_to_nothing(self):
        assert safe_url("\x00", base="https://nyc.legistar.com/") is None


class TestBoardWebsiteGuards:
    """`cb_website` is a nested `{"url": ...}`, and only City-operated hosts are linked."""

    def test_the_nested_socrata_shape_is_unwrapped(self):
        # Read as a string this becomes "{'url': ...}" and every board loses its link.
        assert (
            _board_website({"url": "https://www.nyc.gov/site/queenscb9/index.page"})
            == "https://www.nyc.gov/site/queenscb9/index.page"
        )

    def test_the_old_www1_hostname_is_normalised(self):
        assert (
            _board_website({"url": "https://www1.nyc.gov/site/manhattancb1/index.page"})
            == "https://www.nyc.gov/site/manhattancb1/index.page"
        )

    def test_a_city_url_published_as_http_is_upgraded(self):
        assert (
            _board_website({"url": "http://www.nyc.gov/manhattancb3"})
            == "https://www.nyc.gov/manhattancb3"
        )

    def test_the_city_wordpress_network_is_linked(self):
        assert (
            _board_website({"url": "https://cbmanhattan.cityofnewyork.us/cb4/"})
            == "https://cbmanhattan.cityofnewyork.us/cb4/"
        )

    def test_an_independent_board_domain_is_not_linked(self):
        """Brooklyn CB5's listed domain lapsed and now redirects to an unrelated site.
        The City's dataset still points at it, so the host is the only usable signal."""
        assert _board_website({"url": "https://www.brooklyncb5.org/"}) is None
        assert _board_website({"url": "https://www.cb14brooklyn.com"}) is None

    def test_rejects_empty_missing_and_malformed(self):
        assert _board_website(None) is None
        assert _board_website({}) is None
        assert _board_website({"url": ""}) is None
        assert _board_website({"url": "https://[oops"}) is None

    def test_rejects_credentials_on_a_city_host(self):
        assert _board_website({"url": "https://user:pass@www.nyc.gov/x"}) is None

    def test_rejects_a_dangerous_scheme(self):
        assert _board_website({"url": "javascript:alert(1)"}) is None

    def test_an_unlinked_hostname_is_offered_as_text(self):
        assert _board_website_hostname({"url": "https://www.brooklyncb5.org/"}) == (
            "www.brooklyncb5.org"
        )

    def test_a_linked_board_has_no_text_only_hostname(self):
        """The two are mutually exclusive, or the page would print both."""
        assert _board_website_hostname({"url": "https://www.nyc.gov/site/queenscb9"}) is None

    def test_an_unparseable_url_yields_no_hostname(self):
        assert _board_website_hostname({"url": "https://[oops"}) is None

    def test_a_row_without_a_usable_code_is_skipped(self, tmp_path):
        # Real exports carry blank and short codes, which cannot be joined to geometry.
        path = tmp_path / "boards.json"
        path.write_text(
            json.dumps(
                [
                    {"community_board_1": "", "borough": "Brooklyn"},
                    {"community_board_1": "3", "borough": "Brooklyn"},
                    {"community_board_1": "302", "borough": "Brooklyn"},
                ]
            )
        )
        assert set(load_boards(path)) == {"302"}


class TestMemberGuards:
    def test_a_row_with_a_non_numeric_district_is_skipped(self, tmp_path):
        # The dataset carries the Public Advocate and other citywide seats.
        path = tmp_path / "members.json"
        path.write_text(
            json.dumps(
                [
                    {"name": "Public Advocate", "district": "", "council_member_id": "1"},
                    {"name": "Someone", "district": "not a number", "council_member_id": "2"},
                    {"name": "Real Member", "district": "7", "council_member_id": "3"},
                ]
            )
        )
        members = load_members(path)
        assert [m["district"] for m in members] == [7]

    def test_an_unparseable_term_date_becomes_none(self, tmp_path):
        path = tmp_path / "members.json"
        path.write_text(
            json.dumps(
                [
                    {
                        "name": "A",
                        "district": "1",
                        "council_member_id": "1",
                        "term_start": "not a date",
                        "term_end": None,
                    }
                ]
            )
        )
        member = load_members(path)[0]
        assert member["term_start"] is None
        assert member["term_end"] is None

    def test_a_future_term_is_not_current(self):
        members = [
            {
                "name": "Future",
                "member_id": "1",
                "district": 1,
                "term_start": date(2030, 1, 1),
                "term_end": date(2033, 12, 31),
            }
        ]
        assert current_by_district(members, date(2026, 9, 22)) == {}

    def test_the_later_term_start_wins_when_terms_overlap(self):
        """A mid-term appointment is recorded alongside the outgoing member."""
        members = [
            {
                "name": "Outgoing",
                "member_id": "1",
                "district": 5,
                "term_start": date(2026, 1, 1),
                "term_end": date(2029, 12, 31),
            },
            {
                "name": "Appointed",
                "member_id": "2",
                "district": 5,
                "term_start": date(2026, 6, 1),
                "term_end": date(2029, 12, 31),
            },
        ]
        current = current_by_district(members, date(2026, 9, 22))
        assert current[5]["name"] == "Appointed"


class TestCalendarGuards:
    GRID = '<table id="ctl00_ContentPlaceHolder1_gridCalendar_ctl00">{rows}</table>'

    def _row(self, *cells: str) -> str:
        return "<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>"

    def test_a_row_without_a_parseable_date_is_skipped(self):
        rows = self._row(
            "Committee on Aging", "not a date", "", "1:30 PM", "City Hall", "", "", "", ""
        )
        assert parse_calendar(self.GRID.format(rows=rows)) == []

    def test_a_row_with_no_committee_name_is_skipped(self):
        rows = self._row("", "12/17/2026", "", "1:30 PM", "City Hall", "", "", "", "")
        assert parse_calendar(self.GRID.format(rows=rows)) == []

    def test_a_row_with_too_few_cells_is_skipped(self):
        rows = "<tr><td>Committee on Aging</td><td>12/17/2026</td></tr>"
        assert parse_calendar(self.GRID.format(rows=rows)) == []

    def test_a_blank_time_becomes_time_not_published(self):
        """Distinct from "Deferred": the meeting is on, the time just is not given."""
        rows = self._row("Committee on Aging", "12/17/2026", "", "", "City Hall", "", "", "", "")
        meeting = parse_calendar(self.GRID.format(rows=rows))[0]
        assert meeting.time_state == "time_not_published"
        assert meeting.start_time is None

    def test_an_identical_row_repeated_is_counted_once(self):
        # Legistar emits the same meeting twice across grouped views.
        one = self._row(
            "Committee on Aging", "12/17/2026", "", "1:30 PM", "City Hall", "", "", "", ""
        )
        assert len(parse_calendar(self.GRID.format(rows=one + one))) == 1
