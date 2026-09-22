"""Parsing council.nyc.gov/district-N/ — the only source for district offices.

No open dataset publishes council district office addresses or phone numbers, so
these 51 WordPress pages are it. `wp-json` is not a substitute: it reports
District 1's office as "101 Lafayette St, 9th Floor" while the rendered page says
"65 East Broadway".

We read the page by its visible-text structure, which is stable in *shape*:

    District 1
    Christopher Marte
    The Lower East Side, Chinatown, ...      <- neighbourhoods
    ...bio...
    Committees
    Committee on Public Housing
    ...
    (Chair)                                  <- role attaches to the line above
    Caucuses
    ...
    District Office
    65 East Broadway
    New York, NY 10002
    Phone: 212-587-3159
    Legislative Office
    250 Broadway, Suite 1749
    ...
    District1@council.nyc.gov

But **every field is independently optional**, which was verified and contradicts
an earlier assumption that the 51 pages were identical: `Office Hours` is absent
on D35 and D51; there are three phone-label conventions
(`Phone: 718-260-9191`, `(718) 984-5151 phone`, `phone 1`); two email conventions
(`District35@…`, `Morano@…`); D51 writes `250 Broadway, 1551` with no "Suite";
and committees are absent for districts 3, 5, 9, 14, 25 and 26. So nothing here
raises on a missing field — it records the gap in `missing` and the build reports
it. A silent blank where an office address belongs is the worst outcome, because
someone travels to it.
"""

from __future__ import annotations

import re

from ..model import Committee, Office
from ..text import text_lines
from ..urls import safe_url

__all__ = ["parse_district_page", "to_lines"]

_BLOCK_TAGS = re.compile(r"</?(?:br|p|div|li|tr|td|th|h[1-6]|table|section)\b[^>]*>", re.IGNORECASE)

_ROLE = re.compile(r"^\((Chair|Co-Chair|Vice Chair|Chairperson)\)$", re.IGNORECASE)
_TRAILING_ROLE = re.compile(r"\((Chair|Co-Chair|Vice Chair|Chairperson)\)\s*$", re.IGNORECASE)
_COMMITTEE = re.compile(r"^(Committee on |Subcommittee on |Select Committee)", re.IGNORECASE)
_SECTION_END = re.compile(
    r"^(Caucuses|Biography|Staff Directory|Community Events|Letters from|District Office"
    r"|FY\d{4} Budget|Subscribe|Media Inquiries|Adopt a Tree)",
    re.IGNORECASE,
)
# Three observed phone conventions.
_PHONE = re.compile(r"^(?:Phone\s*\d*\s*:\s*(.+)|(.+?)\s+phone\s*\d*)$", re.IGNORECASE)
_FAX = re.compile(r"^(?:Fax\s*:\s*(.+)|(.+?)\s+fax)$", re.IGNORECASE)
_HOURS = re.compile(r"^Office Hours\s*:\s*(.+)$", re.IGNORECASE)
_ZIP = re.compile(r",\s*(?:NY|New York)\s*,?\s*\d{5}", re.IGNORECASE)
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@council\.nyc\.gov", re.IGNORECASE)
# Present on every page's footer, so not the district's own address.
_SITEWIDE_EMAIL = re.compile(
    r"^(press|correspondence|EEOOfficer|translationservice|hearings)@", re.IGNORECASE
)


def to_lines(html_text: str) -> list[str]:
    """Flatten a page to its visible text lines.

    Delegates to `text.text_lines`, which splits on block boundaries *inside* the
    parser. An earlier version split the raw HTML first and then stripped each
    fragment, which meant a `<script>` open tag and its body landed on separate
    lines — the skip logic never fired and jQuery and CSS were parsed as visible
    text.
    """
    return text_lines(html_text)


