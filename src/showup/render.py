"""The build's output shapes: the payloads a consumer of the artifacts reads.

Nothing here becomes markup. It did until 2026-11-09, when the front end moved to the
`webxp` repository and `render_index`, `templates.py` and the escaping guards around them
went with it. What is left builds the dicts that become `preview.json`,
`board-meetings.json` and `references.json`.

So the whole of docs/phase-1-scope.md §4.1 now rests on the ingest half: upstream text has
its tags stripped by `text.strip_tags` before it reaches any payload below, proved end to
end by `tests/integration/test_build.py::test_hostile_register_text_arrives_stripped`.
There is no render-time escape to forget, because there is no render.
"""

from __future__ import annotations

from datetime import date, datetime

from .deadlines import accommodation_state, written_state
from .model import BoardBudgetRequests, District, DistrictBoard, Meeting
from .sources.participatory_budgeting import PB_PROGRAMME_URL, Participation

__all__ = [
    "board_schedule_payload",
    "preview_payload",
]


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
                # Added 2026-11-08, when the board pages became a webxp program: a reader who
                # wants to write to a board rather than ring it had no address in this file,
                # and the program is the only place that answer lives now.
                "email": b.email,
                # The City suppresses some addresses; the reason travels instead of the
                # address, so the program can say why there is none rather than show a blank.
                "email_suppressed": b.email_suppressed,
                # The board's own site. `website_unlinked` is a bare host the build would not
                # vouch for as a URL, so it is carried as text and the program must not make
                # it a link.
                "website": b.website,
                "website_host": b.website_unlinked,
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


def board_schedule_payload(
    calendars: dict,
    sources: dict,
    *,
    built_at: datetime,
    today: date,
    freshness: dict | None = None,
) -> dict:
    """The published board-schedule artifact, for a backend to fetch rather than re-scrape.

    Owner's instruction, 2026-10-31: a source of truth for every board's schedule. So all
    59 boards appear here, including the ones nothing can be read from — a consumer can
    tell "this board has no meetings scheduled" from "we cannot read this board", which is
    the distinction that matters and the one a list of only the working boards destroys.

    Every entry carries the URL it came from. Nothing is inferred: where a board states a
    recurrence in prose instead of listing dates, there are no dates here.

    `freshness` carries, per board, when its source was last loaded and how far behind
    today the newest date that source asserts is. Both are needed and they answer different
    questions: a source fetched this morning whose newest meeting is eight months old is
    stale, and only the second number shows it, while a board with nothing upcoming but a
    meeting last week is simply between meetings.
    """
    freshness = freshness or {}
    boards = {}
    for code, entry in sorted((sources.get("boards") or {}).items()):
        meetings = calendars.get(code) or []
        # A board may keep its meetings in more than one archive — Queens CB5 lists board
        # notices on one page and committee notices on another. `source_url` stays a
        # string so this published shape does not change type between boards, which a
        # consumer would have to special-case; the rest go in their own list.
        declared = entry.get("url")
        declared = [declared] if isinstance(declared, str) else list(declared or [])
        boards[code] = {
            "label": entry.get("label"),
            "status": entry.get("status"),
            "source_kind": entry.get("kind"),
            "source_url": declared[0] if declared else None,
            "other_source_urls": declared[1:] or None,
            "site": entry.get("site"),
            "note": entry.get("note"),
            "fetched_at": getattr(freshness.get(code), "fetched_at", None),
            "source_latest_entry": (
                latest.isoformat()
                if (latest := getattr(freshness.get(code), "latest_entry", None))
                else None
            ),
            "source_stale_days": getattr(freshness.get(code), "stale_days", None),
            "upcoming": [
                {
                    "date": meeting.day.isoformat(),
                    "start_time": meeting.start_time,
                    "title": meeting.title,
                    "location": meeting.location,
                    "url": meeting.url,
                }
                for meeting in meetings
            ],
        }
    readable = [code for code, board in boards.items() if board["upcoming"]]
    return {
        "generated_at": built_at.isoformat(timespec="seconds"),
        "upcoming_from": today.isoformat(),
        "caveat": sources.get("caveat"),
        "statuses": sources.get("statuses"),
        "coverage": {
            "boards": len(boards),
            "with_a_readable_source": sum(1 for b in boards.values() if b["source_url"]),
            "with_upcoming_meetings": len(readable),
            "upcoming_meetings": sum(len(b["upcoming"]) for b in boards.values()),
            "recurring_entries_expanded": False,
            # A source can be readable and months behind. Counting that is the difference
            # between "we cover 58 boards" and "58 boards are telling us something."
            "sources_current": sum(1 for b in boards.values() if b["source_stale_days"] == 0),
            # The key spells the number out because it is a published name a consumer reads;
            # the threshold itself is `SOURCE_BEHIND_DAYS` so the two cannot disagree.
            f"sources_behind_{SOURCE_BEHIND_DAYS}_days": sum(
                1
                for b in boards.values()
                if (behind := b["source_stale_days"]) is not None and behind > SOURCE_BEHIND_DAYS
            ),
            "sources_asserting_no_date": sum(
                1 for b in boards.values() if b["source_url"] and b["source_latest_entry"] is None
            ),
        },
        "boards": boards,
    }


