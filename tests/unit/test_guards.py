"""The refusal paths: every guard that stops a bad build, and the states behind them.

These are the branches that only run when something is already wrong, which makes
them the least likely to be exercised by accident and the most damaging when broken.
A floor that does not raise is worse than no floor, because it reads as protection.

Grouped by the module whose guard is under test rather than by scenario, so a
failure points at one file.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pytest

from showup.build import BuildError, build_site
from showup.crosswalk import (
    CrosswalkError,
    _zcta_members,
    generate,
    load_boards_to_districts,
    load_zips,
)
from showup.crosswalk import load as load_crosswalk
from showup.geo import Polygon, load_features, overlap_shares, simplify_rings, to_geojson
from showup.model import District, DistrictBoard, Member, Office
from showup.render import render_board, render_district
from showup.sources.districts import _parse_committees
from showup.urls import safe_url

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

#: Lattice spacing for these tests. The production value is 0.001 (~110 m) and a
#: citywide sweep at that resolution takes ~35 s; none of the guards under test
#: depend on resolution, so they run coarse.
COARSE = 0.004


def _squares(key_property: str, keys, *, x0=-74.0, y0=40.6, size=0.02):
    """A FeatureCollection of disjoint squares, one per key."""
    features = []
    for index, key in enumerate(keys):
        left = x0 + index * (size * 2)
        features.append(
            {
                "type": "Feature",
                "properties": {key_property: str(key)},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [left, y0],
                            [left + size, y0],
                            [left + size, y0 + size],
                            [left, y0 + size],
                            [left, y0],
                        ]
                    ],
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


class TestCrosswalkGeneration:
    """`generate` is slow against real geometry, so it is exercised on squares."""

    def test_rejects_the_wrong_number_of_council_districts(self, tmp_path):
        council = tmp_path / "c.geojson"
        council.write_text(json.dumps(_squares("coundist", range(1, 5))))
        community = tmp_path / "cd.geojson"
        community.write_text(json.dumps(_squares("boro_cd", ["101"])))
        with pytest.raises(CrosswalkError, match="expected 51 council districts"):
            generate(council, community, spacing=COARSE)

    def test_rejects_the_wrong_number_of_community_districts(self, tmp_path):
        council = tmp_path / "c.geojson"
        council.write_text(json.dumps(_squares("coundist", range(1, 52))))
        community = tmp_path / "cd.geojson"
        community.write_text(json.dumps(_squares("boro_cd", ["101"])))
        with pytest.raises(CrosswalkError, match="expected 59 community districts"):
            generate(council, community, spacing=COARSE)

    def test_refuses_a_crosswalk_that_leaves_a_district_boardless(self, tmp_path):
        """The guard that would have caught the naive `council_district` join.

        51 council squares and 59 community squares that do not overlap: every
        district resolves to nothing, which must be a loud failure rather than a
        site with empty board sections.
        """
        council = tmp_path / "c.geojson"
        council.write_text(json.dumps(_squares("coundist", range(1, 52), y0=40.6)))
        community = tmp_path / "cd.geojson"
        # Far away, so nothing overlaps.
        community.write_text(
            json.dumps(_squares("boro_cd", [f"1{n:02d}" for n in range(1, 60)], y0=41.9))
        )
        with pytest.raises(CrosswalkError, match="no community board"):
            generate(council, community, spacing=COARSE)

    def test_generates_both_directions_when_geometry_overlaps(self, tmp_path):
        """Both directions, and they are not transposes of each other."""
        council = tmp_path / "c.geojson"
        community = tmp_path / "cd.geojson"
        # Council squares and community squares on the same footprint, so each
        # district maps to exactly one board and vice versa.
        council.write_text(json.dumps(_squares("coundist", range(1, 52))))
        community.write_text(json.dumps(_squares("boro_cd", [f"1{n:02d}" for n in range(1, 60)])))
        data = generate(council, community, spacing=COARSE)
        assert set(data) >= {"districts", "boards", "zips", "method", "sources", "note"}
        assert len(data["districts"]) == 51
        assert data["zips"] == {}, "no ZIP file was supplied"

    def test_zip_geometry_expands_modified_zctas_to_real_zips(self, tmp_path):
        council = tmp_path / "c.geojson"
        community = tmp_path / "cd.geojson"
        zips = tmp_path / "z.geojson"
        council.write_text(json.dumps(_squares("coundist", range(1, 52))))
        community.write_text(json.dumps(_squares("boro_cd", [f"1{n:02d}" for n in range(1, 60)])))
        # One modified ZCTA standing in for three real ZIPs, which is how the City
        # publishes 10001 (covering 10001, 10119, 10199).
        payload = _squares("modzcta", ["10001"])
        payload["features"][0]["properties"]["zcta"] = "10001, 10119, 10199"
        zips.write_text(json.dumps(payload))

        data = generate(council, community, zips, spacing=COARSE)
        assert set(data["zips"]) == {"10001", "10119", "10199"}

    def test_zcta_members_falls_back_to_the_code_itself(self, tmp_path):
        path = tmp_path / "z.geojson"
        payload = _squares("modzcta", ["11217", ""])
        # No zcta or label field, and one feature with no code at all.
        path.write_text(json.dumps(payload))
        members = _zcta_members(path)
        assert members == {"11217": ["11217"]}


class TestCrosswalkLoading:
    def test_missing_file_names_the_command_that_creates_it(self, tmp_path):
        for loader in (load_crosswalk, load_boards_to_districts, load_zips):
            with pytest.raises(CrosswalkError, match="missing"):
                loader(tmp_path / "absent.json")

    def test_a_crosswalk_without_a_boards_section_is_rejected(self, tmp_path):
        path = tmp_path / "c.json"
        path.write_text(json.dumps({"districts": {"1": [["101", 1.0]]}}))
        with pytest.raises(CrosswalkError, match="no `boards` section"):
            load_boards_to_districts(path)

    def test_the_wrong_number_of_boards_is_rejected(self, tmp_path):
        path = tmp_path / "c.json"
        path.write_text(json.dumps({"boards": {"101": [[1, 1.0]]}}))
        with pytest.raises(CrosswalkError, match="covers 1 community boards"):
            load_boards_to_districts(path)

    def test_a_board_with_no_council_district_is_rejected(self, tmp_path):
        path = tmp_path / "c.json"
        boards = {f"1{n:02d}": [[1, 1.0]] for n in range(1, 60)}
        boards["101"] = []
        path.write_text(json.dumps({"boards": boards}))
        with pytest.raises(CrosswalkError, match="no council district"):
            load_boards_to_districts(path)


class TestGeoGuards:
    def test_an_unsupported_geometry_type_yields_no_rings(self, tmp_path):
        path = tmp_path / "g.geojson"
        path.write_text(
            json.dumps(
                {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "properties": {"coundist": "1"},
                            "geometry": {"type": "Point", "coordinates": [0, 0]},
                        }
                    ],
                }
            )
        )
        # A Point cannot be hit-tested, so the feature is dropped rather than
        # loaded as a degenerate polygon.
        assert load_features(path, "coundist") == []

    def test_a_feature_with_no_key_is_dropped(self, tmp_path):
        path = tmp_path / "g.geojson"
        payload = _squares("coundist", ["1"])
        payload["features"][0]["properties"] = {}
        path.write_text(json.dumps(payload))
        assert load_features(path, "coundist") == []

    def test_a_row_with_no_candidate_polygons_is_skipped(self):
        # Latitudes above every polygon: the row filter short-circuits.
        outer = [Polygon("a", [[(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 0.0)]])]
        inner = [Polygon("b", [[(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 0.0)]])]
        result = overlap_shares(outer, inner, spacing=0.4, min_share=0.01)
        assert set(result) == {"a"}

    def test_a_polygon_the_lattice_never_hits_gets_an_empty_list(self):
        # A sliver thinner than the lattice spacing collects no sample points, so
        # its share list is empty rather than a fabricated value.
        wide = Polygon("wide", [[(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0)]])
        sliver = Polygon(
            "sliver",
            [[(100.0, 100.0), (100.0001, 100.0), (100.0001, 100.0001), (100.0, 100.0)]],
        )
        result = overlap_shares([wide, sliver], [wide], spacing=1.0, min_share=0.01)
        assert result["sliver"] == []

    def test_a_ring_too_short_to_simplify_is_returned_unchanged(self):
        triangle = [(0.0, 0.0), (1.0, 0.0), (0.0, 0.0)]
        assert simplify_rings([triangle], tolerance=0.5) == []

    def test_an_unclosed_ring_is_closed(self):
        square = [(0.0, 0.0), (0.0, 1.0), (1.0, 1.0), (1.0, 0.0)]
        out = simplify_rings([square], tolerance=0.0)[0]
        assert out[0] == out[-1]

    def test_to_geojson_skips_a_feature_whose_rings_all_collapse(self):
        speck = Polygon("tiny", [[(0.0, 0.0), (0.000001, 0.0), (0.000001, 0.000001), (0.0, 0.0)]])
        assert to_geojson([speck], "coundist")["features"] == []


class TestBuildGuards:
    def test_a_missing_crosswalk_becomes_a_build_error(self, raw_dir, tmp_path, monkeypatch):
        monkeypatch.setattr("showup.build.CROSSWALK_PATH", tmp_path / "absent.json")
        with pytest.raises(BuildError, match="missing"):
            build_site(raw_dir, tmp_path / "site", today=date(2026, 9, 22))

    def test_a_crosswalk_referencing_an_unknown_board_is_a_build_error(
        self, raw_dir, tmp_path, monkeypatch
    ):
        """The two sources drifting apart must be loud.

        The crosswalk comes from geometry and the contact details from a different
        dataset; if one names a board the other has never heard of, the page would
        silently lose a board rather than say so.
        """
        path = tmp_path / "c.json"
        districts = {str(n): [["999", 1.0]] for n in range(1, 52)}
        boards = {f"1{n:02d}": [[1, 1.0]] for n in range(1, 60)}
        path.write_text(json.dumps({"districts": districts, "boards": boards, "zips": {}}))
        monkeypatch.setattr("showup.build.CROSSWALK_PATH", path)
        with pytest.raises(BuildError, match="drifted apart"):
            build_site(raw_dir, tmp_path / "site", today=date(2026, 9, 22))

    def test_a_stale_staging_directory_is_cleared_first(self, raw_dir, tmp_path):
        out = tmp_path / "site"
        staging = out.with_name(out.name + ".building")
        staging.mkdir(parents=True)
        (staging / "leftover.txt").write_text("from a crashed run")

        build_site(raw_dir, out, today=date(2026, 9, 22))
        assert not (out / "leftover.txt").exists(), "a crashed run's files survived"

    def test_rebuilding_over_an_existing_site_replaces_it(self, raw_dir, tmp_path):
        out = tmp_path / "site"
        out.mkdir()
        (out / "stale.html").write_text("old")
        build_site(raw_dir, out, today=date(2026, 9, 22))
        assert not (out / "stale.html").exists()
        assert (out / "index.html").exists()


class TestRenderFallbacks:
    def _member(self, **kwargs):
        defaults = {
            "name": "Jane Doe",
            "seat_status": "filled",
            "email": None,
            "page_url": None,
            "offices": (Office("District office", None, None),),
            "committees": (),
        }
        defaults.update(kwargs)
        return Member(**defaults)

    def test_an_unlinkable_url_renders_as_inert_text(self):
        district = District(number=9, neighborhoods=None, member=self._member())
        html = render_district(
            district,
            [],
            built_at=datetime(2026, 9, 22, 9, 0),
            window_end=None,
            today=date(2026, 9, 22),
        )
        # page_url is None, so the official-page row must not appear as a dead link.
        assert 'href="None"' not in html

    def test_an_empty_definition_list_renders_nothing(self):
        # A member with no contactable details at all still produces a valid page.
        district = District(
            number=9,
            neighborhoods=None,
            member=self._member(offices=(), email=None, page_url=None),
        )
        html = render_district(
            district,
            [],
            built_at=datetime(2026, 9, 22, 9, 0),
            window_end=None,
            today=date(2026, 9, 22),
        )
        assert "Your Council Member" in html

    def test_a_window_end_of_none_says_so_rather_than_implying_completeness(self):
        district = District(number=9, neighborhoods=None, member=None)
        html = render_district(
            district,
            [],
            built_at=datetime(2026, 9, 22, 9, 0),
            window_end=None,
            today=date(2026, 9, 22),
        )
        assert "No forward window" in html

    def _board(self, **kwargs):
        defaults = {
            "code": "302",
            "label": "Brooklyn Community Board 2",
            "borough_name": "Brooklyn",
            "share": 0.44,
            "neighborhoods": None,
            "address": None,
            "phone": None,
            "email": None,
            "email_suppressed": None,
            "website": None,
            "board_meeting": None,
            "cabinet_meeting": None,
        }
        defaults.update(kwargs)
        return DistrictBoard(**defaults)

    def test_a_board_with_a_website_links_it(self):
        html = render_board(
            self._board(website="https://brooklyncb6.org/"),
            [(35, 0.44)],
            built_at=datetime(2026, 9, 22, 9, 0),
            window_end=None,
        )
        assert "brooklyncb6.org" in html

    def test_a_board_with_no_cadence_says_so(self):
        html = render_board(
            self._board(),
            [(35, 0.44)],
            built_at=datetime(2026, 9, 22, 9, 0),
            window_end=None,
        )
        assert "does not publish a meeting cadence" in html

    def test_a_board_in_an_unknown_borough_still_renders(self):
        # The borough-president link table is keyed on borough name; an unexpected
        # value must degrade to a pointer, not a crash or a dead link.
        html = render_board(
            self._board(borough_name="Atlantis"),
            [(35, 0.44)],
            built_at=datetime(2026, 9, 22, 9, 0),
            window_end=None,
        )
        assert "nyc.gov/communityboards" in html

    def test_a_district_with_no_boards_routes_elsewhere(self):
        district = District(number=9, neighborhoods=None, member=None, boards=())
        html = render_district(
            district,
            [],
            built_at=datetime(2026, 9, 22, 9, 0),
            window_end=None,
            today=date(2026, 9, 22),
        )
        assert "could not match a community board" in html


class TestDistrictPageGuards:
    def test_a_standalone_role_line_attaches_to_the_committee_above(self):
        """Both role layouts occur in the real pages."""
        lines = [
            "Committees",
            "Committee on Aging",
            "(Chair)",
            "Committee on Finance",
            "Caucuses",
        ]
        committees = _parse_committees(lines)
        assert [(c.name, c.role) for c in committees] == [
            ("Committee on Aging", "Chair"),
            ("Committee on Finance", "Member"),
        ]

    def test_a_role_line_with_no_committee_above_is_ignored(self):
        lines = ["Committees", "Committee on Aging", "Caucuses", "(Chair)"]
        assert [c.role for c in _parse_committees(lines)] == ["Member"]

    def test_an_office_heading_with_nothing_under_it_yields_no_office(self):
        from showup.sources.districts import parse_district_page

        html = "<h1>District 9</h1><p>Jane Doe</p><p>District Office</p><p>Legislative Office</p>"
        result = parse_district_page(9, html)
        assert result["offices"] == ()


class TestUrlControlCharacters:
    def test_a_value_that_is_entirely_unprintable_after_a_base_is_rejected(self):
        assert safe_url("\x00\x01", base="https://nyc.legistar.com/") is None


class TestRenderHelpers:
    """Three helpers whose fallback branches the page-level tests do not reach."""

    def test_link_with_no_url_renders_inert_text(self):
        from showup.render import _link

        # Defensive by design: a caller that forgets to check for None gets inert
        # text rather than href="None".
        assert _link(None, "Agenda") == '<span class="nolink">Agenda</span>'
        assert "href" not in _link(None, "Agenda")

    def test_link_escapes_both_url_and_label(self):
        from showup.render import _link

        out = _link("https://council.nyc.gov/?a=1&b=2", '<script>"')
        assert "&amp;b=2" in out
        assert "<script>" not in out

    def test_an_internal_link_gets_no_noopener(self):
        from showup.render import _link

        # rel="noopener noreferrer" is for outbound links; adding it to our own is
        # noise that makes the real ones harder to audit.
        assert "noopener" not in _link("/district/35/", "District 35")

    def test_an_empty_definition_list_is_omitted_entirely(self):
        from showup.render import _dl

        # Returning "<dl></dl>" would render an empty bordered block.
        assert _dl([]) == ""

    def test_a_definition_list_drops_rows_with_no_value(self):
        from showup.render import _dl

        out = _dl([("Phone", "212-555-0000"), ("Fax", "")])
        assert "Phone" in out
        assert "Fax" not in out

    def test_a_board_card_on_a_district_page_links_its_website(self):
        from showup.render import _board_card

        board = DistrictBoard(
            code="302",
            label="Brooklyn Community Board 2",
            borough_name="Brooklyn",
            share=0.44,
            neighborhoods=None,
            address=None,
            phone=None,
            email=None,
            email_suppressed=None,
            website="https://brooklyncb6.org/",
            board_meeting=None,
            cabinet_meeting=None,
        )
        out = _board_card(board)
        assert "brooklyncb6.org" in out
        assert 'href="/board/302/"' in out


class TestFetchInvariantMessages:
    """Each invariant's failure message, because the message is what an operator acts on."""

    def _source(self, name):
        from showup.fetch import SOURCES

        return next(s for s in SOURCES if s.name == name)

    def test_malformed_json_is_named_as_such(self):
        assert "not valid JSON" in self._source("members").invariant(b"{not json")

    def test_a_json_object_where_an_array_is_expected(self):
        assert "expected a JSON array" in self._source("members").invariant(b'{"a": 1}')

    def test_a_valid_row_array_passes(self):
        rows = json.dumps([{"i": n} for n in range(400)]).encode()
        assert self._source("members").invariant(rows) is None

    def test_malformed_geojson_is_named_as_such(self):
        assert "not valid JSON" in self._source("council-geometry").invariant(b"{oops")

    def test_geojson_without_a_feature_list(self):
        problem = self._source("council-geometry").invariant(b'{"type": "Feature"}')
        assert "not a GeoJSON FeatureCollection" in problem

    def test_correct_geojson_feature_count_passes(self):
        body = json.dumps(
            {"type": "FeatureCollection", "features": [{} for _ in range(51)]}
        ).encode()
        assert self._source("council-geometry").invariant(body) is None

    def test_malformed_district_pages_json(self):
        assert "not valid JSON" in self._source("districts").invariant(b"[[[")

    def test_district_pages_must_be_an_object(self):
        problem = self._source("districts").invariant(b'["a page"]')
        assert "object keyed by district number" in problem

    def test_a_complete_district_scrape_passes(self):
        pages = {str(n): f"<h1>District {n}</h1>" for n in range(1, 52)}
        assert self._source("districts").invariant(json.dumps(pages).encode()) is None

    def test_a_geospatial_fetcher_requests_the_export_endpoint(self, monkeypatch):
        import showup.fetch as fetch_module

        seen: list[str] = []
        monkeypatch.setattr(fetch_module, "_get", lambda url: seen.append(url) or b"{}")
        fetch_module._geospatial("abcd-1234")(lambda m: None)
        assert "api/geospatial/abcd-1234" in seen[0]
        assert "format=GeoJSON" in seen[0]

    def test_the_calendar_reports_a_failing_host_before_failing_over(self, monkeypatch):
        import showup.fetch as fetch_module
        from showup.fetch import FetchError

        calls: list[str] = []

        def flaky(url, **kwargs):
            calls.append(url)
            if len(calls) == 1:
                raise FetchError("primary refused the connection")
            return b'<table id="gridCalendar">' + b"x" * 1000

        monkeypatch.setattr(fetch_module, "_get", flaky)
        messages: list[str] = []
        body = fetch_module._fetch_calendar(messages.append)
        assert b"gridCalendar" in body
        # The operator must see WHY the primary was abandoned.
        assert any("refused the connection" in m for m in messages)


