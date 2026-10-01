"""Community boards from NYC Open Data `ruf7-3wgc`.

Community boards matter to this product more than their size suggests: they are
the genuinely local body, they meet on a predictable monthly cadence (unlike
Council committees, which are called by their chair), and for a land-use or
quality-of-life complaint they are usually the right room. Residents routinely
confuse them with council districts, so the district page names both and says
which is which.

TWO THINGS THIS MODULE DELIBERATELY DOES NOT DO

**It does not join on `council_district`.** That column exists and is wrong for
this purpose — see the note in `geo.py`. The join comes from geometry.

**It does not render `cb_chair` or `cb_district_manager`.** Those are named
private-ish individuals; building a searchable name-to-contact index out of a
dataset is an aggregation harm even when every field in it is already public.
The board office is an institution with a duty to be contacted; its chair is a
volunteer. We publish the institution.

ON THE OFFICE EMAIL, AND A DEVIATION FROM R30
The plan's R30 said to display `cb_office_email` only when it matches
`^(mn|bx|bk|qn|si)\\d{2}@cb\\.nyc\\.gov$`. The data says that rule is too strict:
only **31 of 59** match, and the rest include addresses on the board's *own*
domain — `info@brooklyncb6.org`, `info@cb8m.com`, `bronxcb6@bronxcb6.org` — which
are institutional in every sense except hostname.

A middle rule was tried and also rejected: suppress any address whose local part
contains a surname from the row's own chair or district-manager field. That caught
12 boards, and inspecting them settled the question — every one is the district
manager's *work* address on an official domain (11 on `cb.nyc.gov`, one on
`qcb13.org`), which the City publishes on an open data portal specifically so that
residents can contact the board. Withholding a public employee's published work
email removes the only contact route for a fifth of the city's boards and protects
nothing that is not already public and intended to be.

So: **publish any well-formed published address, and never render `cb_chair` or
`cb_district_manager`.** The harm worth avoiding is building a searchable
name-to-mailbox index out of an open dataset; that comes from the *pairing*, and
the pairing is what we decline to do. The address is labelled as the board
office's, because functionally that is what it is. `cb_website` is always offered
alongside as a second route.

The name-detection helper is kept below, unused by the policy, because the
judgement above is a product decision that could be revisited — and if it is, the
mechanism should not have to be rediscovered.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from ..text import strip_tags
from ..urls import ALLOWED_HOSTS, host_allowed, safe_url

__all__ = ["JOINT_INTEREST_AREAS", "Board", "email_policy", "load_boards", "looks_person_named"]

#: `boro_cd` codes in the community-district geometry that are not boards at all:
#: parks, airports and cemeteries filed as "joint interest areas". 71 features
#: minus these 12 is exactly the 59 real boards.
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

#: The city/state/ZIP tail of an address. `cb_office_address` runs the street and
#: the city together with no separator ("350 Jay Street Brooklyn, NY 11201"), and
#: `cb_address_line_2` holds the floor or suite — so a naive join puts the floor
#: after the ZIP. This splits the tail off so line 2 lands where a postal address
#: expects it. 16 of 59 boards have a line 2.
#: Handles "NY", "N.Y." and "N. Y.", with or without a ZIP. Four boards still
#: come out in non-postal order because their source address has no recognisable
#: city/state tail at all ("30-50 Whitestone Expressway Flushing/Whitestone" +
#: "Suite 205"). Those render as readable, correct addresses in a slightly odd
#: order, which is a better outcome than a regex tuned until it starts guessing.
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

    Tokens shorter than four characters are ignored: matching "lee" or "ng" as a
    substring would suppress `college@`, `info@` and most role mailboxes. The
    trade is deliberate — a very short surname may slip through, and that is
    better than withholding half the city's contacts.
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

    Not used by `email_policy` — see the module docstring for why that judgement
    went the other way. Retained because it is the mechanism any future reversal
    would need, and because the count it produces (12 of 59) is the evidence the
    decision rests on.
    """
    local = _NON_ALPHA.sub("", email.split("@", 1)[0].lower())
    return any(surname in local for surname in _surnames(chair, district_manager))


def _compose_address(main: str, line_two: str) -> str | None:
    """Join the two address fields in postal order.

    "350 Jay Street Brooklyn, NY 11201" + "8th Floor" becomes
    "350 Jay Street, 8th Floor, Brooklyn, NY 11201" rather than stranding the
    floor after the ZIP.
    """
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

    `community_board` alone is ambiguous — four boroughs each have a "Community
    Board 9" — so `community_board_1` is the join key, and it is the same code the
    geometry file publishes as `boro_cd`.
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
            # Reproduced verbatim. "Second Tuesday, 7:45pm" is the board's own
            # wording and parsing it into a date would invent a precision the
            # source does not have — boards move meetings without updating this.
            board_meeting=strip_tags(row.get("cb_board_meeting")) or None,
            cabinet_meeting=strip_tags(row.get("cb_cabinet_meeting")) or None,
        )
    return boards


#: `www1.nyc.gov` is the City's old hostname; every path on it 301s to `www.nyc.gov`,
#: verified 2026-09-29. It is the same publisher, so normalising it is not a widening of
#: the allowlist — refusing it was just a miss.
_NYC_GOV_ALIASES = {"www1.nyc.gov": "www.nyc.gov"}

#: Which hosts may be linked lives in `urls.py` (`host_allowed`): the City's own
#: domains only. A board on its own domain is named as text, because a lapsed domain
#: can be re-registered by anyone and the City's dataset keeps pointing at it.


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

    `cb_website` arrives from Socrata as `{"url": "..."}`, not a string. Reading it as a
    string produced `"{'url': 'https://...'}"`, which failed every check — so no board
    page carried a website link at all, while the copy told readers to go there.
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
    # Credentials in a published civic URL are a sign of tampering, not a quirk to clean
    # up: rebuilding without them would accept a crafted value as if it were the City's.
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
    # An independent domain is named but not linked: a board that
    # lets its own domain lapse cannot un-publish the row that points at it.
    return None
