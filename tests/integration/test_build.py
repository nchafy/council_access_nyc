"""Building a whole site from fixtures, and the hostile-content case.

`test_hostile_register_text_arrives_stripped` drives a hostile string from an upstream
payload to a shipped data file, which is the end-to-end proof of docs/phase-1-scope.md §4.1
now that the one page the build writes renders no upstream text.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pytest

from showup import render
from showup.build import BuildError, build_site
from showup.crosswalk import CrosswalkError
from showup.crosswalk import load as load_crosswalk
from showup.render import PREVIEW_REQUESTS

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "tests" / "fixtures"


class TestBuild:
    def test_builds_all_51_districts(self, raw_dir, tmp_path):
        report = build_site(raw_dir, tmp_path / "site", today=date(2026, 9, 22))
        assert report["districts"] == 51
        assert report["meetings_parsed"] == 60
        assert report["shortlist"] == 5

    def test_manifest_carries_inputs_not_a_verdict(self, raw_dir, tmp_path):
        out = tmp_path / "site"
        build_site(raw_dir, out, today=date(2026, 9, 22))
        manifest = json.loads((out / "manifest.json").read_text())
        for source in manifest["sources"].values():
            assert "fetched_at" in source
            assert "max_age_hours" in source
        # Staleness is the browser's job; a baked boolean is what lets a dead site lie.
        assert "degraded" not in json.dumps(manifest)

    def test_every_fetched_source_is_disclosed(self, raw_dir, tmp_path):
        """`fetch.Source` says `label`, `dataset` and `url` exist "so a source cannot be
        fetched without being disclosed". That held because `/references/` rendered them;
        when those pages were deleted on 2026-11-08 the fields stayed populated and nothing
        read them, so the promise was broken silently. `/data/references.json` is where it
        lives now, and this is what keeps it.
        """
        from showup.fetch import SOURCES

        out = tmp_path / "site"
        build_site(raw_dir, out, today=date(2026, 9, 22))
        references = json.loads((out / "data" / "references.json").read_text())

        assert len(references["datasets"]) == len(SOURCES)
        for source in references["datasets"]:
            assert source["dataset"], source
            assert source["url"], source
            assert source["why"], source
            assert source["window"], source

        published = {source["dataset"] for source in references["datasets"]}
        for identifier in ("uvw5-9znb", "ruf7-3wgc", "vn4m-mk4t", "5crt-au7u", "872g-cjhh"):
            assert any(identifier in name for name in published), (
                f"{identifier} is fetched and no longer disclosed anywhere a reader can see"
            )

    def test_a_short_references_artifact_fails_the_build(self, raw_dir, tmp_path, monkeypatch):
        """A source silently missing from the list is the disclosure promise broken in the
        quietest way: the Readme renders a shorter table and looks complete."""
        import showup.build as build_module

        def short(*args, **kwargs):
            payload = render.references_payload(*args, **kwargs)
            payload["datasets"].pop()
            return payload

        monkeypatch.setattr(build_module, "references_payload", short)
        with pytest.raises(BuildError, match="references covers"):
            build_site(raw_dir, tmp_path / "out", today=date(2026, 9, 22))

    def test_a_source_with_no_identifier_fails_the_build(self, raw_dir, tmp_path, monkeypatch):
        """A row with a label and no dataset id renders as a named source a reader cannot
        check, which is worse than an absent row because it looks cited."""
        import showup.build as build_module

        # Bound before the patch, or the replacement calls itself.
        real_rows = build_module._reference_rows

        def undisclosed(*args, **kwargs):
            rows = real_rows(*args, **kwargs)
            rows[0] = {**rows[0], "dataset": ""}
            return rows

        monkeypatch.setattr(build_module, "_reference_rows", undisclosed)
        with pytest.raises(BuildError, match="carry no identifier"):
            build_site(raw_dir, tmp_path / "out", today=date(2026, 9, 22))

    def test_the_caveats_that_qualify_a_published_figure_are_published_with_it(
        self, raw_dir, tmp_path
    ):
        """Each of these qualifies a number shown elsewhere on the site, so losing it leaves
        the number looking more certain than it is. All four were deleted with
        `/references/` and existed nowhere in the repository for a day."""
        out = tmp_path / "site"
        build_site(raw_dir, out, today=date(2026, 9, 22))
        prose = " ".join(json.loads((out / "data" / "references.json").read_text())["caveats"])
        for clause in (
            "ranks within a budget category",
            "not a commitment and not a funded outcome",
            "the board office address, not the meeting venue",
            "compares one board or district with another",
        ):
            assert clause in prose, f"{clause!r} qualifies a published figure and is unpublished"

    def test_every_published_timestamp_names_an_instant(self, raw_dir, tmp_path):
        """Staleness is computed in the reader's browser, so a wall clock is not enough.

        A naive ISO string is read by a browser as *local* time, so the same stamp written by
        a UTC build reads five hours younger in New York — age under-reported, in the
        direction that hides the problem. Every timestamp the manifest publishes therefore
        carries an offset, and `datetime.fromisoformat` is what proves it: it returns a naive
        value for a string without one.
        """
        out = tmp_path / "site"
        build_site(raw_dir, out, today=date(2026, 9, 22))
        manifest = json.loads((out / "manifest.json").read_text())
        stamps = {"built_at": manifest["built_at"]} | {
            f"sources.{name}.fetched_at": source["fetched_at"]
            for name, source in manifest["sources"].items()
        }
        naive = {
            where: value
            for where, value in stamps.items()
            if datetime.fromisoformat(value).tzinfo is None
        }
        assert not naive, f"these stamps name a wall clock rather than an instant: {naive}"

    def test_a_short_calendar_fails_closed(self, raw_dir, tmp_path):
        (raw_dir / "legistar_calendar.html").write_text(
            '<table id="ctl00_ContentPlaceHolder1_gridCalendar_ctl00"></table>',
            encoding="utf-8",
        )
        with pytest.raises(BuildError, match="floor"):
            build_site(raw_dir, tmp_path / "site", today=date(2026, 9, 22))

    def test_a_failed_build_leaves_the_previous_output_intact(self, raw_dir, tmp_path):
        """The staging-then-swap. Read off `manifest.json` rather than the page it used to
        read: the output is eight artifacts now, and a consumer that committed half of a
        failed run would ship a desktop whose programs disagree with each other."""
        out = tmp_path / "site"
        build_site(raw_dir, out, today=date(2026, 9, 22))
        marker = (out / "manifest.json").read_text()

        (raw_dir / "legistar_calendar.html").write_text(
            '<table id="ctl00_ContentPlaceHolder1_gridCalendar_ctl00"></table>', encoding="utf-8"
        )
        with pytest.raises(BuildError):
            build_site(raw_dir, out, today=date(2026, 9, 22))
        assert (out / "manifest.json").read_text() == marker


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


class TestBoardsInTheShippedData:
    """The board facts the programs read. They were a district page section and 59 board
    pages; `data/preview.json` is where they live now."""

    def test_boards_carry_their_contact_details(self, raw_dir, tmp_path):
        out = tmp_path / "site"
        build_site(raw_dir, out, today=date(2026, 9, 22))
        board = json.loads((out / "data" / "preview.json").read_text())["boards"]["302"]
        assert board["label"] == "Brooklyn Community Board 2"
        assert board["phone"]
        assert board["address"]
        # Verbatim, not reformatted into a date.
        assert any(day in (board["cadence"] or "") for day in ("Tuesday", "Wednesday", "Thursday"))

    def test_chair_and_district_manager_are_never_rendered(self, raw_dir, tmp_path):
        """The privacy line: we publish the institution, not the individuals.

        Checked over every file the build writes that is derived from the boards dataset,
        which is where the names could leak now that no page carries a board.
        """
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
        written = [*sorted((out / "data").glob("*.json")), out / "manifest.json"]
        # Pinned, because the sweep is only worth anything over the files that exist: this
        # read `out / "index.html"` until the front end was deleted on 2026-11-09, and a
        # list that silently lost an entry would still pass over the rest. Nine since
        # `detail.json` was added on 2026-11-10 — which is the artifact that matters most
        # here, because it is the only one carrying the boards' own free text.
        assert len(written) == 9, written
        for artifact in written:
            text = artifact.read_text()
            for name in names:
                assert name not in text, f"{name} leaked into {artifact.relative_to(out)}"

    def test_the_officer_fields_never_reach_the_build(self, raw_dir, tmp_path):
        """A negative control for the names above: the dataset's own column names must be
        absent too, so a future field carrying a name cannot arrive unnoticed."""
        out = tmp_path / "site"
        build_site(raw_dir, out, today=date(2026, 9, 22))
        preview = (out / "data" / "preview.json").read_text()
        for field in ("cb_chair", "cb_district_manager", "chair", "district_manager"):
            assert field not in preview, field


class TestBoardCoverage:
    """59 boards or none, and the join that says which districts cover one."""

    def test_all_59_boards_are_covered(self, raw_dir, tmp_path):
        out = tmp_path / "site"
        report = build_site(raw_dir, out, today=date(2026, 9, 22))
        assert report["board_pages"] == 59
        preview = json.loads((out / "data" / "preview.json").read_text())
        assert len(preview["boards"]) == 59

    def test_a_board_names_the_council_districts_covering_it(self, raw_dir, tmp_path):
        out = tmp_path / "site"
        build_site(raw_dir, out, today=date(2026, 9, 22))
        board = json.loads((out / "data" / "preview.json").read_text())["boards"]["302"]
        rows = [
            row[0]["text"]
            for spec in board["tables"]
            if spec["legend"] == "Council districts"
            for row in spec["rows"]
        ]
        # Brooklyn CB 2 spans council districts 33 and 35.
        assert "Council District 33" in rows
        assert "Council District 35" in rows

    def test_a_district_names_the_boards_covering_it(self, raw_dir, tmp_path):
        out = tmp_path / "site"
        build_site(raw_dir, out, today=date(2026, 9, 22))
        district = json.loads((out / "data" / "preview.json").read_text())["districts"]["35"]
        rows = [
            row[0]["text"]
            for spec in district["tables"]
            if spec["legend"] == "Community boards"
            for row in spec["rows"]
        ]
        assert "Brooklyn Community Board 2" in rows


class TestBudgetRequestsInTheShippedData:
    """The eighth source, in the artifact the board program reads. The honesty boundary is
    the spec: an annual filing not current activity, a request not a commitment, quoted not
    bucketed."""

    @staticmethod
    def _board(raw_dir, tmp_path, code: str = "302") -> dict:
        out = tmp_path / "site"
        build_site(raw_dir, out, today=date(2026, 9, 22))
        return json.loads((out / "data" / "preview.json").read_text())["boards"][code]

    def _requests(self, raw_dir, tmp_path, code: str = "302") -> dict | None:
        return next(
            (
                spec
                for spec in self._board(raw_dir, tmp_path, code)["tables"]
                if spec["legend"] == "Budget requests"
            ),
            None,
        )

    def test_the_section_names_the_fiscal_year_and_the_publication_date(self, raw_dir, tmp_path):
        """The caption is the only place the denominator and the edition travel together, so
        a request count without its fiscal year cannot ship."""
        caption = self._requests(raw_dir, tmp_path)["caption"]
        assert "Fiscal 2027" in caption
        # Brooklyn CB 2 has seven requests in the committed fixture's edition.
        assert "7 filed" in caption

    def test_the_cap_is_three_requests(self, raw_dir, tmp_path):
        """Thinner than the page was: carrying every row took this artifact to 41 KB
        gzipped for text the panel never shows."""
        assert len(self._requests(raw_dir, tmp_path)["rows"]) == PREVIEW_REQUESTS

    def test_the_reply_is_not_bucketed_into_a_verdict(self, raw_dir, tmp_path):
        """Agency replies have five phrasings, none of which survives a
        supported/not-supported bucket, so no column may claim one."""
        columns = self._requests(raw_dir, tmp_path)["columns"]
        assert columns == ["Request", "Category"]
        for verdict in ("supported", "approved", "funded", "outcome"):
            assert verdict not in " ".join(columns).lower()

    def test_the_section_neither_ranks_nor_scores_boards(self, raw_dir, tmp_path):
        blob = json.dumps(self._requests(raw_dir, tmp_path)).lower()
        for banned in ("score", "percentile", "league", "out of 100", "compared with"):
            assert banned not in blob

    def test_a_board_the_register_does_not_cover_carries_no_table(self, raw_dir, tmp_path):
        """The fixture carries six boards, so the other 53 are the empty state: the group is
        absent rather than present and empty, which would read as "we looked and found
        nothing"."""
        assert self._requests(raw_dir, tmp_path, "308") is None

    def test_a_missing_register_does_not_break_the_build(self, raw_dir, tmp_path):
        (raw_dir / "board_budget_requests.json").unlink()
        out = tmp_path / "site"
        report = build_site(raw_dir, out, today=date(2026, 9, 22))
        assert report["board_pages"] == 59
        assert report["budget_requests"] == 0
        assert report["budget_publication"] is None
        board = json.loads((out / "data" / "preview.json").read_text())["boards"]["302"]
        assert "Budget requests" not in [spec["legend"] for spec in board["tables"]]

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

    def test_hostile_register_text_arrives_stripped(self, raw_dir, tmp_path):
        """docs/phase-1-scope.md §4.1, end to end: a hostile upstream string reaches a
        shipped artifact with its markup already gone.

        Stripping happens at ingest rather than at render, which is what still makes this
        provable now that no page renders upstream text: `preview.json` is consumed by
        programs that write text nodes, so a tag that survived the parse would be the only
        way markup could reach a reader.
        """
        rows = json.loads((raw_dir / "board_budget_requests.json").read_text())
        hostile = "<script>alert('register')</script>Fix the &quot;park&quot;"
        for row in rows:
            if row["boro"] == "2" and row["board"] == "02":
                row["request"] = hostile
                row["explanation"] = hostile
                row["response"] = hostile
        (raw_dir / "board_budget_requests.json").write_text(json.dumps(rows), encoding="utf-8")
        out = tmp_path / "site"
        build_site(raw_dir, out, today=date(2026, 9, 22))
        preview = (out / "data" / "preview.json").read_text()
        # The negative control: the harmless half of the hostile string must be there, or
        # this is asserting against a file the string never reached.
        assert "Fix the" in preview
        assert "<script" not in preview
        assert "alert(" not in preview


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

    def test_an_unreadable_pb_roster_fails_closed(self, raw_dir, tmp_path):
        """A roster that cannot be read must stop the build, not render 51 districts as
        "not taking part" — a wrong answer is worse than a missing page."""
        (raw_dir / "participatory_budgeting.json").write_text("{", encoding="utf-8")
        with pytest.raises(BuildError, match=r"participatory_budgeting\.json"):
            build_site(raw_dir, tmp_path / "site", today=date(2026, 9, 22))

    def test_a_pb_roster_below_the_floor_fails_closed(self, raw_dir, tmp_path):
        """The floor is enforced in the parser, so it surfaces here as a BuildError."""
        payload = json.loads((raw_dir / "participatory_budgeting.json").read_text())
        payload["idea_map_html"] = '<div data-district="1"></div>'
        (raw_dir / "participatory_budgeting.json").write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(BuildError, match="floor is"):
            build_site(raw_dir, tmp_path / "site", today=date(2026, 9, 22))

    def test_a_broken_board_calendar_fails_closed(self, raw_dir, tmp_path):
        """A thin calendar ingest stops the build rather than quietly emptying 21 board
        pages: a board page with no calendar reads as "this board holds no meetings"."""
        (raw_dir / "board_meetings.json").write_text(json.dumps({"feeds": {}}), encoding="utf-8")
        with pytest.raises(BuildError, match="floor is"):
            build_site(raw_dir, tmp_path / "site", today=date(2026, 9, 22))

    def test_a_thin_zip_geometry_fails_closed(self, raw_dir, tmp_path):
        """The ZIP outline is only a hint, but a half-read file would draw the wrong
        boundary for a ZIP, which is worse than drawing none."""
        payload = json.loads((raw_dir / "modzcta.geojson").read_text())
        payload["features"] = payload["features"][:3]
        (raw_dir / "modzcta.geojson").write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(BuildError, match="ZIP geometry has 3 features"):
            build_site(raw_dir, tmp_path / "site", today=date(2026, 9, 22))

    def test_a_wrong_district_count_fails_closed(self, raw_dir, tmp_path):
        (raw_dir / "districts.geojson").write_text(
            json.dumps({"type": "FeatureCollection", "features": []}), encoding="utf-8"
        )
        with pytest.raises(BuildError, match="district geometry"):
            build_site(raw_dir, tmp_path / "site", today=date(2026, 9, 22))
