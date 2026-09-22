"""Building a whole site from fixtures, and the hostile-content case.

`test_hostile_committee_name_renders_inert` is the test that matters most here: it
is the end-to-end proof of the claim in docs/phase-1-scope.md §4.1 that scraped
content cannot become executable markup. It drives a real hostile string all the
way from an upstream payload to rendered HTML.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime

import pytest

from showup.build import BuildError, build_site
from showup.model import Committee, District, Member, Office
from showup.render import render_district, render_index
from showup.sources.calendar import parse_calendar, upcoming


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
    def test_lists_every_district(self):
        districts = [District(number=n, neighborhoods=None, member=None) for n in range(1, 52)]
        html = render_index(districts, built_at=datetime(2026, 9, 22, 9, 0), window_end=None)
        for n in (1, 25, 51):
            assert f'href="/district/{n}/"' in html
        assert "<select" in html
