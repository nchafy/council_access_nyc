"""Per-board readers for the boards that publish a schedule as nyc.gov HTML.

Nine boards publish real dated schedules on their nyc.gov pages and no feed at all. They
share a host, a CMS and nothing else: one writes a month at a time with venues, one a bare
list of dates with the recurrence in prose, one a year list with ordinal suffixes and no
year on the line, one a sectioned list where only the first entry carries a time, one pastes
its year out of Outlook. So there is a function per board, named for it, and the shape each
one reads is written down in its docstring — because the next person to look at this will be
looking because one board changed its page, and they need to know what this code believed.

Owner's instruction, 2026-10-31: separate parsers per board where needed, with the goal of
a source of truth for every board's schedule.

**On taking an hour stated once, in prose.** Two boards here refuse to: Brooklyn CB18
states its hour in a sentence and marks the exceptions by colour, and Queens CB1 states one
at the head of a section whose extent the markup does not delimit. In both, applying the
hour uniformly would put some meetings at the wrong time. Queens CB11 is different and is
read: one flat list titled `Community Board Meetings`, one sentence immediately beneath it
reading `Meetings are held at 7:30 pm`, and no exception mechanism anywhere on the page.
Taking that is reading what the page says; the other two would be inferring what it does
not. The distinction is the presence of an exception the markup cannot express.

Everything here is third-party prose that reaches the page, so every string goes through
`strip_tags` and nothing is inferred that the page does not say. In particular: where a
board states a recurrence in prose rather than listing dates, this does **not** expand it.
A date we did not read is a gap; a date we invented is a wrong answer.
"""

from __future__ import annotations

import html as html_entities
import re
from datetime import date

from ..text import collapse
from .board_meetings import BoardMeeting

__all__ = ["HTML_READERS", "lines_of", "parse_html"]

_MONTHS = {
    name.lower(): number
    for number, name in enumerate(
        (
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ),
        start=1,
    )
}

#: "November 5", "November 5, 2026", "February 24th, 2027". The ordinal suffix is optional
#: because three of these six boards write one and the others do not.
_DATE = re.compile(
    r"\b(" + "|".join(_MONTHS) + r")\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s*(\d{4}))?\b",
    re.I,
)

#: "6:30pm", "6:00 PM", "7:00 p.m.". Minutes are optional: one board writes "6PM".
_TIME = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*([ap])\.?\s*m\.?", re.I)

#: These pages use an en dash in headings and between a date and a time.
_EN_DASH = "\u2013"

#: A bare year on its own line, which is how two of these boards date a list.
_YEAR = re.compile(r"^\s*(20\d\d)\s*$")


def lines_of(markup: str) -> list[str]:
    """Visible lines, with block boundaries kept so a list of dates stays a list.

    `strip_tags` alone collapses a whole table into one line, which loses exactly the
    structure these parsers need.
    """
    body = re.sub(r"<script.*?</script>|<style.*?</style>", " ", markup, flags=re.S | re.I)
    body = re.sub(r"<(br|/p|/li|/td|/tr|/h\d|/div)[^>]*>", "\n", body, flags=re.I)
    body = re.sub(r"<[^>]+>", " ", body)
    out = []
    for raw in html_entities.unescape(body).split("\n"):
        line = collapse(raw)
        if line:
            out.append(line)
    return out


def _time_of(line: str) -> str | None:
    found = _TIME.search(line)
    if not found:
        return None
    hour = int(found.group(1))
    if not 1 <= hour <= 12:
        return None
    minute = found.group(2) or "00"
    meridiem = found.group(3).upper()
    return f"{hour}:{minute} {meridiem}M"


def _date_of(line: str, *, default_year: int | None) -> date | None:
    found = _DATE.search(line)
    if not found:
        return None
    year = int(found.group(3)) if found.group(3) else default_year
    if year is None:
        return None
    try:
        return date(year, _MONTHS[found.group(1).lower()], int(found.group(2)))
    except ValueError:
        return None


def _meeting(day: date, title: str, start_time: str | None, location: str | None):
    return BoardMeeting(
        day=day,
        start_time=start_time,
        title=collapse(title) or "Meeting",
        location=collapse(location) if location else None,
        url=None,
    )


