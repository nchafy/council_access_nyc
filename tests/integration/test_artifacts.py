"""The eight artifacts the ETL exists to produce, asserted on a real build.

This file is what is left of three gates that drove a browser. `/map/` and then the webxp
programs were this project's front end until 2026-11-09; the programs moved to the `webxp`
repository and this one became headless. What survived the move is every assertion whose
subject is an artifact rather than a rendered page — the counts a consumer indexes by, the
one size budget on a shipped file, and the shapes a pane would silently render empty.

Carried here from `tests/integration/test_map_route.py` (the artifact half of it) and from
`scripts/verify.py`, which asserted some of this against a live server. There is no server
now, so these are hermetic: they build into a tmp directory and read the files.
"""

from __future__ import annotations

import gzip
import json
import shutil
from datetime import date

import pytest

from showup import render
from showup.build import BuildError, build_site
from showup.fetch import cache_path
from showup.model import BOARD_COUNT, DISTRICT_COUNT
from showup.render import PREVIEW_REQUESTS, preview_payload

#: Every file the build writes, and nothing else. A consumer commits these as static files,
#: so one appearing or vanishing is a change to that contract rather than an internal detail.
ARTIFACTS = (
    "data/board-meetings.json",
    "data/boards.geo.json",
    "data/districts.geo.json",
    "data/lookup.json",
    "data/preview.json",
    "data/references.json",
    "data/zips.geo.json",
    "manifest.json",
)

#: outline §6A.3. The two geometry files are the heaviest thing a reader of the consuming
#: site downloads, and the budget was enforced by a page-weight gate that drove a browser.
#: It is pure gzip arithmetic, so it needs no browser and survives here.
GEOMETRY_GZIP_BUDGET = 300 * 1024

#: ZIP codes resolvable without a network round trip. A floor rather than a count: the
#: source publishes about 215 and the number moves, but a handful means the join failed.
ZIP_FLOOR = 150


@pytest.fixture(scope="module")
def site(tmp_path_factory, raw_dir_session):
    out = tmp_path_factory.mktemp("artifact-site")
    build_site(raw_dir_session, out, today=date(2026, 9, 22))
    return out


class TestTheBuildWritesTheseAndOnlyThese:
    def test_every_artifact_is_written(self, site):
        missing = [name for name in ARTIFACTS if not (site / name).is_file()]
        assert not missing, missing

    def test_nothing_else_is_written(self, site):
        """The front end was deleted on 2026-11-09. A stray HTML file, stylesheet or module
        here means some part of it came back without anyone deciding to bring it."""
        written = {path.relative_to(site).as_posix() for path in site.rglob("*") if path.is_file()}
        assert written == set(ARTIFACTS), sorted(written ^ set(ARTIFACTS))

    def test_it_renders_no_html_at_all(self, site):
        """The replacement for "there is exactly one page". That assertion, rewritten to
        expect zero, would be a tautology over a build that cannot emit HTML; this one would
        fail if a renderer were reintroduced, which is the thing worth catching."""
        assert not list(site.rglob("*.html"))
        assert not list(site.rglob("*.css"))
        assert not list(site.rglob("*.mjs"))


class TestTheCountsAConsumerIndexesBy:
    """Each of these was asserted against a live server by `scripts/verify.py`. A short
    artifact is the quiet failure: the consuming desktop draws a map with holes in it, or a
    pane that says nothing, rather than reporting an error."""

    def test_the_lookup_carries_every_district_and_board(self, site):
        lookup = json.loads((site / "data" / "lookup.json").read_text(encoding="utf-8"))
        assert len(lookup["districts"]) == DISTRICT_COUNT
        assert len(lookup["boards"]) == BOARD_COUNT

    def test_the_lookup_resolves_zips_without_a_network(self, site):
        lookup = json.loads((site / "data" / "lookup.json").read_text(encoding="utf-8"))
        assert len(lookup["zips"]) > ZIP_FLOOR, len(lookup["zips"])

    def test_the_schedule_lists_every_board(self, site):
        """All 59, so a consumer can tell "no meetings scheduled" from "this board cannot
        be read"."""
        schedule = json.loads((site / "data" / "board-meetings.json").read_text())
        assert len(schedule["boards"]) == BOARD_COUNT

    def test_the_preview_is_dated(self, site):
        preview = json.loads((site / "data" / "preview.json").read_text(encoding="utf-8"))
        assert preview["as_of"], "without as_of no pane can say how old it is"


class TestTheGeometryBudget:
    """§6A.3, enforced here because the gate that held it drove a browser and is gone.

    What this can and cannot show, stated because the numbers are far apart. The fixture
    build carries a reduced dataset — its districts geometry measured 9,230 bytes raw on
    2026-11-09 — where a citywide build measures 152,836 and 411,411 raw for the two layers,
    32,857 and 96,197 gzipped, 129 KB together against the 300 KB budget. So a pass here is a
    tripwire, not the guarantee: it catches the build shipping raw geometry instead of
    simplified, which would balloon the fixture too, and it does not exercise the real
    headroom. Only a citywide build does that, and this suite has no citywide input.
    """

    def test_both_layers_fit_the_budget_gzipped(self, site):
        total = sum(
            len(gzip.compress((site / "data" / name).read_bytes(), 9))
            for name in ("districts.geo.json", "boards.geo.json")
        )
        assert total <= GEOMETRY_GZIP_BUDGET, (
            f"{total // 1024} KB gzipped against a {GEOMETRY_GZIP_BUDGET // 1024} KB budget"
        )

    def test_the_measurement_is_of_something(self, site):
        """Harness honesty: a budget check over a missing file passes at zero bytes.

        The floor is measured against the fixture, not against a citywide build: its
        districts geometry is 9,230 bytes on 2026-11-09. 1,000 sits well under that and well
        over nothing.
        """
        for name in ("districts.geo.json", "boards.geo.json"):
            assert (site / "data" / name).stat().st_size > 1_000, (
                f"{name} is {(site / 'data' / name).stat().st_size} bytes; the budget above "
                "would pass over a file this small whatever the build did"
            )


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
