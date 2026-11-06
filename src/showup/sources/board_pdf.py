"""Per-board readers for the boards that publish a schedule as a PDF.

Twenty-one boards publish no feed and no dated HTML — they post a PDF. Owner's instruction,
2026-10-31: separate parsers per board where needed, with the goal of a source of truth for
every board's schedule. Every shape here was measured against the board's live document, 15
of them on 2026-10-31 and 6 more on 2026-11-02 while closing the gap on the boards that had
no readable source at all; `docs/board-sources.md` records what each looked like and
where.

Three shapes, and a configuration per board rather than one parser pretending to cover all:
a `GridBoard` is a Sunday-to-Saturday month grid, a `ListBoard` is a plain run of dates, and
an `AgendaBoard` is a notice per meeting on labelled lines.

Two things about these documents drive the whole design.

**A grid encodes the day in horizontal position, not in text.** "Municipal Services /
6:30 pm / The Bedford Community Room" says nothing about which day it is; the fact that it
sits under the column headed by `14` does. So these readers work on column offsets.

**Neither pypdf extraction mode is sufficient alone**, measured on Bronx CB7's October 2026
grid and written up in `docs/dependencies.md`:

- `extraction_mode="layout"` preserves the columns, and silently drops heading and footer
  text blocks. On CB7 it dropped `OCTOBER 2026`, the only place the year appears.
- plain `extract_text()` keeps the heading and flattens the grid to one entry per line,
  losing the day entirely.

So `extract_pdf_text` returns both, the fetcher stores both, and the readers take the month
from `plain` and the entries from `layout`. `tests/unit/test_board_pdf.py` pins that split,
including layout mode's omission — if a future pypdf starts including the heading, the test
reports it rather than the behaviour drifting unobserved.

Extraction runs at **fetch** time. The cache stores each board's `body` as a string and a
PDF is bytes, so storing the extracted text keeps PDF binaries out of `data/`, keeps the
build offline, and makes a fixture something a reviewer can read.

Everything here is third-party prose that reaches the page, so nothing is inferred that the
document does not say. Where a board states a recurrence in words rather than printing
dates, this does not expand it. A date we did not read is a gap; a date we invented is a
wrong answer. The same rule decides the awkward cases: Bronx CB5 prints `5/6PM.`, which
means five or six o'clock, so no time is reported at all.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from io import BytesIO

from ..text import collapse
from .board_meetings import BoardMeeting

__all__ = [
    "PDF_BOARDS",
    "PDF_READERS",
    "extract_pdf_text",
    "grid_cells",
    "parse_pdf",
]

_MONTH_NAMES = (
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
)

_MONTHS = {name.lower(): number for number, name in enumerate(_MONTH_NAMES, start=1)}

#: Staten Island CB1's agenda pages head each meeting `WED · NOV 4 · 6:30 PM · Land Use`.
_MONTH_ABBR = {name[:3].lower(): number for number, name in enumerate(_MONTH_NAMES, start=1)}

#: The weekday headers a grid may carry, full or abbreviated. Queens CB12 writes
#: `SUN MON TUE WED THU FRI SAT`; Bronx CB4 writes no header row at all, which is why a
#: header is a reset signal here and never a requirement.
_WEEKDAY_WORDS = (
    ("SUNDAY", "SUN"),
    ("MONDAY", "MON"),
    ("TUESDAY", "TUE"),
    ("WEDNESDAY", "WED"),
    ("THURSDAY", "THU"),
    ("FRIDAY", "FRI"),
    ("SATURDAY", "SAT"),
)

#: "OCTOBER 2026". The month name alone is not enough: several of these documents name an
#: adjacent month in a footer or a navigation link, so the year must be adjacent.
_HEADING = re.compile(r"\b(" + "|".join(_MONTHS) + r")\s+(20\d\d)\b", re.I)

#: Bronx CB4 heads its grid `2026   OCTOBER`, with the year first.
_HEADING_YEAR_FIRST = re.compile(r"\b(20\d\d)\s+(" + "|".join(_MONTHS) + r")\b", re.I)

#: A time: "6:30 pm", "6PM", "6:30pm", "6.45PM", "7:00 p.m.", "6:30 P.M." — every form seen
#: across these 15 boards. Minutes are optional, and one board separates them with a dot.
_TIME = re.compile(r"(\d{1,2})(?:[:.](\d{2}))?\s*([ap])\.?\s*m\.?", re.I)

#: A time range whose first hour carries no meridiem of its own: "6:30-    8:00PM". The
#: meeting starts at the first hour, so matching `_TIME` alone would publish the END time.
_RANGE = re.compile(
    r"(\d{1,2})(?:[:.](\d{2}))?\s*[-–—]\s*\d{1,2}(?:[:.]\d{2})?\s*([ap])\.?\s*m\.?",
    re.I,
)

#: A full date on one line, for the boards that print a list instead of a grid.
_FULL_DATE = re.compile(
    r"\b(" + "|".join(_MONTHS) + r")\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s*(20\d\d))?\b",
    re.I,
)

#: Brooklyn CB1 prints its year as a section header and its rows as bare `MM/DD`.
_SLASH_DATE = re.compile(r"\b(\d{1,2})/(\d{1,2})(?:/(20\d\d))?\b")

#: A bare year on a line of its own, which is how a list-style document is dated.
_YEAR = re.compile(r"^\s*(20\d\d)\s*$")

#: Queens CB8 dates its list in a title instead — `2026 BOARD MEETING SCHEDULE`. Anchored
#: on the schedule word so a year in a letterhead or a copyright line is not mistaken for
#: the list's own year.
_YEAR_IN_TITLE = re.compile(
    r"\b(20\d\d)\b[^\n]{0,40}?\b(?:schedule|calendar|meeting dates)\b", re.I
)

#: A day number opening a grid cell. Queens CB12 zero-pads (`04`); Staten Island CB2 adds a
#: trailing period (`4.`).
_DAY_NUMBER = re.compile(r"\d{1,2}\.?")


def extract_pdf_text(data: bytes) -> dict[str, str]:
    """Both pypdf text modes for one PDF, because neither alone carries the schedule.

    `layout` keeps the grid's columns and drops the heading; `plain` keeps the heading and
    flattens the grid. See the module docstring and `docs/dependencies.md`.

    pypdf's own logger is quietened to errors for the duration. Several of these documents
    are malformed in ways it reads anyway — `Multiple definitions in dictionary at byte
    0x419fc for key /Info` — and at `WARNING` those lines bury the fetch's own output
    about which board answered. Errors still come through, and a document that cannot be
    read at all raises, which the fetcher catches per link.
    """
    import logging

    from pypdf import PdfReader

    logger = logging.getLogger("pypdf")
    was = logger.level
    logger.setLevel(logging.ERROR)
    try:
        pages = list(PdfReader(BytesIO(data)).pages)
        return _both_modes(pages)
    finally:
        logger.setLevel(was)


def _both_modes(pages: list) -> dict[str, str]:
    return {
        "layout": "\n".join(page.extract_text(extraction_mode="layout") for page in pages),
        "plain": "\n".join(page.extract_text() for page in pages),
        "pages": str(len(pages)),
    }


# --------------------------------------------------------------------------------------
# Shared primitives
# --------------------------------------------------------------------------------------


def _time_of(line: str) -> str | None:
    """The start time printed on a line, or None when it prints none we can trust."""
    found = _RANGE.search(line) or _TIME.search(line)
    if not found:
        return None
    # "5/6PM" means five or six o'clock. Bronx CB5 writes exactly that, and picking one
    # would send somebody to a room an hour early or an hour late.
    if found.start() and line[found.start() - 1] == "/":
        return None
    hour = int(found.group(1))
    if not 1 <= hour <= 12:
        return None
    return f"{hour}:{found.group(2) or '00'} {found.group(3).upper()}M"


#: Cell text that is not a meeting. These grids mark holidays, closures and decoration
#: alongside entries, and a closed office rendered as a meeting sends somebody to a
#: locked door. Matched against a cell's joined text, because layout mode breaks
#: "(OFFICE IS CLOSED)" across three lines.
#: The apostrophe is optional and may be curly: these are typed by hand, and `Veterans’
#: Day` with U+2019 slipped past a pattern that spelled only `veterans\s+day`.
_CLOSURE = re.compile(
    r"office\s+(?:is\s+)?closed|closed:|no\s+meeting|cancell?ed|holiday|recess|"
    r"election\s+day|veterans[’']?\s*\s*day|labor\s+day|memorial\s+day|thanksgiving|"
    r"independence\s+day|juneteenth|diwali|christmas|new\s+year|columbus\s+day|"
    r"indigenous\s+people|presidents?[’']?\s+day|martin\s+luther\s+king|lunar\s+new|"
    r"rosh\s+hashanah|yom\s+kippur|good\s+friday|eid\s+al|all\s+saints",
    re.I,
)

#: A cell that, once its closure markers are out, says nothing but furniture. Bronx CB11
#: writes `OFFICE / CLOSED: / Veterans Day` down one cell; removing the last two lines
#: leaves a bare `OFFICE`, which is not a meeting. Matched whole, because "office" inside
#: a longer string is usually a venue — `CB1 Office` is where several boards meet.
_NOT_A_MEETING = re.compile(r"(?:office|closed|open|virtual|tbd|tba|n/?a)[:.]?", re.I)

#: A cell that is really the document's own footer, which several of these grids print
#: inside the last week's row rather than below the table. Left in, it becomes a meeting
#: on whatever day it is level with — Bronx CB10's "Call the Board Office at 718-892-1161
#: to confirm all meetings" was published as an 11:09 AM meeting on 30 November.
#:
#: Phrases only. An earlier version also matched any phone number, email or URL, which
#: would have dropped a real Bronx CB3 meeting whose cell carries the organiser's address
#: (`PSA 7 Community Council Meeting 5:00 PM Jesus.Correa@nypd.org`). Contact details are
#: stripped from the text instead — see `_CONTACT`.
_FOOTER_PROSE = re.compile(
    r"call\s+the\s+(?:board\s+)?office|to\s+confirm|subject\s+to\s+change|"
    r"for\s+(?:the\s+)?most\s+(?:up.to.date|current)|last\s+modified",
    re.I,
)

#: A slash date. In these documents it is the day the PDF was generated, printed inside
#: the last week's row — Bronx CB10 prints `10/22/2026` and Bronx CB11 `Last modified
#: 10/26/2026`. Removed before the time is read and before the title is built, so the cell
#: collapses to nothing and is dropped rather than published as a meeting.
_STAMP = re.compile(r"\b\d{1,2}/\d{1,2}/(?:20)?\d{2}\b")

#: An email address, a URL or a phone number inside a cell. Removed before the time is
#: read, because `718-892-1161` otherwise parses as a time, and before the title is built,
#: because a reader does not need the organiser's inbox in a meeting name.
_CONTACT = re.compile(
    r"[\w.+-]+@[\w.-]+\.\w+|https?://\S+|\bwww\.\S+|\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}\b",
    re.I,
)

#: Pieces that are never part of an entry:
#:
#: - one or two letters, which is Bronx CB9's month printed vertically down the left
#:   margin — `N`, `O`, `V`, `E`, `M`, `B`, `RE` — landing in whichever cell each is level
#:   with. No committee is named in two letters;
#: - a bare number, which is a day number that did not make it into its own week row;
#: - a bare year, from the same vertical heading;
#: - a slash date, which in these documents is a generation stamp and not a meeting;
#: - punctuation alone, left behind when layout mode splits an address;
#: - a placeholder, which names no time and no committee.
_PIECE_NOISE = re.compile(
    r"^(?:[A-Za-z]{1,2}|\d{1,2}|20\d\d|\d{1,2}/\d{1,2}/\d{2,4}|[^\w]+|\(?tbd\)?|\(?tba\)?)$",
    re.I,
)

#: Labels, hyperlink text and standing notices that are part of the document's furniture
#: rather than the entry. Stripped from a title instead of disqualifying the cell, because
#: the cell is a meeting.
#:
#: The venue notice is a sentence, and a committee name is not. Bronx CB11 prints "All
#: committee meetings are currently held at the BxCB11 Office at 1741 Colden Avenue and
#: remotely via Webex" inside its first cell of the month, which arrived as part of the
#: Transportation Committee's name. Cut at the phrase rather than listed per board: no
#: board names a committee this way, and the notice names no date of its own.
_TITLE_FURNITURE = re.compile(
    r"\(click here\)|^note:\s*time\b|^note:\s*|"
    r"\ball (?:committee )?meetings? (?:are|will be|is)\b.*$",
    re.I | re.S,
)


def _right_edge(columns: list[int]) -> int:
    """How far right a grid's seven day columns reach.

    One median column width past the last day number. Used only to cut off a board that
    prints an extra column beyond Saturday. `grid_cells` only ever calls this with the
    three or more day numbers that opened a week, so there is always a gap to measure.
    """
    gaps = sorted(columns[i] - columns[i - 1] for i in range(1, len(columns)))
    return columns[-1] + gaps[len(gaps) // 2]


def _column_of(offset: int, columns: list[int]) -> int:
    """Which column a piece starting at `offset` sits in.

    All fifteen documents put the day number at its cell's left edge, with the cell's text
    beginning at or just after it — Bronx CB7 prints `13` at column 33 and that day's
    `Housing, Land Use & Economic Development` also at column 33.

    A per-board `align` setting was tried here first, because Bronx CB9 looked
    right-aligned: its `10` sits at column 44 while that day's `Land/Zoning &` starts at
    25. It is not. Its week row is `V              9      10     11`, the `V` being one
    letter of the month printed vertically down the margin, and the `9` at column 21 was
    being lost — so content belonging to the 9th was landing on the 10th. Reading that
    board's own holiday markers settled it: Thanksgiving resolves to 26 November and
    Veterans Day to 11 November only under the left-edge reading, and both are right.
    """
    for index in range(len(columns) - 1, -1, -1):
        previous = columns[index - 1] if index else None
        boundary = columns[index] if previous is None else (previous + columns[index]) // 2
        if offset >= boundary:
            return index
    return 0


def _cell_pieces(line: str) -> list[tuple[int, str]]:
    """One line of a grid row split into per-column pieces, with each piece's offset.

    Layout mode separates cells with runs of spaces, so a run of two or more is a cell
    boundary and a single space is a word break inside one. Two rather than three because
    an under-split line merges two committees into one title, which reads as a single
    meeting that does not exist; an over-split one only loses a line break.
    """
    out = []
    for match in _PIECE.finditer(line):
        text = collapse(match.group())
        if text:
            out.append((match.start(), text))
    return out


#: One cell's worth of text: a run containing no two consecutive spaces.
#:
#: Spelled as "a non-space, then any number of non-spaces or lone spaces" rather than the
#: obvious `\S(?:.*?\S)?(?=\s{2,}|$)`. That form looks equivalent and is not: `?` is
#: greedy, so the engine prefers to match the optional group, and `.*?` then backtracks
#: across any gap until the lookahead is satisfied at end of line. Bronx CB9's
#: `N                     7:00PM` came out as a single piece, which merged its vertical
#: month letter with a committee's hour — and, line by line, merged whole adjacent columns
#: on five of these boards.
_PIECE = re.compile(r"\S(?:[^\s]|\s(?!\s))*")


def _is_weekday_row(line: str) -> bool:
    """Whether a line is a grid's weekday header, in full or abbreviated form.

    Used only to reset state between the pages of a multi-page document. A grid is opened
    by a row of day numbers, because Bronx CB4 publishes no header row at all.
    """
    upper = line.upper()
    cursor = 0
    for full, short in _WEEKDAY_WORDS:
        at = max(upper.find(full, cursor), upper.find(short, cursor))
        if at < 0:
            return False
        cursor = at + len(short)
    return True


def _looks_like_a_week(numbers: list[tuple[int, str]]) -> bool:
    """Whether a run of bare numbers is a grid's week row rather than a split address.

    A week runs forwards and resets at most once, at the month boundary, and no day number
    exceeds 31.
    """
    days = [int(text.rstrip(".")) for _, text in numbers]
    if any(not 1 <= day <= 31 for day in days):
        return False
    return sum(1 for i in range(1, len(days)) if days[i] <= days[i - 1]) <= 1


def _month_offsets(numbers: list[int], *, first_row: bool) -> list[int]:
    """Which month each day number in a week row belongs to: -1, 0 or +1.

    A grid's first row opens with the tail of the previous month and its last row closes
    with the head of the next, both printed as bare numbers with no month of their own. The
    giveaway is that the sequence resets: `27 28 29 30 1 2 3`. Everything before the reset
    on the first row is last month; everything after a reset on any later row is next
    month. Without this, an entry printed under September 28 in October's grid would be
    published as October 28 — a wrong date, which is worse than a missing one.
    """
    reset = next((i for i in range(1, len(numbers)) if numbers[i] < numbers[i - 1]), None)
    if reset is None:
        return [0] * len(numbers)
    if first_row:
        return [-1] * reset + [0] * (len(numbers) - reset)
    return [0] * reset + [1] * (len(numbers) - reset)


def grid_cells(layout: str, *, sidebar: bool = False) -> list[tuple[int, int, list[str]]]:
    """A grid's cells as `(day number, month offset, lines)`, in the order printed.

    This is the shared skeleton every grid board uses. A row of two or more bare day
    numbers opens a week, and **its own offsets — not the weekday header's — become the
    column basis**, because the cells align under the day numbers. Measured on Bronx CB7,
    where `TUESDAY` sits at column 52 but the `13` beneath it sits at 33, so bucketing
    against the headers put days 12 and 13 in one column and lost one of them.

    Every row after that adds its pieces to whichever column they sit under, so a cell's
    lines are the entry as the board laid it out, top to bottom.

    `sidebar` drops pieces that sit to the right of the last day number's own column.
    Bronx CB1 prints an eighth "Community Events" column whose rows carry their own dates,
    so reading it as part of Saturday would attach other events to a Saturday. The cut is
    made on horizontal position, because a column *index* cannot express it: there are
    only ever seven day numbers, so `_column_of` never returns an eighth column and every
    sidebar piece lands on Saturday.

    Day numbers are returned as printed; only the caller knows the heading month, so only
    the caller can turn `(14, 0)` into a date.
    """
    columns: list[int] | None = None
    days: list[int] = []
    offsets: list[int] = []
    cells: dict[int, list[str]] = {}
    out: list[tuple[int, int, list[str]]] = []
    first_row = True

    def flush() -> None:
        for index, number in enumerate(days):
            if cells.get(index):
                out.append((number, offsets[index], cells[index]))
        cells.clear()

    for line in layout.splitlines():
        if not line.strip():
            continue
        if _is_weekday_row(line):
            flush()
            columns, days, offsets = None, [], []
            continue

        pieces = _cell_pieces(line)
        numbers = [(at, text) for at, text in pieces if _DAY_NUMBER.fullmatch(text)]
        # A run of bare day numbers opens a week. Three is the floor because a grid's last
        # row can be as short as `29 30 31`, and the row need not be *only* numbers: Bronx
        # CB1 prints a `Community Events` sidebar heading on the same line as its days.
        # The sequence must also run forwards, with at most the one reset that a grid's
        # edge row makes — `27 28 29 30 1 2 3` — which is what distinguishes a week row
        # from a line of an address that happens to have been split into numerals.
        if len(numbers) >= 3 and _looks_like_a_week(numbers):
            flush()
            columns = [at for at, _ in numbers]
            days = [int(text.rstrip(".")) for _, text in numbers]
            offsets = _month_offsets(days, first_row=first_row)
            first_row = False
            continue

        if columns is None:
            continue
        for at, text in pieces:
            if _PIECE_NOISE.match(text):
                continue
            if sidebar and at > _right_edge(columns):
                continue
            cells.setdefault(_column_of(at, columns), []).append(text)

    flush()
    return out


# --------------------------------------------------------------------------------------
# The per-board configuration
# --------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class GridBoard:
    """One board's month grid, as measured from its live document.

    Every field exists because some board needed it, and the docstring of each entry in
    `PDF_BOARDS` says which observation put it there.
    """

    #: True when the heading prints the year before the month.
    year_first: bool = False
    #: True when the month is printed vertically, one letter per line, and so has to be
    #: reassembled from plain-mode text rather than matched in it.
    month_from_letters: bool = False
    #: Extra per-board text that is not a meeting.
    extra_noise: tuple[str, ...] = ()
    #: True when the grid prints an extra column to the right of Saturday. Bronx CB1
    #: heads one `Community Events`, and its rows carry their own dates, so reading them
    #: as Saturday attaches other events to a Saturday.
    sidebar: bool = False


@dataclass(frozen=True, slots=True)
class ListBoard:
    """One board's plain list of dates — no grid, so plain-mode text is enough."""

    title: str
    #: True when rows are `MM/DD` under a bare-year section header.
    slash_dates: bool = False
    #: Longer than this and a dated line is the document explaining itself, not an entry.
    max_line: int = 80


