"""The map program, and the rule that it is the only thing paying for the map.

`docs/dependencies.md` allows a vendored browser dependency on condition that it is
load-gated. That condition is only real if something checks it, so this file is the check.
The gate moved with the front end: `/map/` was the one page allowed to name MapLibre, and
`apps/showup-map/app.mjs` is now the one module allowed to import it — and it must do so
with a dynamic `import()`, because the desktop loads every program's module up front.
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import date
from pathlib import Path

import pytest
from perf import budget, gzipped_size

from showup import render
from showup.build import BASEMAP_FILES, VENDOR_FILES, BuildError, build_site
from showup.fetch import cache_path
from showup.model import BOARD_COUNT, DISTRICT_COUNT
from showup.render import PREVIEW_REQUESTS, preview_payload
from showup.sources.boards import JOINT_INTEREST_AREAS

REPO_ROOT = Path(__file__).resolve().parents[2]
APPS = REPO_ROOT / "src" / "showup" / "apps"
MAP_APP = APPS / "showup-map" / "app.mjs"


@pytest.fixture(scope="module")
def site(tmp_path_factory, raw_dir_session) -> Path:
    out = tmp_path_factory.mktemp("map-site")
    build_site(raw_dir_session, out, today=date(2026, 9, 22))
    return out


class TestTheMapIsItsOwnProgram:
    def test_the_landing_page_has_no_map(self, site):
        """The one document the build writes is a mount point: no canvas, and nothing that
        would make every reader download a map library to see a list of districts."""
        html = (site / "index.html").read_text(encoding="utf-8")
        assert 'id="map"' not in html
        assert "maplibre" not in html.lower()

    def test_the_landing_page_reaches_the_map_through_its_program(self, site):
        """The desktop has no links: it is a mount point, and the map is a program the Show Up
        folder launches. So the reachable thing to assert is that the program exists and names
        the route it owns."""
        assert 'id="webxp"' in (site / "index.html").read_text(encoding="utf-8")
        folder = (site / "apps" / "showup" / "app.mjs").read_text(encoding="utf-8")
        assert "'showup-map'" in folder

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

    def test_the_toggle_offers_exactly_the_two_layers(self):
        """The buttons are built from `LAYERS`, so the toggle cannot offer a layer the map
        does not draw. Read out of the module, which is where the pair is declared."""
        source = MAP_APP.read_text(encoding="utf-8")
        declared = re.search(r"const LAYERS = \{(.*?)\n\};", source, re.DOTALL)
        assert declared, "LAYERS is no longer a module-level object literal"
        assert re.findall(r"^  (\w+): \{", declared.group(1), re.MULTILINE) == [
            "council",
            "board",
        ]

    def test_the_toggle_preselects_council_and_the_card_starts_hidden(self):
        """A toggle that switches nothing is worse than no toggle, and a card covering the
        map before anything is selected says nothing at all."""
        source = MAP_APP.read_text(encoding="utf-8")
        assert "aria-pressed', String(name === 'council')" in source
        assert "facts.hidden = true;" in source

    def test_every_vendored_file_ships(self, site):
        """MapLibre and the base map both, because the map route imports from each."""
        # `webxp` is a directory rather than a file: the window manager is vendored as a
        # folder with its own PROVENANCE.md, because it has no remote to fetch and pin.
        assert {path.name for path in (site / "vendor").iterdir()} == {
            *VENDOR_FILES,
            *BASEMAP_FILES,
            "webxp",
        }

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
    #: Every module the build ships that is ours rather than vendored. The desktop loads all
    #: of them to draw the taskbar, so a top-level MapLibre import in any of them would make
    #: every reader download the map library.
    OUR_MODULES = (
        REPO_ROOT / "src" / "showup" / "boot.mjs",
        *sorted(APPS.rglob("*.mjs")),
    )

    def test_only_the_map_program_reaches_for_the_library(self):
        """The load-gating condition in docs/dependencies.md, enforced at its new address.

        It was "one page may name MapLibre". The desktop has one page, so the thing that can
        still go wrong is a second program importing the base map — which is what would put
        the library on the critical path for the readme.
        """
        offenders = [
            path.relative_to(REPO_ROOT).as_posix()
            for path in self.OUR_MODULES
            if path != MAP_APP
            and re.search(r"""import\s*\(?\s*['"][^'"\n]*(maplibre|basemap)""", path.read_text())
        ]
        assert not offenders, f"these modules would download the map library: {offenders}"

    def test_the_map_program_imports_it_lazily(self):
        """A top-level import would run when the desktop loads the program list, which is
        before anybody has opened the map."""
        source = MAP_APP.read_text(encoding="utf-8")
        assert "await import('/vendor/basemap.mjs')" in source
        assert not re.search(
            r"""^import[^\n]*['"][^'"\n]*(maplibre|basemap)""", source, re.MULTILINE
        ), "the base map is imported at the top level, so loading the program loads it"

    def test_no_document_loads_the_library_as_a_script(self, site):
        """The library is imported from a module, never as a script tag, so the document's
        own weight stays inside R40's page budget."""
        for page in site.rglob("*.html"):
            html = page.read_text(encoding="utf-8")
            assert "maplibre" not in html.lower(), page
            assert 'src="/vendor/basemap.mjs"' not in html, page

    def test_the_library_is_inside_its_own_budget(self, site):
        """It is excluded from the page and script budgets, so it needs its own number."""
        total = sum(
            gzipped_size(path.read_bytes()) for path in (site / "vendor").glob("maplibre-gl*")
        )
        assert total <= budget()["map_library_gzip_bytes"]


