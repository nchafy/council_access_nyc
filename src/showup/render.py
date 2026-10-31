"""HTML generation: the only place text becomes markup (docs/phase-1-scope.md §4.1).

Escaping is the environment's job, not a thing to remember — `templates.py` sets
`autoescape=True` and `tests/unit/test_template_safety.py` fails the build on every way
of opting out. A link is emitted only for a URL that survived `urls.safe_url`.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from urllib.parse import urlencode

from . import templates
from .deadlines import accommodation_state, written_state
from .model import BoardBudgetRequests, BudgetRequest, District, DistrictBoard, Meeting
from .sources.participatory_budgeting import PB_PROGRAMME_URL, Participation
from .urls import safe_url

__all__ = [
    "preview_payload",
    "render_district",
    "render_index",
    "render_listing",
    "render_map",
    "render_not_found",
    "render_references",
]


#: A phone number as the City publishes it: "(718) 467-5574", sometimes with an extension.
_PHONE_DIGITS = re.compile(r"\d")
_PHONE_SHAPE = re.compile(r"^[\d\s()+.\-]+$")

#: Deliberately strict. This is a constructed `mailto:`, so anything odd is dropped rather
#: than escaped and hoped for.
_EMAIL_SHAPE = re.compile(r"^[^\s<>@]+@[^\s<>@.]+(\.[^\s<>@.]+)+$")


def _tel_href(phone: str | None) -> str | None:
    """`tel:` for a published number, or None.

    Not routed through `safe_url`: that function's contract is https-and-allowlisted-host,
    which is the XSS boundary for *upstream* URLs, and widening it to cover schemes with no
    host would weaken it for every caller. This builds its own and validates the shape.
    """
    if not phone or not _PHONE_SHAPE.match(phone.strip()):
        return None
    digits = "".join(_PHONE_DIGITS.findall(phone))
    # Ten digits is a US number; eleven starting with 1 is the same number written long.
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10:
        return None
    return f"tel:+1{digits}"


def _mailto_href(email: str | None) -> str | None:
    """`mailto:` for a published address, or None."""
    if not email:
        return None
    candidate = email.strip()
    return f"mailto:{candidate}" if _EMAIL_SHAPE.match(candidate) else None


def _maps_href(address: str | None) -> str | None:
    """A Google Maps *search* for an address. Owner's decision, 2026-10-31.

    A search query, not a place id: we do not know the board office's place id and would
    be guessing one. The query is what we hold, so the query is what is sent.
    """
    if not address or not address.strip():
        return None
    query = urlencode({"api": "1", "query": address.strip()})
    return safe_url(f"https://www.google.com/maps/search/?{query}")


def _wikipedia_href(name: str, borough: str | None) -> str | None:
    """Wikipedia's search-and-jump URL for a neighbourhood. Owner's decision, 2026-10-31.

    **Not** `/wiki/<name>`. These names are free text from a City dataset, so a constructed
    article path is a guess: it 404s for anything Wikipedia titles differently and, worse,
    silently lands on the wrong article for a name that is ambiguous between boroughs.
    `index.php?search=` jumps straight to the article when the title matches exactly and
    shows results when it does not, so it is never wrong — only sometimes a search page.
    The borough is appended because that is how Wikipedia disambiguates these.
    """
    label = name.strip()
    if not label:
        return None
    query = f"{label}, {borough}" if borough else label
    return safe_url(f"https://en.wikipedia.org/w/index.php?{urlencode({'search': query})}")


#: The City writes these as "A, B, and C" and occasionally "A and B".
_NEIGHBOURHOOD_SPLIT = re.compile(r",\s*(?:and\s+)?|\s+and\s+")


def neighbourhood_links(text: str | None, borough: str | None) -> list[dict]:
    """One entry per neighbourhood, each with the Wikipedia search that finds it."""
    if not text:
        return []
    names = [part.strip(" .") for part in _NEIGHBOURHOOD_SPLIT.split(text)]
    return [{"name": name, "href": _wikipedia_href(name, borough)} for name in names if name]


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


def render_index(
    districts: list[District],
    boards: list[DistrictBoard],
    *,
    built_at: datetime,
    window_end: date | None,
    meetings: list[Meeting] | None = None,
    today: date | None = None,
    now: datetime | None = None,
) -> str:
    """The landing page: a map button, an address box, and the next citywide meeting.

    It carries no map — that is a route of its own, so the 449 KB library is paid for only by
    a reader who asks for it. The two index pages used to share this template and now have
    `render_listing`.
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
        # Citywide, which is why it sits here and not on a district. Council and committee
        # meetings belong to no district; it was moved off the map's district panel on
        # 2026-10-27 for that reason.
        next_meeting=(
            _meeting_card(meetings[0], today=today or date.today(), now=now or datetime.now())
            if meetings
            else None
        ),
        built_at=built_at,
        window_end=window_end,
    )


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


