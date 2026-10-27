"""Which council districts run Participatory Budgeting, from the two sources that say so.

The Council publishes no dataset of PB participation. `wwhr-5ven`, `qm5f-frjb` and
`wa6b-r9jh` all stop at vote year 2017-2019 and key to the district numbers the 2023
redistricting replaced, and `council.nyc.gov/pb/` names no districts at all. What does
carry the roster:

1. **The open cycle** — the Council's idea map at `rnd.council.nyc.gov/ideamap/`, which
   renders one `data-district` attribute per participating district. The page states no
   year, no fiscal year and no vote date, so neither does this module: the cycle is "the
   current cycle", exactly as the page has it. Unversioned, and overwritten next cycle.
2. **The last completed cycle** — the results press release, reachable as JSON through the
   press site's own WordPress REST API. It enumerates every district *and* states how many
   there were, which gives the parse a checksum rather than a guess.

Only integers cross this boundary. No upstream prose is rendered, which is what keeps the
injection surface at zero here — CLAUDE.md, "injection through scraped upstream content".
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from ..model import DISTRICT_COUNT

__all__ = [
    "IDEA_MAP_URL",
    "PB_DISTRICT_FLOOR",
    "PB_PROGRAMME_URL",
    "Participation",
    "ParticipatoryBudgetingError",
    "ResultsCycle",
    "districts_in_release",
    "is_results_release",
    "load_participation",
    "parse_idea_map",
    "parse_results_release",
    "participation_from_payload",
    "stated_district_count",
]

#: The Council's idea map for the cycle that is open now. Council-operated host.
IDEA_MAP_URL = "https://rnd.council.nyc.gov/ideamap/map/"

#: The programme's own page. Linked, never parsed: it names no districts, and on
#: 2026-10-27 it still advertised the already-closed FY2027 vote window, so a cycle must
#: never be read off it.
PB_PROGRAMME_URL = "https://council.nyc.gov/pb/"

#: Below this a roster is broken rather than small. Observed: 29 districts for FY2024,
#: 24 for FY2026, 22 for FY2027, 24 in the open cycle's idea map (2026-10-27).
PB_DISTRICT_FLOOR = 15


class ParticipatoryBudgetingError(RuntimeError):
    """A roster failed its own checksum or floor. The caller must not fall back to a
    partial list: a district silently dropped from a roster reads as "not taking part"."""


@dataclass(frozen=True, slots=True)
class ResultsCycle:
    """One completed cycle's results release."""

    cycle: str
    published: date
    districts: tuple[int, ...]
    url: str


@dataclass(frozen=True, slots=True)
class Participation:
    """Both rosters, reported against separately and never merged.

    A district absent from both is *unlisted*, which says only that neither source names
    it. It is not evidence that the district runs no programme — a different claim, and
    one nothing this module reads supports.
    """

    open_cycle: tuple[int, ...]
    open_cycle_url: str
    results: ResultsCycle | None


#: A results release titles itself "…Announce Results of FY 2027 Participatory Budgeting".
_TITLE = re.compile(r"Results of\s+(FY\s*20\d\d)\s+Participatory Budgeting", re.I)

#: The release's own count, which the enumerated districts must match.
_STATED_COUNT = re.compile(r"(\d{1,3})\s+Council\s+Districts", re.I)

#: "District 35", and the heading form "District 35 - Council Member ...". A bare "35" is
#: never taken: the releases are thick with dollar figures, school and precinct numbers.
_DISTRICT = re.compile(r"\bDistrict\s+(\d{1,2})\b")

#: One per participating district on the idea map.
_DATA_DISTRICT = re.compile(r'data-district="(\d{1,2})"')


