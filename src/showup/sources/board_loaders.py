"""How each kind of board source gets its bytes.

The `load` halves of the registry in `board_kinds.py`: the only code here that touches the
network. Each takes a `LoadRequest` and returns a string to cache, so `showup build` never
needs the network, a binary, a browser or a model — it reads text.

Fetching policy — the User-Agent, the retries, the crawl delay — belongs to `fetch` and is
handed in as `request.get`. Nothing here imports `fetch`, which is what keeps a loader from
having to know how the project is polite.
"""

from __future__ import annotations

import json
import re
import urllib.parse
from collections.abc import Callable
from datetime import date

from ..urls import safe_url
from .board_kinds import LoadError, LoadRequest

#: Turns one PDF's bytes into the `{layout, plain, pages}` envelope the readers expect.
#: Swapped for the OCR one on the two boards that publish only scanned images, which is
#: why the readers need no idea which it was.
Extractor = Callable[[bytes], dict[str, str]]

__all__ = [
    "BOARD_PDF_FLOOR",
    "BOARD_PDF_LIMIT",
    "TRIBE_PAGE",
    "load_pdf",
    "load_plain",
    "load_tribe",
]

#: The Events Calendar caps a page at 50 however much you ask for, so this is the real
#: ceiling rather than an aspiration. A board page shows a handful.
TRIBE_PAGE = 50


def load_plain(request: LoadRequest) -> str:
    """The body of one URL, as text. Every feed that needs no coaxing uses this."""
    return request.get(request.url, tries=2, timeout=60).decode("utf-8", errors="replace")


def load_tribe(request: LoadRequest) -> str:
    """The Events Calendar, asked for a window rather than its idea of "upcoming".

    Left to itself the endpoint defaults `start_date` to today and reports nothing, which
    is indistinguishable from a board with nothing scheduled. Brooklyn CB11 was recorded as
    publishing no events on exactly that basis and in fact holds 79.
    """
    window = f"per_page={TRIBE_PAGE}&start_date={request.today.isoformat()}"
    url = f"{request.url.split('?')[0]}?{window}"
    return request.get(url, tries=2, timeout=60).decode("utf-8", errors="replace")


#: How many of a board's linked PDFs to read, after `_board_pdf_links` has put the nearest
#: upcoming month first. These pages link an archive — Bronx CB11 lists every month through
#: June 2027 — so this bounds an otherwise unbounded fetch. Six covers the two months a
#: reader can act on plus the boards that interleave a file which is not a calendar.
BOARD_PDF_LIMIT = 6

#: A PDF big enough to be a calendar. Below this the link resolved to an error page that
#: happens to be served as `application/pdf`, which nyc.gov does.
BOARD_PDF_FLOOR = 2_000


#: A month named in a link or its text. `2026-11`, `2026_11` and `2026.11.01` are how
#: three of these boards name a file; `November-2026`, `november_2026` and `November2026`
#: are how four others do. Both orders are needed, and the month name may be abbreviated.
_PDF_MONTH_NUMBER = re.compile(r"(?<!\d)(20\d\d)[-_.](0[1-9]|1[0-2])(?!\d)")
_PDF_MONTH_NAME = re.compile(
    r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[-_.\s]*(20\d\d)",
    re.I,
)
_PDF_NAME_MONTH = re.compile(
    r"(20\d\d)[-_.\s]*(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*",
    re.I,
)

#: `October 14, 2026`, `Oct14-2026`, `March 11th, 2015` — a month, then a day, then the
#: year. Queens CB5 names its files `BoardMeetingNoticeOct14-2026.pdf` and labels its links
#: `October 14, 2026`, and neither of the two patterns above matches that: both expect the
#: year to sit next to the month with only separators between. Without this the board's
#: 2015 and 2021 agendas outranked its 2026 ones and were the ones fetched.
_PDF_MONTH_DAY_YEAR = re.compile(
    r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?[-_.\s]*"
    r"(\d{1,2})(?:st|nd|rd|th)?[,\s_-]+(20\d\d)",
    re.I,
)
#: `12012021` — month, day and four-digit year run together, which is how Queens CB5 names
#: `AGENDA_CB5QBdMtg_12012021.pdf`. Nothing else here matches it: the digits are flanked by
#: other digits, so even the bare-year pattern fails, and the file ranked as undated. Those
#: 2021 notices then outranked the board's dated 2026 ones and were the ones fetched.
_PDF_COMPACT = re.compile(r"(?<!\d)(0[1-9]|1[0-2])\d{2}(20\d\d)(?!\d)")

