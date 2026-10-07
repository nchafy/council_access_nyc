"""HTML generation.

The only place in the project where text becomes markup, which makes it the last
line of the XSS defence described in docs/phase-1-scope.md §4.1. Two rules:

1. **Escaping is the template engine's job, not something to remember.** The
   environment in `templates.py` runs with `autoescape=True`, so every
   interpolation is escaped unless someone opts out, and
   `tests/unit/test_template_safety.py` fails the build on every way of opting
   out. Nothing here hands a template pre-rendered HTML: it hands over plain
   values, and the markup lives in `templates/`.
2. **Links are only emitted for URLs that survived `urls.safe_url`.** A None URL
   renders as plain text, never as a dead or unchecked `href`.
"""

from __future__ import annotations

from datetime import date, datetime

from . import templates
from .deadlines import accommodation_state, written_state
from .model import BoardBudgetRequests, BudgetRequest, District, DistrictBoard, Meeting

__all__ = ["render_district", "render_index", "render_not_found", "render_references"]


def _link(url: str | None, label: str, *, extra: str = "") -> str:
    """An anchor for a checked URL, or inert text when there is none."""
    return templates.fragment("link", url, label, extra)


def _dl(rows: list[tuple[str, str]]) -> str:
    """A definition list, or nothing at all when there is no row to carry."""
    return templates.fragment("dl", rows)


def _short(value: str | None, limit: int = 58) -> str:
    if not value:
        return ""
    text = value.strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip(" ,;") + "…"


# --------------------------------------------------------------------------- #
# Index
# --------------------------------------------------------------------------- #


def render_index(
    districts: list[District],
    boards: list[DistrictBoard],
    *,
    built_at: datetime,
    window_end: date | None,
) -> str:
    """The front page: two ways in, because they answer different questions.

    Residents routinely want the community board and go looking for the council
    district, so both are offered side by side and the difference is stated.
    """
    return templates.render(
        "index.html",
        title="Council districts and community boards",
        districts=[
            {"number": d.number, "hood": _short(d.neighborhoods) if d.neighborhoods else None}
            for d in districts
        ],
        boards=[
            {
                "code": b.code,
                "label": b.label,
                "hood": _short(b.neighborhoods, 44) if b.neighborhoods else None,
            }
            for b in boards
        ],
        built_at=built_at,
        window_end=window_end,
    )


# --------------------------------------------------------------------------- #
# District page
# --------------------------------------------------------------------------- #

_MODE_LABEL = {
    "in_person": "In person",
    "hybrid": "Hybrid — in person or remote",
    "remote": "Remote only",
}
_TIME_STATE_LABEL = {
    "deferred": "Postponed — no new date published",
    "time_not_published": "Time not published",
}
#: The written-testimony window, named by how much of it is left.
_WRITTEN_LABEL = {
    "open": "Written testimony",
    "closing": "Written testimony — closing soon",
    "closed": "Written testimony — window has passed",
}


def _meeting_card(meeting: Meeting, *, today: date, now: datetime) -> dict:
    """One meeting as plain values, with both computed deadlines decided here."""
    written = None
    if meeting.written_safe_until:
        state = written_state(meeting.written_safe_until, now)
        written = {
            "label": _WRITTEN_LABEL[state],
            "state": state,
            "stamp": meeting.written_safe_until.strftime("%-d %B, %H:%M"),
        }
    accommodation = None
    if meeting.accommodation_by:
        accommodation = {
            "stamp": meeting.accommodation_by.strftime("%-d %B"),
            "passed": accommodation_state(meeting.date, today) != "open",
        }
    return {
        "committee": meeting.committee,
        "day": meeting.date.strftime("%A %-d %B %Y"),
        "start_time": meeting.start_time or "",
        "time_state_label": (
            None if meeting.time_state == "scheduled" else _TIME_STATE_LABEL[meeting.time_state]
        ),
        "mode": _MODE_LABEL.get(meeting.attendance_mode, meeting.attendance_mode),
        "venue_name": meeting.venue.name,
        "venue_address": meeting.venue.address,
        "topic": meeting.topic,
        "entry": meeting.venue.entry,
        "written": written,
        "accommodation": accommodation,
        "links": [
            (url, label)
            for url, label in (
                (meeting.detail_url, "Meeting details"),
                (meeting.agenda_url, "Agenda (PDF)"),
                (meeting.minutes_url, "Minutes (PDF)"),
            )
            if url
        ],
    }


