"""HTML generation.

The only place in the project where text becomes markup, which makes it the last
line of the XSS defence described in docs/phase-1-scope.md §4.1. Two rules:

1. **Every interpolated value goes through `esc`.** There is no "this one is
   safe" exception. Values arriving here have already been stripped of markup at
   ingest, so escaping is belt-and-braces — and belt-and-braces is the correct
   posture for a defence whose failure is someone else's browser running someone
   else's script.
2. **Links are only emitted for URLs that survived `urls.safe_url`.** A None URL
   renders as plain text, never as a dead or unchecked `href`.

Templates are f-strings rather than a template engine, because a dependency-free
build is a smaller attack surface and the page count here is two. The cost is
vigilance at each `{}`; the `esc()` calls are therefore never factored out into
something clever.
"""

from __future__ import annotations

from datetime import date, datetime

from .deadlines import accommodation_state, written_state
from .model import District, DistrictBoard, Meeting
from .text import esc

__all__ = ["render_district", "render_index", "render_not_found"]

_DOC_TITLE = "Show Up NYC"
#: Covers both views — a board page is not about the Council.
_TAGLINE = "What your city government is doing, and what you can still do about it."


def _layout(*, title: str, body: str, built_at: datetime, window_end: date | None) -> str:
    """The shared shell. No inline script and no inline style — the CSP in
    `_headers` forbids both, so everything is an external first-party file."""
    window = (
        f"We can see meetings scheduled through {esc(window_end.strftime('%-d %B %Y'))}."
        if window_end
        else "No forward window could be determined from the calendar."
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)} — {esc(_DOC_TITLE)}</title>
<meta name="description" content="{esc(_TAGLINE)}">
<meta name="referrer" content="no-referrer">
<link rel="stylesheet" href="/assets/site.css">
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
<header class="site">
  <p class="wordmark"><a href="/">{esc(_DOC_TITLE)}</a></p>
  <p class="tagline">{esc(_TAGLINE)}</p>
</header>
<main id="main">
{body}
</main>
<footer class="site">
  <p class="freshness" data-built-at="{esc(built_at.isoformat(timespec="seconds"))}">
    Data fetched {esc(built_at.strftime("%-d %B %Y, %H:%M"))}. {window}
  </p>
  <p class="caveat">
    Hearings are deferred or moved without notice.
    <strong>Confirm on Legistar before you travel.</strong>
  </p>
  <p class="caveat">
    Nothing here measures public opinion. No City source records who attended a
    hearing, who testified, or which side they took.
  </p>