#: `10.27.26` — month, day, two-digit year, which is how Brooklyn CB16 names its notices.
_PDF_DOTTED = re.compile(r"(?<!\d)(0?[1-9]|1[0-2])[-_.]\d{1,2}[-_.](\d{2})(?!\d)")

_PDF_MONTH_ABBR = {
    name: number
    for number, name in enumerate(
        ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"),
        start=1,
    )
}


def _encoded_path(url: str) -> str:
    """The same URL with its path percent-encoded.

    Bronx CB3 links `calendar/Committee Schedules.pdf`, with a literal space. `urllib`
    raises `InvalidURL` on that rather than encoding it, and because the raise was neither
    a `FetchError` nor caught per link, one board's filename took the whole board-calendar
    fetch down with it. Measured 2026-11-01.
    """
    parts = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit(parts._replace(path=urllib.parse.quote(parts.path, safe="/%:@")))


#: A year with no month beside it. Queens CB12 keeps a `2018_general_meeting_schedule.pdf`
#: in the same list as its current calendar; a year that has already ended is enough to
#: know the file is an archive, without pretending to know which month it covers.
#: Bounded with digit lookarounds rather than `\b`: `_` is a word character, so `\b`
#: after the year never matched `2018_general_meeting_schedule.pdf` — the exact filename
#: this is for.
_PDF_BARE_YEAR = re.compile(r"(?<!\d)(20\d\d)(?!\d)")


def _pdf_month(text: str) -> tuple[int, int] | None:
    """The month a PDF link names, from its href or its link text."""
    numbered = _PDF_MONTH_NUMBER.search(text)
    if numbered:
        return int(numbered.group(1)), int(numbered.group(2))
    compact = _PDF_COMPACT.search(text)
    if compact:
        return int(compact.group(2)), int(compact.group(1))
    dotted = _PDF_DOTTED.search(text)
    if dotted:
        return 2000 + int(dotted.group(2)), int(dotted.group(1))
    spelled = _PDF_MONTH_DAY_YEAR.search(text)
    if spelled:
        return int(spelled.group(3)), _PDF_MONTH_ABBR[spelled.group(1).lower()]
    named = _PDF_MONTH_NAME.search(text)
    if named:
        return int(named.group(2)), _PDF_MONTH_ABBR[named.group(1).lower()]
    reversed_ = _PDF_NAME_MONTH.search(text)
    if reversed_:
        return int(reversed_.group(1)), _PDF_MONTH_ABBR[reversed_.group(2).lower()]
    return None


def _pdf_spent_year(text: str, today: date) -> bool:
    """Whether a link names a year that is already over.

    Only meaningful for a link `_pdf_month` found no month in, which is the only place
    this is called from — so it does not re-check that.
    """
    found = _PDF_BARE_YEAR.search(text)
    return bool(found) and int(found.group(1)) < today.year