def _reassembled_month(plain: str) -> tuple[int, int] | None:
    """The month and year where the month is set vertically, one letter per line.

    Bronx CB9 prints `NOVEMBER` down the left margin. In plain-mode text that arrives as
    nine consecutive single-character lines followed by the year; in layout mode the
    letters are scattered into whichever grid rows they are level with, which is why this
    reads plain mode only.
    """
    letters: list[str] = []
    for raw in plain.splitlines():
        line = raw.strip()
        if len(line) == 1 and line.isalpha():
            letters.append(line)
            continue
        year = _YEAR.match(line)
        if year and len(letters) >= 3:
            name = "".join(letters).lower()
            for month, number in _MONTHS.items():
                if name.endswith(month):
                    return number, int(year.group(1))
        letters = []
    return None


def _heading_month(plain: str, board: GridBoard) -> tuple[int, int] | None:
    """The month and year this document is for."""
    if board.month_from_letters:
        return _reassembled_month(plain)
    if board.year_first:
        found = _HEADING_YEAR_FIRST.search(plain)
        return (_MONTHS[found.group(2).lower()], int(found.group(1))) if found else None
    found = _HEADING.search(plain)
    if found:
        return _MONTHS[found.group(1).lower()], int(found.group(2))
    return _split_heading(plain)