</footer>
<script src="/assets/site.js" defer></script>
</body>
</html>
"""


def _link(url: str | None, label: str, *, extra: str = "") -> str:
    """An anchor for a checked URL, or inert text when there is none."""
    if not url:
        return f'<span class="nolink">{esc(label)}</span>'
    rel = 'rel="noopener noreferrer"' if url.startswith("http") else ""
    return f'<a href="{esc(url)}" {rel} {extra}>{esc(label)}</a>'


def _dl(rows: list[tuple[str, str]]) -> str:
    if not rows:
        return ""
    items = "\n".join(f"  <dt>{esc(key)}</dt>\n  <dd>{value}</dd>" for key, value in rows if value)
    return f"<dl>\n{items}\n</dl>"


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

    A council district tells you who legislates for you and which hearings you can
    testify at. A community board tells you who reviews the zoning on your block
    and will seat you on a committee. Residents routinely want the second and go
    looking for the first, so both are offered side by side and the difference is
    stated rather than assumed.
    """
    district_options = "\n".join(
        '    <option value="/district/{n}/">District {n}{hood}</option>'.format(
            n=d.number,
            hood=f" — {esc(_short(d.neighborhoods))}" if d.neighborhoods else "",
        )
        for d in districts
    )
    board_options = "\n".join(
        '    <option value="/board/{code}/">{label}{hood}</option>'.format(
            code=esc(b.code),
            label=esc(b.label),
            hood=f" — {esc(_short(b.neighborhoods, 44))}" if b.neighborhoods else "",
        )
        for b in boards
    )
    # The <noscript> lists are not a courtesy: they are the whole interface when
    # JavaScript is off, and the keyboard and screen-reader path either way.
    district_links = "\n".join(
        '    <li><a href="/district/{n}/">District {n}{hood}</a></li>'.format(
            n=d.number,
            hood=f" — {esc(_short(d.neighborhoods))}" if d.neighborhoods else "",
        )
        for d in districts
    )
    board_links = "\n".join(
        '    <li><a href="/board/{code}/">{label}{hood}</a></li>'.format(
            code=esc(b.code),
            label=esc(b.label),
            hood=f" — {esc(_short(b.neighborhoods, 44))}" if b.neighborhoods else "",
        )
        for b in boards
    )

    body = f"""<section class="intro">
  <h1>Find out what your city government is doing</h1>
  <p>
    Two views, because they answer different questions. Pick whichever matches what
    you are trying to do.
  </p>
</section>

<section class="picker">
  <h2>City Council district</h2>
  <p class="why">
    Who legislates for you, the next five Council meetings with addresses, and how
    to testify — including how long you have left to file in writing.
    <strong>51 districts.</strong>
  </p>
  <form id="district-form" action="/district/" method="get">
    <label for="district-select">Council district</label>
    <select id="district-select" name="district">
      <option value="">Select a council district…</option>
{district_options}
    </select>
    <button type="submit">Go</button>
  </form>
</section>

<section class="picker">
  <h2>Community board</h2>
  <p class="why">
    The most local unit of City government: it reviews zoning on your block, sets
    local budget priorities, meets on a standing monthly cadence, and
    <strong>will seat a member of the public on its committees</strong>.
    <strong>59 boards.</strong>
  </p>
  <form id="board-form" action="/board/" method="get">
    <label for="board-select">Community board</label>
    <select id="board-select" name="board">
      <option value="">Select a community board…</option>
{board_options}
    </select>
    <button type="submit">Go</button>
  </form>
  <p class="hint">
    Not sure which is which, or which one you are in?
    {_link("https://council.nyc.gov/districts/", "Council district lookup")} ·
    {_link("https://communityprofiles.planning.nyc.gov/", "Community district profiles")}.
  </p>
</section>

<section class="all-districts">
  <h2>All 51 council districts</h2>
  <ul class="district-list">
{district_links}
  </ul>
</section>

<section class="all-districts">
  <h2>All 59 community boards</h2>
  <ul class="district-list">
{board_links}
  </ul>
</section>
"""
    return _layout(
        title="Find your district or board", body=body, built_at=built_at, window_end=window_end
    )


def _short(value: str | None, limit: int = 58) -> str:
    if not value:
        return ""
    text = value.strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip(" ,;") + "…"


# --------------------------------------------------------------------------- #
# District page
# --------------------------------------------------------------------------- #


def _member_block(district: District) -> str:
    member = district.member
    if member is None or member.seat_status == "vacant":
        return """<section class="member vacant">
  <h2>Your Council Member</h2>
  <p class="designed-state">
    <strong>This seat is currently vacant.</strong> Until it is filled, the
    committee and hearing information below still applies, and you can testify at
    any hearing regardless of which district you live in.
  </p>
</section>
"""
    rows: list[tuple[str, str]] = []
    if member.email:
        rows.append(("Email", esc(member.email)))
    for office in member.offices:
        parts = [esc(office.address or "")]
        if office.phone:
            parts.append(f"Phone: {esc(office.phone)}")
        if office.hours:
            parts.append(f"Hours: {esc(office.hours)}")
        rows.append((office.label, "<br>".join(p for p in parts if p)))
    if member.page_url:
        rows.append(("Official page", _link(member.page_url, "council.nyc.gov")))

    conflict = (
        '<p class="gap">The City\'s own member dataset has no current term on '
        "record for this seat yet, which happens after a special election. The "
        "name above comes from council.nyc.gov, which updates sooner.</p>"
        if member.seat_conflict
        else ""
    )
    return f"""<section class="member">
  <h2>Your Council Member</h2>
  <p class="member-name">{esc(member.name)}</p>
{conflict}
{_dl(rows)}
</section>
"""


