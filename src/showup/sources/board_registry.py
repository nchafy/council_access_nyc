"""Every kind of board source, with its load half and its read half bound together.

This is the whole list. A board's `kind` in `crosswalks/board_schedule_sources.json` names
an entry here, `showup fetch` asks it to load, `showup build` asks it to read, and nothing
else in the project needs to know how many kinds there are.

Importing this module registers them. It is imported lazily, from inside the two functions
that need it, because `board_meetings` holds `BoardMeeting` and would otherwise be imported
in a circle.
"""

from __future__ import annotations

from datetime import date

from .board_kinds import BoardSourceKind, register
from .board_loaders import load_pdf, load_plain, load_tribe
from .board_meetings import BoardMeeting

__all__ = ["install"]


def _read_ics(code: str, body: str, on_or_after: date) -> list[BoardMeeting]:  # noqa: ARG001
    from .board_meetings import parse_ics

    return parse_ics(body, on_or_after=on_or_after)


def _read_tribe(code: str, body: str, on_or_after: date) -> list[BoardMeeting]:  # noqa: ARG001
    from .board_meetings import as_object, parse_tribe

    return parse_tribe(as_object("tribe", body), on_or_after=on_or_after)


def _read_mcb7(code: str, body: str, on_or_after: date) -> list[BoardMeeting]:  # noqa: ARG001
    from .board_meetings import as_array, parse_mcb7

    return parse_mcb7(as_array("other-json", body), on_or_after=on_or_after)


def _read_nyc_html(code: str, body: str, on_or_after: date) -> list[BoardMeeting]:
    from .board_html import parse_html

    return parse_html(code, body, on_or_after=on_or_after)


def _read_nyc_pdf(code: str, body: str, on_or_after: date) -> list[BoardMeeting]:
    from .board_pdf import parse_pdf

    return parse_pdf(code, body, on_or_after=on_or_after)


_INSTALLED = False


def install() -> None:
    """Register every kind, once."""
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    register(
        BoardSourceKind(
            name="gcal-ics",
            load=load_plain,
            read=_read_ics,
            summary="A public Google Calendar, served as iCalendar.",
        )
    )
    register(
        BoardSourceKind(
            name="other-ics",
            load=load_plain,
            read=_read_ics,
            summary="A board serving its own iCalendar file.",
        )
    )
    register(
        BoardSourceKind(
            name="tribe",
            load=load_tribe,
            read=_read_tribe,
            summary="The Events Calendar, a WordPress plugin with a REST API.",
        )
    )
    register(
        BoardSourceKind(
            name="other-json",
            load=load_plain,
            read=_read_mcb7,
            summary="One board's bespoke JSON file.",
        )
    )
    register(
        BoardSourceKind(
            name="nyc-html",
            load=load_plain,
            read=_read_nyc_html,
            summary="Dates in nyc.gov HTML, read by a per-board reader.",
        )
    )
    register(
        BoardSourceKind(
            name="nyc-pdf",
            load=load_pdf,
            read=_read_nyc_pdf,
            summary="A schedule or a notice in a text PDF, read by a per-board reader.",
        )
    )