#: How far apart a month and a year may be and still be one heading. Bronx CB3 centres the
#: month and right-aligns the year, so plain mode puts them on different lines with the
#: board's name between them; three lines covers that and stops well short of reaching a
#: footer.
_HEADING_SPAN = 3


def _split_heading(plain: str) -> tuple[int, int] | None:
    """A month and year printed apart from each other, as Bronx CB3 does.

    Only the first month name in the document is considered, and only a year within
    `_HEADING_SPAN` lines of it. Scanning the whole document for any month and any year
    would pair a footer's copyright year with a body month and date a schedule wrongly.
    """
    lines = plain.splitlines()
    for index, raw in enumerate(lines):
        month = re.search(r"\b(" + "|".join(_MONTHS) + r")\b", raw, re.I)
        if not month:
            continue
        window = lines[max(0, index - _HEADING_SPAN) : index + _HEADING_SPAN + 1]
        year = re.search(r"\b(20\d\d)\b", " ".join(window))
        if year:
            return _MONTHS[month.group(1).lower()], int(year.group(1))
        return None
    return None


def _without_closures(lines: list[str]) -> list[str]:
    """A cell's lines with the holiday and closure markers taken out.

    Filtered per line, not per cell, because a holiday and a meeting share a cell. Bronx
    CB9 prints `Veterans Day` in the same Wednesday cell as a 7:00pm NYPD precinct council
    meeting at the ShopRite community room; dropping the cell for the holiday would lose a
    real meeting, and keeping the marker would publish a public holiday as one.

    What survives is checked again by the caller: Bronx CB7's `HOLIDAY / (OFFICE IS /
    CLOSED)` leaves `(OFFICE IS CLOSED)` behind, which is still not a meeting.
    """
    return [line for line in lines if not _CLOSURE.search(line)]