def _parse_committees(lines: list[str]) -> tuple[Committee, ...]:
    """ "Committees" also appears twice in the site navigation, so anchor on the
    occurrence actually followed by a committee name."""
    start = -1
    for index, line in enumerate(lines):
        if (
            line.lower() == "committees"
            and index + 1 < len(lines)
            and _COMMITTEE.match(lines[index + 1])
        ):
            start = index + 1
            break
    if start == -1:
        return ()

    found: list[Committee] = []
    for line in lines[start:]:
        if _SECTION_END.match(line):
            break
        # A role can arrive two ways, and both occur in the real pages: on its
        # own line below the committee, or as a trailing parenthetical on the
        # same line ("Subcommittee on Landmarks … (Chair)").
        if _ROLE.match(line):
            if found:
                found[-1] = Committee(found[-1].name, line.strip("()"))
            continue
        if _COMMITTEE.match(line):
            if trailing := _TRAILING_ROLE.search(line):
                found.append(Committee(line[: trailing.start()].strip(), trailing.group(1)))
            else:
                found.append(Committee(line))
    return tuple(found)


def _parse_office(lines: list[str], heading_index: int, label: str) -> Office | None:
    if heading_index == -1:
        return None
    address_parts: list[str] = []
    phone = fax = hours = None
    address_done = False

    for line in lines[heading_index + 1 : heading_index + 14]:
        if re.match(
            r"^(District Office|Legislative Office|Visit the Council|Send Email)$", line, re.I
        ):
            break
        if match := _PHONE.match(line):
            phone = phone or (match.group(1) or match.group(2) or "").strip()
            continue
        if match := _FAX.match(line):
            fax = fax or (match.group(1) or match.group(2) or "").strip()
            continue
        if match := _HOURS.match(line):
            hours = match.group(1).strip()
            continue
        # The city/state/ZIP line ends the address, but scanning must continue —
        # Phone, Fax and Office Hours all come *after* it. Breaking here (an
        # earlier bug) lost the phone number on every district.
        if not address_done:
            address_parts.append(line)
            if _ZIP.search(line):
                address_done = True

    if not address_parts and not phone:
        return None
    return Office(
        label=label,
        address=", ".join(address_parts) or None,
        phone=phone or None,
        fax=fax,
        hours=hours,
    )


def parse_district_page(number: int, html_text: str | None) -> dict:
    """Extract one district's facts. Never raises; reports gaps in `missing`."""
    url = f"https://council.nyc.gov/district-{number}/"
    result: dict = {
        "district": number,
        "member_name": None,
        "neighborhoods": None,
        "committees": (),
        "offices": (),
        "email": None,
        "page_url": safe_url(url),
        "missing": [],
    }
    if not html_text:
        result["missing"] = ["page"]
        return result

    lines = to_lines(html_text)

    heading = next((i for i, line in enumerate(lines) if line.lower() == f"district {number}"), -1)
    if heading != -1:
        candidate = lines[heading + 1] if heading + 1 < len(lines) else None
        # A vacant seat has no name line; guard against picking up the next heading.
        if candidate and len(candidate) < 60 and not candidate.lower().startswith("district "):
            result["member_name"] = candidate
        hood = lines[heading + 2] if heading + 2 < len(lines) else None
        if hood and len(hood) > 15 and not hood.lower().startswith("council member"):
            result["neighborhoods"] = hood

    result["committees"] = _parse_committees(lines)

    offices = []
    for pattern, label in (
        (r"^District Office$", "District office"),
        (r"^Legislative Office$", "Legislative office"),
    ):
        index = next((i for i, line in enumerate(lines) if re.match(pattern, line, re.I)), -1)
        if office := _parse_office(lines, index, label):
            offices.append(office)
    result["offices"] = tuple(offices)

    # Prefer the district's own mailbox. Searching raw HTML and taking the first
    # hit picked up a staff member's address (`ckelmar@` on District 1), because
    # staff emails appear in markup above the office block. So: look only at
    # visible text, and prefer the `district<N>@` convention before falling back
    # to the surname convention some members use (`Morano@` on District 51).
    visible = " ".join(lines)
    preferred = re.compile(rf"\bdistrict{number}@council\.nyc\.gov\b", re.IGNORECASE)
    if match := preferred.search(visible):
        result["email"] = match.group(0)
    else:
        for match in _EMAIL.finditer(visible):
            if not _SITEWIDE_EMAIL.match(match.group(0)):
                result["email"] = match.group(0)
                break

    result["missing"] = [
        name
        for name, value in (
            ("member_name", result["member_name"]),
            ("neighborhoods", result["neighborhoods"]),
            ("committees", result["committees"] or None),
            ("offices", result["offices"] or None),
            ("email", result["email"]),
        )
        if not value
    ]
    return result
