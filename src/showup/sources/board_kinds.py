"""The registry of ways a community board's schedule can be obtained.

Owner's instruction, 2026-11-02: however the data is loaded — a browser, a PDF, an
iCalendar feed, OCR — it should hook on the same way and publish the same format.

Fifty-nine boards publish their meetings in no agreed way at all. Twenty-four expose a
machine-readable calendar, nine put dates in nyc.gov HTML, twenty-one post a PDF, two post
scanned images, and two sit behind something no HTTP client can read. Each of those is a
different way of *getting* the bytes and a different way of *reading* them, but every one
of them ends at the same place: a list of `BoardMeeting`.

So a kind is one object with two halves:

- **`load`** turns a third party into a string we can cache. It runs in `showup fetch`, is
  the only half allowed to touch the network, and returns text — never bytes — because
  `etl/raw/board_meetings.json` holds strings and a build must never need a binary.
- **`read`** turns that cached string into meetings. It runs in `showup build`, offline,
  and is the only half a test needs a fixture for.

Adding a source is registering one of these, not editing two dispatchers. Before this
existed, `fetch.py` and `board_meetings.py` each carried an `if kind == ...` chain, and the
two could disagree about what a kind meant — a kind could be fetchable and unreadable, or
readable and never fetched, with nothing to catch it. `tests/unit/test_board_kinds.py`
asserts the halves stay matched.

**`needs` is the point of the design.** Two kinds cannot run everywhere: OCR wants a
rasteriser and a model, and the browser kind wants a local Chrome. Neither may be a
condition of building the site. A kind that declares a `needs` and cannot meet it fails
*its own boards* and no others, which is the same contract a dead third-party site already
has. That is what makes a 50 MB OCR runtime an optional extra rather than a tax on every
contributor.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from .board_meetings import BoardMeeting

__all__ = [
    "KINDS",
    "BoardSourceKind",
    "LoadError",
    "LoadRequest",
    "kind_for",
    "register",
    "urls_of",
]


class LoadError(RuntimeError):
    """A board's schedule could not be obtained.

    Distinct from `fetch.FetchError`, which is about one HTTP request, and raised for the
    board-shaped failures above it: nothing on the page was a schedule, every document was
    unreadable, the capability this kind needs is absent. `fetch` catches both and records
    either as that board's failure, so the other 53 continue.
    """


class Getter(Protocol):
    """How a loader fetches bytes. Supplied by the caller so that this module, and every
    loader in it, stays free of `fetch`'s politeness, retry and User-Agent machinery —
    and free of an import cycle back to it."""

    def __call__(self, url: str, *, tries: int = ..., timeout: int = ...) -> bytes: ...


@dataclass(frozen=True, slots=True)
class LoadRequest:
    """Everything a loader is given. One board, one attempt."""

    #: The board's code, for logging and for per-board readers.
    code: str
    #: Where the schedule lives. Several, for a board that keeps two archives.
    urls: tuple[str, ...]
    #: Fetches bytes, with the caller's User-Agent and retry policy.
    get: Getter
    #: Records something a human should see. One line, already indented by the caller.
    log: Callable[[str], None]
    #: The day the fetch is for, so a loader can ask a feed for a window.
    today: date

    @property
    def url(self) -> str:
        """The first page, for the loaders that only have one."""
        return self.urls[0]


#: Reads a cached body into meetings: `(code, body, on_or_after) -> meetings`.
Reader = Callable[[str, str, date], list[BoardMeeting]]


@dataclass(frozen=True, slots=True)
class BoardSourceKind:
    """One way of obtaining a board's schedule, from the network to `BoardMeeting`."""

    #: What `crosswalks/board_schedule_sources.json` calls this kind.
    name: str
    #: Third party to a cacheable string. Raises `FetchError` if it cannot.
    load: Callable[[LoadRequest], str]
    #: Cached string to meetings. Never raises for a board-shaped problem; returns none.
    read: Reader
    #: One line, for `docs/board-sources.md` and for anybody reading the registry.
    summary: str
    #: What this kind needs beyond the standard library and the pinned runtime deps, when
    #: it needs anything. A kind that cannot meet its `needs` fails only its own boards.
    needs: str | None = None


KINDS: dict[str, BoardSourceKind] = {}


def register(kind: BoardSourceKind) -> BoardSourceKind:
    """Add a kind to the registry. Registering a name twice is a mistake, not an update."""
    if kind.name in KINDS:
        raise ValueError(f"board source kind {kind.name!r} is already registered")
    KINDS[kind.name] = kind
    return kind


def kind_for(name: str | None) -> BoardSourceKind | None:
    """The kind by the name the crosswalk uses, or None if nothing handles it."""
    return KINDS.get(str(name)) if name else None


def urls_of(declared: str | Sequence[str] | None) -> tuple[str, ...]:
    """The crosswalk's `url` as a tuple, whether it wrote one or several."""
    if not declared:
        return ()
    if isinstance(declared, str):
        return (declared,)
    return tuple(str(url) for url in declared)
