"""Community boards from NYC Open Data `ruf7-3wgc`.

Policy, measured and amended: publish any well-formed office email, never render
`cb_chair` or `cb_district_manager`, and take the district join from geometry. R30 in
`council-access-project-outline.md` carries the counts; CLAUDE.md carries the rule.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from ..text import strip_tags
from ..urls import ALLOWED_HOSTS, host_allowed, safe_url

__all__ = ["JOINT_INTEREST_AREAS", "Board", "email_policy", "load_boards", "looks_person_named"]

#: `boro_cd` codes in the geometry that are not boards: parks, airports and cemeteries.
JOINT_INTEREST_AREAS = frozenset(
    {"164", "226", "227", "228", "355", "356", "480", "481", "482", "483", "484", "595"}
)

_BOROUGH_PREFIX = {
    "1": "Manhattan",
    "2": "Bronx",
    "3": "Brooklyn",
    "4": "Queens",
    "5": "Staten Island",
}

_EMAIL_SHAPE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")

#: `cb_office_address` runs street and city together with no separator, so line 2 has to
#: be inserted before this tail. tests/unit/test_boards.py carries the cases, including the
#: addresses with no recognisable tail, which stay in source order.
_CITY_TAIL = re.compile(
    r"\s*((?:Manhattan|New\s+York|Brooklyn|Bronx|Queens|Staten\s+Island|Kew\s+Gardens)"
    r"\s*,?\s*N\.?\s*Y\.?\s*,?\s*(?:\d{5}(?:-\d{4})?)?\s*)$",
    re.IGNORECASE,
)
_NON_ALPHA = re.compile(r"[^a-z]")


class Board:
    """One community board's contact facts. Frozen by convention, not enforced."""

    __slots__ = (
        "address",
        "board_meeting",
        "borough",
        "cabinet_meeting",
        "code",
        "email",
        "email_suppressed",
        "neighborhoods",
        "number",
        "phone",
        "website",
        "website_unlinked",
    )

    def __init__(self, **kwargs: object) -> None:
        for slot in self.__slots__:
            setattr(self, slot, kwargs.get(slot))

    @property
    def label(self) -> str:
        return f"{self.borough} Community Board {self.number}"


def _surnames(*values: str | None) -> set[str]:
    """Surname-ish tokens from a person-name field, for the suppression check.

    Tokens under four characters are ignored: "lee" or "ng" as a substring would
    suppress `college@` and `info@`.
    """
    tokens: set[str] = set()
    for value in values:
        for raw in re.split(r"[\s,.;/&()-]+", strip_tags(value or "")):
            token = _NON_ALPHA.sub("", raw.lower())
            if len(token) >= 4:
                tokens.add(token)
    return tokens


def email_policy(email: str | None) -> tuple[str | None, str | None]:
    """Return (publishable_email, suppression_reason).

    Exactly one of the two is None. The reason is kept so the UI can say why a
    contact is absent instead of rendering a blank.
    """
    candidate = strip_tags(email or "").strip()
    if not candidate:
        return None, "no email published"
    if not _EMAIL_SHAPE.match(candidate):
        return None, "published value is not a usable address"

    return candidate, None


def looks_person_named(email: str, chair: str | None, district_manager: str | None) -> bool:
    """Whether an address's local part carries a name from this row's own people.

    Unused by `email_policy`: R30 went the other way on measurement. Retained because it
    is the mechanism a reversal would need, and it produced the count R30 rests on.
    """
    local = _NON_ALPHA.sub("", email.split("@", 1)[0].lower())
    return any(surname in local for surname in _surnames(chair, district_manager))


def _compose_address(main: str, line_two: str) -> str | None:
    """Join the two address fields in postal order: "350 Jay Street Brooklyn, NY 11201" +
    "8th Floor" becomes "350 Jay Street, 8th Floor, Brooklyn, NY 11201"."""
    main = (main or "").strip().rstrip(",")
    line_two = (line_two or "").strip().rstrip(",")
    if not main:
        return line_two or None
    if not line_two:
        return main

    match = _CITY_TAIL.search(main)
    if match:
        street = main[: match.start()].strip().rstrip(",")
        return f"{street}, {line_two}, {match.group(1).strip()}"
    return f"{main}, {line_two}"


def load_boards(path: Path) -> dict[str, Board]:
    """Load boards keyed on the borough-prefixed code (`109` = Manhattan CB 9).

    `community_board` alone is ambiguous — four boroughs have a Community Board 9 — so
    the key is `community_board_1`, the same code the geometry publishes as `boro_cd`.
    """
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    boards: dict[str, Board] = {}
    for row in rows:
        code = strip_tags(row.get("community_board_1")).strip()
        if not code or len(code) != 3:
            continue

        email, reason = email_policy(row.get("cb_office_email"))

        address = _compose_address(
            strip_tags(row.get("cb_office_address")),
            strip_tags(row.get("cb_address_line_2")),
        )
        boards[code] = Board(
            code=code,
            borough=strip_tags(row.get("borough")) or _BOROUGH_PREFIX.get(code[0], ""),
            number=code[1:].lstrip("0") or code[1:],
            neighborhoods=strip_tags(row.get("neighborhoods")) or None,
            address=address,
            phone=strip_tags(row.get("cb_office_phone")) or None,
            email=email,
            email_suppressed=reason,
            website=_board_website(row.get("cb_website")),
            website_unlinked=_board_website_hostname(row.get("cb_website")),
            # Verbatim: parsing "Second Tuesday, 7:45pm" into a date would invent a
            # precision the source does not have.
            board_meeting=strip_tags(row.get("cb_board_meeting")) or None,
            cabinet_meeting=strip_tags(row.get("cb_cabinet_meeting")) or None,
        )
    return boards


#: Every path on the City's old hostname 301s to `www.nyc.gov` (verified 2026-09-29), so
#: normalising it widens nothing.
_NYC_GOV_ALIASES = {"www1.nyc.gov": "www.nyc.gov"}


def _board_website_hostname(value: object) -> str | None:
    """The bare hostname of a board site we decline to link, for display as text."""
    if _board_website(value) is not None:
        return None
    if isinstance(value, dict):
        value = value.get("url")
    candidate = strip_tags(str(value or "")).strip()
    try:
        host = urlsplit(candidate).hostname
    except ValueError:
        return None
    return host.lower() if host else None


def _board_website(value: object) -> str | None:
    """The board's own site, preferring an official nyc.gov URL.

    `cb_website` arrives from Socrata as `{"url": "..."}`, not a string
    (docs/OBSERVATIONS.md, 2026-09-29).
    """
    if isinstance(value, dict):
        value = value.get("url")
    candidate = strip_tags(str(value or "")).strip()
    if not candidate:
        return None

    candidate = "".join(character for character in candidate if character.isprintable())
    try:
        parts = urlsplit(candidate)
    except ValueError:
        return None
    # Credentials are a sign of tampering, so refuse rather than strip them.
    if parts.username or parts.password:
        return None

    host = (parts.hostname or "").lower()
    if host in _NYC_GOV_ALIASES or host in ALLOWED_HOSTS:
        # The City publishes some of its own URLs as http; nyc.gov serves https.
        return safe_url(
            urlunsplit(("https", _NYC_GOV_ALIASES.get(host, host), parts.path, parts.query, ""))
        )
    if host_allowed(host) and parts.scheme.lower() == "https":
        return candidate
    # An independent domain is named as text by `_board_website_hostname`, never linked.
    return None
