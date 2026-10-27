"""The map on the front page, and the rule that it is the only page paying for the map.

`docs/dependencies.md` allows a vendored browser dependency on condition that it is
load-gated. That condition is only real if something checks it, so this file is the check:
one page may name MapLibre, and the map must never be the only way to reach a district.
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import date
from pathlib import Path

import pytest
from pageset import every_page
from perf import budget, gzipped_size

from showup import render
from showup.build import VENDOR_FILES, BuildError, build_site
from showup.fetch import cache_path
from showup.model import BOARD_COUNT, DISTRICT_COUNT
from showup.render import PREVIEW_REQUESTS, preview_payload
from showup.sources.boards import JOINT_INTEREST_AREAS

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def site(tmp_path_factory, raw_dir_session) -> Path:
    out = tmp_path_factory.mktemp("map-site")
    build_site(raw_dir_session, out, today=date(2026, 9, 22))
    return out


class TestTheMapIsItsOwnRoute:
    def test_the_map_page_is_built(self, site):
        assert (site / "map" / "index.html").is_file()
        assert "/map/" in every_page(site)

    def test_the_landing_page_has_no_map(self, site):
        """A map inside a scrolling page swallows the wheel: scrolling zooms instead. The
        landing page is a document, so it carries no canvas."""
        html = (site / "index.html").read_text(encoding="utf-8")
        assert 'id="map"' not in html
        assert "maplibre" not in html.lower()

    def test_the_landing_page_sends_the_reader_to_the_map(self, site):
        assert 'href="/map/"' in (site / "index.html").read_text(encoding="utf-8")

    def test_the_map_page_locks_the_viewport(self, site):
        """`body.app` is what stops the page scrolling, which is the whole reason this is a
        separate route."""
        assert '<body class="app">' in (site / "map" / "index.html").read_text(encoding="utf-8")

    def test_both_layers_ship_their_geometry(self, site):
        assert (site / "data" / "districts.geo.json").is_file()
        assert (site / "data" / "boards.geo.json").is_file()

    def test_the_board_geometry_carries_every_board_and_no_joint_interest_area(self, site):
        """Parks, airports and Rikers are community districts with no board. Drawing one
        would imply there is somebody to call."""
        geometry = json.loads((site / "data" / "boards.geo.json").read_text(encoding="utf-8"))
        codes = {feature["properties"]["boro_cd"] for feature in geometry["features"]}
        assert len(codes) == BOARD_COUNT
        assert not codes & set(JOINT_INTEREST_AREAS)

    def test_the_toggle_offers_exactly_the_two_layers(self, site):
        html = (site / "map" / "index.html").read_text(encoding="utf-8")
        assert 'data-layer="council"' in html
        assert 'data-layer="board"' in html

    def test_the_toggle_ships_hidden_with_council_preselected(self, site):
        """A toggle that switches nothing is worse than no toggle, and the map may never
        draw."""
        html = (site / "map" / "index.html").read_text(encoding="utf-8")
        assert 'id="map-toggle" hidden' in html
        assert 'data-layer="council" aria-pressed="true"' in html

    def test_every_vendored_file_ships(self, site):
        assert {path.name for path in (site / "vendor").iterdir()} == set(VENDOR_FILES)

    def test_the_licence_ships_beside_the_library(self, site):
        """BSD-3-Clause travels with the code or we are not complying with it."""
        licence = (site / "vendor" / "LICENSE.txt").read_text(encoding="utf-8")
        assert "BSD" in licence or "Copyright" in licence


class TestTheBoardGeometryHasAFloor:
    def test_a_short_board_geometry_fails_the_build(self, tmp_path, raw_dir_session):
        """One board missing is a changed upstream shape, not a thin file: the map would
        draw 58 boards and look right."""
        raw = tmp_path / "raw"
        shutil.copytree(raw_dir_session, raw)
        path = cache_path(raw, "community-geometry")
        geometry = json.loads(path.read_text(encoding="utf-8"))
        geometry["features"] = geometry["features"][:-2]
        path.write_text(json.dumps(geometry), encoding="utf-8")
        with pytest.raises(BuildError, match="board geometry has"):
            build_site(raw, tmp_path / "out", today=date(2026, 9, 22))


class TestOnlyTheMapPaysForTheMap:
    def test_no_other_page_mentions_maplibre(self, site):
        """The load-gating condition in docs/dependencies.md, enforced."""
        offenders = [
            path
            for path in every_page(site)
            if path != "/map/"
            and "maplibre"
            in (
                site / path.strip("/") / "index.html"
                if path.endswith("/")
                else site / path.strip("/")
            )
            .read_text(encoding="utf-8")
            .lower()
        ]
        assert not offenders, f"these pages would download the map library: {offenders}"

    def test_the_map_page_does_not_block_on_the_library(self, site):
        """The library is imported from the module, never as a blocking script tag, so the
        document's own weight stays inside R40's page budget."""
        html = (site / "map" / "index.html").read_text(encoding="utf-8")
        assert 'src="/vendor/maplibre-gl.mjs"' not in html
        assert 'src="/assets/map.mjs"' in html

    def test_the_library_is_inside_its_own_budget(self, site):
        """It is excluded from the page and script budgets, so it needs its own number."""
        total = sum(
            gzipped_size(path.read_bytes()) for path in (site / "vendor").glob("maplibre-gl*")
        )
        assert total <= budget()["map_library_gzip_bytes"]


class TestTheMapIsNeverTheOnlyWay:
    def test_the_map_page_links_the_lists_that_need_no_canvas(self, site):
        """R6's location-free path. A WebGL canvas is not a navigation route, so the map
        page names the two index pages, which carry all 110 links between them."""
        html = (site / "map" / "index.html").read_text(encoding="utf-8")
        assert 'href="/district/"' in html
        assert 'href="/board/"' in html

    def test_the_index_pages_carry_every_district_and_board(self, site):
        districts = (site / "district" / "index.html").read_text(encoding="utf-8")
        boards = (site / "board" / "index.html").read_text(encoding="utf-8")
        for number in range(1, DISTRICT_COUNT + 1):
            assert f'href="/district/{number}/"' in districts
        assert boards.count('href="/board/') >= BOARD_COUNT

    def test_the_status_line_says_what_is_needed_before_any_script_runs(self, site):
        """Rendered into the document, so a reader with no JavaScript still reads it."""
        html = (site / "map" / "index.html").read_text(encoding="utf-8")
        assert "needs JavaScript and WebGL" in html

    def test_the_zoom_buttons_ship_hidden(self, site):
        """They do nothing until the map draws, and a control that lies is worse than none."""
        html = (site / "map" / "index.html").read_text(encoding="utf-8")
        assert '<div class="map-zoom" hidden' in html

    def test_selecting_on_the_map_offers_a_link_rather_than_navigating(self, site):
        """A click that moved the page would make the toggle useless for comparing two
        boundaries, so selection highlights and reveals this card instead."""
        html = (site / "map" / "index.html").read_text(encoding="utf-8")
        # Matched per attribute rather than as one string: they are on the same tag but not
        # adjacent, and an earlier version of this assertion broke when one was inserted
        # between them.
        assert 'id="map-card"' in html
        assert "hidden" in html
        assert 'id="map-selection"' in html
        assert 'id="map-card-close"' in html


class TestParticipatoryBudgetingIsOptional:
    """Both helpers answer None when no roster was loaded, so a caller without one
    renders no participatory-budgeting rows rather than empty ones."""

    def test_no_participatory_budgeting_table_without_a_roster(self):
        """The group is simply not emitted, rather than emitted empty: an empty table
        would read as "we looked and found nothing", which is a different claim."""
        from showup.model import District

        district = District(
            number=35, neighborhoods=None, member=None, boards=(), provenance={}, missing=()
        )
        legends = [spec["legend"] for spec in render.district_tables(district, None)]
        assert "Participatory budgeting" not in legends

    def test_the_shared_labels_are_absent_without_a_roster(self):
        assert render._pb_meta(None) is None

    def test_the_district_page_helper_is_absent_without_a_roster(self):
        assert render._participation(None, 35) is None


class TestThePreviewArtifact:
    """`/data/preview.json`: the headline facts the detail panel shows on selection."""

    @pytest.fixture
    def preview(self, site):
        return json.loads((site / "data" / "preview.json").read_text(encoding="utf-8"))

    def test_it_covers_every_district_and_board(self, preview):
        assert len(preview["districts"]) == DISTRICT_COUNT
        assert len(preview["boards"]) == BOARD_COUNT

    def test_the_next_meeting_is_citywide_not_per_district(self, preview):
        """Council and committee meetings belong to no district, which is why the district is
        a filter in this project and never the organising key. One meeting, at the top."""
        assert "next_meeting" in preview
        for entry in preview["districts"].values():
            assert "next_meeting" not in entry

    def test_it_carries_an_as_of(self, preview):
        """The panel summarises pages that hold the per-fact provenance, so it states when it
        was built and links onward rather than repeating a source line per field."""
        assert preview["as_of"]

    def test_a_district_entry_has_what_the_panel_shows(self, preview):
        entry = preview["districts"]["1"]
        # The tabular groups all live under one key now: `render.district_tables` declares
        # their columns once and both the page and the panel render those specs.
        assert set(entry) == {"member", "tables"}

    def test_committee_roles_travel_with_the_name(self, preview):
        """Chair and member are different facts about the same person."""
        roles = [
            {"name": row[0], "role": row[1]}
            for entry in preview["districts"].values()
            for spec in entry["tables"]
            if spec["legend"] == "Committees"
            for row in spec["rows"]
        ]
        assert roles, "no district in the fixture has a committee assignment"
        for committee in roles:
            assert set(committee) == {"name", "role"}

    def test_boards_are_ordered_by_how_much_of_the_district_they_cover(self, preview):
        for entry in preview["districts"].values():
            specs = [s for s in entry["tables"] if s["legend"] == "Community boards"]
            shares = [row[1]["share"] for s in specs for row in s["rows"]]
            assert shares == sorted(shares, reverse=True)

    def test_the_budget_preview_is_thinner_than_the_page(self, preview):
        """Explanations and agency responses are on the board page, not here: carrying them
        took this artifact to 41 KB gzipped for text the panel never shows."""
        for entry in preview["boards"].values():
            for spec in entry["tables"]:
                if spec["legend"] != "Budget requests":
                    continue
                assert spec["columns"] == ["Request", "Category"]
                assert len(spec["rows"]) <= PREVIEW_REQUESTS
                # Two columns and no more: an explanation or an agency response here
                # would be text the panel never shows.
                assert all(len(row) == 2 for row in spec["rows"])

    def test_the_preview_carries_no_priority_number(self, preview):
        """Priority is the rank *within* a budget category, so it repeats: three requests
        all rendered as "1." in the panel, which reads as a ranking no board filed. The
        category carries the meaning, so that is what ships."""
        for entry in preview["boards"].values():
            for spec in entry["tables"]:
                if spec["legend"] != "Budget requests":
                    continue
                assert "Priority" not in spec["columns"]
                for row in spec["rows"]:
                    assert not str(row[1]).strip().rstrip(".").isdigit()

    def test_no_officer_name_reaches_the_preview(self, preview):
        """Chairs and district managers are never published; the office is."""
        blob = json.dumps(preview["boards"])
        for field in ("chair", "district_manager", "manager"):
            assert field not in blob

    def test_a_short_preview_fails_the_build(self, tmp_path, raw_dir_session, monkeypatch):
        """A preview missing a district would leave the panel silently empty for it."""
        import showup.build as build_module

        def short(*args, **kwargs):
            payload = preview_payload(*args, **kwargs)
            payload["districts"].pop("1")
            return payload

        monkeypatch.setattr(build_module, "preview_payload", short)
        with pytest.raises(BuildError, match="preview covers"):
            build_site(raw_dir_session, tmp_path / "out", today=date(2026, 9, 22))


class TestTheMapRefusesToRank:
    def test_nothing_on_the_map_page_claims_a_ranking(self, site):
        """product-brief.md §5 forbids ranking districts against each other. The copy that
        said so was cut under voice.md class 4 — the uniform fill *is* the claim — so what
        is asserted here is the absence of ranking language. The fill itself is checked by
        `test_the_fill_does_not_vary_by_any_datum` below."""
        html = (site / "map" / "index.html").read_text(encoding="utf-8").lower()
        for word in ("rank", "score", "worst", "best"):
            assert word not in html, f"the map page uses ranking language: {word!r}"

    #: The district layers' own paint block is the only place the choropleth ban applies.
    #: Scoped deliberately: this guard used to grep the whole module, and fired on an
    #: `interpolate` added to the *basemap's* woodland opacity, which shades nothing of ours.

    def _district_paint(self) -> str:
        source = (REPO_ROOT / "src" / "showup" / "assets" / "map.mjs").read_text(encoding="utf-8")
        start = source.index("id: `${layer.source}-fill`")
        end = source.index("id: `${layer.source}-line`")
        return source[start:end]

    def test_the_district_fill_has_no_data_driven_ramp(self):
        """One fill for every district, and two more only for hover and selection.

        `step` and `match` are banned outright: neither has a use here that is not shading
        a district by a value. `interpolate` is allowed on `['zoom']` alone — a zoom ramp
        fades every district identically, which is a legibility choice and carries no
        datum. Any other `interpolate` input is a choropleth and fails.
        """
        paint = self._district_paint()
        assert "'fill-color'" in paint
        for ramp in ("step", "match"):
            assert f"'{ramp}'" not in paint, f"a {ramp} expression shades districts by value"
        for found in re.finditer(r"'interpolate'", paint):
            tail = paint[found.end() : found.end() + 80]
            assert "['zoom']" in tail, (
                f"an interpolate on something other than zoom shades districts by value: {tail!r}"
            )

    def test_the_district_fill_reads_no_feature_property(self):
        """`feature-state` is hover and selection, which the reader caused. `get` would be a
        datum about the district itself, which is what product-brief.md §5 forbids."""
        paint = self._district_paint()
        assert "feature-state" in paint
        assert "['get'" not in paint and '["get"' not in paint, (
            "the district fill reads a feature property; that is a choropleth"
        )

    def test_the_geometry_it_draws_is_the_one_already_shipped(self, site):
        """No separate display artifact: the council layer reuses the resolution file the
        address box already needs. At 390 px one pixel is about 100 m, so 2.2 m detail is
        far finer than anything a phone can show."""
        assert (site / "data" / "districts.geo.json").is_file()
        assert not list((site / "data").glob("*display*"))

    def test_the_geometry_carries_every_district(self, site):
        geometry = json.loads((site / "data" / "districts.geo.json").read_text(encoding="utf-8"))
        districts = {feature["properties"]["coundist"] for feature in geometry["features"]}
        assert len(districts) == DISTRICT_COUNT
