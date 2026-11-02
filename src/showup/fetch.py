"""Stage 1: pull every upstream payload into `etl/raw/`, which the build then reads offline.

A payload replaces a cache entry only after clearing a size floor and a body invariant,
because these hosts return HTTP 200 carrying error pages — CLAUDE.md, "Check body
invariants, not status codes". Crawl rates come from each host's own robots.txt
(docs/OBSERVATIONS.md, 2026-09-22).
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from .model import BOARD_COUNT, DISTRICT_COUNT
from .sources.board_meetings import BOARD_FEED_FLOOR
from .sources.boards import JOINT_INTEREST_AREAS
from .sources.participatory_budgeting import (
    IDEA_MAP_URL,
    ParticipatoryBudgetingError,
    is_results_release,
    participation_from_payload,
)
from .urls import safe_url

__all__ = ["SOURCES", "FetchError", "cache_path", "fetch_all", "fetch_one", "manifest_key"]

#: Says who we are and how to be asked to stop, which is what a UA is for. It does **not**
#: claim to be a browser: that was tried and turned out to be unnecessary.
#:
#: The contact is written `repo nchafy/council_access_nyc` rather than as a URL because
#: **the literal string `github.com` in a User-Agent makes nyc.gov return HTTP 403**.
#: Bisected 2026-10-31 on a board calendar page: `showup-nyc/0.1 (civic data ETL for a
#: public-interest site)` gets 200, `showup-nyc/0.1 (github.com)` gets 403, and the
#: hostname is the only token that matters — not the length, not "ETL", not the
#: parentheses. Verified afterwards against every host this project fetches.
USER_AGENT = (
    "showup-nyc/0.1 (civic data ETL for a public-interest site; repo nchafy/council_access_nyc)"
)

#: Seconds between requests to the same host; 2 s where the host publishes no robots.txt.
CRAWL_DELAY = {
    "council.nyc.gov": 10.0,
    "data.cityofnewyork.us": 1.0,
    "nyc.legistar.com": 2.0,
    "rnd.council.nyc.gov": 2.0,
}
DEFAULT_DELAY = 2.0

SOCRATA = "https://data.cityofnewyork.us"
LEGISTAR = "https://nyc.legistar.com"
#: Verified byte-identical to LEGISTAR, so this is a real failover and not a hopeful one.
LEGISTAR_FAILOVER = "https://legistar.council.nyc.gov"

_last_request: dict[str, float] = {}


class FetchError(RuntimeError):
    """A source could not be fetched, or what came back was not usable.

    Raised only after retries. The existing cache entry is left untouched.
    """


def _polite_wait(host: str) -> None:
    delay = CRAWL_DELAY.get(host, DEFAULT_DELAY)
    previous = _last_request.get(host)
    if previous is not None:
        remaining = delay - (time.monotonic() - previous)
        if remaining > 0:
            time.sleep(remaining)
    _last_request[host] = time.monotonic()


def _get(url: str, *, tries: int = 4, timeout: int = 120) -> bytes:
    """One GET with backoff. Retries transport errors and 5xx/429, not 404."""
    host = urllib.parse.urlsplit(url).hostname or ""
    last: Exception | None = None

    for attempt in range(1, tries + 1):
        _polite_wait(host)
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            last = error
            if error.code not in (408, 429, 500, 502, 503, 504):
                raise FetchError(f"{url} -> HTTP {error.code} (not retryable)") from error
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            last = error

        if attempt < tries:
            backoff = min(30.0, 2.0 ** (attempt - 1))
            time.sleep(backoff)

    raise FetchError(f"{url} failed after {tries} attempts: {last}")


def _must_contain(needle: bytes, what: str) -> Callable[[bytes], str | None]:
    def check(body: bytes) -> str | None:
        return None if needle in body else f"body does not contain {what}"

    return check


def _json_rows(minimum: int) -> Callable[[bytes], str | None]:
    def check(body: bytes) -> str | None:
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as error:
            return f"not valid JSON ({error})"
        if isinstance(parsed, dict) and "error" in parsed:
            return f"Socrata error: {str(parsed)[:120]}"
        if not isinstance(parsed, list):
            return f"expected a JSON array, got {type(parsed).__name__}"
        if len(parsed) < minimum:
            return f"{len(parsed)} rows, floor is {minimum}"
        return None

    return check


def _geojson_features(expected: int) -> Callable[[bytes], str | None]:
    def check(body: bytes) -> str | None:
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as error:
            return f"not valid JSON ({error})"
        features = parsed.get("features") if isinstance(parsed, dict) else None
        if not isinstance(features, list):
            return "not a GeoJSON FeatureCollection"
        if len(features) != expected:
            return f"{len(features)} features, expected exactly {expected}"
        return None

    return check


#: Doubles as a shape invariant: without every one of these the payload is not `vn4m-mk4t`.
BUDGET_REQUEST_COLUMNS = (
    "boro",
    "board",
    "priority",
    "request",
    "explanation",
    "responsible_agency",
    "response",
    "responded_by",
    "publication",
    "tracking_code",
)
#: `uvw5-9znb` carries every term ever served, so the current 51 are a small fraction of
#: it; under this the dataset has been truncated rather than gone quiet.
MEMBER_ROW_FLOOR = 300

BUDGET_REQUESTS_DATASET = "vn4m-mk4t"
#: Editions run 3,411-3,814 rows; below 3,000 the shape has changed, not the year.
BUDGET_REQUEST_ROW_FLOOR = 3_000


def _board_budget_requests(body: bytes) -> str | None:
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as error:
        return f"not valid JSON ({error})"
    if isinstance(parsed, dict) and "error" in parsed:
        return f"Socrata error: {str(parsed)[:120]}"
    if not isinstance(parsed, list):
        return f"expected a JSON array, got {type(parsed).__name__}"
    if len(parsed) < BUDGET_REQUEST_ROW_FLOOR:
        return f"{len(parsed)} rows, floor is {BUDGET_REQUEST_ROW_FLOOR}"

    absent = [column for column in BUDGET_REQUEST_COLUMNS if column not in parsed[0]]
    if absent:
        return f"not vn4m-mk4t: no {', '.join(absent)} column"
    boards = {(row.get("boro"), row.get("board")) for row in parsed}
    if len(boards) < BOARD_COUNT:
        return f"{len(boards)} boro/board pairs, expected all {BOARD_COUNT}"
    editions = {row.get("publication") for row in parsed}
    if len(editions) != 1:
        return f"{len(editions)} publications in one payload, expected exactly 1"
    return None


def _district_pages(body: bytes) -> str | None:
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as error:
        return f"not valid JSON ({error})"
    if not isinstance(parsed, dict):
        return "expected an object keyed by district number"
    present = [key for key, value in parsed.items() if value]
    if len(present) != DISTRICT_COUNT:
        return f"{len(present)} of {DISTRICT_COUNT} district pages have content"
    # A hand-picked sample — first, middle, last — not a count, so these stay literal.
    for number in ("1", "26", "51"):
        page = parsed.get(number) or ""
        if f"District {number}" not in page:
            return f"district {number}'s page does not contain its own heading"
    return None


def _fetch_calendar(log: Callable[[str], None]) -> bytes:
    """One plain GET of page 1, which already spans months ahead.

    Page 2 would need a POST of the ~374 KB `__VIEWSTATE`, which we never send.
    """
    for base in (LEGISTAR, LEGISTAR_FAILOVER):
        try:
            body = _get(f"{base}/Calendar.aspx")
            if b"gridCalendar" in body:
                if base != LEGISTAR:
                    log(f"    (primary host failed; used failover {base})")
                return body
            log(f"    {base} returned {len(body)} bytes with no calendar grid")
        except FetchError as error:
            log(f"    {base}: {error}")
    raise FetchError("neither Legistar host returned a usable calendar")


def _fetch_district_pages(log: Callable[[str], None]) -> bytes:
    """All 51 pages at `Crawl-delay: 10`, so ~8.5 minutes.

    Failures are recorded as null and retried once as a set, then the invariant refuses an
    incomplete file (docs/OBSERVATIONS.md, 2026-09-23: a cold run lost 4 of 51 to DNS).
    """
    pages: dict[str, str | None] = {}

    def attempt(numbers: list[int], label: str) -> list[int]:
        failed: list[int] = []
        for number in numbers:
            url = f"https://council.nyc.gov/district-{number}/"
            try:
                pages[str(number)] = _get(url, tries=3).decode("utf-8", errors="replace")
            except FetchError as error:
                log(f"    district-{number} failed{label}: {error}")
                pages[str(number)] = None
                failed.append(number)
            if number % 10 == 0:
                log(f"    {number}/{DISTRICT_COUNT} district pages")
        return failed

    failed = attempt(list(range(1, DISTRICT_COUNT + 1)), "")
    if failed:
        log(f"    retrying {len(failed)} page(s) that failed: {failed}")
        still_failed = attempt(failed, " again")
        if still_failed:
            log(f"    {len(still_failed)} page(s) failed twice: {still_failed}")
    return json.dumps(pages).encode()


def _socrata_rows(
    dataset: str, select: str, *, page: int = 50_000, where: str | None = None
) -> Callable[..., bytes]:
    def fetch(log: Callable[[str], None]) -> bytes:
        rows: list[dict] = []
        offset = 0
        while True:
            query = urllib.parse.urlencode(
                {
                    "$select": select,
                    "$order": ":id",
                    "$limit": page,
                    "$offset": offset,
                    **({"$where": where} if where else {}),
                }
            )
            body = _get(f"{SOCRATA}/resource/{dataset}.json?{query}")
            batch = json.loads(body)
            if isinstance(batch, dict) and "error" in batch:
                raise FetchError(f"{dataset}: Socrata error {str(batch)[:160]}")
            rows.extend(batch)
            if len(batch) < page:
                break
            offset += page
            log(f"    {dataset}: {len(rows)} rows")
        return json.dumps(rows).encode()

    return fetch


def _published_not_in_the_future(log: Callable[[str], None], today: date) -> str:
    """The newest edition of the register not dated ahead of `today`.

    The newest value overall is in the future (docs/OBSERVATIONS.md, 2026-09-30).
    """
    query = urllib.parse.urlencode(
        {"$select": "publication", "$group": "publication", "$order": "publication DESC"}
    )
    body = _get(f"{SOCRATA}/resource/{BUDGET_REQUESTS_DATASET}.json?{query}")
    parsed = json.loads(body)
    if isinstance(parsed, dict) and "error" in parsed:
        raise FetchError(f"{BUDGET_REQUESTS_DATASET}: Socrata error {str(parsed)[:160]}")

    stamp = today.strftime("%Y%m%d")
    editions = sorted({str(row.get("publication") or "") for row in parsed}, reverse=True)
    for candidate in editions:
        if len(candidate) == 8 and candidate.isdigit() and candidate <= stamp:
            return candidate
        log(f"    skipping publication {candidate!r}: not a date on or before {stamp}")
    raise FetchError(
        f"{BUDGET_REQUESTS_DATASET}: no publication on or before {stamp}. "
        "Refusing to cache a future-dated register."
    )


def _fetch_board_budget_requests(log: Callable[[str], None]) -> bytes:
    """Only the edition the page will cite, so the cache cannot hold a future one."""
    publication = _published_not_in_the_future(log, date.today())
    log(f"    publication {publication}")
    return _socrata_rows(
        BUDGET_REQUESTS_DATASET,
        ",".join(BUDGET_REQUEST_COLUMNS),
        where=f"publication='{publication}'",
    )(log)


def _geospatial(dataset: str) -> Callable[..., bytes]:
    def fetch(log: Callable[[str], None]) -> bytes:  # noqa: ARG001
        return _get(f"{SOCRATA}/api/geospatial/{dataset}?method=export&format=GeoJSON")

    return fetch


#: Where every board's schedule comes from, discovered by measurement and committed in
#: `crosswalks/board_schedule_sources.json`. All 59 boards are listed, including the ones
#: nothing can be read from; only the ones marked `fetched` are requested here.
BOARD_SOURCES_PATH = (
    Path(__file__).resolve().parents[2] / "crosswalks" / "board_schedule_sources.json"
)

#: The Events Calendar caps a page at 50 however much you ask for, so this is the real
#: ceiling rather than an aspiration. A board page shows a handful.
TRIBE_PAGE = 50


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
    from .text import parse_html

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


def _board_pdf_body(landing: str | list, *, log: Callable[[str], None], code: str) -> str:
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
    from .sources.board_pdf import extract_pdf_text

    pages = [landing] if isinstance(landing, str) else list(landing)
    links: list[str] = []
    for page_url in pages:
        found = _board_pdf_links(_get(page_url, tries=2, timeout=60), page_url)
        links.extend(href for href in found[:BOARD_PDF_LIMIT] if href not in links)
    if not links:
        raise FetchError(f"no PDF linked from {', '.join(pages)}")

    documents = []
    for href in links:
        try:
            data = _get(href, tries=2, timeout=120)
        except (FetchError, ValueError) as error:
            # `ValueError` is `http.client.InvalidURL`'s base: a board can link an href
            # that is not a requestable URL, and that is its problem, not the fetch's.
            log(f"    board {code} pdf {href} failed: {error}")
            continue
        if len(data) < BOARD_PDF_FLOOR:
            log(f"    board {code} pdf {href} is {len(data)} bytes, not a calendar")
            continue
        try:
            extracted = extract_pdf_text(data)
        except Exception as error:
            # Caught broadly on purpose: pypdf raises its own hierarchy, and one
            # malformed document must not take the other 14 boards' schedules down.
            log(f"    board {code} pdf {href} did not extract: {type(error).__name__}")
            continue
        documents.append({"url": href, **extracted})

    if not documents:
        raise FetchError(f"none of {len(links)} PDFs at {', '.join(pages)} yielded text")
    return json.dumps(documents)


def _fetch_board_meetings(log: Callable[[str], None]) -> bytes:
    """Every board feed we hold, stored raw so the build parses offline.

    One failing board is recorded as a failure and the rest continue: these are 23
    independent third-party sites, several of which were already dead or behind Cloudflare
    when the list was made, so insisting on all of them would mean never refreshing any.
    """
    registry = json.loads(BOARD_SOURCES_PATH.read_text(encoding="utf-8"))
    feeds = {
        code: entry
        for code, entry in (registry.get("boards") or {}).items()
        if entry.get("fetched") and entry.get("url")
    }
    out: dict[str, dict] = {}
    answered = 0

    for code, entry in sorted(feeds.items()):
        raw_url = entry.get("url") or ""
        url = raw_url if isinstance(raw_url, str) else ", ".join(raw_url)
        kind = str(entry.get("kind") or "")
        if kind == "nyc-pdf":
            try:
                body = _board_pdf_body(raw_url, log=log, code=code)
            except FetchError as error:
                log(f"    board {code} (nyc-pdf) failed: {error}")
                out[code] = {"kind": kind, "url": url, "body": None, "error": str(error)[:200]}
                continue
            out[code] = {"kind": kind, "url": url, "body": body}
            answered += 1
            continue
        if kind == "tribe":
            # Ask for a window rather than the default "upcoming", which some of these
            # return empty even where the plugin holds events.
            url = f"{url.split('?')[0]}?per_page={TRIBE_PAGE}&start_date={date.today().isoformat()}"
        try:
            body = _get(url, tries=2, timeout=60).decode("utf-8", errors="replace")
        except FetchError as error:
            log(f"    board {code} ({kind}) failed: {error}")
            out[code] = {"kind": kind, "url": url, "body": None, "error": str(error)[:200]}
            continue
        out[code] = {"kind": kind, "url": url, "body": body}
        answered += 1

    log(f"    {answered} of {len(feeds)} board feeds answered")
    stamp = datetime.now().isoformat(timespec="seconds")
    return json.dumps({"fetched_at": stamp, "feeds": out}).encode()


def _board_meetings(body: bytes) -> str | None:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as error:
        return f"not valid JSON ({error})"
    if not isinstance(payload, dict):
        return f"expected a JSON object, got {type(payload).__name__}"
    feeds = payload.get("feeds")
    if not isinstance(feeds, dict):
        return "no feeds in the payload"
    answered = sum(1 for entry in feeds.values() if isinstance(entry, dict) and entry.get("body"))
    if answered < BOARD_FEED_FLOOR:
        return f"{answered} of {len(feeds)} board feeds answered, floor is {BOARD_FEED_FLOOR}"
    return None


PRESS_API = "https://council.nyc.gov/press/wp-json/wp/v2/posts"


def _fetch_participatory_budgeting(log: Callable[[str], None]) -> bytes:
    """Both PB rosters: the cycle the idea map is running, and the newest results release.

    The release is located through the press index, never by a URL pattern — press slugs
    are bare post ids, so no address is derivable from a cycle (docs/OBSERVATIONS.md,
    2026-10-27). Note the press site is a *second* WordPress install: the main site's API
    has no press post type, which is why a main-site search suggests PB coverage stopped
    in 2019.
    """
    query = urllib.parse.urlencode(
        {
            "search": "participatory budgeting",
            "per_page": 100,
            "_fields": "id,date,link,title",
        }
    )
    index = json.loads(_get(f"{PRESS_API}?{query}"))
    if not isinstance(index, list):
        raise FetchError(f"press index: expected a JSON array, got {type(index).__name__}")

    releases = [
        post
        for post in index
        if isinstance(post, dict)
        and is_results_release(str((post.get("title") or {}).get("rendered") or ""))
    ]
    if not releases:
        raise FetchError(
            f"press index: none of {len(index)} posts is a participatory budgeting "
            "results release. Keeping the previous cache."
        )
    newest = max(releases, key=lambda post: str(post.get("date") or ""))
    log(f"    {len(releases)} results release(s); newest is post {newest.get('id')}")

    release = json.loads(_get(f"{PRESS_API}/{newest.get('id')}?_fields=id,date,title,content"))
    idea_map = _get(IDEA_MAP_URL).decode("utf-8", errors="replace")

    return json.dumps(
        {
            "idea_map_url": IDEA_MAP_URL,
            "idea_map_html": idea_map,
            "release_url": str(newest.get("link") or ""),
            "release": release,
        }
    ).encode()


def _participatory_budgeting(body: bytes) -> str | None:
    """Refuse a payload either roster cannot be read from.

    Both are parsed here rather than only counted, because the release's own stated
    district count is the only check on the parse and it lives inside the body.
    """
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as error:
        return f"not valid JSON ({error})"
    if not isinstance(payload, dict):
        return f"expected a JSON object, got {type(payload).__name__}"
    try:
        participation = participation_from_payload(payload)
    except ParticipatoryBudgetingError as error:
        return str(error)
    if participation.results is None:
        return "no results release in the payload"
    return None


@dataclass(frozen=True)
class Source:
    name: str
    filename: str
    fetch: Callable[[Callable[[str], None]], bytes]
    invariant: Callable[[bytes], str | None]
    min_bytes: int
    max_age_hours: float
    why: str = field(default="")
    #: `label`, `dataset` and `url` are what `/references/` renders, so a source cannot
    #: be fetched without being disclosed.
    label: str = field(default="")
    dataset: str = field(default="")
    url: str = field(default="")


SOURCES: tuple[Source, ...] = (
    Source(
        name="calendar",
        filename="legistar_calendar.html",
        fetch=_fetch_calendar,
        invariant=_must_contain(b"gridCalendar", "the Legistar calendar grid"),
        min_bytes=200_000,
        max_age_hours=12,
        why="the only source of forward-looking meeting dates; the open dataset ends 2024",
        label="Legistar meeting calendar",
        dataset="Calendar.aspx, the live Legistar layer",
        url="https://nyc.legistar.com/Calendar.aspx",
    ),
    Source(
        name="districts",
        filename="district_pages.json",
        fetch=_fetch_district_pages,
        invariant=_district_pages,
        min_bytes=1_000_000,
        max_age_hours=24 * 30,
        why="the only source for council district office addresses",
        label="Council district pages",
        dataset="council.nyc.gov/district-N/, one page per district",
        url="https://council.nyc.gov/districts/",
    ),
    Source(
        name="members",
        filename="members.json",
        fetch=_socrata_rows(
            "uvw5-9znb", "name,council_member_id,term_start,term_end,district,office_id"
        ),
        invariant=_json_rows(MEMBER_ROW_FLOOR),
        min_bytes=50_000,
        max_age_hours=24 * 30,
        why="term windows decide which seats are currently held",
        label="Council members and term windows",
        dataset="uvw5-9znb",
        url="https://data.cityofnewyork.us/d/uvw5-9znb",
    ),
    Source(
        name="boards",
        filename="community_boards.json",
        fetch=_socrata_rows(
            "ruf7-3wgc",
            "borough,community_board,community_board_1,neighborhoods,cb_office_address,"
            "cb_address_line_2,cb_office_phone,cb_office_email,cb_website,cb_chair,"
            "cb_district_manager,cb_board_meeting,cb_cabinet_meeting",
        ),
        invariant=_json_rows(BOARD_COUNT),
        min_bytes=20_000,
        max_age_hours=24 * 60,
        why="community board contact details and meeting cadence",
        label="Community boards",
        dataset="ruf7-3wgc",
        url="https://data.cityofnewyork.us/d/ruf7-3wgc",
    ),
    Source(
        name="budget-requests",
        filename="board_budget_requests.json",
        fetch=_fetch_board_budget_requests,
        invariant=_board_budget_requests,
        min_bytes=1_000_000,
        max_age_hours=24 * 30,
        why="what each board asked the City for, in the board's own words",
        label="Community board budget requests",
        dataset="vn4m-mk4t",
        url="https://data.cityofnewyork.us/d/vn4m-mk4t",
    ),
    Source(
        name="council-geometry",
        filename="districts.geojson",
        fetch=_geospatial("mkqi-d8x3"),
        invariant=_geojson_features(DISTRICT_COUNT),
        # 862 KB against the shoreline-clipped file's 3.8 MB: the difference is the
        # thousands of vertices that traced every marsh island.
        min_bytes=500_000,
        max_age_hours=24 * 365,
        why="address lookup and the board crosswalk",
        label="Council district boundaries, water areas included",
        dataset="mkqi-d8x3",
        url="https://data.cityofnewyork.us/d/mkqi-d8x3",
    ),
    Source(
        name="council-geometry-land",
        filename="districts_land.geojson",
        fetch=_geospatial("872g-cjhh"),
        invariant=_geojson_features(DISTRICT_COUNT),
        min_bytes=1_000_000,
        max_age_hours=24 * 365,
        why="the denominator for board shares; never shipped, and never drawn",
        label="Council district boundaries, shoreline-clipped",
        dataset="872g-cjhh",
        url="https://data.cityofnewyork.us/d/872g-cjhh",
    ),
    Source(
        name="community-geometry",
        filename="community_districts.geojson",
        fetch=_geospatial("5crt-au7u"),
        # 59 real boards plus 12 joint interest areas (parks, airports).
        invariant=_geojson_features(BOARD_COUNT + len(JOINT_INTEREST_AREAS)),
        min_bytes=1_000_000,
        max_age_hours=24 * 365,
        why="the council-district to community-board crosswalk",
        label="Community district boundaries",
        dataset="5crt-au7u",
        url="https://data.cityofnewyork.us/d/5crt-au7u",
    ),
    Source(
        name="zip-geometry",
        filename="modzcta.geojson",
        fetch=_geospatial("pri4-ifjk"),
        invariant=_geojson_features(178),
        min_bytes=1_000_000,
        max_age_hours=24 * 365,
        why="ZIP code lookup without touching the geocoder",
        label="ZIP code boundaries",
        dataset="pri4-ifjk",
        url="https://data.cityofnewyork.us/d/pri4-ifjk",
    ),
    Source(
        name="board-meetings",
        filename="board_meetings.json",
        fetch=_fetch_board_meetings,
        invariant=_board_meetings,
        min_bytes=100_000,
        max_age_hours=24,
        why="the boards' own calendars; the City publishes no board meeting calendar",
        label="Community board calendars",
        dataset="23 board websites: Google Calendar, The Events Calendar, two bespoke",
        url="https://www.nyc.gov/site/cau/community-boards/community-boards.page",
    ),
    Source(
        name="participatory-budgeting",
        filename="participatory_budgeting.json",
        fetch=_fetch_participatory_budgeting,
        invariant=_participatory_budgeting,
        min_bytes=200_000,
        max_age_hours=24 * 7,
        why="the only two sources naming which districts run participatory budgeting",
        label="Participatory budgeting rosters",
        dataset="rnd.council.nyc.gov/ideamap/ + the press results release",
        url="https://council.nyc.gov/pb/",
    ),
)


_BY_NAME: dict[str, Source] = {source.name: source for source in SOURCES}


def cache_path(raw_dir: Path, name: str) -> Path:
    """Where a registered source's payload sits under `raw_dir`.

    `SOURCES` is the only place a cache filename is spelled, so a reader cannot drift from
    the writer.
    """
    return Path(raw_dir) / _BY_NAME[name].filename


def manifest_key(name: str) -> str:
    """A source's key in `manifest.json`: its cache filename without the suffix."""
    return Path(_BY_NAME[name].filename).stem