def _split_cell(lines: list[str]) -> tuple[str, str | None]:
    """A grid cell's lines as a committee name and a venue.

    **The line carrying the time is the divider.** These boards lay a cell out as name,
    then hour, then venue, and layout mode breaks each of those across as many lines as
    the column is narrow — which is why taking the first line as the name produced titles
    like `& Ethics` and `Traffic/Transportation /`.

    Two boards print the hour first (Bronx CB4 and CB11), so there is nothing before the
    divider. Their whole cell becomes the name, with the time text removed from it. That
    is a longer title than the others get and it is never a wrong one, which is the right
    way round: these cells are prose the board wrote, and this quotes them rather than
    guessing where an address begins.
    """
    clean = [collapse(_STAMP.sub(" ", _CONTACT.sub(" ", line))) for line in lines]
    clean = [line for line in clean if line]
    at = next((i for i, line in enumerate(clean) if _TIME.search(line)), None)
    if at is None or at == 0:
        before, after = clean, []
    else:
        before, after = clean[:at], clean[at + 1 :]

    title = _clean_title(" ".join(before))
    # Bronx CB4 writes its hour as `6:30-` on one line and `8:00PM` on the next, so the
    # divider lands below the start time and everything before it is the digits of a
    # range. A title that survives cleaning as nothing, or as nothing but digits, means
    # the divider was wrong, and the whole cell is the better answer.
    if not re.search(r"[A-Za-z]{3}", title):
        return _clean_title(" ".join(clean)), None
    return title, collapse(" ".join(after)) or None