def _committees_block(district: District) -> str:
    member = district.member
    if member is None or not member.committees:
        return """<section class="committees">
  <h2>Committees</h2>
  <p class="designed-state">No committee assignments are published on this
  district's page. Check the
  <a href="https://council.nyc.gov/committees/" rel="noopener noreferrer">Council
  committees list</a>.</p>
</section>
"""
    items = "\n".join(
        "    <li>{name}{role}</li>".format(
            name=esc(c.name),
            role=f' <span class="role">({esc(c.role)})</span>'
            if c.role and c.role != "Member"
            else "",
        )
        for c in member.committees
    )
    return f"""<section class="committees">
  <h2>Committees your member sits on</h2>
  <p class="why">
    These are the rooms where your representative has a seat — the hearings where
    someone accountable to you is on the dais.
  </p>
  <ul class="committee-list">
{items}
  </ul>
</section>
"""


_MODE_LABEL = {
    "in_person": "In person",
    "hybrid": "Hybrid — in person or remote",
    "remote": "Remote only",
}
_TIME_STATE_LABEL = {
    "deferred": "Postponed — no new date published",
    "time_not_published": "Time not published",
}


def _meeting_card(meeting: Meeting, *, today: date, now: datetime) -> str:
    when = meeting.date.strftime("%A %-d %B %Y")
    time_line = (
        esc(meeting.start_time)
        if meeting.time_state == "scheduled"
        else f"<em>{esc(_TIME_STATE_LABEL[meeting.time_state])}</em>"
    )

    rows: list[tuple[str, str]] = [
        ("When", f"{esc(when)} · {time_line}"),
        ("Format", esc(_MODE_LABEL.get(meeting.attendance_mode, meeting.attendance_mode))),
        (
            "Where",
            esc(meeting.venue.name)
            + (f"<br>{esc(meeting.venue.address)}" if meeting.venue.address else ""),
        ),
    ]
    if meeting.topic:
        rows.append(("Topic", esc(meeting.topic)))
    else:
        rows.append(("Topic", "<em>Agenda not yet published.</em>"))

    if meeting.venue.entry:
        rows.append(("Getting in", esc(meeting.venue.entry)))

    # The two computed deadlines. Both state their basis, because a deadline the
    # reader cannot check is a deadline they have to take on faith.
    if meeting.written_safe_until:
        state = written_state(meeting.written_safe_until, now)
        label = {
            "open": "Written testimony",
            "closing": "Written testimony — closing soon",
            "closed": "Written testimony — window has passed",
        }[state]
        stamp = meeting.written_safe_until.strftime("%-d %B, %H:%M")
        rows.append(
            (
                label,
                f'<span class="deadline {esc(state)}">Safe to file until {esc(stamp)}</span>'
                "<br><small>The real deadline is 72 hours after the hearing is "
                "adjourned, which the Council does not publish. Filing before the "
                "time shown is certainly inside the window.</small>",
            )
        )
    if meeting.accommodation_by:
        acc = accommodation_state(meeting.date, today)
        stamp = meeting.accommodation_by.strftime("%-d %B")
        note = (
            f"Request by {esc(stamp)}"
            if acc == "open"
            else f"<em>Deadline passed ({esc(stamp)}) — ask anyway</em>"
        )
        rows.append(
            (
                "ASL, CART or interpretation",
                f"{note}<br><small>EEOOfficer@council.nyc.gov · 212-788-6936 · "
                "translationservice@council.nyc.gov</small>",
            )
        )

    links = " · ".join(
        filter(
            None,
            [
                _link(meeting.detail_url, "Meeting details") if meeting.detail_url else "",
                _link(meeting.agenda_url, "Agenda (PDF)") if meeting.agenda_url else "",
                _link(meeting.minutes_url, "Minutes (PDF)") if meeting.minutes_url else "",
            ],
        )
    )

    return f"""  <article class="meeting">
    <h3>{esc(meeting.committee)}</h3>
{_dl(rows)}
    <p class="links">{links}</p>
  </article>
"""


def _meetings_block(meetings: list[Meeting], *, today: date, now: datetime) -> str:
    if not meetings:
        return """<section class="meetings">
  <h2>The next Council meetings</h2>
  <p class="designed-state">
    No upcoming meetings appear on the Legistar calendar right now. That can mean
    a recess or a quiet period, not necessarily a problem. Check
    <a href="https://nyc.legistar.com/Calendar.aspx" rel="noopener noreferrer">the
    Council calendar</a> directly.
  </p>
</section>
"""
    cards = "\n".join(_meeting_card(m, today=today, now=now) for m in meetings)
    return f"""<section class="meetings">
  <h2>The next {len(meetings)} Council meetings</h2>
  <p class="why">
    Listed in date order — not ranked. Committee hearings are citywide and open to
    anyone, whichever district you live in.
  </p>
{cards}
</section>
"""


