"""Parsing the meeting grid out of nyc.legistar.com/Calendar.aspx.

Why we scrape this at all: the NYC Open Data meetings dataset (m48u-yjt8) ends
2024-12-19, so it can never answer "when is the next meeting", and
webapi.legistar.com returns `403 Token is required` to anonymous callers. The
public HTML calendar carries the current session including future dates, needs no
key, and one plain GET of page 1 is enough — it is date-descending and already
spans several months ahead. We never POST the ~374 KB `__VIEWSTATE` for page 2.

The grid is ASP.NET Telerik. Ten cells per row; the ones we use:
  0 body name, 1 date, 3 time (or the literal "Deferred"), 4 location,
  5 topic (often a placeholder), 6 detail link, 7 agenda, 8 minutes.

Rows are located with a regex, which is safe here because nothing extracted is
trusted: every cell's text goes through `strip_tags` and every href through
`safe_url` before it can reach a page. If Legistar redesigns the grid this yields
an empty list, and the build's row floor turns that into a loud failure rather
than a site that quietly shows no meetings.
"""

from __future__ import annotations

import re
from datetime import date, time

from ..deadlines import accommodation_deadline, written_safe_until
from ..model import Meeting
from ..text import strip_tags
from ..urls import safe_url
from ..venues import normalize_location

__all__ = ["CalendarParseError", "parse_calendar", "parse_clock", "parse_us_date"]

BASE = "https://nyc.legistar.com/"

_ROW = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
_CELL = re.compile(r"<td\b[^>]*>(.*?)</td>", re.IGNORECASE | re.DOTALL)
_HREF = re.compile(r"""href\s*=\s*["']([^"']+)["']""", re.IGNORECASE)
_US_DATE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")
_CLOCK = re.compile(r"^(\d{1,2})(?::(\d{2}))?\s*([ap])\.?\s*m\.?$", re.IGNORECASE)
_PLACEHOLDER = re.compile(r"^multiple meeting items", re.IGNORECASE)


class CalendarParseError(RuntimeError):
    """The document did not look like the Legistar calendar at all."""


def parse_us_date(value: str) -> date | None:
    """ "12/17/2026" -> date. Rejects impossible dates like 02/31 rather than
    rolling them over, since a rolled-over date would send someone on the wrong
    day."""
    match = _US_DATE.match(value.strip())
    if not match:
        return None
    month, day, year = (int(part) for part in match.groups())
    try:
        return date(year, month, day)
    except ValueError:
        return None


def parse_clock(value: str) -> time | None:
    """ "1:30 PM" -> time. Returns None for "Deferred" and anything unparseable —
    we never guess a start time."""
    match = _CLOCK.match(value.strip())
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    is_pm = match.group(3).lower() == "p"
    if hour == 12:
        hour = 12 if is_pm else 0
    elif is_pm:
        hour += 12
    if hour > 23 or minute > 59:
        return None
    return time(hour, minute)


def _cell_url(cell: str) -> str | None:
    match = _HREF.search(cell)
    return safe_url(match.group(1), base=BASE) if match else None


def parse_calendar(html_text: str) -> list[Meeting]:
    """Extract every meeting row. Raises CalendarParseError if the page is not
    recognisably the calendar, which is a different failure from "no meetings"."""
    if "gridCalendar" not in html_text:
        raise CalendarParseError(
            "no gridCalendar element — page is not the Legistar calendar "
            "(check for an error body served with HTTP 200)"
        )

    meetings: list[Meeting] = []
    seen: set[tuple[str, date, str | None]] = set()

    for row_match in _ROW.finditer(html_text):
        cells = _CELL.findall(row_match.group(1))
        if len(cells) < 7:
            continue

        when = parse_us_date(strip_tags(cells[1]))
        if when is None:
            continue

        committee = strip_tags(cells[0])
        if not committee:
            continue

        raw_time = strip_tags(cells[3])
        start = parse_clock(raw_time)
        if start is not None:
            time_state = "scheduled"
        elif re.search(r"deferred", raw_time, re.IGNORECASE):
            time_state = "deferred"
        else:
            time_state = "time_not_published"

        raw_location = strip_tags(cells[4])
        venue, mode = normalize_location(raw_location)

        topic_text = strip_tags(cells[5]) if len(cells) > 5 else ""
        topic = None if (not topic_text or _PLACEHOLDER.match(topic_text)) else topic_text

        key = (committee, when, raw_time or None)
        if key in seen:
            continue
        seen.add(key)

        meetings.append(
            Meeting(
                committee=committee,
                date=when,
                start_time=raw_time if time_state == "scheduled" else None,
                time_state=time_state,
                attendance_mode=mode,
                venue=venue,
                raw_location=raw_location,
                topic=topic,
                detail_url=_cell_url(cells[6]) if len(cells) > 6 else None,
                agenda_url=_cell_url(cells[7]) if len(cells) > 7 else None,
                minutes_url=_cell_url(cells[8]) if len(cells) > 8 else None,
                written_safe_until=written_safe_until(when, start),
                accommodation_by=accommodation_deadline(when),
            )
        )

    return meetings


def upcoming(meetings: list[Meeting], today: date | None = None, limit: int = 5) -> list[Meeting]:
    """The next `limit` meetings, soonest first.

    Phase 1's shortlist is purely chronological — no ranking and no scoring, per
    docs/phase-1-scope.md. Deferred meetings are kept, because "postponed, no new
    date" is information a user needs, not noise.
    """
    horizon = today or date.today()
    ahead = [meeting for meeting in meetings if meeting.date >= horizon]
    ahead.sort(key=lambda meeting: (meeting.date, meeting.start_time or "00:00"))
    return ahead[:limit]
