"""Building a whole site from fixtures, and the hostile-content case.

`test_hostile_committee_name_renders_inert` drives a hostile string from an upstream
payload to rendered HTML, which is the end-to-end proof of docs/phase-1-scope.md §4.1.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from html import unescape
from pathlib import Path

import pytest

from showup.build import BuildError, build_site
from showup.crosswalk import CrosswalkError
from showup.crosswalk import load as load_crosswalk
from showup.model import Committee, District, DistrictBoard, Member, Office
from showup.render import render_district, render_index
from showup.sources.calendar import parse_calendar, upcoming

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "tests" / "fixtures"


class TestBuild:
    def test_builds_all_51_districts(self, raw_dir, tmp_path):
        report = build_site(raw_dir, tmp_path / "site", today=date(2026, 9, 22))
        assert report["districts"] == 51
        assert report["meetings_parsed"] == 60
        assert report["shortlist"] == 5

    def test_writes_the_expected_files(self, raw_dir, tmp_path):
        out = tmp_path / "site"
        build_site(raw_dir, out, today=date(2026, 9, 22))
        assert (out / "index.html").is_file()
        assert (out / "404.html").is_file()
        assert (out / "manifest.json").is_file()
        assert (out / "assets" / "site.css").is_file()
        assert (out / "assets" / "site.js").is_file()
        for number in (1, 25, 51):
            assert (out / "district" / str(number) / "index.html").is_file()

    def test_manifest_carries_inputs_not_a_verdict(self, raw_dir, tmp_path):
        out = tmp_path / "site"
        build_site(raw_dir, out, today=date(2026, 9, 22))
        manifest = json.loads((out / "manifest.json").read_text())
        for source in manifest["sources"].values():
            assert "fetched_at" in source
            assert "max_age_hours" in source
        # Staleness is the browser's job; a baked boolean is what lets a dead site lie.
        assert "degraded" not in json.dumps(manifest)

    def test_a_short_calendar_fails_closed(self, raw_dir, tmp_path):
        (raw_dir / "legistar_calendar.html").write_text(
            '<table id="ctl00_ContentPlaceHolder1_gridCalendar_ctl00"></table>',
            encoding="utf-8",
        )
        with pytest.raises(BuildError, match="floor"):
            build_site(raw_dir, tmp_path / "site", today=date(2026, 9, 22))

    def test_failed_build_leaves_the_previous_site_intact(self, raw_dir, tmp_path):
        out = tmp_path / "site"
        build_site(raw_dir, out, today=date(2026, 9, 22))
        marker = (out / "index.html").read_text()

        (raw_dir / "legistar_calendar.html").write_text(
            '<table id="ctl00_ContentPlaceHolder1_gridCalendar_ctl00"></table>', encoding="utf-8"
        )
        with pytest.raises(BuildError):
            build_site(raw_dir, out, today=date(2026, 9, 22))
        assert (out / "index.html").read_text() == marker


class TestRenderedSafety:
    def _district(self, committee_name: str) -> District:
        return District(
            number=9,
            neighborhoods="Test neighbourhood",
            member=Member(
                name="Jane Doe",
                seat_status="filled",
                email="District9@council.nyc.gov",
                page_url="https://council.nyc.gov/district-9/",
                offices=(Office("District office", "1 Test St", "212-555-0000"),),
                committees=(Committee(committee_name),),
            ),
        )

    def test_hostile_committee_name_renders_inert(self, calendar_html):
        """The end-to-end XSS case from docs/phase-1-scope.md §4.1."""
        payload = "<script>alert('xss')</script>Committee on Aging"
        district = self._district(payload)
        meetings = upcoming(parse_calendar(calendar_html), date(2026, 1, 1), 5)

        html = render_district(
            district,
            meetings,
            built_at=datetime(2026, 9, 22, 9, 0),
            window_end=date(2026, 12, 17),
            today=date(2026, 9, 22),
            now=datetime(2026, 9, 22, 9, 0),
        )

        assert "<script>alert" not in html
        assert "&lt;script&gt;" in html
        assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>\s*\S", html)
        assert "onerror" not in html.lower()
        assert "javascript:" not in html.lower()

    def test_quote_in_a_name_cannot_break_an_attribute(self):
        district = self._district('Committee" onmouseover="alert(1)')
        html = render_district(
            district,
            [],
            built_at=datetime(2026, 9, 22, 9, 0),
            window_end=None,
            today=date(2026, 9, 22),
        )
        # The characters "onmouseover=" are legitimate text; what must be absent is the
        # unescaped quote that would end the attribute and start a new one.
        assert '" onmouseover="' not in html
        assert "&quot; onmouseover=&quot;" in html

    def test_no_inline_script_or_style_anywhere(self, raw_dir, tmp_path):
        out = tmp_path / "site"
        build_site(raw_dir, out, today=date(2026, 9, 22))
        for page in out.rglob("*.html"):
            html = page.read_text()
            assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>\s*\S", html), page
            assert not re.search(r"\sstyle\s*=\s*[\"']", html), page
            assert " onclick=" not in html.lower(), page


class TestVacantSeat:
    def test_vacancy_is_a_designed_state(self):
        district = District(number=3, neighborhoods="Chelsea", member=None)
        html = render_district(
            district,
            [],
            built_at=datetime(2026, 9, 22, 9, 0),
            window_end=None,
            today=date(2026, 9, 22),
        )
        assert "vacant" in html.lower()
        assert "Testimony and attendance" in html
        assert "hearings@council.nyc.gov" in html


class TestIndex:
    def _boards(self):
        return [
            DistrictBoard(
                code=code,
                label=f"Brooklyn Community Board {code[1:]}",
                borough_name="Brooklyn",
                share=1.0,
                neighborhoods=None,
                address=None,
                phone=None,
                email=None,
                email_suppressed=None,
                website=None,
                board_meeting=None,
                cabinet_meeting=None,
            )
            for code in ("301", "302")
        ]

    def test_lists_every_district(self):
        districts = [District(number=n, neighborhoods=None, member=None) for n in range(1, 52)]
        html = render_index(
            districts, self._boards(), built_at=datetime(2026, 9, 22, 9, 0), window_end=None
        )
        for n in (1, 25, 51):
            assert f'href="/district/{n}/"' in html
        assert "<select" in html

    def test_offers_both_views(self):
        districts = [District(number=n, neighborhoods=None, member=None) for n in range(1, 52)]
        html = render_index(
            districts, self._boards(), built_at=datetime(2026, 9, 22, 9, 0), window_end=None
        )
        assert 'id="district-select"' in html
        assert 'id="board-select"' in html
        assert 'href="/board/302/"' in html
        assert "most local unit" in html


class TestCrosswalk:
    """The committed crosswalk is a real artifact with a coverage guarantee."""

    def test_covers_all_51_districts(self):
        crosswalk = load_crosswalk(REPO_ROOT / "crosswalks" / "council_to_boards.json")
        assert sorted(crosswalk) == list(range(1, 52))

    def test_every_district_has_at_least_one_board(self):
        crosswalk = load_crosswalk(REPO_ROOT / "crosswalks" / "council_to_boards.json")
        for number, boards in crosswalk.items():
            assert boards, f"council district {number} has no community board"

    def test_shares_are_ordered_and_plausible(self):
        crosswalk = load_crosswalk(REPO_ROOT / "crosswalks" / "council_to_boards.json")
        for number, boards in crosswalk.items():
            shares = [share for _, share in boards]
            assert shares == sorted(shares, reverse=True), f"district {number} unordered"
            assert all(0 < share <= 1 for share in shares), f"district {number} share out of range"
            assert sum(shares) <= 1.02, f"district {number} shares sum above 1"

    def test_known_overlaps_are_right(self):
        """District 35 covers Fort Greene, Clinton Hill and Crown Heights, which are
        Brooklyn community boards 2, 8 and 9 — codes 302/308/309."""
        crosswalk = load_crosswalk(REPO_ROOT / "crosswalks" / "council_to_boards.json")
        assert {code for code, _ in crosswalk[35]} == {"302", "308", "309"}
        # District 51 is Staten Island's south shore: board 503 dominates.
        assert crosswalk[51][0][0] == "503"

    def test_missing_crosswalk_is_a_loud_failure(self, tmp_path):
        with pytest.raises(CrosswalkError, match="missing"):
            load_crosswalk(tmp_path / "nope.json")

    def test_incomplete_crosswalk_is_rejected(self, tmp_path):
        path = tmp_path / "partial.json"
        path.write_text(json.dumps({"districts": {"1": [["101", 0.9]]}}))
        with pytest.raises(CrosswalkError, match="no board for council districts"):
            load_crosswalk(path)


class TestBoardsOnThePage:
    def test_boards_render_with_contact_details(self, raw_dir, tmp_path):
        out = tmp_path / "site"
        build_site(raw_dir, out, today=date(2026, 9, 22))
        page = (out / "district" / "35" / "index.html").read_text()
        assert "Brooklyn Community Board 2" in page
        assert "community board" in page.lower()
        # Verbatim, not reformatted into a date.
        assert "Wednesday" in page or "Tuesday" in page or "Thursday" in page

    def test_chair_and_district_manager_are_never_rendered(self, raw_dir, tmp_path):
        """The privacy line: we publish the institution, not the individuals."""
        out = tmp_path / "site"
        build_site(raw_dir, out, today=date(2026, 9, 22))
        boards = json.loads((raw_dir / "community_boards.json").read_text())
        names = {
            (row.get(field) or "").strip()
            for row in boards
            for field in ("cb_chair", "cb_district_manager")
            if (row.get(field) or "").strip()
        }
        assert names, "fixture should carry some names to check against"
        for page in (out / "district").rglob("index.html"):
            html = page.read_text()
            for name in names:
                assert name not in html, f"{name} leaked into {page}"


class TestBoardView:
    """The board view is a different page, not a district page variant."""

    def test_all_59_board_pages_are_written(self, raw_dir, tmp_path):
        out = tmp_path / "site"
        report = build_site(raw_dir, out, today=date(2026, 9, 22))
        assert report["board_pages"] == 59
        pages = [p for p in (out / "board").iterdir() if p.is_dir()]
        assert len(pages) == 59

    def test_board_page_carries_the_involvement_route(self, raw_dir, tmp_path):
        out = tmp_path / "site"
        build_site(raw_dir, out, today=date(2026, 9, 22))
        page = " ".join((out / "board" / "302" / "index.html").read_text().split())
        assert "non-Board (public) members" in page
        assert "not allowed to vote" in page
        assert "up to 50 unsalaried members" in page
        assert "Borough President" in page
        assert "reside, work, or have some other significant interest" in page

    def test_board_page_says_the_office_is_not_the_venue(self, raw_dir, tmp_path):
        """A field note, not a disclosure paragraph: the address is directly above it, and
        silence there reads as "that is where the board meets" — wrong on 8 of 8 checked."""
        out = tmp_path / "site"
        build_site(raw_dir, out, today=date(2026, 9, 22))
        page = " ".join((out / "board" / "302" / "index.html").read_text().split())
        assert "The City's dataset records the board office, not the meeting venue" in page
        assert "<dd>350 Jay Street, 8th Floor, Brooklyn, NY 11201<br><small>" in page

    def test_the_board_page_does_not_catalogue_what_is_missing(self, raw_dir, tmp_path):
        """Owner, 2026-10-07: absences nobody asked about are padding, not honesty.

        Refusing to *invent* a fact is untouched; listing what the City does not publish
        is what went.
        """
        out = tmp_path / "site"
        build_site(raw_dir, out, today=date(2026, 9, 22))
        page = " ".join((out / "board" / "302" / "index.html").read_text().split())
        assert "Things the City does not publish" not in page
        assert "could not find an official source" not in page
        assert "measures public opinion" not in page

    def test_board_page_distinguishes_the_office_from_the_full_board_venue(self, raw_dir, tmp_path):
        """The office is the committee room for several boards, not the full-board venue.

        Bronx CB11 lists "Board Office" against every committee and "Varies" against the
        full board; Brooklyn CB4 and SI CB3 separate the two by name.
        """
        out = tmp_path / "site"
        build_site(raw_dir, out, today=date(2026, 9, 22))
        page = " ".join((out / "board" / "302" / "index.html").read_text().split())
        assert "Committees often meet at the board office listed above" in page
        assert "the full board often does not" in page
        assert "others meet elsewhere or on video" in page

    def test_board_page_links_its_council_districts(self, raw_dir, tmp_path):
        out = tmp_path / "site"
        build_site(raw_dir, out, today=date(2026, 9, 22))
        page = (out / "board" / "302" / "index.html").read_text()
        # Brooklyn CB 2 spans council districts 33 and 35.
        assert 'href="/district/33/"' in page
        assert 'href="/district/35/"' in page

    def test_board_shares_are_of_the_board_not_the_district(self, raw_dir, tmp_path):
        """The two crosswalk directions answer different questions: Brooklyn CB 2 covers
        ~44% *of district 35*, while district 33 holds ~53% *of CB 2*."""
        out = tmp_path / "site"
        build_site(raw_dir, out, today=date(2026, 9, 22))
        board_page = (out / "board" / "302" / "index.html").read_text()
        assert "of this board" in board_page
        district_page = (out / "district" / "35" / "index.html").read_text()
        assert "of this council district" in district_page

    def test_district_page_links_to_the_board_view(self, raw_dir, tmp_path):
        out = tmp_path / "site"
        build_site(raw_dir, out, today=date(2026, 9, 22))
        page = (out / "district" / "35" / "index.html").read_text()
        assert 'href="/board/302/"' in page

    def test_no_board_officer_names_on_board_pages(self, raw_dir, tmp_path):
        """The privacy rule holds on the new view too."""
        out = tmp_path / "site"
        build_site(raw_dir, out, today=date(2026, 9, 22))
        rows = json.loads((raw_dir / "community_boards.json").read_text())
        names = {
            (row.get(field) or "").strip()
            for row in rows
            for field in ("cb_chair", "cb_district_manager")
            if len((row.get(field) or "").strip()) > 4
        }
        for page in (out / "board").rglob("index.html"):
            html = page.read_text()
            for name in names:
                assert name not in html, f"{name} leaked into {page}"


class TestBudgetRequestsOnTheBoardPage:
    """The eighth source, on the page it belongs to. The honesty boundary is the spec: an
    annual filing not current activity, a request not a commitment, quoted not bucketed."""

    @staticmethod
    def _page(raw_dir, tmp_path, code: str = "302") -> str:
        out = tmp_path / "site"
        build_site(raw_dir, out, today=date(2026, 9, 22))
        return " ".join((out / "board" / code / "index.html").read_text().split())

    def test_the_section_names_the_fiscal_year_and_the_publication_date(self, raw_dir, tmp_path):
        page = self._page(raw_dir, tmp_path)
        assert "Fiscal Year Requests" in page
        assert "Fiscal Year 2027" in page
        assert "30 June 2026" in page

    def test_it_links_the_register_it_came_from(self, raw_dir, tmp_path):
        page = self._page(raw_dir, tmp_path)
        assert 'href="https://data.cityofnewyork.us/d/vn4m-mk4t"' in page
        assert "vn4m-mk4t" in page

    def test_every_number_carries_its_denominator(self, raw_dir, tmp_path):
        # Brooklyn CB 2 has seven requests in the committed fixture's edition.
        assert "5 of 7" in self._page(raw_dir, tmp_path)

    def test_the_cap_is_five_requests(self, raw_dir, tmp_path):
        assert self._page(raw_dir, tmp_path).count('<article class="request">') == 5

    def test_the_agencys_reply_is_quoted_not_bucketed(self, raw_dir, tmp_path):
        page = self._page(raw_dir, tmp_path)
        # Five phrasings, none of which survives a supported/not-supported bucket.
        assert "brought to the attention of your Elected Officials" in page
        assert "recommended funding for this request in part" in page
        assert "try to accommodate this issue within existing resources" in page
        assert "does not support and cannot accommodate" in page

    def test_no_single_top_request_is_presented(self, raw_dir, tmp_path):
        page = self._page(raw_dir, tmp_path)
        assert "top priority" not in page.lower()
        assert "number one request" not in page.lower()

    def test_the_section_neither_ranks_nor_scores_boards(self, raw_dir, tmp_path):
        page = self._page(raw_dir, tmp_path)
        section = page.split("Fiscal Year Requests", 1)[1].split("</section>", 1)[0]
        for banned in ("score", "percentile", "league", "out of 100", "compared with"):
            assert banned not in section.lower()

    def test_the_caveats_moved_to_references_rather_than_vanishing(self, raw_dir, tmp_path):
        """The board page's "What this is not" paragraph was deleted on 2026-10-07.

        Its clauses are provenance, so they relocated to /references/ instead. Without
        the priority clause somewhere, repeated "Priority 01" labels read as the board
        filing twenty-three number-one requests.
        """
        out = tmp_path / "site"
        build_site(raw_dir, out, today=date(2026, 9, 22))
        references = unescape(" ".join((out / "references" / "index.html").read_text().split()))
        assert "ranks within a budget category" in references
        assert "not a commitment and not a funded outcome" in references
        assert "quoted" in references
        board = self._page(raw_dir, tmp_path)
        assert "What this is not" not in board

    def test_a_board_the_register_does_not_cover_says_so(self, raw_dir, tmp_path):
        # The fixture carries six boards, so the other 53 are the empty state.
        page = self._page(raw_dir, tmp_path, "308")
        assert "no budget requests on file" in page
        assert "City Charter requires" in page

    def test_a_missing_register_does_not_break_the_build(self, raw_dir, tmp_path):
        (raw_dir / "board_budget_requests.json").unlink()
        report = build_site(raw_dir, tmp_path / "site", today=date(2026, 9, 22))
        assert report["board_pages"] == 59
        assert report["budget_requests"] == 0
        assert report["budget_publication"] is None
        page = " ".join((tmp_path / "site" / "board" / "302" / "index.html").read_text().split())
        assert "no budget requests on file" in page

    def test_an_empty_register_does_not_break_the_build(self, raw_dir, tmp_path):
        (raw_dir / "board_budget_requests.json").write_text("[]", encoding="utf-8")
        report = build_site(raw_dir, tmp_path / "site", today=date(2026, 9, 22))
        assert report["boards_with_budget_requests"] == 0

    def test_a_future_only_register_refuses_the_build(self, raw_dir, tmp_path):
        rows = json.loads((raw_dir / "board_budget_requests.json").read_text())
        future = [row for row in rows if row["publication"] == "20270217"]
        assert future, "the fixture should carry the future-dated edition"
        (raw_dir / "board_budget_requests.json").write_text(json.dumps(future), encoding="utf-8")
        with pytest.raises(BuildError, match="on or before"):
            build_site(raw_dir, tmp_path / "site", today=date(2026, 9, 22))

    def test_the_report_and_manifest_carry_the_source(self, raw_dir, tmp_path):
        out = tmp_path / "site"
        report = build_site(raw_dir, out, today=date(2026, 9, 22))
        assert report["boards_with_budget_requests"] == 6
        assert report["budget_publication"] == "2026-06-30"
        manifest = json.loads((out / "manifest.json").read_text())
        assert "board_budget_requests" in manifest["sources"]

    def test_hostile_register_text_renders_inert(self, raw_dir, tmp_path):
        rows = json.loads((raw_dir / "board_budget_requests.json").read_text())
        hostile = "<script>alert('register')</script>Fix the &quot;park&quot;"
        for row in rows:
            if row["boro"] == "2" and row["board"] == "02":
                row["request"] = hostile
                row["explanation"] = hostile
                row["response"] = hostile
        (raw_dir / "board_budget_requests.json").write_text(json.dumps(rows), encoding="utf-8")
        build_site(raw_dir, tmp_path / "site", today=date(2026, 9, 22))
        html = (tmp_path / "site" / "board" / "302" / "index.html").read_text()
        assert "<script>alert" not in html
        assert "alert(" not in html
        assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>\s*\S", html)


class TestShippedData:
    """The payloads the address box fetches at runtime."""

    def test_geometry_and_lookup_are_written(self, raw_dir, tmp_path):
        out = tmp_path / "site"
        build_site(raw_dir, out, today=date(2026, 9, 22))
        assert (out / "data" / "districts.geo.json").is_file()
        assert (out / "data" / "lookup.json").is_file()

    def test_geometry_carries_all_51_districts(self, raw_dir, tmp_path):
        out = tmp_path / "site"
        build_site(raw_dir, out, today=date(2026, 9, 22))
        geo = json.loads((out / "data" / "districts.geo.json").read_text())
        keys = {f["properties"]["coundist"] for f in geo["features"]}
        assert keys == {str(n) for n in range(1, 52)}

    def test_lookup_resolves_without_the_network(self, raw_dir, tmp_path):
        out = tmp_path / "site"
        build_site(raw_dir, out, today=date(2026, 9, 22))
        lookup = json.loads((out / "data" / "lookup.json").read_text())
        assert len(lookup["districts"]) == 51
        assert len(lookup["boards"]) == 59
        assert len(lookup["zips"]) > 150
        for code, districts in lookup["zips"].items():
            assert code.isdigit() and len(code) == 5
            assert districts and all(1 <= n <= 51 for n in districts)

    def test_a_wrong_district_count_fails_closed(self, raw_dir, tmp_path):
        (raw_dir / "districts.geojson").write_text(
            json.dumps({"type": "FeatureCollection", "features": []}), encoding="utf-8"
        )
        with pytest.raises(BuildError, match="district geometry"):
            build_site(raw_dir, tmp_path / "site", today=date(2026, 9, 22))


class TestProgressiveDisclosureOnRequestCards:
    """Owner, 2026-10-07: collapsed a card is its headers, expanded it is the detail.

    Native `<details>`, because the CSP forbids inline script and R39 requires the page to
    work without JavaScript. The `<h3>` inside the `<summary>` keeps both the heading and
    the expanded state in the accessibility tree (tests/browser/test_keyboard.py).
    """

    @staticmethod
    def _page(raw_dir, tmp_path) -> str:
        out = tmp_path / "site"
        build_site(raw_dir, out, today=date(2026, 9, 22))
        return (out / "board" / "302" / "index.html").read_text()

    def test_each_card_is_a_details_with_the_heading_inside_the_summary(self, raw_dir, tmp_path):
        page = self._page(raw_dir, tmp_path)
        assert page.count("<details>") == 5
        assert page.count("<summary><h3>") == 5

    def test_the_priority_label_stays_visible_collapsed(self, raw_dir, tmp_path):
        """It is short, and it is what makes the collapsed list readable."""
        page = self._page(raw_dir, tmp_path)
        for summary in re.findall(r"<summary>(.*?)</summary>", page, re.DOTALL):
            assert 'class="priority"' in summary

    def test_the_detail_fields_are_inside_the_disclosure(self, raw_dir, tmp_path):
        page = self._page(raw_dir, tmp_path)
        for body in re.findall(r"</summary>(.*?)</details>", page, re.DOTALL):
            assert "<dt>Register reference</dt>" in body
        assert "<dt>Requestee</dt>" in page
        assert "<dt>Response</dt>" in page

    def test_the_old_narrated_field_labels_are_gone(self, raw_dir, tmp_path):
        page = self._page(raw_dir, tmp_path)
        for narration in ("Asked of", "The board&#x27;s words", "The reply, quoted"):
            assert narration not in page

    def test_nothing_about_the_disclosure_needs_script(self, raw_dir, tmp_path):
        page = self._page(raw_dir, tmp_path)
        assert "<script" not in page.split("<footer")[0]
        assert "onclick" not in page.lower()


class TestReferencesPage:
    """One page carrying every identifier, fetch date, window and relocated caveat, built
    from the `fetch.SOURCES` registry, so a source cannot be used without appearing."""

    @staticmethod
    def _page(raw_dir, tmp_path) -> str:
        """Flattened and unescaped: these assertions are about text, not markup."""
        out = tmp_path / "site"
        build_site(raw_dir, out, today=date(2026, 9, 22))
        return unescape(" ".join((out / "references" / "index.html").read_text().split()))

    def test_it_is_written(self, raw_dir, tmp_path):
        out = tmp_path / "site"
        build_site(raw_dir, out, today=date(2026, 9, 22))
        assert (out / "references" / "index.html").is_file()

    def test_every_registered_source_is_disclosed(self, raw_dir, tmp_path):
        from showup.fetch import SOURCES

        page = self._page(raw_dir, tmp_path)
        for source in SOURCES:
            assert source.label in page, f"{source.name} is fetched and not disclosed"
            assert source.dataset in page, f"{source.name} has no identifier on the page"
            assert source.url in page, f"{source.name} has no link on the page"
            assert source.why in page, f"{source.name} does not say what it is used for"

    def test_each_source_carries_its_freshness_window(self, raw_dir, tmp_path):
        from showup.fetch import SOURCES

        page = self._page(raw_dir, tmp_path)
        assert page.count("<dt>Freshness window</dt>") == len(SOURCES)
        assert "12 hours" in page
        assert "40 days" in page

    def test_a_fetched_source_carries_its_fetch_date(self, raw_dir, tmp_path):
        page = self._page(raw_dir, tmp_path)
        # Six of the eight: the two geometry files are not in this fixture's cache.
        assert page.count("<dt>Fetched</dt>") == 6

    def test_the_relocated_provenance_all_landed(self, raw_dir, tmp_path):
        """Deleting a disclosure paragraph may relocate a citation, never lose one."""
        page = self._page(raw_dir, tmp_path)
        for relocated in (
            "dg92-zbpx",
            "a few dozen land-use hearing notices a year across all 59 community boards",
            "no City dataset publishes a dated board calendar",
            "quoted exactly as ruf7-3wgc records it",
            "disagree with what boards publish on their own sites",
            "records the board office address, not the meeting venue",
            "rounded to a whole number and approximate",
            "nominate half of the board's members",
            "called by their chair, a community board meets on a standing monthly cadence",
        ):
            assert relocated in page, f"lost in relocation: {relocated!r}"

    def test_every_page_links_it(self, raw_dir, tmp_path):
        out = tmp_path / "site"
        build_site(raw_dir, out, today=date(2026, 9, 22))
        for page_file in out.rglob("*.html"):
            if page_file.parent.name == "references":
                continue
            assert 'href="/references/"' in page_file.read_text(), page_file
