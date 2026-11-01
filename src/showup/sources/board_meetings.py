"""Community board meetings, from the boards' own calendars.

The City publishes no board meeting calendar — `docs/board-meeting-sources.json` records
that, and it is still true. What the *boards* publish is another matter: 23 of 59 expose a
machine-readable feed, measured 2026-10-31, in three shapes.

1. **iCalendar**, 9 boards. Eight embed a public Google Calendar; one serves its own `.ics`.
2. **The Events Calendar**, 13 boards, a WordPress plugin with a REST API. All 12 boards on
   the City's own `cityofnewyork.us` network run it, plus one self-hosted.
3. One bespoke JSON file, Manhattan CB7.

Explicit dates alone give **1,424 upcoming meetings across 19 boards**; the other four have
live feeds with nothing scheduled forward. Recurring series are not expanded yet — 45 live
`RRULE`s would add more, concentrated on boards 109, 303 and 308.

Unlike every other source here, this is third-party **prose** that reaches the page: a
committee name and a venue, written by whoever keeps the calendar. Every string therefore
goes through `strip_tags` at ingest, which is the rule in CLAUDE.md for scraped content.
Nothing in these feeds says whether a meeting is remote, whether testimony is taken, or
when a comment window closes, so this module records none of those and the page must not
imply them.
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from ..text import collapse, strip_tags

__all__ = [
    "BOARD_MEETING_FLOOR",
    "BoardMeeting",
    "BoardMeetingsError",
    "load_board_meetings",
    "parse_feed",
    "parse_ics",
    "parse_mcb7",
    "parse_tribe",
]

#: Below this the ingest is broken rather than thin. Measured 2026-10-31: 1,424 upcoming
#: across 19 boards. A floor well under that still catches a feed format changing under us.
BOARD_MEETING_FLOOR = 300

#: How many boards must still be answering. 29 are fetched, and not all of them have
#: something ahead on any given day, so the floor is below both numbers.
BOARD_FEED_FLOOR = 15


class BoardMeetingsError(RuntimeError):
    """A feed could not be read, or the whole ingest fell below its floor."""


@dataclass(frozen=True, slots=True)
class BoardMeeting:
    """One meeting a board published. Deliberately thinner than `model.Meeting`.

    No attendance mode, no testimony deadline, no topic: a council hearing has those
    because Legistar publishes them, and a board calendar does not. Inventing them here
    would be the worst failure this project has available.
    """

    day: date
    #: As the calendar wrote it, e.g. "6:30 PM". None when the entry carries no time.
    start_time: str | None
    title: str
    #: The venue as published. Boards write these freely, so it is quoted, never parsed.
    location: str | None
    url: str | None


def _clean(value: object) -> str:
    """Upstream text to something safe to render: tags out, entities resolved, collapsed."""
    if value is None:
        return ""
    # `strip_tags` handles markup; tribe titles arrive entity-encoded ("&#038;") and are
    # not markup, so they are unescaped first.
    return collapse(strip_tags(html.unescape(str(value))))


def _unfold(body: str) -> list[str]:
    """iCalendar folds long lines with a leading space or tab. Put them back together."""
    lines: list[str] = []
    for raw in body.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    return lines


#: An iCalendar TEXT value escapes these; nothing else is special.
_ICS_UNESCAPE = (("\\n", " "), ("\\N", " "), ("\\,", ","), ("\\;", ";"), ("\\\\", "\\"))


def _ics_text(value: str) -> str:
    for token, replacement in _ICS_UNESCAPE:
        value = value.replace(token, replacement)
    return _clean(value)


_DTSTART = re.compile(r"^DTSTART([^:]*):(.+)$")


def _ics_when(params: str, value: str) -> tuple[date, str | None] | None:
    """A DTSTART as a day and, when the entry carries one, a time.

    Three shapes appear: `20261112T183000` local, `20261112T233000Z` in UTC, and
    `VALUE=DATE:20261112` for an all-day entry. The UTC form is converted to New York,
    which is the only timezone any of these calendars is about; without that a 7pm meeting
    reads as the next day.
    """
    raw = value.strip()
    if "VALUE=DATE" in params:
        try:
            return datetime.strptime(raw[:8], "%Y%m%d").date(), None
        except ValueError:
            return None
    try:
        moment = datetime.strptime(raw[:15], "%Y%m%dT%H%M%S")
    except ValueError:
        try:
            return datetime.strptime(raw[:8], "%Y%m%d").date(), None
        except ValueError:
            return None
    if raw.endswith("Z"):
        # New York is UTC-5, or UTC-4 under daylight saving from the second Sunday in March
        # to the first Sunday in November. Worked out rather than imported: the stdlib has
        # no tz database guarantee and a dependency for one date rule is not worth it.
        #
        # Subtracted with `timedelta`, not `replace(hour=...)`: an 02:00Z entry becomes
        # hour -3, which `replace` rejects, and that killed every iCalendar feed.
        moment = moment - timedelta(hours=_ny_offset(moment.date()))
    return moment.date(), moment.strftime("%-I:%M %p")


def _ny_offset(day: date) -> int:
    """Hours to subtract from UTC for New York on `day`: 4 in summer, 5 in winter."""
    march = date(day.year, 3, 8)
    dst_start = march + ((6 - march.weekday()) % 7) * timedelta(1)
    november = date(day.year, 11, 1)
    dst_end = november + ((6 - november.weekday()) % 7) * timedelta(1)
    return 4 if dst_start <= day < dst_end else 5


def parse_ics(body: str, *, on_or_after: date) -> list[BoardMeeting]:
    """Every dated entry in an iCalendar feed, from `on_or_after` onwards.

    Recurring entries are **not** expanded: an `RRULE` whose `DTSTART` is in the past still
    produces meetings, and 45 such series exist across these feeds, so this undercounts.
    Undercounting is the safe direction — a meeting we do not list is a gap, a meeting we
    invent is a wrong answer.
    """
    meetings: list[BoardMeeting] = []
    current: dict[str, str] = {}
    inside = False

    for line in _unfold(body):
        if line.startswith("BEGIN:VEVENT"):
            inside, current = True, {}
            continue
        if line.startswith("END:VEVENT"):
            inside = False
            when = current.get("when")
            if when:
                day, start_time = when  # type: ignore[misc]
                if day >= on_or_after:
                    meetings.append(
                        BoardMeeting(
                            day=day,
                            start_time=start_time,
                            title=current.get("title") or "Meeting",
                            location=current.get("location") or None,
                            url=None,
                        )
                    )
            continue
        if not inside:
            continue

        found = _DTSTART.match(line)
        if found:
            when = _ics_when(found.group(1), found.group(2))
            if when:
                current["when"] = when  # type: ignore[assignment]
            continue
        for key, field in (("SUMMARY:", "title"), ("LOCATION:", "location")):
            if line.startswith(key):
                current[field] = _ics_text(line[len(key) :])
    return meetings


def parse_tribe(payload: dict, *, on_or_after: date) -> list[BoardMeeting]:
    """The Events Calendar's REST response. `start_date` is "YYYY-MM-DD HH:MM:SS" local."""
    meetings = []
    for event in payload.get("events") or []:
        stamp = str(event.get("start_date") or "")
        try:
            moment = datetime.strptime(stamp[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        if moment.date() < on_or_after:
            continue
        venue = event.get("venue") or {}
        meetings.append(
            BoardMeeting(
                day=moment.date(),
                start_time=None if event.get("all_day") else moment.strftime("%-I:%M %p"),
                title=_clean(event.get("title")) or "Meeting",
                location=_clean(venue.get("venue")) or _clean(venue.get("address")) or None,
                url=str(event.get("url") or "") or None,
            )
        )
    return meetings


def parse_mcb7(payload: list, *, on_or_after: date) -> list[BoardMeeting]:
    """Manhattan CB7's own JSON. One board, one shape, so it gets its own reader."""
    meetings = []
    for item in payload or []:
        stamp = str(item.get("date") or "")
        try:
            day = date.fromisoformat(stamp[:10])
        except ValueError:
            continue
        if day < on_or_after:
            continue
        meetings.append(
            BoardMeeting(
                day=day,
                start_time=_clean(item.get("time")) or None,
                title=_clean(item.get("title")) or _clean(item.get("committee")) or "Meeting",
                location=_clean(item.get("location")) or None,
                url=str(item.get("agendaUrl") or "") or None,
            )
        )
    return meetings


def parse_feed(
    kind: str, body: str, *, on_or_after: date, code: str | None = None
) -> list[BoardMeeting]:
    """Dispatch on the kind recorded at fetch time.

    `nyc-html` needs the board code too: those six boards share a host and a CMS and
    nothing else, so each has its own reader in `board_html`.
    """
    if kind == "nyc-html":
        from .board_html import parse_html

        return parse_html(str(code), body, on_or_after=on_or_after)
    if kind == "nyc-pdf":
        from .board_pdf import parse_pdf

        return parse_pdf(str(code), body, on_or_after=on_or_after)
    if kind in ("gcal-ics", "other-ics"):
        return parse_ics(body, on_or_after=on_or_after)
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as error:
        raise BoardMeetingsError(f"{kind}: not valid JSON ({error})") from error
    if kind == "tribe":
        if not isinstance(payload, dict):
            raise BoardMeetingsError(f"tribe: expected an object, got {type(payload).__name__}")
        return parse_tribe(payload, on_or_after=on_or_after)
    if kind == "other-json":
        if not isinstance(payload, list):
            raise BoardMeetingsError(f"other-json: expected an array, got {type(payload).__name__}")
        return parse_mcb7(payload, on_or_after=on_or_after)
    raise BoardMeetingsError(f"unknown feed kind {kind!r}")


def load_board_meetings(path: Path, *, on_or_after: date) -> dict[str, list[BoardMeeting]]:
    """Every board's upcoming meetings, from the cached payloads, newest first by day.

    A board whose feed failed is simply absent, which the page renders as "we hold none"
    rather than as "there are none".
    """
    try:
        cached = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BoardMeetingsError(f"{path}: {error}") from error
    if not isinstance(cached, dict):
        raise BoardMeetingsError(f"{path}: expected an object, got {type(cached).__name__}")

    by_board: dict[str, list[BoardMeeting]] = {}
    for code, entry in (cached.get("feeds") or {}).items():
        if not isinstance(entry, dict) or not entry.get("body"):
            continue
        try:
            found = parse_feed(
                str(entry.get("kind")),
                str(entry["body"]),
                on_or_after=on_or_after,
                code=str(code),
            )
        except BoardMeetingsError:
            continue
        if found:
            by_board[str(code)] = sorted(found, key=lambda m: (m.day, m.start_time or ""))

    total = sum(len(v) for v in by_board.values())
    if total < BOARD_MEETING_FLOOR:
        raise BoardMeetingsError(
            f"{total} upcoming board meetings across {len(by_board)} boards, floor is "
            f"{BOARD_MEETING_FLOOR}. Refusing to publish a thin calendar."
        )
    if len(by_board) < BOARD_FEED_FLOOR:
        raise BoardMeetingsError(f"{len(by_board)} boards answered, floor is {BOARD_FEED_FLOOR}")
    return by_board