#: Beyond this, a board's source is reported as behind rather than merely quiet. Three
#: months: long enough that a board publishing one month at a time, or taking the summer
#: recess, is not accused of neglect, and short enough that a site abandoned mid-2025 is.
SOURCE_BEHIND_DAYS = 90


# ---------------------------------------------------------------------------
# The sources artifact.
#
# Every dataset identifier, fetch date, freshness window and caveat. This was the
# `/references/` page until 2026-11-08, and went with it when the static pages were
# deleted — along with the invariant `fetch.Source` still states, that `label`, `dataset`
# and `url` exist "so a source cannot be fetched without being disclosed". It is published
# as data now and rendered by the Readme program, which is what the desktop's own footer
# promises when it says "Open Readme for every source".
# ---------------------------------------------------------------------------

#: Values this site computes rather than reads, and how. Each one is a number a reader could
#: otherwise only take on trust.
DERIVED = (
    (
        "Council district to community board crosswalk",
        "Areal overlap between the shoreline-clipped council district boundaries (872g-cjhh) "
        "and the community district boundaries (5crt-au7u), regenerated when either boundary "
        "file changes. Percentages are rounded to a whole number and approximate; on a board "
        "the denominator is that board, on a district it is that district. The boards dataset "
        "also carries a council_district column, which holds 44 distinct values across 59 "
        "rows and omits 7 council districts — it records the board office's district rather "
        "than the districts a board covers, so it is not used for this join.",
    ),
    (
        "Written-testimony safe-until timestamp",
        "Hearing start plus 72 hours. Adjournment times are not published and adjournment is "
        "at or after the start, so the stamp is a provable lower bound on the real deadline "
        "rather than the deadline.",
    ),
    (
        "Accommodation request-by date",
        "Three business days before the hearing, against a committed holiday table.",
    ),
)

#: Named in the text but never fetched, so no row above covers them.
CITED = (
    (
        "The City Record (dg92-zbpx)",
        "A few dozen land-use hearing notices a year across all 59 community boards. It is "
        "the only City dataset carrying dated board notices, and no City dataset publishes a "
        "dated board calendar.",
    ),
    (
        "Each board's own website",
        "Agendas, minutes and the meeting location are published there and nowhere in the "
        "City's data. A board on its own domain rather than a City one is given as text "
        "rather than a link, because the host cannot be verified at build time.",
    ),
)

#: What the data does not mean. Every one of these qualifies a figure shown elsewhere, which
#: is why they are published rather than kept in the repository.
CAVEATS = (
    "The City publishes no community board meeting calendar, so each of the 59 boards is read "
    "from whatever it publishes itself — a feed, a page, a PDF, a scan. A source can answer "
    "and still be months behind, which is why the Community boards program reports both.",
    "Community board meeting cadence is quoted exactly as ruf7-3wgc records it. That is the "
    "City's record of the cadence, and it has been observed to disagree with what boards "
    "publish on their own sites.",
    "ruf7-3wgc records the board office address, not the meeting venue. Committees often sit "
    "at the office and the full board often does not.",
    "Unlike Council committees, which are called by their chair, a community board meets on a "
    "standing monthly cadence.",
    "Budget requests are an annual filing rather than current activity: the register appears a "
    "few times a year, so an entry can be months old. A board shows the newest edition of the "
    "register (vn4m-mk4t) published on or before the build date, capped at five requests with "
    "the total stated beside it. Priority numbers repeat because each one ranks within a "
    "budget category — capital, capital support, expense.",
    "Agency replies are quoted rather than sorted into yes and no: the phrasing changes "
    "between editions of the same row, and it records a position rather than an outcome. A "
    "request is not a commitment and not a funded outcome.",
    "The Council Members listed against a board can introduce legislation for that area, and "
    "nominate half of the board's members.",
    "Council district geometry ships simplified — 132 KB gzipped against 3.8 MB raw, measured "
    "to assign the same district as full precision on 99.99% of a citywide lattice.",
    "No figure anywhere on this site compares one board or district with another.",
)