def _clean_title(text: str) -> str:
    """A cell's name with the hour and the document's furniture taken out of it."""
    without_time = _TIME.sub(" ", _RANGE.sub(" ", text))
    return collapse(_TITLE_FURNITURE.sub(" ", without_time)).strip(" .,|·–-")


def _meeting(day: date, title: str, start_time: str | None, location: str | None, url: str | None):
    return BoardMeeting(
        day=day,
        start_time=start_time,
        title=collapse(title) or "Meeting",
        location=collapse(location) if location else None,
        url=url,
    )


def _grid_reader(board: GridBoard) -> Callable[..., list[BoardMeeting]]:
    """A reader for one board's month grid."""
    noise = re.compile("|".join(board.extra_noise), re.I) if board.extra_noise else None

    def read(layout: str, plain: str, *, on_or_after: date, url: str | None):
        month = _heading_month(plain, board)
        if month is None:
            # A grid prints only day numbers, so without the heading there is no year.
            # Guessing the current month would invent a schedule for whenever it is run.
            return []
        number, year = month

        out = []
        for day_number, offset, lines in grid_cells(layout, sidebar=board.sidebar):
            # An edge row's days belong to a neighbouring month, which the grid never
            # names. They are dropped rather than misdated; the board's own PDF for that
            # month carries them.
            if offset:
                continue
            try:
                day = date(year, number, day_number)
            except ValueError:
                continue
            if day < on_or_after:
                continue
            if _FOOTER_PROSE.search(collapse(" ".join(lines))):
                continue
            kept = _without_closures(lines)
            if not kept:
                continue
            joined = collapse(_STAMP.sub(" ", _CONTACT.sub(" ", " ".join(kept))))
            if _CLOSURE.search(joined) or _NOT_A_MEETING.fullmatch(joined):
                continue
            if noise and noise.search(joined):
                continue
            title, location = _split_cell(kept)
            if not title:
                continue
            out.append(_meeting(day, title, _time_of(joined), location, url))
        return out

    return read


def _list_reader(board: ListBoard) -> Callable[..., list[BoardMeeting]]:
    """A reader for one board's plain list of dates."""

    def read(layout: str, plain: str, *, on_or_after: date, url: str | None):  # noqa: ARG001
        out = []
        seen: set[date] = set()
        # Queens CB8 states the year once, in the document's title, and never on a row.
        titled = _YEAR_IN_TITLE.search(plain)
        year: int | None = int(titled.group(1)) if titled else None
        for raw in plain.splitlines():
            line = collapse(raw)
            if not line:
                continue
            bare = _YEAR.match(line)
            if bare:
                year = int(bare.group(1))
                continue
            # A long line carrying a date is the document explaining itself. Brooklyn CB1's
            # closing paragraph names a date in prose, and Queens CB8's memo header does.
            if len(line) > board.max_line:
                continue
            day = _list_date(line, year, slash=board.slash_dates)
            if day is None or day < on_or_after or day in seen:
                continue
            if _CLOSURE.search(line):
                continue
            seen.add(day)
            out.append(_meeting(day, board.title, _time_of(line), None, url))
        return out

    return read


