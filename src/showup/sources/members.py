"""Current Council Members from NYC Open Data `uvw5-9znb`.

558 rows spanning 1999 to the present, one per member-term. "Current" is a
predicate over term windows rather than a flag in the data:

    term_start <= today <= term_end

A district with no matching row is **vacant**, which is a designed result and not
an error — the page names the vacancy and still shows every other fact, because a
resident of a vacant district needs the committee and hearing information more
than most, not less.

`term_end` is authoritative over any list of "who holds the seat" we could
hardcode, so nothing here is hardcoded.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

from ..text import strip_tags

__all__ = ["current_by_district", "load_members"]


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    # Socrata emits "2026-01-01T00:00:00.000"; take the date part only.
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except ValueError:
        return None


def load_members(path: Path) -> list[dict]:
    """Read the raw Socrata rows, normalising only types and whitespace."""
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    members: list[dict] = []
    for row in rows:
        district_raw = row.get("district")
        try:
            district = int(district_raw)
        except (TypeError, ValueError):
            # Rows exist for the Public Advocate and other non-district seats.
            continue
        members.append(
            {
                "name": strip_tags(row.get("name")),
                "member_id": strip_tags(row.get("council_member_id")),
                "district": district,
                "term_start": _parse_date(row.get("term_start")),
                "term_end": _parse_date(row.get("term_end")),
            }
        )
    return members


def current_by_district(members: list[dict], today: date | None = None) -> dict[int, dict]:
    """Map district number -> the member holding it today.

    Where terms overlap (a mid-term appointment recorded alongside the outgoing
    member), the later `term_start` wins, because that is the more recent fact.
    """
    now = today or date.today()
    current: dict[int, dict] = {}
    for member in members:
        start, end = member["term_start"], member["term_end"]
        if start and start > now:
            continue
        if end and end < now:
            continue
        district = member["district"]
        existing = current.get(district)
        if existing is None or (
            member["term_start"]
            and existing["term_start"]
            and member["term_start"] > existing["term_start"]
        ):
            current[district] = member
    return current