def read_manhattan_cb3(markup: str, *, on_or_after: date) -> list[BoardMeeting]:
    """Manhattan CB3: one month at a time, venue after a double dash.

    `Calendar of Meetings - November 2026` heads the page and is the only place the year
    appears; every entry then reads
    `Thursday, November 5 at 6:30pm -- Community Board 3 Office - 59 East 4th Street`.
    The committee is not named on these lines at all, so the title stays generic rather
    than being guessed from the venue.
    """
    lines = lines_of(markup)
    year = None
    for line in lines:
        heading = re.search(r"Calendar of Meetings.*?(20\d\d)", line, re.I)
        if heading:
            year = int(heading.group(1))
            break

    out = []
    for line in lines:
        if " at " not in line.lower() and "--" not in line:
            continue
        day = _date_of(line, default_year=year)
        if not day or day < on_or_after:
            continue
        location = None
        if "--" in line:
            location = line.split("--", 1)[1]
        out.append(_meeting(day, "Board or committee meeting", _time_of(line), location))
    return out


def read_brooklyn_cb4(markup: str, *, on_or_after: date) -> list[BoardMeeting]:
    """Brooklyn CB4: a year heading, then `December 16th Public Hearing and Regular Meeting`.

    The year is a line of its own above the list and the entries run newest first. No times
    anywhere on the page, so none are reported.
    """
    out = []
    year = None
    for line in lines_of(markup):
        bare = _YEAR.match(line)
        if bare:
            year = int(bare.group(1))
            continue
        day = _date_of(line, default_year=year)
        if not day or day < on_or_after:
            continue
        title = _DATE.sub("", line).strip(" ,-" + _EN_DASH)
        out.append(_meeting(day, title or "Meeting", _time_of(line), None))
    return out


def read_brooklyn_cb15(markup: str, *, on_or_after: date) -> list[BoardMeeting]:
    """Brooklyn CB15: a date line, then the entry's details on the lines after it.

    `Tuesday, November 17, 2026` is followed by
    `General Board Meeting (In Person)`, `7:00pm`, then the venue over several lines. The
    details therefore belong to whichever date line came last, which is why this one
    cannot be a line-at-a-time match like the others.
    """
    out = []
    pending: tuple[date, list[str]] | None = None

    def flush(entry):
        if not entry:
            return
        day, detail = entry
        joined = " ".join(detail)
        # The first detail line is the title, but on some entries the time runs on from it,
        # so it is cut at the time rather than kept whole.
        title = _TIME.split(detail[0], maxsplit=1)[0] if detail else "Meeting"
        start_time = _time_of(joined)
        # The venue is whatever follows the time, which is how the page is laid out.
        location = None
        if start_time:
            after = _TIME.split(joined, maxsplit=1)
            if len(after) > 3:
                location = after[-1]
        out.append(_meeting(day, title, start_time, location))

    for line in lines_of(markup):
        day = _date_of(line, default_year=None)
        if day and re.match(r"^(Mon|Tues|Wednes|Thurs|Fri|Satur|Sun)day,", line):
            flush(pending)
            pending = (day, []) if day >= on_or_after else None
            continue
        if pending:
            pending[1].append(line)
    flush(pending)
    return out


def read_brooklyn_cb18(markup: str, *, on_or_after: date) -> list[BoardMeeting]:
    """Brooklyn CB18: a bare list of dates, one per line, with the time only in prose.

    The page says the board meets the third Wednesday "unless otherwise specified in red",
    and the exceptions are in the list. The prose time is not attached to the entries,
    because a colour is not something this can read.
    """
    out = []
    for line in lines_of(markup):
        day = _date_of(line, default_year=None)
        if not day or day < on_or_after:
            continue
        # A date and little else: anything longer is prose that happens to carry a date.
        if len(line) > 40:
            continue
        out.append(_meeting(day, "Full board meeting", None, None))
    return out