def _list_date(line: str, year: int | None, *, slash: bool) -> date | None:
    """A date from one line of a list, under the year its section header gave."""
    if slash:
        found = _SLASH_DATE.search(line)
        if not found:
            return None
        on = int(found.group(3)) if found.group(3) else year
        month, day_number = int(found.group(1)), int(found.group(2))
    else:
        found = _FULL_DATE.search(line)
        if not found:
            return None
        on = int(found.group(3)) if found.group(3) else year
        month, day_number = _MONTHS[found.group(1).lower()], int(found.group(2))
    if on is None:
        return None
    try:
        return date(on, month, day_number)
    except ValueError:
        return None


#: Staten Island CB1 heads each committee's agenda `WED  ·  NOV 4  ·  6:30 PM  ·  Land Use`.
_SICB1_HEAD = re.compile(
    r"[A-Z]{3}\s*·\s*([A-Z]{3})\s+(\d{1,2})\s*·\s*([^·]+?)\s*·\s*(.+)",
    re.I,
)


def read_staten_island_cb1(layout: str, plain: str, *, on_or_after: date, url: str | None):
    """Staten Island CB1: a month grid on page 1, then one agenda per meeting after it.

    The agenda pages are the better source and the reason this board is not a plain grid
    reader: each meeting gets a middot-delimited header carrying the weekday, the date, the
    hour and the committee, which is more than the grid cell says. The grid is read too,
    for the full board meeting that the committee agendas do not cover, and the two are
    reconciled on `(day, hour)` — the same meeting appearing in both must not be published
    twice.
    """
    year = _heading_month(plain, GridBoard())
    if year is None:
        return []

    out: list[BoardMeeting] = []
    seen: set[tuple[date, str | None]] = set()

    for raw in layout.splitlines():
        found = _SICB1_HEAD.search(collapse(raw))
        if not found:
            continue
        month = _MONTH_ABBR.get(found.group(1).lower())
        if month is None:
            continue
        try:
            day = date(year[1], month, int(found.group(2)))
        except ValueError:
            continue
        if day < on_or_after:
            continue
        start_time = _time_of(found.group(3))
        key = (day, start_time)
        if key in seen:
            continue
        seen.add(key)
        out.append(_meeting(day, found.group(4), start_time, None, url))

    for meeting in _SICB1_GRID(layout, plain, on_or_after=on_or_after, url=url):
        if (meeting.day, meeting.start_time) in seen:
            continue
        seen.add((meeting.day, meeting.start_time))
        out.append(meeting)
    return out


#: The grid half of Staten Island CB1's document. Its cells carry decorative prose — a
#: daylight-saving note reading "Set clocks back 1 hour at 2 AM" would otherwise publish a
#: 2 AM meeting.
_SICB1_GRID = _grid_reader(
    GridBoard(
        extra_noise=(
            r"set clocks back",
            r"sleepyheads",
            r"honoring all who served",
            r"thank you for your service",
            r"your voice matters",
            r"vote!",
        ),
    )
)

# --------------------------------------------------------------------------------------
# The agenda boards: one meeting per PDF, on labelled lines
# --------------------------------------------------------------------------------------

#: `DATE:`, `Date :`, `TIME:`, `Place:`, `VENUE:`, `Location:`. The space before the colon
#: is Queens CB5's, and the label's case varies within a single document.
_FIELD = re.compile(r"^(DATE|TIME|PLACE|VENUE|LOCATION)\s*:\s*(.*)$", re.I)

#: A date and hour on one line, under no label: `TUESDAY, MAY 27, 2025 at 7:00 P.M.`
#: Anchored on the weekday so that a sentence mentioning a date is not mistaken for one.
_COMBINED = re.compile(
    r"^(?:mon|tues|wednes|thurs|fri|satur|sun)day,?\s+(" + "|".join(_MONTHS) + r")\s+"
    r"(\d{1,2})(?:st|nd|rd|th)?,?\s*(20\d\d)\b.*?\bat\b",
    re.I,
)

#: A meeting's own name, where the document states one. `RE: Executive Committee Meeting`
#: is how Brooklyn CB9 titles its memo; the others print a heading in capitals.
_AGENDA_TITLE = re.compile(
    r"^(?:RE|SUBJECT)\s*:\s*(.{4,60}?(?:meeting|hearing|agenda).*)$|"
    r"^([A-Z][A-Z0-9 ,&/'’\-\.]{6,60}(?:MEETING|HEARING|COMMITTEE)"
    r"(?:\s+(?:AGENDA|NOTICE))?)\s*$",
    re.I,
)


@dataclass(frozen=True, slots=True)
class AgendaBoard:
    """One board that publishes a notice per meeting rather than a schedule.

    Five boards do this, and Queens CB9 was the first found. Each document yields exactly
    one meeting, so full coverage means fetching every notice the board's page lists.
    """

    #: What to call the meeting when the document states no name of its own.
    title: str = "Full board meeting"
    #: A heading to find the date under, for the documents that print no `DATE:` label.
    #: Queens CB4 buries one dated notice in an eleven-page newsletter whose other pages
    #: carry dozens of unrelated dates, so the heading is the only thing that locates it.
    anchor: str | None = None
    #: How many lines after the anchor the date may appear.
    anchor_span: int = 4


def _labelled_fields(lines: list[str]) -> list[tuple[int, str, str]]:
    """Every labelled line, as `(index, label, value)`.

    A label whose own line carries no value takes the next line as its value. Queens CB10
    sets its notice in two columns, so the labels and the values are separate text boxes
    and arrive as `DATE:` then `November 5, 2026` on the line after. Only applied when the
    value is genuinely empty, so a label that states its value inline is untouched.
    """
    out = []
    for index, line in enumerate(lines):
        found = _FIELD.match(line)
        if not found:
            continue
        value = found.group(2).strip()
        if not value and index + 1 < len(lines):
            value = lines[index + 1]
        out.append((index, found.group(1).upper(), value))
    return out


