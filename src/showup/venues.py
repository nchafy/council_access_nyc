"""Collapsing Legistar's free-text location column onto real places.

`meeting_location` is typed by clerks and has accumulated 30-plus spellings of
about five rooms across 25 years — en-dash and double-space variants, "HYBRID
HEARING - " prefixes, "REMOTE HEARING (VIRTUAL ROOM 3)". Attendance mode is kept
separate from place, because "remote" is not a room, and a hybrid hearing has
both.

Unrecognised strings become `offsite` carrying the raw label rather than being
forced into the nearest match. The Council really does sit in borough halls,
schools and libraries occasionally, and inventing a City Hall address for one of
those would send someone to the wrong building.
"""

from __future__ import annotations

import re

from .model import Venue

__all__ = ["VENUES", "normalize_location"]

_CITY_HALL = "New York City Hall, City Hall Park, New York, NY 10007"
_250 = "250 Broadway, New York, NY 10007"

_CITY_HALL_ENTRY = (
    "Enter through NYPD security and metal detectors. Tell the officers which hearing you are "
    'attending. No food, beverage containers, or signs larger than 8.5" x 11" in hearing rooms.'
)
_250_ENTRY = (
    "Bring photo ID and pass through security and metal detectors. Every floor has a "
    "Sergeant-at-Arms who can direct you. No food, beverage containers, or signs larger than "
    '8.5" x 11" in hearing rooms.'
)

VENUES: dict[str, Venue] = {
    "city-hall-chambers": Venue(
        "city-hall-chambers",
        "Council Chambers, City Hall",
        _CITY_HALL,
        _CITY_HALL_ENTRY,
        "Where Stated Meetings of the full 51-member Council are held.",
    ),
    "city-hall-committee": Venue(
        "city-hall-committee",
        "Committee Room, City Hall",
        _CITY_HALL,
        _CITY_HALL_ENTRY,
        "The second hearing room inside City Hall.",
    ),
    "250-broadway-8": Venue(
        "250-broadway-8",
        "250 Broadway — 8th Floor Hearing Rooms",
        "250 Broadway, 8th Floor, New York, NY 10007",
        _250_ENTRY,
        "The current main committee-hearing location (Hearing Rooms 1, 2 and 3).",
    ),
    "250-broadway-14": Venue(
        "250-broadway-14",
        "250 Broadway — 14th Floor",
        "250 Broadway, 14th Floor, New York, NY 10007",
        _250_ENTRY,
        None,
    ),
    "250-broadway-16": Venue(
        "250-broadway-16",
        "250 Broadway — 16th Floor",
        "250 Broadway, 16th Floor, New York, NY 10007",
        _250_ENTRY,
        None,
    ),
    "250-broadway": Venue(
        "250-broadway", "250 Broadway", _250, _250_ENTRY, "Floor not stated in the source."
    ),
    "emigrant": Venue(
        "emigrant",
        "Emigrant Savings Bank Building",
        "49-51 Chambers Street, New York, NY 10007",
        "Bring photo ID and pass through building security.",
        "Overflow hearing space across from City Hall.",
    ),
    "remote": Venue(
        "remote",
        "Remote hearing (Zoom)",
        None,
        "To speak, register in advance on the Council's Register to Testify form. To watch "
        "only, no registration is needed — use the Council livestream.",
        "Remote participants are subject to the Council's Remote Attendance Policy.",
    ),
    "offsite": Venue(
        "offsite",
        "Off-site hearing",
        None,
        "Check the agenda PDF for the exact address and entry instructions.",
        "Occasionally the Council sits closer to affected residents — a borough hall, school, "
        "library or state office building.",
    ),
}

_DASHES = re.compile(r"[‐-―−~]")
_JOINTLY = re.compile(r"\bjointly with the committee on\b.*$", re.IGNORECASE)


def _clean(raw: str) -> str:
    text = _DASHES.sub("-", raw)
    # "Council Chambers - City Hall Jointly with the Committee on Education." —
    # the joint-hearing note rides along in the location cell and must come off
    # before matching, or every joint hearing looks like an unknown venue.
    text = _JOINTLY.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_location(raw: str | None) -> tuple[Venue, str]:
    """Map a raw location string to (venue, attendance_mode).

    attendance_mode is one of "in_person", "hybrid", "remote".
    """
    label = (raw or "").strip()
    if not label:
        return VENUES["offsite"], "in_person"

    text = _clean(label)
    hybrid = bool(re.search(r"hybrid", text, re.IGNORECASE))
    remote = bool(re.search(r"remote|virtual|zoom|teleconference", text, re.IGNORECASE))

    if remote and not hybrid:
        return VENUES["remote"], "remote"

    mode = "hybrid" if hybrid else "in_person"

    if re.search(r"250\s*broadway", text, re.IGNORECASE):
        for floor, key in (
            ("8", "250-broadway-8"),
            ("14", "250-broadway-14"),
            ("16", "250-broadway-16"),
        ):
            if re.search(rf"\b{floor}(th)?\b", text):
                return VENUES[key], mode
        return VENUES["250-broadway"], mode

    if re.search(r"emigrant|chambers\s+st", text, re.IGNORECASE):
        return VENUES["emigrant"], mode

    if re.search(r"city hall", text, re.IGNORECASE):
        # "Council Committee Room - City Hall" is the committee room, not the
        # Chambers, so "committee" has to win over "chamber".
        if re.search(r"committee", text, re.IGNORECASE):
            return VENUES["city-hall-committee"], mode
        if re.search(r"chamber", text, re.IGNORECASE):
            return VENUES["city-hall-chambers"], mode
        return VENUES["city-hall-committee"], mode

    return VENUES["offsite"], mode
