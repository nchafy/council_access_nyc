"""The shapes that reach a template.

Deliberately plain dataclasses with no behaviour. Every string in here has
already been through `text.strip_tags` at ingest, so a renderer only has to
escape; and every URL has already been through `urls.safe_url`, so a None means
"no link" rather than "link we have not checked yet".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

__all__ = ["Committee", "District", "Manifest", "Meeting", "Member", "Office", "Venue"]


@dataclass(frozen=True, slots=True)
class Venue:
    id: str
    name: str
    address: str | None
    entry: str | None
    note: str | None = None


@dataclass(frozen=True, slots=True)
class Meeting:
    committee: str
    date: date
    #: None when the source says "Deferred" or publishes no time. Never a guess.
    start_time: str | None
    #: "scheduled" | "deferred" | "time_not_published"
    time_state: str
    #: "in_person" | "hybrid" | "remote"
    attendance_mode: str
    venue: Venue
    raw_location: str
    topic: str | None
    detail_url: str | None
    agenda_url: str | None
    minutes_url: str | None
    #: Provable lower bound on the written-testimony window: start + 72h. The
    #: real deadline is 72h after *adjournment*, which is never published, and
    #: adjournment is always at or after the start — so this is always inside it.
    written_safe_until: datetime | None
    #: Three business days before the hearing, for ASL/CART and interpretation.
    accommodation_by: date | None

    @property
    def is_past(self) -> bool:
        return self.date < date.today()


@dataclass(frozen=True, slots=True)
class Office:
    label: str
    address: str | None
    phone: str | None
    fax: str | None = None
    hours: str | None = None


@dataclass(frozen=True, slots=True)
class Committee:
    name: str
    role: str = "Member"


@dataclass(frozen=True, slots=True)
class Member:
    name: str
    #: "filled" | "vacant" — a vacancy is a designed state, not an error.
    seat_status: str
    email: str | None
    page_url: str | None
    offices: tuple[Office, ...] = ()
    committees: tuple[Committee, ...] = ()
    term_start: date | None = None
    term_end: date | None = None
    #: True when council.nyc.gov names a member but the open dataset has no
    #: current term for the seat. The scraped page is the fresher source — a
    #: special election reaches it weeks before Socrata — so we show the member
    #: and disclose that the official dataset has not caught up. District 3 is
    #: the live example: Bottcher's term ends 2026-02-03 with no successor row.
    seat_conflict: bool = False


@dataclass(frozen=True, slots=True)
class DistrictBoard:
    """A community board covering part of this council district.

    `share` is the approximate fraction of the council district's sampled land
    area inside this board, from the committed crosswalk. It orders the list and
    is shown as approximate; it is not a precise areal measurement.
    """

    code: str
    label: str
    share: float
    neighborhoods: str | None
    address: str | None
    phone: str | None
    email: str | None
    email_suppressed: str | None
    website: str | None
    board_meeting: str | None
    cabinet_meeting: str | None


@dataclass(frozen=True, slots=True)
class District:
    number: int
    neighborhoods: str | None
    member: Member | None
    boards: tuple[DistrictBoard, ...] = ()
    #: Per-field record of where each fact came from and when it was seen, so a
    #: page can show provenance without the renderer guessing.
    provenance: dict[str, str] = field(default_factory=dict)
    #: Fields the scrape could not find. Surfaced, never silently blank.
    missing: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Manifest:
    """Per-source freshness. The client compares these to now; the build never
    bakes in a 'fresh' or 'stale' boolean (outline §2.12)."""

    sources: dict[str, dict[str, str | int]]
    built_at: datetime
    #: The last date we can see a meeting for — stated literally, never implied
    #: to be complete.
    calendar_window_end: date | None