def _agenda_date(lines: list[str], fields: list[tuple[int, str, str]], board: AgendaBoard):
    """The meeting's date, and the line to read its hour and venue from.

    **The last labelled date wins.** Two of these boards print an earlier date first and
    mean a later one: Bronx CB2's page 1 is the previous month's notice, and Brooklyn CB9's
    Executive memo is dated the day it was written before giving the meeting's own date
    under "has been scheduled as follows". Taking the first would publish both wrong.

    Returns the day, the index to read the hour and venue from, and the index to read the
    meeting's name from. Those last two differ on Bronx CB2, which prints a public hearing
    and then the full board that follows it, both on the same day: only the hearing states
    a clock time — the board's own says "Upon Public Hearing completion", which is not a
    time anybody can be told — while the name of the thing a reader attends is the full
    board's, above the later date. So the hour comes from the first line carrying the date
    and the name from the last.
    """
    dated = [
        (index, _list_date(value, None, slash=False))
        for index, label, value in fields
        if label == "DATE"
    ]
    dated = [(index, day) for index, day in dated if day is not None]
    if dated:
        day = dated[-1][1]
        return day, next(index for index, found in dated if found == day), dated[-1][0]

    for index, line in enumerate(lines):
        combined = _COMBINED.match(line)
        if combined:
            try:
                month = _MONTHS[combined.group(1).lower()]
                day = date(int(combined.group(3)), month, int(combined.group(2)))
                return day, index, index
            except ValueError:
                continue

    if board.anchor:
        heading = re.compile(board.anchor, re.I)
        for index, line in enumerate(lines):
            if not heading.search(line):
                continue
            for offset in range(1, board.anchor_span + 1):
                if index + offset >= len(lines):
                    break
                day = _list_date(lines[index + offset], None, slash=False)
                if day is not None:
                    return day, index + offset, index + offset
    return None, 0, 0


def _agenda_reader(board: AgendaBoard) -> Callable[..., list[BoardMeeting]]:
    """A reader for one board's per-meeting notices."""

    def read(layout: str, plain: str, *, on_or_after: date, url: str | None):  # noqa: ARG001
        # **Plain mode, not layout.** A notice has no columns worth preserving, and layout
        # mode actively hurts here: it keeps horizontal position, so a board's sidebar of
        # officers' names shares a line with the field it happens to sit level with.
        # Brooklyn CB9's executive notice comes out as
        # `    Nicolas Almonor        DATE:     Tuesday, October 13, 2026`, which a
        # line-anchored label cannot match. Plain mode puts each label at the start of its
        # own line, which is what `_FIELD` is anchored on.
        lines = [collapse(raw) for raw in plain.splitlines()]
        lines = [line for line in lines if line]
        fields = _labelled_fields(lines)

        day, at, named_at = _agenda_date(lines, fields, board)
        if day is None or day < on_or_after:
            return []

        # Queens CB5 puts the hour in brackets on the date line itself. Otherwise it is on
        # a labelled TIME line below, and only the first one that parses as a clock time.
        start_time = _time_of(lines[at])
        if start_time is None:
            start_time = next(
                (
                    found
                    for index, label, value in fields
                    if label == "TIME" and index >= at and (found := _time_of(value))
                ),
                None,
            )
        if start_time is None:
            # Queens CB4 labels nothing: the hour is simply the next line under the date.
            start_time = next(
                (found for line in lines[at + 1 : at + 3] if (found := _time_of(line))), None
            )
        location = next(
            (value for index, label, value in fields if label in _VENUE_LABELS and index >= at),
            None,
        )
        title = _title_near(lines, named_at, board)
        return [_meeting(day, title, start_time, location, url)]

    return read


#: The labels these boards use for a venue. Three different words, one meaning.
_VENUE_LABELS = frozenset({"PLACE", "VENUE", "LOCATION"})


#: How far above the date to look for the meeting's own heading.
_TITLE_SPAN = 4


def _title_near(lines: list[str], at: int, board: AgendaBoard) -> str:
    """The meeting's own name, taken from the heading just above its date.

    Searched upward from the date rather than across the document, because these notices
    carry other headings: Queens CB4's newsletter offers "CLICK HERE FOR MINUTES FROM OUR
    SEPTEMBER 2026 MEETING", and Bronx CB2 prints the public hearing's heading above the
    full board's that follows it. The nearest heading above the date is the one that
    describes it.
    """
    for index in range(at, max(-1, at - _TITLE_SPAN - 1), -1):
        stated = _agenda_title(lines[index])
        if stated:
            return stated
    return board.title


def _agenda_title(line: str) -> str | None:
    """The meeting's own name, where the document prints one."""
    found = _AGENDA_TITLE.match(line)
    if not found:
        return None
    stated = collapse(found.group(1) or found.group(2) or "")
    # An invitation to click is not the name of a meeting, and Queens CB4's newsletter
    # offers "CLICK HERE FOR MINUTES FROM OUR SEPTEMBER 2026 MEETING" — which ends in the
    # right word and is otherwise shaped exactly like a heading.
    #
    # A bare "AGENDA" or "OCTOBER AGENDA" needs no guard: the pattern only accepts a
    # heading ending in MEETING or HEARING, so neither reaches here.
    if re.match(r"click\b", stated, re.I):
        return None
    return collapse(re.sub(r"\s+(?:AGENDA|NOTICE)$", "", stated, flags=re.I))