def _board_pdf_links(page: bytes, base: str, *, today: date | None = None) -> list[str]:
    """Every PDF this board's page links, nearest upcoming month first.

    The order matters because `BOARD_PDF_LIMIT` truncates. Document order is not usable:
    Bronx CB11's calendar page lists `meeting_preferences.pdf`, then `2023-09.pdf`, then
    `2027-06.pdf`, then `2027-05.pdf`, so taking the first four got one file that is not a
    calendar, one three-year-old month and two in mid-2027 — and missed the November its
    readers needed. Measured 2026-11-01.

    So links are ranked by the month they name, in the href or the link text:

    1. this month and later, soonest first — what a reader is about to attend;
    2. links naming no month, in document order, because a filename is not a convention
       (Bronx CB1 writes `-2026-CB1-Calendars-4.pdf`, which says nothing about its month);
    3. past months, most recent first, which is what a board with nothing current has,
       together with links naming only a year that has already ended — Queens CB12 keeps
       a `2018_general_meeting_schedule.pdf` beside its current calendar.
    """
    from ..text import parse_html

    today = today or date.today()
    current = (today.year, today.month)

    found: dict[str, tuple[int, int]] = {}
    for position, anchor in enumerate(
        parse_html(page.decode("utf-8", errors="replace")).find_all("a", href=True)
    ):
        href = safe_url(str(anchor["href"]), base=base)
        if not href or not href.lower().split("?")[0].endswith(".pdf") or href in found:
            continue
        href = _encoded_path(href)
        # The link's own text is asked first, and the filename only as a fallback,
        # because these filenames demonstrably lie: Queens CB5 publishes
        # `ZoningHousingAugust2026.pdf` under a link reading `October 7, 2026`.
        label = anchor.get_text(" ", strip=True)
        describes = f"{label} {href}"
        named = _pdf_month(label) or _pdf_month(href)
        if named is None:
            # A year that has ended, with no month, is an archive file. Anything else
            # unnamed may well be the current calendar and is tried before the archive.
            found[href] = (2, 0) if _pdf_spent_year(describes, today) else (1, position)
        elif named >= current:
            found[href] = (0, named[0] * 12 + named[1])
        else:
            found[href] = (2, -(named[0] * 12 + named[1]))
    return sorted(found, key=lambda href: found[href])


def load_pdf(request: LoadRequest) -> str:
    """Every PDF a board links, read as text by pypdf."""
    from .board_pdf import extract_pdf_text

    return _load_pdfs(request, extract_pdf_text)


def _load_pdfs(request: LoadRequest, extract_text: Extractor) -> str:
    """One board's schedule PDFs as extracted text, ready to cache as a string.

    `landing` may be several pages. Two boards keep their meetings in more than one
    archive: Queens CB5 lists 53 board notices on `/meetings/agendas.page` and 331
    committee notices on `/meetings/notices.page`, and reading only the first means
    reporting none of its committees. Each page contributes its own
    `BOARD_PDF_LIMIT` nearest months.

    The PDF bytes are deliberately not stored. `extract_pdf_text` runs here, at fetch time,
    so that `data/` holds no binaries, the build stays offline, and a fixture is a text
    file a reviewer can read. See `sources/board_pdf.py`.
    """
    pages = list(request.urls)
    links: list[str] = []
    for page_url in pages:
        found = _board_pdf_links(
            request.get(page_url, tries=2, timeout=60), page_url, today=request.today
        )
        links.extend(href for href in found[:BOARD_PDF_LIMIT] if href not in links)
    if not links:
        raise LoadError(f"no PDF linked from {', '.join(pages)}")

    documents = []
    for href in links:
        try:
            data = request.get(href, tries=2, timeout=120)
        except (LoadError, ValueError) as error:
            # `ValueError` is `http.client.InvalidURL`'s base: a board can link an href
            # that is not a requestable URL, and that is its problem, not the fetch's.
            request.log(f"    board {request.code} pdf {href} failed: {error}")
            continue
        if len(data) < BOARD_PDF_FLOOR:
            request.log(f"    board {request.code} pdf {href} is {len(data)} bytes, not a calendar")
            continue
        try:
            extracted = extract_text(data)
        except Exception as error:
            # Caught broadly on purpose: pypdf raises its own hierarchy, and one
            # malformed document must not take the other boards' schedules down.
            request.log(
                f"    board {request.code} pdf {href} did not extract: {type(error).__name__}"
            )
            continue
        documents.append({"url": href, **extracted})

    if not documents:
        raise LoadError(f"none of {len(links)} PDFs at {', '.join(pages)} yielded text")
    return json.dumps(documents)
