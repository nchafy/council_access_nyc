"""Collapsing Legistar's free-text location column onto real places.

`meeting_location` is typed by clerks and carries 30-plus spellings of about five rooms.
Attendance mode is kept separate from place, and an unrecognised string becomes `offsite`
carrying its raw label rather than being forced to the nearest match.
"""

from __future__ import annotations

import re

from .model import Venue

__all__ = ["VENUES", "normalize_location"]

_CITY_HALL = "New York City Hall, City Hall Park, New York, NY 10007"
_250 = "250 Broadway, New York, NY 10007"

#: Procedural facts, stated rather than instructed (docs/voice.md).
_CITY_HALL_ENTRY = (
    "Entry is through NYPD security and metal detectors, and the officers ask which hearing "
    'each visitor is attending. No food, beverage containers, or signs larger than 8.5" x 11" '
    "in hearing rooms."
)
_250_ENTRY = (
    "Photo ID is required, and entry is through security and metal detectors. Every floor has "
    "a Sergeant-at-Arms, who gives directions. No food, beverage containers, or signs larger "
    'than 8.5" x 11" in hearing rooms.'
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
        "Photo ID is required, and entry is through building security.",
        "Overflow hearing space across from City Hall.",
    ),
    "remote": Venue(
        "remote",
        "Remote hearing (Zoom)",
        None,
        "Speaking requires advance registration on the Council's Register to Testify form. "
        "Watching requires no registration and runs on the Council livestream.",
        "Remote participants are subject to the Council's Remote Attendance Policy.",
    ),
    "offsite": Venue(
        "offsite",
        "Off-site hearing",
        None,
        "The exact address and entry instructions are in the agenda PDF.",
        "Occasionally the Council sits closer to affected residents — a borough hall, school, "
        "library or state office building.",
    ),
}

_DASHES = re.compile(r"[‐-―−~]")
_JOINTLY = re.compile(r"\bjointly with the committee on\b.*$", re.IGNORECASE)


def _clean(raw: str) -> str:
    text = _DASHES.sub("-", raw)
    # The joint-hearing note rides along in the location cell, so every joint hearing
    # would otherwise match no venue.
    text = _JOINTLY.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_location(raw: str | None) -> tuple[Venue, str]:
    """Map a raw location string to (venue, attendance_mode)."""
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
        # "Council Committee Room - City Hall" names both, so "committee" wins.
        if re.search(r"committee", text, re.IGNORECASE):
            return VENUES["city-hall-committee"], mode
        if re.search(r"chamber", text, re.IGNORECASE):
            return VENUES["city-hall-chambers"], mode
        return VENUES["city-hall-committee"], mode

    return VENUES["offsite"], mode
