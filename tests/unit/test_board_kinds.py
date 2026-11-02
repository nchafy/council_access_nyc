"""The registry of ways a board's schedule can be obtained.

Owner's instruction, 2026-11-02: however the data is loaded — a browser, a PDF, an
iCalendar feed, OCR — it should hook on the same way and publish the same format.

The tests that matter here are the consistency ones. Before the registry, `fetch.py` and
`board_meetings.py` each carried an `if kind == ...` chain, and the two could disagree:
a kind could be fetchable and unreadable, or readable and never fetched, with nothing to
catch it. The first thing this file does is make that a test failure instead of a silent
gap — and it has already earned its place, by catching a refactor that left the registry
uninstalled on the fetch path, so every board recorded "no loader" and answered nothing.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import ClassVar

import pytest

from showup.sources.board_kinds import (
    KINDS,
    BoardSourceKind,
    LoadError,
    LoadRequest,
    kind_for,
    register,
    urls_of,
)
from showup.sources.board_registry import install

CROSSWALK = Path(__file__).resolve().parents[2] / "crosswalks" / "board_schedule_sources.json"

# Installed at import, not in a fixture: `parametrize` over `KINDS` is evaluated while the
# module is collected, so a fixture would leave those cases with an empty parameter set and
# pytest would skip them — three tests that look present and never run.
install()


@pytest.fixture(scope="module")
def boards() -> dict:
    return json.loads(CROSSWALK.read_text(encoding="utf-8"))["boards"]


class TestTheRegistryMatchesTheCrosswalk:
    def test_every_kind_a_fetched_board_declares_has_a_handler(self, boards):
        """The failure this exists for: a board marked `fetched` whose kind nothing
        handles answers nothing, and looks exactly like a dead website."""
        declared = {b.get("kind") for b in boards.values() if b.get("fetched")}
        assert declared <= set(KINDS), declared - set(KINDS)

    def test_every_registered_kind_is_used_by_some_board(self):
        """A kind nobody uses is dead code wearing a registry entry."""
        used = {
            b.get("kind")
            for b in json.loads(CROSSWALK.read_text(encoding="utf-8"))["boards"].values()
        }
        assert set(KINDS) <= used, set(KINDS) - used

    def test_every_board_with_a_handler_also_has_a_url(self, boards):
        for code, board in boards.items():
            if board.get("fetched"):
                assert urls_of(board.get("url")), code

    def test_a_board_that_is_not_fetched_declares_no_url(self, boards):
        """The two must not drift: a URL with `fetched: false` reads as an oversight."""
        for code, board in boards.items():
            if not board.get("fetched"):
                assert not board.get("url"), code


class TestEveryKindHasBothHalves:
    @pytest.mark.parametrize("name", sorted(KINDS))
    def test_it_can_load_and_read(self, name):
        kind = KINDS[name]
        assert callable(kind.load), name
        assert callable(kind.read), name

    @pytest.mark.parametrize("name", sorted(KINDS))
    def test_it_says_what_it_is(self, name):
        """The summary is what `docs/board-pdf-shapes.md` and a reader of the registry
        go on, so an entry without one is an entry nobody can audit."""
        assert len(KINDS[name].summary) > 20, name

    #: A body each kind accepts and finds nothing in. Not the same string for all of
    #: them: two of these kinds reject a body that is not the JSON shape they expect, and
    #: that refusal is deliberate.
    EMPTY: ClassVar[dict[str, str]] = {
        "gcal-ics": "",
        "other-ics": "",
        "tribe": "{}",
        "other-json": "[]",
        "nyc-html": "",
        "nyc-pdf": "[]",
    }

    @pytest.mark.parametrize("name", sorted(KINDS))
    def test_its_reader_takes_the_board_code_and_finds_nothing_in_nothing(self, name):
        """Several kinds need the code — the nine HTML boards and the twenty-one PDF
        boards share a host and a file format and nothing else — so every reader takes
        it, and the ones that do not need it ignore it.

        An empty source must yield no meetings rather than raise: a board publishing
        nothing is an ordinary Tuesday, not a broken build."""
        assert name in self.EMPTY, f"{name} needs an empty body in this table"
        assert KINDS[name].read("999", self.EMPTY[name], datetime.date(2026, 11, 2)) == []

    def test_a_reader_given_the_wrong_json_shape_refuses(self):
        """The two JSON kinds check their shape, because a feed that changed from an
        object to an array is a format change and must be loud, not silently empty."""
        from showup.sources.board_meetings import BoardMeetingsError

        with pytest.raises(BoardMeetingsError, match="expected an object"):
            KINDS["tribe"].read("999", "[]", datetime.date(2026, 11, 2))
        with pytest.raises(BoardMeetingsError, match="expected an array"):
            KINDS["other-json"].read("999", "{}", datetime.date(2026, 11, 2))


class TestTheRegistryItself:
    def test_a_kind_is_found_by_the_name_the_crosswalk_uses(self):
        assert kind_for("nyc-pdf") is KINDS["nyc-pdf"]

    @pytest.mark.parametrize("name", [None, "", "carrier-pigeon"])
    def test_an_unhandled_name_is_none_rather_than_an_error(self, name):
        """`fetch` records this as that board's failure and carries on."""
        assert kind_for(name) is None

    def test_registering_a_name_twice_is_refused(self):
        """A second registration would silently replace the first, which is how two
        loaders for one kind would come to exist without anybody noticing."""
        with pytest.raises(ValueError, match="already registered"):
            register(
                BoardSourceKind(
                    name="nyc-pdf",
                    load=lambda _r: "",
                    read=lambda _c, _b, _d: [],
                    summary="a duplicate, which must not be accepted",
                )
            )

    def test_installing_twice_is_harmless(self):
        """Both `fetch` and `parse_feed` install, and either may run first."""
        before = dict(KINDS)
        install()
        assert before == KINDS


class TestWhatTheCrosswalkCanDeclare:
    @pytest.mark.parametrize(
        ("declared", "expected"),
        [
            ("https://a", ("https://a",)),
            (["https://a", "https://b"], ("https://a", "https://b")),
            (None, ()),
            ("", ()),
            ([], ()),
        ],
    )
    def test_one_url_or_several(self, declared, expected):
        """Queens CB5 keeps its board notices and its committee notices in two places."""
        assert urls_of(declared) == expected


class TestTheLoadRequest:
    def test_url_is_the_first_page(self):
        request = LoadRequest(
            code="405",
            urls=("https://a", "https://b"),
            get=lambda _u, **_k: b"",
            log=lambda _m: None,
            today=datetime.date(2026, 11, 2),
        )
        assert request.url == "https://a"

    def test_a_load_error_is_not_an_http_error(self):
        """`LoadError` is for the board-shaped failures above one request: nothing on the
        page was a schedule, every document was unreadable, the capability is absent."""
        assert issubclass(LoadError, RuntimeError)