class TestBuildBoardPageFloor:
    def test_a_crosswalk_with_too_few_distinct_boards_is_refused(
        self, raw_dir, tmp_path, monkeypatch
    ):
        """59 board pages or none.

        `load_crosswalk` checks that every district has a board but not that all 59
        boards are reachable, so a districts section referencing only 58 codes would
        silently publish 58 board pages. This is the floor that catches it.
        """
        # Real board codes, because the build first checks that every code the
        # crosswalk names actually exists in the contact dataset.
        from showup.sources.boards import load_boards

        codes = sorted(load_boards(FIXTURES / "community_boards.json"))
        assert len(codes) == 59
        # Districts reference only the first 40 codes, leaving 19 boards with no
        # page — which must be refused, not quietly published.
        districts = {str(n): [[codes[n % 40], 1.0]] for n in range(1, 52)}
        boards = {code: [[1, 1.0]] for code in codes}
        path = tmp_path / "c.json"
        path.write_text(json.dumps({"districts": districts, "boards": boards, "zips": {}}))
        monkeypatch.setattr("showup.build.CROSSWALK_PATH", path)
        with pytest.raises(BuildError, match="board pages, expected 59"):
            build_site(raw_dir, tmp_path / "site", today=date(2026, 9, 22))


class TestOverlapSharesEmptyTally:
    def test_a_polygon_the_lattice_misses_entirely_reports_no_shares(self):
        """A polygon smaller than the lattice spacing collects zero samples.

        Its share list must be empty rather than a division by zero or an invented
        value — which is exactly the case the crosswalk's coverage floor then
        catches.
        """
        big = Polygon("big", [[(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0), (0.0, 0.0)]])
        missed = Polygon(
            "missed",
            [[(1.4, 1.4), (1.45, 1.4), (1.45, 1.45), (1.4, 1.45), (1.4, 1.4)]],
        )
        result = overlap_shares([big, missed], [big], spacing=1.0, min_share=0.01)
        assert result["missed"] == []
        assert result["big"], "the large polygon should still be sampled"


