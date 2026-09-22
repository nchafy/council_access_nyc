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
_TAGLINE = "What your City Council is doing, and what you can still do about it."


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


def render_index(districts: list[District], *, built_at: datetime, window_end: date | None) -> str:
    options = "\n".join(
        '    <option value="/district/{n}/">District {n}{hood}</option>'.format(
            n=d.number,
            hood=f" — {esc(_short(d.neighborhoods))}" if d.neighborhoods else "",
        )
        for d in districts
    )
    # The <noscript> list is not a courtesy: it is the whole interface when
    # JavaScript is off, and it is also the keyboard- and screen-reader-friendly
    # path. The <select> is a convenience layered on top of it.
    links = "\n".join(
        '    <li><a href="/district/{n}/">District {n}{hood}</a></li>'.format(
            n=d.number,
            hood=f" — {esc(_short(d.neighborhoods))}" if d.neighborhoods else "",
        )
        for d in districts
    )
    body = f"""<section class="intro">
  <h1>Find your Council district</h1>
  <p>
    Pick your district to see who represents you, the next five Council meetings
    with addresses, and exactly how to be heard — including how long you have
    left to file written testimony.
  </p>
</section>

<section class="picker">
  <h2>Choose a district</h2>
  <form id="district-form" action="/district/" method="get">
    <label for="district-select">Council district</label>
    <select id="district-select" name="district">
      <option value="">Select a district…</option>
{options}
    </select>
    <button type="submit">Go</button>
  </form>
  <p class="hint">
    Not sure which district you are in?
    {_link("https://council.nyc.gov/districts/", "Look it up on council.nyc.gov")}.
  </p>
</section>

<section class="all-districts">
  <h2>All 51 districts</h2>
  <ul class="district-list">
{links}
  </ul>
</section>
"""
    return _layout(title="Find your district", body=body, built_at=built_at, window_end=window_end)


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
    <h3>{esc(board.label)}</h3>
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


def render_not_found(*, built_at: datetime, window_end: date | None) -> str:
    body = """<section class="intro">
  <h1>Page not found</h1>
  <p>There are 51 council districts, numbered 1 to 51.
  <a href="/">Choose one</a>.</p>
</section>
"""
    return _layout(title="Not found", body=body, built_at=built_at, window_end=window_end)