def read_queens_cb1(markup: str, *, on_or_after: date) -> list[BoardMeeting]:
    """Queens CB1: sections of dates, where only the first entry states the time.

    `Full Board / Public Hearing Meetings` heads a list whose first line is
    `September 22, 2026 - 6:00 PM` and whose rest are bare dates. The section heading is
    the title, and the time carries down the section as the page plainly intends.
    """
    out = []
    section = "Meeting"
    for line in lines_of(markup):
        if re.search(r"meetings?\s*$", line, re.I) and not _DATE.search(line):
            section = line.strip(" :")
            continue
        day = _date_of(line, default_year=None)
        if not day:
            continue
        if day < on_or_after:
            continue
        # Only the time printed on this line. The page states one time at the head of a
        # section and leaves the rest bare, plainly meaning they share it — but the
        # sections are not reliably delimited in the markup, so carrying a time down one
        # risks attaching the full board's hour to a committee's date. An absent time is a
        # gap; a wrong one sends somebody to a room at the wrong hour.
        out.append(_meeting(day, section, _time_of(line), None))
    return out


def read_queens_cb7(markup: str, *, on_or_after: date) -> list[BoardMeeting]:
    """Queens CB7: one sentence naming the next meeting, and the venue beneath it.

    `Our Regular & Public Hearing meeting will be November 16, 2026 at 7:00 p.m.` then
    `Meeting is held at:` and an address. One meeting at a time is all this board
    publishes, so one is all this returns.
    """
    lines = lines_of(markup)
    for index, line in enumerate(lines):
        if not re.search(r"meeting will be", line, re.I):
            continue
        day = _date_of(line, default_year=None)
        if not day or day < on_or_after:
            continue
        location = None
        for follower in lines[index + 1 : index + 5]:
            if re.search(r"held at", follower, re.I):
                tail = follower.split(":", 1)
                location = tail[1] if len(tail) > 1 else None
                if not collapse(location or ""):
                    nxt = lines[index + 2 : index + 4]
                    location = " ".join(nxt) if nxt else None
                break
        return [_meeting(day, "Regular and public hearing meeting", _time_of(line), location)]
    return []


#: Brooklyn CB13 heads its block `Upcoming Brooklyn Community Board 13 Meetings for 2026
#: Calendar`. That heading is the only place the year appears.
_CB13_YEAR = re.compile(r"Meetings\s+for\s+(20\d\d)", re.I)

#: A venue in parentheses at the end of a line, which is how Brooklyn CB13 writes one.
_PARENTHESISED = re.compile(r"\(([^)]{6,})\)\s*$")


def read_brooklyn_cb13(markup: str, *, on_or_after: date) -> list[BoardMeeting]:
    """Brooklyn CB13: a centred block on the **home page**, pasted out of Outlook.

    `Wednesday, September 23, @ 7 PM (2601 Ocean Pkwy-South Brooklyn Hospital, 2nd floor
    Auditorium)`, under a heading that is the only place the year appears. The rows carry
    `data-olk-copy-source="MessageBody"`, which is the giveaway that somebody pasted them
    from an email — so the markup around them is not a structure to rely on, and this reads
    the lines instead.

    The page says the dates are tentative. That is the board's caveat to make, not a reason
    to withhold them, and `docs/board-pdf-shapes.md` records it.
    """
    lines = lines_of(markup)
    year = None
    for line in lines:
        heading = _CB13_YEAR.search(line)
        if heading:
            year = int(heading.group(1))
            break

    out = []
    for line in lines:
        # Every row begins with the weekday. Without that anchor, a sentence further down
        # the home page that happens to name a month becomes a meeting.
        if not re.match(r"^(Mon|Tues|Wednes|Thurs|Fri|Satur|Sun)day,", line):
            continue
        day = _date_of(line, default_year=year)
        if not day or day < on_or_after:
            continue
        venue = _PARENTHESISED.search(line)
        where = venue.group(1) if venue else None
        out.append(_meeting(day, "General board meeting", _time_of(line), where))
    return out


#: Queens CB11's standing note, immediately below its one list of dates.
_CB11_HOUR = re.compile(r"Meetings\s+are\s+held\s+at\s+(\d{1,2}(?::\d{2})?\s*[ap]\.?\s*m\.?)", re.I)


