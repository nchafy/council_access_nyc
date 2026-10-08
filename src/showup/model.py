"""The shapes that reach a template: plain dataclasses, no behaviour.

Every string has already been through `text.strip_tags` and every URL through
`urls.safe_url`, so a `None` URL means "no link", not "not checked yet".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

__all__ = [
    "BOARD_COUNT",
    "DISTRICT_COUNT",
    "BoardBudgetRequests",
    "BudgetRequest",
    "Committee",
    "District",
    "Manifest",
    "Meeting",
    "Member",
    "Office",
    "Venue",
]

#: How many `District`s and `DistrictBoard`s New York City has. Facts about the city, not
#: thresholds: the fetch invariants, the crosswalk guards and the build all count to these.
DISTRICT_COUNT = 51
BOARD_COUNT = 59


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
    #: None when the source says "Deferred" or publishes no time; never a guess.
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
    #: start + 72h. A provable lower bound: adjournment is never published and never earlier.
    written_safe_until: datetime | None
    #: Three business days before the hearing, for ASL/CART and interpretation.
    accommodation_by: date | None


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
    #: "filled" | "vacant"
    seat_status: str
    email: str | None
    page_url: str | None
    offices: tuple[Office, ...] = ()
    committees: tuple[Committee, ...] = ()
    term_start: date | None = None
    term_end: date | None = None
    #: council.nyc.gov names a member the open dataset has no current term for. The scrape
    #: is the fresher source, so the member renders and the page discloses the disagreement.
    seat_conflict: bool = False


@dataclass(frozen=True, slots=True)
class DistrictBoard:
    """A community board covering part of this council district.

    `share` is the crosswalk's approximate fraction of sampled land area, not a precise
    areal measurement. It orders the list and is rendered as approximate.
    """

    code: str
    label: str
    borough_name: str
    share: float
    neighborhoods: str | None
    address: str | None
    phone: str | None
    email: str | None
    email_suppressed: str | None
    website: str | None
    board_meeting: str | None
    cabinet_meeting: str | None
    #: Hostname rendered as text, not linked: the City cannot vouch for a board's own domain.
    website_unlinked: str | None = None


@dataclass(frozen=True, slots=True)
class BudgetRequest:
    """One line a community board filed with OMB, in the board's and the agency's words."""

    priority: str
    #: Capital, capital support or expense. None when the tracking code does not say.
    category: str | None
    tracking_code: str
    request: str | None
    agency: str | None
    explanation: str | None
    response: str | None


@dataclass(frozen=True, slots=True)
class BoardBudgetRequests:
    """One board's requests from one edition of the register, with that edition pinned."""

    publication: date
    #: From the tracking codes, when the whole edition agrees on one year.
    fiscal_year: str | None
    requests: tuple[BudgetRequest, ...]


@dataclass(frozen=True, slots=True)
class District:
    number: int
    neighborhoods: str | None
    member: Member | None
    boards: tuple[DistrictBoard, ...] = ()
    #: Per field, where the fact came from and when it was seen.
    provenance: dict[str, str] = field(default_factory=dict)
    missing: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Manifest:
    """Per-source freshness. The client compares these to now; the build bakes in no
    'fresh' or 'stale' boolean (outline §2.12)."""

    sources: dict[str, dict[str, str | int]]
    built_at: datetime
    #: The last date a meeting is visible for. Stated literally, never implied complete.
    calendar_window_end: date | None