def _age_hours(path: Path) -> float | None:
    if not path.exists():
        return None
    return (time.time() - path.stat().st_mtime) / 3600


def fetch_one(source: Source, raw_dir: Path, *, log: Callable[[str], None] = print) -> str:
    """Fetch one source into the cache, or raise `FetchError`.

    The download lands in a `.part` file and is validated before it replaces the real
    one, so a bad response cannot destroy a good cache entry.
    """
    target = raw_dir / source.filename
    body = source.fetch(log)

    if len(body) < source.min_bytes:
        raise FetchError(
            f"{source.name}: {len(body)} bytes, floor is {source.min_bytes}. "
            "Keeping the previous cache."
        )
    problem = source.invariant(body)
    if problem is not None:
        raise FetchError(f"{source.name}: {problem}. Keeping the previous cache.")

    partial = target.with_suffix(target.suffix + ".part")
    partial.write_bytes(body)
    partial.replace(target)
    return "fetched"


def fetch_all(
    raw_dir: Path,
    *,
    only: str | None = None,
    force: bool = False,
    log: Callable[[str], None] = print,
) -> dict:
    """Refresh the cache. Returns a per-source report.

    A source younger than its `max_age_hours` is skipped unless `force`. One failed
    source does not stop the others; the build's own floors refuse what is unusable.
    """
    raw_dir = Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)

    selected = [s for s in SOURCES if only is None or s.name == only]
    if only and not selected:
        raise FetchError(f"unknown source {only!r}. Known: {', '.join(s.name for s in SOURCES)}")

    report: dict[str, dict] = {}
    failures: list[str] = []

    for source in selected:
        target = raw_dir / source.filename
        age = _age_hours(target)
        if not force and age is not None and age < source.max_age_hours:
            log(
                f"  {source.name}: fresh ({age:.1f}h old, "
                f"refresh after {source.max_age_hours:.0f}h)"
            )
            report[source.name] = {"status": "fresh", "age_hours": round(age, 1)}
            continue

        log(f"  {source.name}: fetching — {source.why}")
        try:
            fetch_one(source, raw_dir, log=log)
        except FetchError as error:
            log(f"    REFUSED: {error}")
            report[source.name] = {"status": "failed", "error": str(error)}
            failures.append(source.name)
            continue
        size = target.stat().st_size
        log(f"    ok, {size / 1e6:.2f} MB")
        report[source.name] = {"status": "fetched", "bytes": size}

    return {
        "sources": report,
        "failed": failures,
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
    }
