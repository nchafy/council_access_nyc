"""Stage 1: pull every upstream payload into `etl/raw/`, which the build then reads offline.

A payload replaces a cache entry only after clearing a size floor and a body invariant,
because these hosts return HTTP 200 carrying error pages — CLAUDE.md, "Check body
invariants, not status codes". Crawl rates come from each host's own robots.txt
(docs/OBSERVATIONS.md, 2026-09-22).
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

__all__ = ["SOURCES", "FetchError", "fetch_all", "fetch_one"]

USER_AGENT = (
    "showup-nyc/0.1 (civic data ETL for a public-interest site; "
    "contact via github.com/nchafy/council_access_nyc)"
)

#: Seconds between requests to the same host; 2 s where the host publishes no robots.txt.
CRAWL_DELAY = {
    "council.nyc.gov": 10.0,
    "data.cityofnewyork.us": 1.0,
    "nyc.legistar.com": 2.0,
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
    if len(boards) < 59:
        return f"{len(boards)} boro/board pairs, expected all 59"
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
    if len(present) != 51:
        return f"{len(present)} of 51 district pages have content"
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
                log(f"    {number}/51 district pages")
        return failed

    failed = attempt(list(range(1, 52)), "")
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
        invariant=_json_rows(300),
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
        invariant=_json_rows(59),
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
        fetch=_geospatial("872g-cjhh"),
        invariant=_geojson_features(51),
        min_bytes=1_000_000,
        max_age_hours=24 * 365,
        why="address lookup and the board crosswalk",
        label="Council district boundaries",
        dataset="872g-cjhh",
        url="https://data.cityofnewyork.us/d/872g-cjhh",
    ),
    Source(
        name="community-geometry",
        filename="community_districts.geojson",
        fetch=_geospatial("5crt-au7u"),
        # 59 real boards plus 12 joint interest areas (parks, airports).
        invariant=_geojson_features(71),
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
)


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