#: Every board whose schedule is a PDF, with the shape measured on its live document.
#: One entry per board, on purpose: these 21 share a file format and nothing else, and the
#: next person here will be here because one of them redesigned its PDF.
PDF_BOARDS: dict[str, GridBoard | ListBoard | AgendaBoard] = {
    # Bronx CB2: a Full Board agenda per month. Page 1 is the previous month's notice, so
    # the date must come from the last labelled one, not the first.
    "202": AgendaBoard(),
    # Bronx CB1: a grid plus an eighth "Community Events" sidebar whose rows carry their
    # own dates, so the sidebar must not be read as Saturday.
    "201": GridBoard(sidebar=True),
    # Bronx CB3: a plain grid. Stale as of 2026-10-31 — newest published is September 2026.
    "203": GridBoard(),
    # Bronx CB4: no weekday header row at all, year-first heading, and range times whose
    # first hour carries no meridiem.
    "204": GridBoard(year_first=True),
    # Bronx CB5: a very sparse grid; prints `5/6PM.`, which reports no time.
    "205": GridBoard(),
    # Bronx CB7: the heading is in plain mode only, and at the very end of it.
    "207": GridBoard(),
    # Bronx CB9: the month is set vertically, one letter per line.
    "209": GridBoard(month_from_letters=True),
    # Bronx CB10: heading prefixed `TENTATIVE`, times written `7 p.m.`.
    "210": GridBoard(),
    # Bronx CB11: the time precedes the committee name, inverting every other board's
    # field order, and cells carry a `(Click here)` hyperlink label.
    "211": GridBoard(),
    # Brooklyn CB9: a General Board and an Executive agenda per month. The Executive memo
    # is dated the day it was written before it gives the meeting's own date.
    "309": AgendaBoard(),
    # Brooklyn CB12: one combined all-caps line, `TUESDAY, MAY 27, 2025 at 7:00 P.M.`, and
    # no labelled fields at all. The site stops at 2025.
    "312": AgendaBoard(),
    # Brooklyn CB16: one notice at a time, on `DATE:` / `TIME:` / `LOCATION:` lines.
    "316": AgendaBoard(title="General board meeting"),
    # Queens CB4: the notice is on page 2 of an eleven-page newsletter whose other pages
    # carry dozens of unrelated dates, and it carries no label — so it is found under its
    # own heading. The board's agenda archive stopped in 2022; this is the only live source.
    "404": AgendaBoard(anchor=r"BOARD MEETING NOTICE"),
    # Queens CB5: `Date  : Wednesday, October 14, 2026 (7:30pm)` — hour on the date line.
    # Two archives, board meetings and committee notices, both live.
    "405": AgendaBoard(),
    # Brooklyn CB1: a press release listing two years of dates as `Tuesday 01/13`, with the
    # year as a bare section header. The list appears twice in the extracted text.
    "301": ListBoard(title="Full board meeting", slash_dates=True),
    # Queens CB8: an annual memo, `January 7th` per row, no times anywhere in the document.
    "408": ListBoard(title="Full board meeting"),
    # Queens CB9: the first agenda board found. One notice per monthly meeting.
    "409": AgendaBoard(),
    # Bronx CB12: scanned. Its notice is one sentence — "will be held on / Thursday,
    # April 23, 2026, at 7:00 P.M. in Town Hall 4101 White Plains Road" — which is the
    # combined shape Brooklyn CB12 uses, so no label and no anchor are needed.
    "212": AgendaBoard(),
    # Queens CB10: scanned, and set in two columns, so OCR returns `DATE:` and
    # `November 5, 2026` as separate lines — see `_labelled_fields`.
    "410": AgendaBoard(),
    # Queens CB12: abbreviated weekday row and zero-padded day numbers.
    "412": GridBoard(),
    # Staten Island CB2: day numbers carry a trailing period.
    "502": GridBoard(),
    # Staten Island CB3: the cleanest plain grid of the fifteen.
    "503": GridBoard(),
}


def _reader_for(board: GridBoard | ListBoard | AgendaBoard) -> Callable[..., list[BoardMeeting]]:
    if isinstance(board, GridBoard):
        return _grid_reader(board)
    if isinstance(board, ListBoard):
        return _list_reader(board)
    return _agenda_reader(board)


#: Board code to the reader that understands that board's document.
PDF_READERS: dict[str, Callable[..., list[BoardMeeting]]] = {
    code: _reader_for(board) for code, board in PDF_BOARDS.items()
}

# The one board whose document is not any single shape: a grid on page 1, then an agenda
# per meeting on the pages after it.
PDF_READERS["501"] = read_staten_island_cb1


def parse_pdf(code: str, body: str, *, on_or_after: date) -> list[BoardMeeting]:
    """Read one board's PDFs with that board's reader, or return nothing.

    `body` is what `extract_pdf_text` produced for each PDF found on the board's page,
    serialised by the fetcher as a JSON array. A board links several months at once, so
    this reads them all and lets the cutoff drop the ones already past — which is also why
    nothing here has to work out which PDF is the current one.
    """
    reader = PDF_READERS.get(str(code))
    if reader is None:
        return []
    try:
        documents = json.loads(body)
    except json.JSONDecodeError:
        return []
    if not isinstance(documents, list):
        return []

    found: list[BoardMeeting] = []
    seen: set[tuple[date, str, str | None]] = set()
    for document in documents:
        if not isinstance(document, dict):
            continue
        for meeting in reader(
            str(document.get("layout") or ""),
            str(document.get("plain") or ""),
            on_or_after=on_or_after,
            url=str(document.get("url") or "") or None,
        ):
            # Boards link overlapping months, and two of these documents repeat their own
            # schedule in the extracted text, so the same meeting arrives more than once.
            key = (meeting.day, meeting.title.lower()[:12], meeting.start_time)
            if key in seen:
                continue
            seen.add(key)
            found.append(meeting)
    return sorted(found, key=lambda m: (m.day, m.start_time or ""))