class TestTheMapIsNeverTheOnlyWay:
    def test_the_folder_offers_a_route_that_needs_no_canvas(self):
        """R6's location-free path. A WebGL canvas is not a navigation route, so the folder
        that opens on the desktop lists two programs that answer without one."""
        folder = (APPS / "showup" / "app.mjs").read_text(encoding="utf-8")
        for program in ("showup-councils", "showup-boards"):
            assert f"id: '{program}'" in folder, program

    def test_those_programs_can_answer_about_every_district_and_board(self, site):
        """The two list programs read the shipped lookup through `shared/data.mjs`, so what
        they can reach is what it carries. 110 entries between them, with no map loaded."""
        lookup = json.loads((site / "data" / "lookup.json").read_text(encoding="utf-8"))
        assert len(lookup["districts"]) == DISTRICT_COUNT
        assert len(lookup["boards"]) == BOARD_COUNT
        assert "LOOKUP = '/data/lookup.json'" in (APPS / "shared" / "data.mjs").read_text()
        for program in ("showup-councils", "showup-boards"):
            source = (APPS / program / "app.mjs").read_text(encoding="utf-8")
            assert "from '../shared/data.mjs'" in source, program

    def test_selecting_fills_a_card_rather_than_navigating(self):
        """A click that moved the page would make the layer toggle useless for comparing two
        boundaries, so selection highlights and fills the card instead.

        It was a sliding `<aside class="detail">` on `/map/`; the window is that panel now,
        and the card is built in `build()`.
        """
        source = MAP_APP.read_text(encoding="utf-8")
        assert "el('div', 'card facts-card')" in source
        assert "location.assign" not in source
        assert "location.href =" not in source


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
    def test_nothing_the_map_program_says_claims_a_ranking(self):
        """product-brief.md §5 forbids ranking districts against each other. The copy that
        said so was cut under voice.md class 4 — the uniform fill *is* the claim — so what
        is asserted here is the absence of ranking language. The fill itself is checked
        below.

        Over the program's quoted strings rather than the whole file: the page this replaced
        carried only rendered text, and a comment explaining a CSS specificity fight is not
        something a reader sees.
        """
        quoted = re.findall(r"'([^'\n]*)'|`([^`\n]*)`", MAP_APP.read_text(encoding="utf-8"))
        copy = " ".join(single or backtick for single, backtick in quoted).lower()
        # Harness honesty: a regex that stopped matching would report clean over nothing.
        assert "council districts" in copy, "the string scan found no rendered copy"
        for word in ("rank", "score", "worst", "best"):
            assert word not in copy, f"the map program says {word!r} to a reader"

    #: The district layers' own paint block is the only place the choropleth ban applies.
    #: Scoped deliberately: this guard used to grep the whole module, and fired on an
    #: `interpolate` added to the *basemap's* woodland opacity, which shades nothing of ours.

    def _district_paint(self) -> str:
        source = MAP_APP.read_text(encoding="utf-8")
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
