"""Reading the boards whose schedule only exists once a browser has run.

Owner's instruction, 2026-11-02: implement the browser route.

One board needs it. Manhattan CB11 keeps its meetings in an Airtable shared view: the
embed's HTML carries no row data, and the `readSharedViewData` route the page itself emits
returns 401. The rows exist only after the app has rendered, so the only client that can
read them is a browser.

**This is a loader like any other.** It returns a string for the cache, so `showup build`
still parses text offline and needs no browser — see `board_kinds`. And it declares a
`needs`, so a machine without Chrome fails this board and no others.

## Manhattan CB5 was attempted and is not here

That board sits behind a Cloudflare JS challenge. Measured 2026-11-02: headless Chrome is
served `Just a moment...` and still has it 40 seconds later, so the challenge does not
resolve — it detects the automation rather than merely requiring JavaScript.

Getting past it would mean defeating bot detection: patched fingerprints, a persistent
real-browser profile, an arms race against a control the board's host deliberately put up.
That is a different act from rendering a page, it was not what was asked for, and it is not
done here. The board stays recorded as `blocked`, and the way through is a feed from the
district office rather than a cleverer client.
"""

from __future__ import annotations

import re
from datetime import date

from ..text import collapse
from .board_kinds import LoadError, LoadRequest
from .board_meetings import BoardMeeting

__all__ = ["BROWSER_READERS", "browser_available", "load_browser", "parse_rendered"]

#: How long to let an app render before giving up, and how often to look. Airtable's view
#: takes a few seconds; polling means a fast render is not charged the whole wait.
RENDER_TIMEOUT_S = 40
RENDER_POLL_S = 5

#: What a rendered schedule has to contain before it is worth reading. Without a check like
#: this the loader caches a spinner and the board reports no meetings.
_RENDERED = re.compile(r"\d{1,2}/\d{1,2}/20\d\d|\b20\d\d\b")


def browser_available() -> bool:
    """Whether a local Chrome and the CDP client are both present."""
    try:
        from ..cdp import find_chrome
    except ImportError:
        return False
    return find_chrome() is not None


def load_browser(request: LoadRequest) -> str:
    """One board's schedule as the text a browser shows, ready to cache.

    The **rendered text**, not the HTML: these are app-generated DOMs where the markup is a
    framework's business and the text is the board's. Manhattan CB11's rows arrive as
    `Environment, Open Space & Parks11/5/2026via Video Conference, "1664 Park Avenue"`,
    which is ugly and stable, where the surrounding markup is neither.
    """
    if not browser_available():
        raise LoadError(
            "no local Chrome; this board's schedule exists only once a browser has run. "
            "Install Chrome, or ask the district office for a calendar feed."
        )
    import time

    from ..cdp import Browser, CDPError

    try:
        with Browser() as browser:
            page = browser.page()
            page.navigate(request.url, timeout=90)
            text = ""
            waited = 0
            while waited < RENDER_TIMEOUT_S:
                time.sleep(RENDER_POLL_S)
                waited += RENDER_POLL_S
                text = str(page.evaluate("document.body.innerText") or "")
                if _RENDERED.search(text):
                    break
    except CDPError as error:
        raise LoadError(f"browser could not read {request.url}: {error}") from error

    if not _RENDERED.search(text):
        # A challenge page, a spinner, or an app that did not load. Caching it would turn
        # "we could not read this" into "this board holds no meetings".
        raise LoadError(
            f"{request.url} showed nothing dated after {RENDER_TIMEOUT_S}s "
            f"(title-level content only, {len(text)} characters)"
        )
    request.log(f"    board {request.code} rendered {len(text)} characters")
    return text


#: `11/5/2026`, which is how Airtable prints a date in a grid cell.
_SLASHED = re.compile(r"(\d{1,2})/(\d{1,2})/(20\d\d)")

#: A row that is a closure rather than a meeting. Manhattan CB11 marks these in the same
#: view: `Election Day - CLOSED11/3/2026`.
#:
#: Each word is closed with `(?![a-z])` rather than `\b`, because the cells arrive with no
#: separator and the next character is a digit — `\bclosed\b` does not match `CLOSED11`,
#: which is how three public holidays were published as meetings.
_CLOSED = re.compile(
    r"\bclosed(?![a-z])|\bno meeting(?![a-z])|\bcancell?ed(?![a-z])|\bholiday(?![a-z])",
    re.I,
)


def read_manhattan_cb11(text: str, *, on_or_after: date) -> list[BoardMeeting]:
    """Manhattan CB11: an Airtable month view, read as the text the grid shows.

    One row per line, with no separator between the cells, so the date is the divider:
    `Environment, Open Space & Parks11/5/2026via Video Conference, "1664 Park Avenue, New
    York, NY 10035"`. Whatever precedes the date is the committee and whatever follows it
    is where the meeting is held.

    Only the month the view happens to be showing is read. Paging the app to collect the
    rest is a click this does not make, so this board's coverage is the current month —
    which is what its own page shows a reader.
    """
    out = []
    for raw in text.splitlines():
        line = collapse(raw)
        found = _SLASHED.search(line)
        if not found:
            continue
        try:
            day = date(int(found.group(3)), int(found.group(1)), int(found.group(2)))
        except ValueError:
            continue
        if day < on_or_after:
            continue
        title = collapse(line[: found.start()]).strip(" -–—,")
        if not title or _CLOSED.search(line):
            continue
        location = collapse(line[found.end() :]).strip(' -–—,"')
        out.append(
            BoardMeeting(
                day=day,
                start_time=None,
                title=title,
                location=location or None,
                url=None,
            )
        )
    return out


#: Board code to the reader that understands that board's rendered page.
BROWSER_READERS = {"111": read_manhattan_cb11}


def parse_rendered(code: str, text: str, *, on_or_after: date) -> list[BoardMeeting]:
    """Read one board's rendered text with that board's reader, or return nothing."""
    reader = BROWSER_READERS.get(str(code))
    if reader is None:
        return []
    return sorted(reader(text, on_or_after=on_or_after), key=lambda m: m.day)
