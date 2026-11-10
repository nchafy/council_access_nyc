"""The board whose schedule only exists once a browser has run.

Owner's instruction, 2026-11-02: implement the browser route.

**These tests do not launch a browser.** `tests/fixtures/board_browser/111.txt` is the text
Chrome actually showed for Manhattan CB11's Airtable view, so what is tested is the part
that is ours — reading those rows — and the suite passes on a machine with no Chrome.
Nothing drives a real one any more: `showup fetch` does, against the live view, and that is
not a thing a test should depend on.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from showup.sources.board_browser import (
    BROWSER_READERS,
    browser_available,
    load_browser,
    parse_rendered,
)
from showup.sources.board_kinds import LoadError, LoadRequest, kind_for
from showup.sources.board_registry import install

install()

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "board_browser"
RENDERED = (FIXTURE / "111.txt").read_text(encoding="utf-8")
TODAY = date(2026, 11, 1)


def read(code: str = "111", text: str | None = None, *, on_or_after: date = TODAY):
    return parse_rendered(code, RENDERED if text is None else text, on_or_after=on_or_after)


class TestManhattanCb11:
    """An Airtable month view, read as the text the grid shows.

    One row per line with no separator between the cells, so the date is the divider:
    `Environment, Open Space & Parks11/5/2026via Video Conference, "1664 Park Avenue"`.
    """

    def test_it_reads_the_committee_the_date_and_the_venue(self):
        first = read()[0]
        assert first.day == date(2026, 11, 5)
        assert first.title == "Environment, Open Space & Parks"
        assert "1664 Park Avenue" in (first.location or "")

    def test_it_finds_every_meeting_the_view_shows(self):
        assert [m.day for m in read()] == [
            date(2026, 11, 5),
            date(2026, 11, 9),
            date(2026, 11, 17),
            date(2026, 11, 18),
            date(2026, 11, 19),
            date(2026, 11, 24),
            date(2026, 12, 3),
        ]

    def test_it_reports_no_time_because_the_view_shows_none(self):
        assert all(m.start_time is None for m in read())

    def test_a_closure_is_not_a_meeting(self):
        """This view marks public holidays in the same grid as the meetings:
        `Election Day - CLOSED11/3/2026`."""
        titles = " ".join(m.title for m in read())
        for holiday in ("Election Day", "Veterans Day", "Thanksgiving"):
            assert holiday not in titles

    def test_a_closure_whose_marker_runs_into_the_date_is_still_caught(self):
        """The cells arrive with no separator, so the character after `CLOSED` is a digit.
        `\\bclosed\\b` does not match `CLOSED11`, and three public holidays were published
        as meetings until each word was closed with a lookahead instead."""
        assert read(text="Election Day - CLOSED11/3/2026") == []

    def test_a_zoom_registration_link_is_kept_as_the_venue(self):
        """It is where the meeting is held, which is the thing the City publishes
        nowhere."""
        online = [m for m in read() if m.day == date(2026, 11, 9)]
        assert [m.location.startswith("https://") for m in online] == [True]

    def test_a_row_with_no_date_is_skipped(self):
        assert read(text="Month\nSun\nMon\n2 records") == []

    def test_a_row_with_no_committee_is_skipped(self):
        """The grid's day numbers sit on their own lines beside the rows."""
        assert read(text="11/5/2026") == []

    def test_an_impossible_date_is_dropped_rather_than_clamped(self):
        assert read(text="Full Board2/30/2027") == []

    def test_a_past_row_is_dropped(self):
        assert read(text="Full Board11/5/2020") == []

    def test_rows_come_back_in_date_order(self):
        days = [m.day for m in read()]
        assert days == sorted(days)

    def test_a_board_with_no_reader_yields_nothing_rather_than_raising(self):
        assert parse_rendered("999", RENDERED, on_or_after=TODAY) == []

    def test_only_manhattan_cb11_needs_a_browser(self):
        assert set(BROWSER_READERS) == {"111"}


class TestTheCapabilityIsOptional:
    """`showup fetch` must not require a browser, and `showup build` never touches one."""

    def test_the_kind_declares_what_it_needs(self):
        assert kind_for("browser").needs == "a local Chrome"

    def test_without_chrome_the_board_fails_and_says_what_to_do(self, monkeypatch):
        import showup.sources.board_browser as board_browser

        monkeypatch.setattr(board_browser, "browser_available", lambda: False)
        request = LoadRequest(
            code="111",
            urls=("https://airtable.com/embed/app/shr",),
            get=lambda _u, **_k: b"",
            log=lambda _m: None,
            today=TODAY,
        )
        with pytest.raises(LoadError, match="no local Chrome"):
            load_browser(request)

    def test_reading_a_cached_body_never_needs_a_browser(self):
        """The whole point of caching the rendered text: only the machine that fetched
        needs Chrome. Every test above relies on it."""
        assert read()

    def test_whether_a_browser_is_present_is_reported_not_assumed(self):
        assert isinstance(browser_available(), bool)