_HOW_TO_BE_HEARD = """<section class="participate">
  <h2>How to be heard</h2>
  <p class="lead-truth">
    <strong>Only Council Members can introduce legislation.</strong> There is no
    public petition route onto the agenda, so the levers below are testimony and
    your member.
  </p>
  <h3>Speak at a hearing</h3>
  <ul>
    <li><strong>In person: no pre-registration.</strong> Turn up and sign up at the hearing.</li>
    <li>Remotely, by Zoom web or phone: register in advance on the
      <a href="https://council.nyc.gov/testify/" rel="noopener noreferrer">Register to
      Testify</a> form.</li>
    <li>For Zoning and Franchises, or Landmarks, Public Sitings and Dispositions, use the
      <a href="https://council.nyc.gov/land-use/" rel="noopener noreferrer">Land Use page</a>
      instead.</li>
  </ul>
  <h3>File written testimony</h3>
  <ul>
    <li>Accepted <strong>up to 72 hours after the hearing is adjourned</strong> — so you can
      still act after a hearing you missed.</li>
    <li>DOC, DOCX or PDF, maximum 10&nbsp;MB, through the same form.</li>
    <li>Pre-recorded testimony is not played. Audio or video links need a transcript too.</li>
    <li>Whatever you submit becomes part of the <strong>permanent public record</strong>.</li>
  </ul>
  <h3>Two things nobody publishes</h3>
  <p class="refusal">
    The Council does not publish a <strong>registration cut-off time</strong> before a hearing,
    or a <strong>per-speaker time limit</strong>. We will not guess at either. Chairs usually
    announce a limit at the start. To confirm for a specific hearing, ask the hearings office:
    <strong>hearings@council.nyc.gov</strong> or <strong>212-482-4219</strong>.
  </p>
  <h3>What happens after you testify</h3>
  <p>
    The committee may amend the bill, then votes. If it passes by majority it goes to the full
    Council, then to the Mayor, who has 30 days to sign it, veto it, or do nothing — in which
    case it becomes law anyway. The Council can override a veto with a two-thirds vote.
  </p>
</section>
"""


def _board_card(board: DistrictBoard) -> str:
    rows: list[tuple[str, str]] = []
    if board.neighborhoods:
        rows.append(("Covers", esc(board.neighborhoods)))
    if board.address:
        rows.append(("Office", esc(board.address)))
    if board.phone:
        rows.append(("Phone", esc(board.phone)))
    if board.email:
        rows.append(("Email", esc(board.email)))
    elif board.email_suppressed:
        # Say why there is no email rather than leaving a blank the reader has to
        # interpret. "The published address names an individual" is a deliberate
        # suppression, not missing data.
        rows.append(("Email", f"<em>Not shown — {esc(board.email_suppressed)}.</em>"))
    if board.website:
        rows.append(("Website", _link(board.website, board.website.replace("https://", ""))))
    if board.board_meeting:
        rows.append(
            (
                "Full board meets",
                f"{esc(board.board_meeting)}<br><small>The board's own published "
                "wording. Confirm on their site — boards move meetings.</small>",
            )
        )
    if board.cabinet_meeting:
        rows.append(("Cabinet meets", esc(board.cabinet_meeting)))

    share = f"{round(board.share * 100)}%" if board.share else None
    extent = (
        f'<span class="share">about {esc(share)} of this council district</span>' if share else ""
    )
    return f"""  <article class="board">
    <h3><a href="/board/{esc(board.code)}/">{esc(board.label)}</a></h3>
    {extent}
{_dl(rows)}
  </article>
"""