def _window(max_age_hours: float) -> str:
    """A freshness window in the unit a reader thinks in. 960 hours is nobody's sentence."""
    hours = float(max_age_hours)
    if hours >= 48 and hours % 24 == 0:
        days = int(hours // 24)
        return f"{days} day{'' if days == 1 else 's'}"
    rounded = int(hours) if hours == int(hours) else hours
    return f"{rounded} hour{'' if rounded == 1 else 's'}"


def references_payload(dataset_rows: list[dict], *, window_end: date | None) -> dict:
    """`/data/references.json`: what the Readme program renders.

    `dataset_rows` comes from the `fetch.py` registry joined to the manifest, so no
    identifier, URL or window is typed here — a source that is fetched is disclosed.
    """
    return {
        "datasets": [
            {
                "label": row["label"],
                "dataset": row["dataset"],
                "url": row["url"],
                "why": row["why"],
                "fetched_at": row["fetched_at"],
                "window": _window(row["max_age_hours"]),
                "rows": row["rows"],
            }
            for row in dataset_rows
        ],
        "derived": [{"term": term, "detail": detail} for term, detail in DERIVED],
        "cited": [{"term": term, "detail": detail} for term, detail in CITED],
        "caveats": list(CAVEATS),
        "calendar_window_end": window_end.isoformat() if window_end else None,
    }


# ---------------------------------------------------------------------------
# The detail artifact.
#
# `preview.json` was built for a map side-panel: `PREVIEW_REQUESTS` caps the budget table at
# five rows of two columns, and a district carries only its member's name and seat status.
# That was the right shape while a page per district and per board carried everything else.
#
# When those pages were deleted the summary silently became the only thing published, so
# every build computed the member's email, offices and term, and every board's budget
# explanations and agency responses, and threw them away. This is the artifact that stops
# that: the facts the pages showed, published whole, for a consumer that renders detail.
# ---------------------------------------------------------------------------


def _office(office) -> dict:
    return {
        "label": office.label,
        "address": office.address,
        "phone": office.phone,
        "fax": office.fax,
        "hours": office.hours,
    }


def _member_detail(member) -> dict | None:
    """Everything the district page showed about the member, or None for a vacant seat."""
    if member is None:
        return None
    return {
        "name": member.name,
        "seat_status": member.seat_status,
        "email": member.email,
        "page_url": member.page_url,
        "offices": [_office(office) for office in member.offices],
        "term_start": member.term_start.isoformat() if member.term_start else None,
        "term_end": member.term_end.isoformat() if member.term_end else None,
        # Disclosed rather than resolved: council.nyc.gov names a member the open dataset has
        # no current term for, and the reader is told the two sources disagree.
        "seat_conflict": member.seat_conflict,
    }


def _request_detail(request) -> dict:
    """One budget line in the board's words and the agency's.

    The pair is the point. `preview.json` publishes the request and its category; what it
    drops is the board's own explanation of why it asked, and what the agency said back.
    Quoted, never sorted into yes and no: the phrasing changes between editions of the same
    row, and it records a position rather than an outcome.
    """
    return {
        "priority": request.priority,
        "category": request.category,
        "tracking_code": request.tracking_code,
        "request": request.request,
        "agency": request.agency,
        "explanation": request.explanation,
        "response": request.response,
    }


def detail_payload(districts, boards, budget_requests) -> dict:
    """`/data/detail.json`: what the deleted pages showed and `preview.json` does not.

    Keyed the same way as `preview.json` — districts by number, boards by `boro_cd` — so a
    consumer can read one against the other without a join table.
    """
    return {
        "districts": {
            str(district.number): {
                "member": _member_detail(district.member),
                # Per field, where the fact came from and when it was seen. The district page
                # carried this inline; it is the only record of which source answered.
                "provenance": dict(district.provenance),
                "missing": list(district.missing),
            }
            for district in districts
        },
        "boards": {
            str(board.code): {
                "budget": (
                    {
                        "publication": entry.publication.isoformat(),
                        "fiscal_year": entry.fiscal_year,
                        "requests": [_request_detail(request) for request in entry.requests],
                    }
                    if (entry := budget_requests.get(str(board.code))) is not None
                    else None
                ),
            }
            for board in boards
        },
    }
