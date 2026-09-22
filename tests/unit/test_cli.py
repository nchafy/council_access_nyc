"""The command line surface.

Thin by design — the logic lives in the modules it calls — but not untested, for a
specific reason: a change to the build report once silently failed to apply, so the
board page count stopped being printed and nothing noticed. The report lines are how
a regression gets seen by a human, which makes them worth asserting.
"""

from __future__ import annotations

import json

import pytest

from showup.cli import main


@pytest.fixture
def repo(tmp_path, monkeypatch, calendar_html, district_page_html):
    """A minimal repo layout the CLI can run against."""
    import shutil
    from pathlib import Path

    fixtures = Path(__file__).resolve().parents[1] / "fixtures"
    raw = tmp_path / "etl" / "raw"
    raw.mkdir(parents=True)
    (raw / "legistar_calendar.html").write_text(calendar_html, encoding="utf-8")

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
    ] + [
        {
            "name": f"Former {i}",
            "council_member_id": str(2000 + i),
            "district": str((i % 51) + 1),
            "term_start": "2014-01-01T00:00:00.000",
            "term_end": "2017-12-31T00:00:00.000",
        }
        for i in range(300)
    ]
    (raw / "members.json").write_text(json.dumps(members), encoding="utf-8")
    shutil.copy2(fixtures / "community_boards.json", raw / "community_boards.json")

    features = [
        {
            "type": "Feature",
            "properties": {"coundist": str(n)},
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [-74.3 + (n - 1) * 0.02, 40.5],
                        [-74.282 + (n - 1) * 0.02, 40.5],
                        [-74.282 + (n - 1) * 0.02, 40.518],
                        [-74.3 + (n - 1) * 0.02, 40.518],
                        [-74.3 + (n - 1) * 0.02, 40.5],
                    ]
                ],
            },
        }
        for n in range(1, 52)
    ]
    (raw / "districts.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8"
    )

    crosswalks = tmp_path / "crosswalks"
    crosswalks.mkdir()
    shutil.copy2(
        Path(__file__).resolve().parents[2] / "crosswalks" / "council_to_boards.json",
        crosswalks / "council_to_boards.json",
    )

    monkeypatch.setattr("showup.cli.REPO_ROOT", tmp_path)
    monkeypatch.setattr("showup.build.CROSSWALK_PATH", crosswalks / "council_to_boards.json")
    return tmp_path


class TestBuild:
    def test_reports_both_page_counts(self, repo, capsys):
        """The regression this file exists for: the board count silently vanished
        from the report because a patch to the print statement did not apply."""
        assert main(["build"]) == 0
        out = capsys.readouterr().out
        assert "51 district pages" in out
        assert "59 board pages" in out

    def test_reports_the_figures_a_human_watches_for_drift(self, repo, capsys):
        main(["build"])
        out = capsys.readouterr().out
        for label in ("meetings parsed", "shortlist shown", "calendar through", "board links"):
            assert label in out, f"the build report no longer prints {label!r}"

    def test_missing_cache_is_a_clear_error_not_a_traceback(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr("showup.cli.REPO_ROOT", tmp_path)
        assert main(["build"]) == 2
        assert "no cached sources" in capsys.readouterr().err

    def test_a_refused_build_exits_nonzero_and_says_why(self, repo, capsys):
        (repo / "etl" / "raw" / "legistar_calendar.html").write_text(
            '<table id="ctl00_ContentPlaceHolder1_gridCalendar_ctl00"></table>', encoding="utf-8"
        )
        assert main(["build"]) == 1
        assert "build refused" in capsys.readouterr().err


class TestFetch:
    def test_reports_fresh_and_fetched_counts(self, tmp_path, monkeypatch, capsys):
        from dataclasses import replace

        from showup.fetch import SOURCES

        raw = tmp_path / "etl" / "raw"
        raw.mkdir(parents=True)
        monkeypatch.setattr("showup.cli.REPO_ROOT", tmp_path)

        calendar = next(s for s in SOURCES if s.name == "calendar")
        body = b'<table id="gridCalendar">' + b"x" * 300_000
        monkeypatch.setattr("showup.fetch.SOURCES", (replace(calendar, fetch=lambda log: body),))
        assert main(["fetch", "--force"]) == 0
        assert "fetched 1" in capsys.readouterr().out

    def test_a_failed_source_exits_nonzero_but_keeps_the_cache(self, tmp_path, monkeypatch, capsys):
        from dataclasses import replace

        from showup.fetch import SOURCES, FetchError

        raw = tmp_path / "etl" / "raw"
        raw.mkdir(parents=True)
        monkeypatch.setattr("showup.cli.REPO_ROOT", tmp_path)

        def boom(log):
            raise FetchError("upstream is down")

        calendar = next(s for s in SOURCES if s.name == "calendar")
        monkeypatch.setattr("showup.fetch.SOURCES", (replace(calendar, fetch=boom),))
        assert main(["fetch", "--force"]) == 1
        err = capsys.readouterr().err
        assert "failed: calendar" in err
        # The operator must be told the old copy is still there, or they will
        # assume the site is now broken.
        assert "previous cached copies were kept" in err

    def test_unknown_source_is_rejected_by_argparse(self, tmp_path, monkeypatch):
        monkeypatch.setattr("showup.cli.REPO_ROOT", tmp_path)
        with pytest.raises(SystemExit):
            main(["fetch", "--only", "not-a-source"])


class TestArgparse:
    def test_no_command_exits(self):
        with pytest.raises(SystemExit):
            main([])

    def test_help_lists_every_subcommand(self, capsys):
        with pytest.raises(SystemExit):
            main(["--help"])
        out = capsys.readouterr().out
        for command in ("build", "fetch", "crosswalk"):
            assert command in out
