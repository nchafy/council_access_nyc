# The fifteen boards whose schedule is a PDF

Measured 2026-10-31 by fetching each board's landing page, following every `.pdf` link it
carries, and extracting both pypdf text modes. Every URL below returned HTTP 200 and
`application/pdf`. **All fifteen yield extractable text; none is a scan.** The readers are
in `src/showup/sources/board_pdf.py`, one per board, and
`tests/fixtures/board_pdf_text.json` holds the extracted text these observations are from.

The crosswalk `crosswalks/board_schedule_sources.json` is the source of truth for *where*
each board's schedule comes from. This file records *what each document looks like*, which
is what the parsers encode.

## Why both extraction modes are stored

`extraction_mode="layout"` preserves the Sunday-to-Saturday columns and **silently drops
heading and footer text blocks**. Plain `extract_text()` keeps the heading and flattens the
grid. Neither is sufficient alone, so the cache stores both. The clearest case is Bronx
CB7, where layout mode dropped `OCTOBER 2026` — the only place the year appears in the
whole document. See `docs/dependencies.md` for the dependency decision this drove.

## A grid encodes the day in horizontal position

"Municipal Services / 6:30 pm / The Bedford Community Room" says nothing about which day it
is. The column it sits under does. Three properties of that turned out to be load-bearing:

1. **The day numbers are the column basis, not the weekday headers.** Bronx CB7 prints
   `TUESDAY` at column 52 and the `13` beneath it at column 33. Bucketing against the
   headers put days 12 and 13 in one column and lost one of them.
2. **The day number sits at its cell's left edge** in all fifteen documents, with the
   cell's text beginning at or just after it. A per-board `align` setting was tried first,
   because Bronx CB9 looked right-aligned; it is not — its week row is
   `V              9      10     11`, where `V` is one letter of a vertically-printed
   month, and the `9` was being lost. The boards' own holiday markers settled it:
   Thanksgiving resolves to 26 November 2026 and Veterans Day to 11 November 2026 only
   under the left-edge reading, and both of those are correct.
3. **A grid's edge rows carry the neighbouring months' days**, printed as bare numbers with
   no month of their own — `27 28 29 30 1 2 3`. They are dropped rather than dated, because
   an entry printed under September 28 in October's grid would otherwise be published as
   October 28.

## Per board