class TestManhattanCb5IsNotHere:
    """That board sits behind a Cloudflare JS challenge, and this records why rendering is
    not the answer for it — so the next person does not try the same thing again.

    Measured 2026-11-02: headless Chrome is served `Just a moment...` and still has it 40
    seconds later. The challenge detects the automation rather than merely requiring
    JavaScript. Going further would mean defeating bot detection, which is not done here.
    """

    def test_it_has_no_browser_reader(self):
        assert "105" not in BROWSER_READERS

    def test_a_challenge_page_is_refused_rather_than_cached(self):
        """Caching it would turn "we could not read this" into "this board holds no
        meetings", which is a different and false claim."""
        assert read(code="111", text="Just a moment...\nEnable JavaScript to continue.") == []

    def test_the_crosswalk_still_records_it_as_blocked(self):
        import json

        crosswalk = Path(__file__).resolve().parents[2] / "crosswalks"
        boards = json.loads(
            (crosswalk / "board_schedule_sources.json").read_text(encoding="utf-8")
        )["boards"]
        assert boards["105"]["status"] == "blocked"
        assert not boards["105"].get("fetched")
        assert "bot detection" in boards["105"]["note"]


class FakeSession:
    """Stands in for a CDP page. Returns each text in turn, so a test can make the first
    look like a spinner and the second like a rendered view."""

    def __init__(self, texts):
        self.texts = list(texts)
        self.navigated = None

    def navigate(self, url, timeout=None):
        self.navigated = url

    def evaluate(self, _expression):
        return self.texts.pop(0) if len(self.texts) > 1 else self.texts[0]


class FakeBrowser:
    def __init__(self, session):
        self.session = session

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def page(self):
        return self.session


def driving(monkeypatch, texts, *, raises=None):
    """Replace the CDP client, and make sleeping free so a timeout test is not slow."""
    import showup.cdp as cdp
    import showup.sources.board_browser as board_browser

    session = FakeSession(texts)

    def browser():
        if raises is not None:
            raise raises
        return FakeBrowser(session)

    monkeypatch.setattr(cdp, "Browser", browser)
    monkeypatch.setattr(board_browser, "browser_available", lambda: True)
    monkeypatch.setattr("time.sleep", lambda _s: None)
    return session


def a_request(log=None) -> LoadRequest:
    return LoadRequest(
        code="111",
        urls=("https://airtable.com/embed/appedcOCWGdk7kppK/shrEZxc5vi8McZNFb",),
        get=lambda _u, **_k: b"",
        log=log if log is not None else (lambda _m: None),
        today=TODAY,
    )


class TestTheLoader:
    def test_it_caches_the_rendered_text(self, monkeypatch):
        """The text, not the HTML: these are app-generated DOMs where the markup is a
        framework's business and the text is the board's."""
        session = driving(monkeypatch, [RENDERED])
        said = []
        body = load_browser(a_request(log=said.append))
        assert body == RENDERED
        assert session.navigated.startswith("https://airtable.com/embed/")
        assert any("rendered" in line for line in said)

    def test_it_waits_for_the_app_and_stops_as_soon_as_it_renders(self, monkeypatch):
        """Polling rather than one long sleep, so a fast render is not charged the whole
        wait."""
        session = driving(monkeypatch, ["Loading...", RENDERED])
        assert load_browser(a_request()) == RENDERED
        assert session.texts == [RENDERED], "it stopped looking once the rows appeared"

    def test_a_page_that_never_renders_is_refused_not_cached(self, monkeypatch):
        """Caching a spinner would turn "we could not read this" into "this board holds no
        meetings", which is a different and false claim."""
        driving(monkeypatch, ["Loading..."])
        with pytest.raises(LoadError, match="nothing dated"):
            load_browser(a_request())

    def test_a_cloudflare_challenge_is_refused(self, monkeypatch):
        """What Manhattan CB5 serves. It is not a slow app, and it must not be cached as
        an empty schedule."""
        driving(monkeypatch, ["Just a moment...\nEnable JavaScript and cookies to continue"])
        with pytest.raises(LoadError, match="nothing dated"):
            load_browser(a_request())

    def test_a_browser_that_will_not_start_is_that_boards_failure(self, monkeypatch):
        from showup.cdp import CDPError

        driving(monkeypatch, [""], raises=CDPError("no port"))
        with pytest.raises(LoadError, match="could not read"):
            load_browser(a_request())

    def test_an_empty_page_is_refused(self, monkeypatch):
        driving(monkeypatch, [""])
        with pytest.raises(LoadError, match="nothing dated"):
            load_browser(a_request())

    def test_availability_is_false_without_the_cdp_client(self, monkeypatch):
        import builtins

        real = builtins.__import__

        def refuse(name, *args, **kwargs):
            if name.endswith("cdp"):
                raise ImportError(name)
            return real(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", refuse)
        assert browser_available() is False