def _flatten(markup: str) -> str:
    """Markup to plain text, scripts and styles dropped first so their contents cannot be
    mistaken for prose."""
    text = re.sub(r"<(script|style)\b.*?</\1>", " ", markup, flags=re.S | re.I)
    text = re.sub(r"<[^>]*>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text))


def _in_range(numbers: list[str]) -> tuple[int, ...]:
    """Unique district numbers, sorted, with anything outside 1-51 discarded."""
    return tuple(sorted({n for raw in numbers if 1 <= (n := int(raw)) <= DISTRICT_COUNT}))


def stated_district_count(markup: str) -> int | None:
    """The count the release states about itself, or None when it states none."""
    found = _STATED_COUNT.search(_flatten(markup))
    return int(found.group(1)) if found else None


def districts_in_release(markup: str) -> tuple[int, ...]:
    """Every district the release names."""
    return _in_range(_DISTRICT.findall(_flatten(markup)))


def parse_results_release(post: dict, *, url: str) -> ResultsCycle:
    """One WordPress REST post as a cycle, or raise.

    The checksum is the whole point. A release that enumerates 21 districts while stating
    22 has either been reworded or parsed wrongly, and both cases must stop the build:
    the missing district would render as "not taking part". This mirrors the hard
    invariant on minutes vote blocks — match the printed integer or quarantine the
    document, never publish the subset.
    """
    title = _flatten(str((post.get("title") or {}).get("rendered") or ""))
    body = str((post.get("content") or {}).get("rendered") or "")

    named = _TITLE.search(title)
    if named is None:
        raise ParticipatoryBudgetingError(
            f"{url}: title is not a participatory budgeting results release ({title[:80]!r})"
        )
    cycle = re.sub(r"\s+", " ", named.group(1)).upper()

    stated = stated_district_count(body)
    districts = districts_in_release(body)
    if stated is None:
        raise ParticipatoryBudgetingError(
            f"{url}: release states no district count, so the {len(districts)} parsed "
            "cannot be checked"
        )
    if len(districts) != stated:
        raise ParticipatoryBudgetingError(
            f"{url}: release states {stated} districts, parsed {len(districts)} "
            f"({', '.join(str(d) for d in districts)}). Refusing a partial roster."
        )
    if len(districts) < PB_DISTRICT_FLOOR:
        raise ParticipatoryBudgetingError(
            f"{url}: {len(districts)} districts, floor is {PB_DISTRICT_FLOOR}"
        )

    stamp = str(post.get("date") or "")[:10]
    try:
        published = date.fromisoformat(stamp)
    except ValueError as error:
        raise ParticipatoryBudgetingError(f"{url}: unreadable date {stamp!r}") from error

    return ResultsCycle(cycle=cycle, published=published, districts=districts, url=url)


def parse_idea_map(markup: str) -> tuple[int, ...]:
    """Districts in the cycle the idea map is currently running.

    Read from the attribute rather than the visible table: the table repeats every
    district's member and borough, so a name there is not evidence of participation.
    """
    districts = _in_range(_DATA_DISTRICT.findall(markup))
    if len(districts) < PB_DISTRICT_FLOOR:
        raise ParticipatoryBudgetingError(
            f"{IDEA_MAP_URL}: {len(districts)} districts carry data-district, floor is "
            f"{PB_DISTRICT_FLOOR}. The idea map is unversioned, so a rebuild of that page "
            "can change the attribute without notice."
        )
    return districts


def is_results_release(title: str) -> bool:
    """Whether a press-release title announces a cycle's results.

    Used to pick the post out of the press index *and* to re-check the one that was
    cached, so the fetcher and the parser cannot drift on what counts as a release.
    """
    return _TITLE.search(_flatten(title)) is not None


def participation_from_payload(payload: dict) -> Participation:
    """Both rosters from an already-decoded payload. Raises rather than returning a
    partial one — the fetch invariant and the build run this same path."""
    open_cycle = parse_idea_map(str(payload.get("idea_map_html") or ""))

    release = payload.get("release")
    results = (
        parse_results_release(release, url=str(payload.get("release_url") or ""))
        if isinstance(release, dict)
        else None
    )
    return Participation(
        open_cycle=open_cycle,
        open_cycle_url=str(payload.get("idea_map_url") or IDEA_MAP_URL),
        results=results,
    )


def load_participation(path: Path) -> Participation:
    """Both rosters from the cached payload."""
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ParticipatoryBudgetingError(f"{path}: {error}") from error
    if not isinstance(payload, dict):
        raise ParticipatoryBudgetingError(
            f"{path}: expected a JSON object, got {type(payload).__name__}"
        )
    return participation_from_payload(payload)