def read_queens_cb11(markup: str, *, on_or_after: date) -> list[BoardMeeting]:
    """Queens CB11: a flat `<ul>` of full dates, with the hour in one sentence beneath it.

    `May 4, 2026` … `December 7, 2026`, then `**Meetings are held at 7:30 pm`. The year is
    on every row, and the hour governs the whole list — see the module docstring for why
    this board's prose hour is taken where Brooklyn CB18's and Queens CB1's are not.

    This board also publishes 79 agenda PDFs carrying `DATE:`/`TIME:`/`PLACE:`. The HTML is
    read instead because it lists the whole year, where an agenda exists only once a
    meeting is imminent.
    """
    lines = lines_of(markup)
    stated = next((found for found in map(_CB11_HOUR.search, lines) if found), None)
    hour = _time_of(stated.group(1)) if stated else None

    out = []
    for line in lines:
        day = _date_of(line, default_year=None)
        if not day or day < on_or_after:
            continue
        # A row here is a date and nothing else. Longer lines are the page's own prose
        # about registering to speak, which also names dates.
        if len(line) > 24:
            continue
        out.append(_meeting(day, "Community board meeting", hour, None))
    return out


#: Queens CB14 labels each agenda link with its full date: `Monthly Board Meeting Agenda,
#: November 10, 2026`. The label before the comma is the committee.
_CB14_AGENDA = re.compile(
    r"^(.*?Agenda),\s*(" + "|".join(_MONTHS) + r")\s+(\d{1,2}),\s*(20\d\d)", re.I
)


def read_queens_cb14(markup: str, *, on_or_after: date) -> list[BoardMeeting]:
    """Queens CB14: a year's full-board dates, plus one dated label per agenda link.

    Two lists on one page. `May 12th, 2026<br />June 9th, 2026` under
    `Full Board / Public Hearing Meetings` gives the year's board meetings with ordinal
    suffixes; below it, every agenda link is labelled with its own full date and the
    committee, which is where the committee meetings come from.

    **No time and no venue are reported.** The page names two alternating locations in
    prose — Knights of Columbus or the Bayswater Jewish Center — and tells the reader to
    check the agenda for which; the agendas are scanned images. So the venue is genuinely
    not readable here, and the prose hour covers only the monthly board meetings and not
    the committees, which share the page. Dates alone are what this document supports.
    """
    lines = lines_of(markup)
    labelled: dict[date, list[str]] = {}
    listed: list[date] = []

    for line in lines:
        found = _CB14_AGENDA.match(line)
        if found:
            try:
                month = _MONTHS[found.group(2).lower()]
                day = date(int(found.group(4)), month, int(found.group(3)))
            except ValueError:
                continue
            title = collapse(re.sub(r"\s*Agenda$", "", found.group(1))) or "Meeting"
            if title not in labelled.setdefault(day, []):
                labelled[day].append(title)
            continue
        day = _date_of(line, default_year=None)
        # A bare dated line is one of the year's board meetings. Anything longer is the
        # page explaining its two venues.
        if day and len(line) <= 24 and day not in listed:
            listed.append(day)

    out = []
    for day, titles in labelled.items():
        if day >= on_or_after:
            out.extend(_meeting(day, title, None, None) for title in titles)
    for day in listed:
        # The year's list and the agenda labels describe the same board meetings, so a day
        # whose agenda is already posted must not be published twice. The label is the
        # better of the two — it names the committee — so the generic entry yields to it.
        if day < on_or_after or any("board" in title.lower() for title in labelled.get(day, [])):
            continue
        out.append(_meeting(day, "Full board or public hearing", None, None))
    return out


#: Board code to the reader that understands that board's page. One per board, on purpose.
HTML_READERS = {
    "313": read_brooklyn_cb13,
    "411": read_queens_cb11,
    "414": read_queens_cb14,
    "103": read_manhattan_cb3,
    "304": read_brooklyn_cb4,
    "315": read_brooklyn_cb15,
    "318": read_brooklyn_cb18,
    "401": read_queens_cb1,
    "407": read_queens_cb7,
}


def parse_html(code: str, markup: str, *, on_or_after: date) -> list[BoardMeeting]:
    """Read one board's page with that board's reader, or return nothing."""
    reader = HTML_READERS.get(str(code))
    if reader is None:
        return []
    return sorted(reader(markup, on_or_after=on_or_after), key=lambda m: m.day)