def render_listing(
    districts: list[District],
    boards: list[DistrictBoard],
    *,
    built_at: datetime,
    window_end: date | None,
) -> str:
    """`/district/` and `/board/`: both lists in full, and the two dropdowns.

    Separate from the landing page since 2026-10-22. The landing page is a map button and an
    address box; these are where the no-JavaScript path actually lives.
    """
    return templates.render(
        "listing.html",
        title="All council districts and community boards",
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


#: How many filed requests the panel lists before sending the reader to the page.
PREVIEW_REQUESTS = 3


def preview_payload(
    districts: list[District],
    boards: list[DistrictBoard],
    meetings: list[Meeting],
    budget_requests: dict[str, BoardBudgetRequests],
    *,
    built_at: datetime,
    today: date | None = None,
    now: datetime | None = None,
    participation: Participation | None = None,
    boards_to_districts: dict[str, list[tuple[int, float]]] | None = None,
) -> dict:
    """The headline facts the map's detail panel shows, one artifact for both layers.

    Summaries only. Everything here is on the page the panel links to, which is where the
    provenance lives, so the panel states `as_of` once and sends the reader on rather than
    repeating a source line per field.

    `next_meeting` is top-level and not per district on purpose: Council and committee
    meetings are citywide and belong to no district, which is the whole reason the district
    is a filter in this project and never the organising key.
    """
    day = today or date.today()
    moment = now or datetime.now()
    upcoming = _meeting_card(meetings[0], today=day, now=moment) if meetings else None
    boards_to_districts = boards_to_districts or {}

    return {
        "as_of": built_at.isoformat(timespec="seconds"),
        "next_meeting": upcoming,
        "pb": _pb_meta(participation),
        "districts": {
            str(d.number): {
                "member": None
                if d.member is None
                else {"name": d.member.name, "seat_status": d.member.seat_status},
                # The same specs the district page renders. Committees carry their role,
                # boards their share, and participatory budgeting its cycle, because the
                # columns are declared once in `district_tables` for both views.
                "tables": district_tables(d, participation),
            }
            for d in districts
        },
        "boards": {
            b.code: {
                "label": b.label,
                # Quoted verbatim: the City's dataset and the boards' own sites have been
                # observed to disagree, so this is not reworded into a schedule.
                "cadence": b.board_meeting,
                "phone": b.phone,
                "address": b.address,
                "tables": board_tables(
                    boards_to_districts.get(b.code, []), budget_requests.get(b.code)
                ),
            }
            for b in boards
        },
    }


def _participation(participation: Participation | None, number: int) -> dict | None:
    """Participatory budgeting as two dated findings, never one standing claim.

    A district is in the programme *for a cycle*. Measured on 2026-10-27: 24 districts are
    in the cycle the idea map is running, 22 were named in the FY2027 results, and only 21
    are in both — so "this district has participatory budgeting" is not a fact either
    source supports. Each row therefore names its cycle and carries its own link.
    """
    if participation is None:
        return None
    results = participation.results
    return {
        "in_open_cycle": number in participation.open_cycle,
        "open_cycle_url": participation.open_cycle_url,
        "cycle": results.cycle if results else None,
        "named_in_results": bool(results and number in results.districts),
        "results_url": results.url if results else None,
        "results_published": results.published.strftime("%-d %B %Y") if results else None,
        "programme_url": PB_PROGRAMME_URL,
    }


#: The one place a panel/page table's shape is written down. A spec is
#: `{legend, href, caption, columns, rows}`; a cell is a plain string, `{"text", "href"}`
#: for a link, or `{"text", "share"}` for a share figure with its bar.
#:
#: Both views render these specs and neither invents a column: the district page through
#: the `group` macro, the map panel from `preview.json`. Before this, the panel built its
#: tables in JavaScript while the page built its own in Jinja, so a column added to one
#: was silently missing from the other.
COMMITTEES_INDEX = "https://council.nyc.gov/committees/"

#: Matches the panel, which shows the headline and links on for the rest.
COMMITTEES_SHOWN = 5


#: Both cell kinds carry both optional keys. The template environment uses
#: StrictUndefined, so a cell that omits one would fail the build the first time a
#: different kind appeared in the same column.
def _link_cell(text: str, href: str) -> dict:
    return {"text": text, "href": href, "share": None}


def _share_cell(share: float) -> dict:
    """A share as a percentage and a bar. Rounded once, here, so the two views cannot
    round differently."""
    percent = round(share * 100)
    return {"text": f"{percent}%", "href": None, "share": percent}


def _table(legend: str, columns: list[str], rows: list[list], **extra) -> dict | None:
    """A spec, or None when there is no row to carry — an empty table is not rendered."""
    if not rows:
        return None
    # `caption` and `href` are always present, never omitted: the environment runs with
    # StrictUndefined, so a missing key is a build failure rather than an empty string.
    return {
        "legend": legend,
        "columns": columns,
        "rows": rows,
        "caption": extra.get("caption"),
        "href": extra.get("href"),
    }


def district_tables(district: District, participation: Participation | None) -> list[dict]:
    """Every tabular group for one council district, in the order both views show them."""
    pb = _participation(participation, district.number)
    meta = _pb_meta(participation)
    specs = []

    if pb and meta:
        rows = [
            [
                "Current",
                "Named" if pb["in_open_cycle"] else "Not named",
                _link_cell("Idea map", meta["open_cycle_url"]),
            ]
        ]
        if meta["cycle"]:
            rows.append(
                [
                    meta["cycle"],
                    "Named" if pb["named_in_results"] else "Not named",
                    _link_cell("Results release", meta["results_url"]),
                ]
            )
        specs.append(
            _table(
                "Participatory budgeting",
                ["Cycle", "Status", "Source"],
                rows,
                href=meta["programme_url"],
            )
        )

    committees = (getattr(district.member, "committees", ()) or ())[:COMMITTEES_SHOWN]
    specs.append(
        _table(
            "Committees",
            ["Committee", "Role"],
            [[c.name, c.role] for c in committees],
            href=COMMITTEES_INDEX,
        )
    )

    specs.append(
        _table(
            "Community boards",
            ["Board", "Share of district"],
            [
                [_link_cell(b.label, f"/board/{b.code}/"), _share_cell(b.share)]
                for b in sorted(district.boards or (), key=lambda b: -b.share)
            ],
        )
    )
    return [spec for spec in specs if spec]


def board_tables(
    districts: list[tuple[int, float]],
    asked: BoardBudgetRequests | None,
) -> list[dict]:
    """Every tabular group for one community board."""
    specs = [
        _table(
            "Council districts",
            ["District", "Share of board"],
            [
                [_link_cell(f"Council District {n}", f"/district/{n}/"), _share_cell(share)]
                for n, share in districts
            ],
        )
    ]
    if asked is not None and asked.requests:
        specs.append(
            _table(
                "Budget requests",
                ["Request", "Category"],
                [
                    [
                        r.request or "The register does not describe this request",
                        (r.category or "").lower(),
                    ]
                    for r in asked.requests[:PREVIEW_REQUESTS]
                ],
                caption=(
                    f"Fiscal {asked.fiscal_year}: {len(asked.requests)} filed, the first few below."
                ),
            )
        )
    return [spec for spec in specs if spec]


def _pb_meta(participation: Participation | None) -> dict | None:
    """The labels and links both rosters share, stated once for the whole artifact."""
    if participation is None:
        return None
    results = participation.results
    return {
        "open_cycle_url": participation.open_cycle_url,
        "cycle": results.cycle if results else None,
        "results_url": results.url if results else None,
        "results_published": results.published.strftime("%-d %B %Y") if results else None,
        "programme_url": PB_PROGRAMME_URL,
    }


def render_map(*, built_at: datetime, window_end: date | None) -> str:
    """The full-screen map. Its own route because a map inside a scrolling page steals the
    wheel: the reader scrolls and the map zooms instead. Here nothing scrolls."""
    return templates.render(
        "map.html",
        title="Map of council districts and community boards",
        built_at=built_at,
        window_end=window_end,
    )


def render_district(
    district: District,
    meetings: list[Meeting],
    *,
    built_at: datetime,
    window_end: date | None,
    today: date | None = None,
    now: datetime | None = None,
    participation: Participation | None = None,
) -> str:
    day = today or date.today()
    moment = now or datetime.now()
    return templates.render(
        "district.html",
        title=f"District {district.number}",
        district=district,
        tables=district_tables(district, participation),
        cards=[_meeting_card(meeting, today=day, now=moment) for meeting in meetings],
        built_at=built_at,
        window_end=window_end,
    )


#: Roots only: the Bronx deep link nyc.gov publishes is a 404, and three of these hosts
#: return 403 to a non-browser client, so a deep path cannot be verified.
BP_SITES = {
    "Bronx": "https://bronxboropres.nyc.gov/",
    "Brooklyn": "https://www.brooklynbp.nyc.gov/community-boards/",
    "Manhattan": "https://www.manhattanbp.nyc.gov/",
    "Queens": "https://www.queensbp.nyc.gov/",
    "Staten Island": "https://www.statenislandusa.com/",
}

BUDGET_REGISTER_URL = "https://data.cityofnewyork.us/d/vn4m-mk4t"

#: Five, matching the meeting shortlist. One board filed 134, and the register is linked.
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
    """The community board view. No dataset publishes board agendas or a venue, so the
    page states that rather than implying a calendar."""
    return templates.render(
        "board.html",
        title=board.label,
        board=board,
        districts=districts,
        # Every contact field as something to act on: the neighbourhoods as Wikipedia
        # searches, the office on a map, the phone dialable, the address mailable. Owner's
        # decision, 2026-10-31.
        covers=neighbourhood_links(board.neighborhoods, board.borough_name),
        office_href=_maps_href(board.address),
        phone_href=_tel_href(board.phone),
        email_href=_mailto_href(board.email),
        tables=board_tables(districts, budget_requests),
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


#: Cited for its denominator, never fetched: a few dozen land-use notices a year is not
#: a board calendar.
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