def _boards_block(district: District) -> str:
    if not district.boards:
        return """<section class="boards">
  <h2>Your community board</h2>
  <p class="designed-state">
    We could not match a community board to this district. Find yours through
    <a href="https://www.nyc.gov/site/cau/community-boards/community-boards.page"
       rel="noopener noreferrer">the Mayor's Community Affairs Unit</a>.
  </p>
</section>
"""
    plural = "boards" if len(district.boards) > 1 else "board"
    intro = (
        f"This council district overlaps {len(district.boards)} community "
        f"{plural}. They are listed by how much of the district each covers."
        if len(district.boards) > 1
        else "This council district falls almost entirely inside one community board."
    )
    cards = "\n".join(_board_card(board) for board in district.boards)
    return f"""<section class="boards">
  <h2>Your community {plural}</h2>
  <p class="why">
    {esc(intro)} A community board meets on a <strong>predictable monthly
    cadence</strong>, unlike Council committees, and for a land-use, construction,
    liquor-licence or quality-of-life question it is usually the right room to
    start in.
  </p>
{cards}
  <p class="hint">
    Board members are volunteers appointed by the Borough President. We list the
    board <em>office</em>, which is staffed and whose job is to hear from you — not
    individual members.
  </p>
</section>
"""


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
    hood = (
        f'<p class="neighborhoods">{esc(district.neighborhoods)}</p>'
        if district.neighborhoods
        else ""
    )
    missing = (
        '<p class="gap">Some details are not published on this district\'s page: '
        + esc(", ".join(district.missing))
        + ".</p>"
        if district.missing
        else ""
    )

    body = f"""<section class="where">
  <h1>Council District {esc(district.number)}</h1>
{hood}
  <p class="distinction">
    Your <strong>council district</strong> elects the member below. Your
    <strong>community board</strong> is a different, smaller body that handles many
    local land-use and quality-of-life questions — often the right place to start.
    Both are below.
  </p>
{missing}
</section>

{_member_block(district)}
{_committees_block(district)}
{_meetings_block(meetings, today=day, now=moment)}
{_boards_block(district)}
{_HOW_TO_BE_HEARD}
<p class="back"><a href="/">Choose a different district</a></p>
"""
    return _layout(
        title=f"District {district.number}", body=body, built_at=built_at, window_end=window_end
    )


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

#: Every claim here was read off nyc.gov/site/communityboards on 2026-09-22.
#: The things those pages do NOT state — term length, any minimum age, meeting
#: frequency requirements, and whether the public may speak at a full board
#: meeting — are rendered as refusals further down rather than guessed at.
_BOARD_INVOLVEMENT_TEMPLATE = """<section class="participate">
  <h2>How to get involved with this board</h2>
  <p class="lead-truth">
    The route most people do not know about: <strong>board committees admit
    non-board members of the public.</strong> You can join the discussion and make
    recommendations without being appointed to anything — you just cannot vote.
  </p>

  <h3>Join a committee as a public member</h3>
  <ul>
    <li>Committees are "composed of Board members, and non-Board (public) members".</li>
    <li>As a public member you take part in discussion and offer recommendations, but are
      "not allowed to vote".</li>
    <li>Most boards ask for an application and a current resume — contact the board office
      above.</li>
    <li>Committees are open to the public and, under the New York State Open Meetings Law,
      must keep full and accurate minutes.</li>
  </ul>

  <h3>Apply to be a board member</h3>
  <ul>
    <li>Each board has <strong>up to 50 unsalaried members</strong>, and <strong>half are
      nominated by the City Council members</strong> whose districts cover it — which is why
      the council districts listed above matter.</li>
    <li>Members are appointed by the <strong>Borough President</strong>, whose office processes
      applications at various times of the year.</li>
    <li>You must "reside, work, or have some other significant interest in the community".</li>
    <li>Apply through the {borough} Borough President: {bp_link}</li>
  </ul>

  <h3>What this board can and cannot do</h3>
  <ul>
    <li>Zoning: "Applications for a change in or variance from the zoning resolution must come
      before the board for review." Boards must also be consulted on the siting of most
      municipal facilities.</li>
    <li>Budget: boards assess local needs and meet with City agencies to make recommendations
      in the City's budget process.</li>
    <li>The limit, stated plainly by the City: boards "do not have the ability to order any City
      agency or official to perform any task". They advise, and are often persuasive.</li>
    <li>Boards are "autonomous City agencies and members are City officers" — not a
      neighbourhood association.</li>
  </ul>

  <h3>Things the City does not publish</h3>
  <p class="refusal">
    We could not find an official source for how long a board term lasts, any minimum age to
    serve, how often the full board must meet, or whether and how the public may speak at a
    full board meeting. Those vary by board and we will not guess. Ask the board office
    directly — its phone and email are above.
  </p>
</section>
"""


