"""Stage 1: pull every upstream payload into the local cache.

Separate from the build on purpose. The build never touches the network, so it is
reproducible, testable offline, and a flaky download can never half-write a site.
This stage's only job is to leave `etl/raw/` in a state the build can trust.

FAIL CLOSED, THE SAME WAY THE BUILD DOES
A download is written to a temporary file, checked against a size floor **and** a
body invariant, and only then moved into place. A cache entry is therefore either
the last known-good payload or a new known-good payload — never a truncated file,
never an error page. This matters more here than anywhere else: a 200-response
containing an error page, silently cached, would make the build produce a
confident, wrong site.

BODY INVARIANTS, NOT STATUS CODES
Three verified cases where these hosts return HTTP 200 carrying an error:
`nyc.legistar.com/Feed.ashx` yields a 721-byte `<title>Invalid feed</title>`; a bad
`LegislationDetail` GUID yields a 19-byte `Invalid parameters!`; and a Socrata
query error arrives as JSON with an `error` key. So every source declares what its
body must contain to count as real.

POLITENESS, FROM EACH HOST'S OWN robots.txt (checked 2026-09-22)
  council.nyc.gov        Crawl-delay: 10   -> 51 district pages take ~8.5 minutes
  data.cityofnewyork.us  Crawl-delay: 1
  nyc.legistar.com       no robots.txt (404) -> no stated policy, so 2 s by choice
We are a guest on these servers. Hammering a city website would be a failure in
the one direction entirely under our control.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

__all__ = ["SOURCES", "FetchError", "fetch_all", "fetch_one"]

USER_AGENT = (
    "showup-nyc/0.1 (civic data ETL for a public-interest site; "
    "contact via github.com/nchafy/council_access_nyc)"
)

#: Seconds between requests to the same host. Sourced from robots.txt where the
#: host publishes one; conservative where it does not.
CRAWL_DELAY = {
    "council.nyc.gov": 10.0,
    "data.cityofnewyork.us": 1.0,
    "nyc.legistar.com": 2.0,
}
DEFAULT_DELAY = 2.0

SOCRATA = "https://data.cityofnewyork.us"
LEGISTAR = "https://nyc.legistar.com"
#: Verified to serve a byte-identical calendar, so it is a real failover rather
#: than a hopeful one.
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
            # A 404 or 403 will not fix itself; retrying is just rudeness.
            if error.code not in (408, 429, 500, 502, 503, 504):
                raise FetchError(f"{url} -> HTTP {error.code} (not retryable)") from error
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            last = error

        if attempt < tries:
            backoff = min(30.0, 2.0 ** (attempt - 1))
            time.sleep(backoff)

    raise FetchError(f"{url} failed after {tries} attempts: {last}")


# --------------------------------------------------------------------------- #
# Invariants
# --------------------------------------------------------------------------- #


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
            # Socrata reports query errors as a 200 with an error object.
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
    # Each page must actually look like a district page, or we have cached 51
    # copies of a login wall.
    for number in ("1", "26", "51"):
        page = parsed.get(number) or ""
        if f"District {number}" not in page:
            return f"district {number}'s page does not contain its own heading"
    return None


# --------------------------------------------------------------------------- #
# Fetchers
# --------------------------------------------------------------------------- #


def _fetch_calendar(log: Callable[[str], None]) -> bytes:
    """One plain GET of page 1.

    Page 1 is date-descending and already spans months ahead, so it answers "when
    is the next meeting" on its own. Page 2 would require POSTing a ~374 KB
    `__VIEWSTATE` for the least valuable rows, which we never do.
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
    """All 51 pages, at the rate council.nyc.gov's robots.txt asks for.

    ~8.5 minutes at Crawl-delay: 10. A page that fails is recorded as null rather
    than aborting, and the invariant then rejects an incomplete file — so a partial
    scrape never replaces a complete cached one.

    **The whole set is retried once before giving up.** A cold run on a fresh clone
    measured four pages lost to transient DNS failures out of 51, which refused the
    whole fetch — correct, but on a fresh clone there is no previous cache to fall
    back to, so the build could not proceed at all and the operator had to repeat
    nine minutes of crawling. A second pass over only the failures costs seconds in
    the normal case and rescues exactly this.
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


def _socrata_rows(dataset: str, select: str, *, page: int = 50_000) -> Callable[..., bytes]:
    def fetch(log: Callable[[str], None]) -> bytes:
        rows: list[dict] = []
        offset = 0
        while True:
            query = urllib.parse.urlencode(
                {
                    "$select": select,
                    # A stable sort is required for correct paging: without it
                    # Socrata gives no ordering guarantee and rows silently
                    # duplicate or vanish between pages.
                    "$order": ":id",
                    "$limit": page,
                    "$offset": offset,
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


def _geospatial(dataset: str) -> Callable[..., bytes]:
    def fetch(log: Callable[[str], None]) -> bytes:  # noqa: ARG001
        return _get(f"{SOCRATA}/api/geospatial/{dataset}?method=export&format=GeoJSON")

    return fetch


# --------------------------------------------------------------------------- #
# The source table
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Source:
    name: str
    filename: str
    fetch: Callable[[Callable[[str], None]], bytes]
    invariant: Callable[[bytes], str | None]
    min_bytes: int
    #: How old a cached copy may be before `fetch` refreshes it. The calendar
    #: changes daily; boundaries change about once a decade.
    max_age_hours: float
    why: str = field(default="")


SOURCES: tuple[Source, ...] = (
    Source(
        name="calendar",
        filename="legistar_calendar.html",
        fetch=_fetch_calendar,
        invariant=_must_contain(b"gridCalendar", "the Legistar calendar grid"),
        min_bytes=200_000,
        max_age_hours=12,
        why="the only source of forward-looking meeting dates; the open dataset ends 2024",
    ),
    Source(
        name="districts",
        filename="district_pages.json",
        fetch=_fetch_district_pages,
        invariant=_district_pages,
        min_bytes=1_000_000,
        max_age_hours=24 * 30,
        why="the only source for council district office addresses",
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
    ),
    Source(
        name="council-geometry",
        filename="districts.geojson",
        fetch=_geospatial("872g-cjhh"),
        invariant=_geojson_features(51),
        min_bytes=1_000_000,
        max_age_hours=24 * 365,
        why="address lookup and the board crosswalk",
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
    ),
    Source(
        name="zip-geometry",
        filename="modzcta.geojson",
        fetch=_geospatial("pri4-ifjk"),
        invariant=_geojson_features(178),
        min_bytes=1_000_000,
        max_age_hours=24 * 365,
        why="ZIP code lookup without touching the geocoder",
    ),
)


def _age_hours(path: Path) -> float | None:
    if not path.exists():
        return None
    return (time.time() - path.stat().st_mtime) / 3600


def fetch_one(source: Source, raw_dir: Path, *, log: Callable[[str], None] = print) -> str:
    """Fetch one source into the cache. Returns "fetched", "fresh", or raises.

    The download lands in a `.part` file and is validated before replacing the
    real one, so a bad response cannot destroy a good cache entry.
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
    # Atomic on the same filesystem, so the cache is never a half-written file.
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

    A source whose cached copy is younger than its `max_age_hours` is skipped
    unless `force`, which makes this cheap to run often — the calendar refreshes
    and the once-a-decade boundary files do not.
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
            # Keep going: one dead source should not stop the others, and the
            # build's own floors will refuse if what remains is unusable.
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