class TestShortHelper:
    def test_short_returns_empty_for_no_value(self):
        from showup.render import _short

        # Districts with no published neighbourhood list render without a dash.
        assert _short(None) == ""
        assert _short("") == ""

    def test_short_truncates_on_a_word_boundary_with_an_ellipsis(self):
        from showup.render import _short

        out = _short("A" * 80)
        assert out.endswith("…")
        assert len(out) <= 58

    def test_short_leaves_a_fitting_value_alone(self):
        from showup.render import _short

        assert _short("Fort Greene, Clinton Hill") == "Fort Greene, Clinton Hill"


class TestZipCrosswalkSkips:
    def test_a_zcta_overlapping_nothing_is_omitted(self, tmp_path):
        """A ZIP area outside every council district yields no entry.

        Rather than mapping it to an empty list, which the address box would then
        have to special-case at runtime.
        """
        council = tmp_path / "c.geojson"
        community = tmp_path / "cd.geojson"
        zips = tmp_path / "z.geojson"
        council.write_text(json.dumps(_squares("coundist", range(1, 52))))
        community.write_text(json.dumps(_squares("boro_cd", [f"1{n:02d}" for n in range(1, 60)])))
        # One ZCTA on the districts, one far away.
        payload = _squares("modzcta", ["10001"])
        away = _squares("modzcta", ["99999"], y0=44.0)
        payload["features"].extend(away["features"])
        zips.write_text(json.dumps(payload))

        data = generate(council, community, zips, spacing=COARSE)
        assert "99999" not in data["zips"]
        assert "10001" in data["zips"]