def _board_involvement(borough: str) -> str:
    url = BP_SITES.get(borough)
    bp_link = (
        _link(url, url.replace("https://", "").rstrip("/"))
        if url
        else '<span class="nolink">see nyc.gov/communityboards</span>'
    )
    return _BOARD_INVOLVEMENT_TEMPLATE.format(borough=esc(borough), bp_link=bp_link)


def render_board(
    board: DistrictBoard,
    districts: list[tuple[int, float]],
    *,
    built_at: datetime,
    window_end: date | None,
) -> str:
    """The community board view.

    Deliberately not a copy of the district page. A board's value to a resident is
    different: it meets on a predictable cadence, it reviews zoning in its own
    area, and it will seat a member of the public on a committee. It has no
    hearing calendar we can read — no dataset publishes board agendas — so this
    page does not pretend to one and sends the reader to the board's own site.
    """
    rows: list[tuple[str, str]] = []
    if board.neighborhoods:
        rows.append(("Covers", esc(board.neighborhoods)))
    if board.address:
        rows.append(("Office", esc(board.address)))
    if board.phone:
        rows.append(("Phone", esc(board.phone)))
    if board.email:
        rows.append(("Email", esc(board.email)))
    elif board.email_suppressed:
        rows.append(("Email", f"<em>Not shown — {esc(board.email_suppressed)}.</em>"))
    if board.website:
        rows.append(
            (
                "Website",
                _link(board.website, board.website.replace("https://", "").rstrip("/"))
                + "<br><small>The board's own site is the only place its agendas and "
                "minutes are published — no City dataset carries them.</small>",
            )
        )

    meetings: list[tuple[str, str]] = []
    if board.board_meeting:
        meetings.append(("Full board meets", esc(board.board_meeting)))
    if board.cabinet_meeting:
        meetings.append(("Cabinet meets", esc(board.cabinet_meeting)))

    meetings_block = (
        f"""<section class="meetings">
  <h2>When it meets</h2>
  <p class="why">
    Quoted exactly as the board publishes it. Unlike Council committees, which are
    called by their chair, a community board meets on a standing monthly cadence —
    which makes it the easier of the two to plan around.
  </p>
{_dl(meetings)}
  <p class="refusal">
    We do not have this board's calendar. No City dataset publishes community board
    agendas or meeting dates, so the cadence above is a pattern, not a confirmed
    date. <strong>Confirm with the board before you travel.</strong>
  </p>
</section>
"""
        if meetings
        else """<section class="meetings">
  <h2>When it meets</h2>
  <p class="designed-state">
    This board does not publish a meeting cadence in the City's dataset. Contact the
    office or check its website.
  </p>
</section>
"""
    )

    district_items = "\n".join(
        f'    <li><a href="/district/{number}/">Council District {number}</a>'
        f' <span class="share">{round(share * 100)}% of this board</span></li>'
        for number, share in districts
    )
    districts_block = f"""<section class="committees">
  <h2>Council districts covering this board</h2>
  <p class="why">
    These are the Council Members who can introduce legislation for this area — and
    who nominate half of this board's members. Percentages are the share of
    <em>this board</em> that sits in each district, computed from the City's
    boundary files and approximate.
  </p>
  <ul class="district-list">
{district_items}
  </ul>
</section>
"""

    body = f"""<section class="where">
  <h1>{esc(board.label)}</h1>
  <p class="distinction">
    A <strong>community board</strong> is the most local unit of City government. It
    advises on zoning, budget priorities and local services for one community
    district. It is <em>not</em> the same thing as a council district — the Council
    Members for this area are listed below.
  </p>
{_dl(rows)}
</section>

{meetings_block}
{districts_block}
{_board_involvement(board.borough_name)}
<p class="back"><a href="/">Find another board or district</a></p>
"""
    return _layout(title=board.label, body=body, built_at=built_at, window_end=window_end)


def render_not_found(*, built_at: datetime, window_end: date | None) -> str:
    body = """<section class="intro">
  <h1>Page not found</h1>
  <p>There are 51 council districts, numbered 1 to 51.
  <a href="/">Choose one</a>.</p>
</section>
"""
    return _layout(title="Not found", body=body, built_at=built_at, window_end=window_end)