def _board_card(board: DistrictBoard) -> str:
    """One community board as it appears on a council district's page."""
    return templates.fragment("board_card", board)


def render_district(
    district: District,
    meetings: list[Meeting],
    *,
    built_at: datetime,
    window_end: date | None,
    today: date | None = None,
    now: datetime | None = None,
) -> str:
    day = today or date.today()
    moment = now or datetime.now()
    return templates.render(
        "district.html",
        title=f"District {district.number}",
        district=district,
        cards=[_meeting_card(meeting, today=day, now=moment) for meeting in meetings],
        built_at=built_at,
        window_end=window_end,
    )


# --------------------------------------------------------------------------- #
# Board page
# --------------------------------------------------------------------------- #

#: Borough president offices appoint board members and process applications.
#: Roots only: the Bronx deep link nyc.gov publishes is a 404, and three of these
#: hosts return 403 to a non-browser client, so a deep path cannot be verified.
BP_SITES = {
    "Bronx": "https://bronxboropres.nyc.gov/",
    "Brooklyn": "https://www.brooklynbp.nyc.gov/community-boards/",
    "Manhattan": "https://www.manhattanbp.nyc.gov/",
    "Queens": "https://www.queensbp.nyc.gov/",
    "Staten Island": "https://www.statenislandusa.com/",
}

BUDGET_REGISTER_URL = "https://data.cityofnewyork.us/d/vn4m-mk4t"

#: Five, matching the shortlist size used for meetings. The register runs to 134
#: requests for one board, and the whole edition is one link away.
REQUESTS_SHOWN = 5
_EXPLANATION_CHARS = 260
_RESPONSE_CHARS = 260


def _budget_request(request: BudgetRequest) -> dict:
    """One filed request, quoted and cut short — never bucketed into yes and no."""
    return {
        "title": request.request or "The register does not describe this request",
        "priority": request.priority
        + (f" — {request.category.lower()}" if request.category else ""),
        "agency": request.agency,
        "explanation": _short(request.explanation, _EXPLANATION_CHARS),
        "response": _short(request.response, _RESPONSE_CHARS),
        "tracking_code": request.tracking_code,
    }


def _budget(asked: BoardBudgetRequests | None) -> dict | None:
    """One edition of the register for one board, or None when we hold none."""
    if asked is None or not asked.requests:
        return None
    return {
        "fiscal_year": asked.fiscal_year,
        "published": asked.publication.strftime("%-d %B %Y"),
        "total": len(asked.requests),
        "requests": [_budget_request(request) for request in asked.requests[:REQUESTS_SHOWN]],
    }


def render_board(
    board: DistrictBoard,
    districts: list[tuple[int, float]],
    *,
    built_at: datetime,
    window_end: date | None,
    budget_requests: BoardBudgetRequests | None = None,
) -> str:
    """The community board view — deliberately not a copy of the district page.

    No dataset publishes board agendas or a venue, so this page says so and sends
    the reader to the board's own site rather than pretending to a calendar.
    """
    return templates.render(
        "board.html",
        title=board.label,
        board=board,
        districts=districts,
        budget=_budget(budget_requests),
        register_url=BUDGET_REGISTER_URL,
        bp_url=BP_SITES.get(board.borough_name),
        built_at=built_at,
        window_end=window_end,
    )


def render_not_found(*, built_at: datetime, window_end: date | None) -> str:
    return templates.render(
        "not_found.html", title="Not found", built_at=built_at, window_end=window_end
    )


# --------------------------------------------------------------------------- #
# References
# --------------------------------------------------------------------------- #

#: The City Record is cited for its denominator and never fetched: a few dozen
#: land-use notices a year is not a board calendar, and saying so needs the number.
CITY_RECORD_URL = "https://data.cityofnewyork.us/d/dg92-zbpx"


def _window(hours: float) -> str:
    """A max_age as an exact unit: hours below two days, days above. Never rounded."""
    return f"{hours:g} hours" if hours < 48 else f"{hours / 24:g} days"


def render_references(sources: list[dict], *, built_at: datetime, window_end: date | None) -> str:
    """The one page carrying every identifier, fetch date, window and caveat."""
    return templates.render(
        "references.html",
        title="Sources",
        sources=[{**source, "window": _window(source["max_age_hours"])} for source in sources],
        city_record_url=CITY_RECORD_URL,
        register_url=BUDGET_REGISTER_URL,
        built_at=built_at,
        window_end=window_end,
    )