| Board | Form | Where the month and year live | Time forms | What is particular to it |
|---|---|---|---|---|
| Bronx CB1 (201) | grid + sidebar | `NOVEMBER 2026 CALENDAR`, both modes | `6:00 PM`, `6:30PM`, `8AM`, `1PM` | An eighth `Community Events` column whose rows carry their own dates. Cut by horizontal position, because there are only ever seven day numbers so no column *index* can express an eighth column. Cells use `TIME • VENUE`. |
| Bronx CB3 (203) | grid | month and year on **different lines** in plain mode, with the board's name between them | `6:00 PM`, `9:00 AM`, `1PM to 6PM` | **Stale**: the newest published is September 2026, so it currently yields nothing. A cell carries an organiser's email, which is stripped rather than treated as a disqualifying footer. |
| Bronx CB4 (204) | grid, **no weekday header row** | `2026   OCTOBER` — year first | `6:30-    8:00PM`, `7:00PM    -8:30PM` | No Sunday-to-Saturday labels at all, which is why a week is opened by a row of day numbers. Times are **ranges**, and the meeting starts at the first hour — matching the plain time pattern published the end of the meeting as its start. |
| Bronx CB5 (205) | grid, sparse | `October 2026`, both modes | `6PM.`, `5/6PM.` | `5/6PM` means five or six o'clock, so **no time is reported**. Picking one would send somebody to a room an hour out. |
| Bronx CB7 (207) | grid | `OCTOBER 2026`, **plain mode only, at the very end of it** | `6:30 pm` (lowercase) | The case that proved both modes are needed. Prints `HOLIDAY / (OFFICE IS / CLOSED)` down one cell across three lines. |
| Bronx CB9 (209) | grid | **vertical**: `NOVEMBER` set one letter per line down the left margin, reassembled from plain mode | `7:00PM`, `6:30PM`, `7:00pm` | Layout mode scatters the margin letters into whichever grid rows they are level with, so they are dropped as pieces — no committee is named in one or two letters. Prints `Veterans Day` in the same cell as a real 7:00pm NYPD precinct council meeting, which is why closures are filtered per line and not per cell. |
| Bronx CB10 (210) | grid | `TENTATIVE  NOVEMBER 2026`, both modes | `7 p.m.`, `7:00 p.m.` | Prints its footer inside the last week's row: `Call the Board Office at 718-892-1161 to confirm all meetings` was published as an 11:09 AM meeting on 30 November. Also prints a generation stamp, `10/22/2026`. |
| Bronx CB11 (211) | grid | `Bronx CB11's November 2026 Calendar` | `7:00 PM`, `6:45 PM` | **The time precedes the committee name**, so there is nothing before the divider and the whole cell becomes the name. Cells carry a `(Click here)` hyperlink label. The only board publishing far ahead — `calendar/YYYY-MM.pdf`, linked through June 2027. |
| Brooklyn CB1 (301) | annual list | year as a bare section header, rows are `Tuesday 01/13` | `6:00 PM` in trailing prose only, so none is attached | Spans 2026 **and** 2027. **The list appears twice** in the extracted text and is deduplicated. |
| Queens CB8 (408) | annual list | `2026 BOARD MEETING SCHEDULE` — the title, never a row | **none in the document** | Ordinal suffixes (`January 7th`). July and August omitted for the summer recess. Goes stale on 2027-01-01. |
| Queens CB9 (409) | **single-meeting agenda** | `DATE:   Tuesday, November 10, 2026` | `7:15 PM` | This board's page links agendas, not a schedule, so each document yields exactly one meeting and full coverage means fetching every agenda the page lists. |
| Queens CB12 (412) | grid | `OCTOBER 2026     CB12Q`, both modes | `7:00 PM`, `7:00PM`, `(TBD)` | Abbreviated weekday row (`SUN MON TUE…`) and **zero-padded day numbers** (`01 02 03`). |
| Staten Island CB1 (501) | **grid on page 1, one agenda per meeting on pages 2–4** | `November 2026` on page 1 | `6:30 PM`; page-1 cells use `6:30 PM \| Virtual` | The richest of the fifteen. The agenda pages head each meeting `WED  ·  NOV 4  ·  6:30 PM  ·  Land Use`, which is more than the grid cell says, so both halves are read and reconciled on `(day, hour)`. Cells carry decorative prose: `Set clocks back 1 hour at 2 AM` would otherwise publish a 2 AM meeting. |
| Staten Island CB2 (502) | grid | `October 2026` + `Committee Meetings` | `6:30 P.M.` (uppercase dotted) | **Day numbers carry a trailing period**: `1.` `2.` `10.` |
| Staten Island CB3 (503) | grid | `October 2026` under a seven-line letterhead | `6:30PM` (no space, no dots) | The cleanest plain grid. Only one PDF on the whole landing page, so no archive and no future month. |

## What these documents do not say

Nothing in a board's PDF states whether a meeting is remote, whether testimony is taken, or
when a comment window closes. `BoardMeeting` therefore carries none of those, and the page
must not imply them — the same refusal as for the feed boards
(`src/showup/sources/board_meetings.py`).

Where a board states a recurrence in words rather than printing dates, it is **not
expanded**. Queens CB8's memo says the board meets monthly; only the printed dates are
read. A date we did not list is a gap; a date we invented is a wrong answer.

## Staleness, as of 2026-10-31

A reader existing is not the same as a board publishing. Re-measured on this date:

- **Publishing ahead**: Bronx CB11 (through June 2027), Brooklyn CB1 (through 2027),
  Queens CB8 (through December 2026), Bronx CB9, Bronx CB10, Queens CB9, Staten Island CB1.
- **Current month only, nothing future**: Bronx CB1, Bronx CB4, Bronx CB5, Queens CB12,
  Staten Island CB2, Staten Island CB3.
- **Stale**: Bronx CB3 — newest published is September 2026.

The stale ones are not an error and are not removed: the reader is correct and will start
yielding meetings again when the board posts a current document. That is why
`crosswalks/board_schedule_sources.json` keeps `pdf-stale` as a status rather than dropping
the board, and why the ingest floors in `sources/board_meetings.py` are set below the
measured total rather than at it.
