"""Building a whole site from fixtures, and the hostile-content case.

`test_hostile_committee_name_renders_inert` is the test that matters most here: it
is the end-to-end proof of the claim in docs/phase-1-scope.md §4.1 that scraped
content cannot become executable markup. It drives a real hostile string all the
way from an upstream payload to rendered HTML.
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import date, datetime
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


@pytest.fixture
def raw_dir(tmp_path, calendar_html, district_page_html):
    """A minimal but floor-passing raw cache."""
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "legistar_calendar.html").write_text(calendar_html, encoding="utf-8")

    # All 51 pages must be present to clear the district_pages floor; reuse the
    # four real fixtures cyclically for the rest.
    available = sorted(district_page_html)
    pages = {str(n): district_page_html[available[(n - 1) % len(available)]] for n in range(1, 52)}
    (raw / "district_pages.json").write_text(json.dumps(pages), encoding="utf-8")

    members = [
        {
            "name": f"Member {n}",
            "council_member_id": str(1000 + n),
            "district": str(n),
            "term_start": "2026-01-01T00:00:00.000",
            "term_end": "2029-12-31T00:00:00.000",
        }
        for n in range(1, 52)
    ]
    # Pad past the members floor with historical rows, as the real dataset has.
    members += [
        {
            "name": f"Former Member {i}",
            "council_member_id": str(2000 + i),
            "district": str((i % 51) + 1),
            "term_start": "2014-01-01T00:00:00.000",
            "term_end": "2017-12-31T00:00:00.000",
        }
        for i in range(300)
    ]
    (raw / "members.json").write_text(json.dumps(members), encoding="utf-8")

    # Real community-board rows: 59 of them, needed to clear the boards floor and
    # to carry the real chair / district-manager names the privacy test checks.
    # From tests/fixtures, NOT etl/raw — the cache is gitignored, and reading it
    # here made these tests pass locally and error in CI.
    shutil.copy2(FIXTURES / "community_boards.json", raw / "community_boards.json")

    # Synthetic district geometry: 51 disjoint squares. The build needs 51 features
    # to emit site/data/districts.geo.json, and nothing here depends on the shapes
    # being real — the accuracy of the real simplification is covered separately by
    # tests/unit/test_geo.py::TestSimplifiedGeometryAgrees, which runs against the
    # actual DCP file. Committing a 3.8 MB geojson to satisfy a smoke test would be
    # the wrong trade.
    features = []
    for n in range(1, 52):
        x0 = -74.3 + (n - 1) * 0.02
        y0 = 40.5
        features.append(
            {
                "type": "Feature",
                "properties": {"coundist": str(n)},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [x0, y0],
                            [x0 + 0.018, y0],
                            [x0 + 0.018, y0 + 0.018],
                            [x0, y0 + 0.018],
                            [x0, y0],
                        ]
                    ],
                },
            }
        )
    (raw / "districts.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8"
    )
    return raw


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
        # Staleness is the browser's job; baking a boolean here is what lets an
        # abandoned site claim to be fresh.
        assert "degraded" not in json.dumps(manifest)

    def test_a_short_calendar_fails_closed(self, raw_dir, tmp_path):
        # Below the floor must raise, not publish a nearly-empty site.
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

        # The literal tag must not appear; the escaped form must.
        assert "<script>alert" not in html
        assert "&lt;script&gt;" in html
        # And no executable construct anywhere.
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
        # The escaped form legitimately contains the characters "onmouseover="
        # as text. What must be absent is the *unescaped* quote that would end
        # the attribute and start a new one.
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
        # The rest of the page must still be useful to that district's residents.
        assert "How to be heard" in html
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
        # The difference between the two must be stated, not assumed — residents
        # routinely want the board and go looking for the council district.
        assert "most local unit" in html


class TestCrosswalk:
    """The committed crosswalk is a real artifact with a coverage guarantee."""

    def test_covers_all_51_districts(self):
        crosswalk = load_crosswalk(REPO_ROOT / "crosswalks" / "council_to_boards.json")
        assert sorted(crosswalk) == list(range(1, 52))

    def test_every_district_has_at_least_one_board(self):
        # The naive ruf7-3wgc.council_district join left 7 districts empty. This
        # is the assertion that would have caught it.
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
        """Spot-check against geography a human can verify.

        District 35 covers Fort Greene, Clinton Hill and Crown Heights, which sit
        in Brooklyn community boards 2, 8 and 9 (codes 302/308/309).
        """
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
        # The cadence must appear verbatim, not reformatted into a date.
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
        # The fact most residents do not know, and the reason this view exists.
        assert "non-Board (public) members" in page
        assert "not allowed to vote" in page
        # Verified appointment facts.
        assert "up to 50 unsalaried members" in page
        assert "Borough President" in page
        assert "reside, work, or have some other significant interest" in page

    def test_board_page_refuses_what_the_city_does_not_publish(self, raw_dir, tmp_path):
        out = tmp_path / "site"
        build_site(raw_dir, out, today=date(2026, 9, 22))
        page = " ".join((out / "board" / "302" / "index.html").read_text().split())
        # Term length, minimum age, meeting frequency and public-comment rules are
        # not published by the City, so the page says so rather than guessing.
        assert "could not find an official source" in page
        assert "No City dataset publishes community board agendas" in page

    def test_board_page_links_its_council_districts(self, raw_dir, tmp_path):
        out = tmp_path / "site"
        build_site(raw_dir, out, today=date(2026, 9, 22))
        page = (out / "board" / "302" / "index.html").read_text()
        # Brooklyn CB 2 spans council districts 33 and 35.
        assert 'href="/district/33/"' in page
        assert 'href="/district/35/"' in page

    def test_board_shares_are_of_the_board_not_the_district(self, raw_dir, tmp_path):
        """The two crosswalk directions answer different questions.

        On district 35's page, Brooklyn CB 2 covers ~44% *of the district*. On CB
        2's own page, district 33 holds ~53% *of the board*. Transposing one into
        the other would silently mis-state both.
        """
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
        # ZIPs come from the committed crosswalk, so this also guards against the
        # crosswalk losing its zips section.
        assert len(lookup["zips"]) > 150
        # Every ZIP maps to at least one real district number.
        for code, districts in lookup["zips"].items():
            assert code.isdigit() and len(code) == 5
            assert districts and all(1 <= n <= 51 for n in districts)

    def test_a_wrong_district_count_fails_closed(self, raw_dir, tmp_path):
        # Geometry with the wrong number of features means the upstream changed;
        # the build must refuse rather than ship a partial address lookup.
        (raw_dir / "districts.geojson").write_text(
            json.dumps({"type": "FeatureCollection", "features": []}), encoding="utf-8"
        )
        with pytest.raises(BuildError, match="district geometry"):
            build_site(raw_dir, tmp_path / "site", today=date(2026, 9, 22))
