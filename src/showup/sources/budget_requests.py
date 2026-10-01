"""Community board budget requests from NYC Open Data `vn4m-mk4t` (OMB).

Four upstream facts, each recorded in docs/OBSERVATIONS.md on 2026-09-30, shape every
decision below: `boro` is alphabetical by borough acronym, the newest `publication` is
dated in the future, `priority` repeats within a board, and `response` cannot be bucketed.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from datetime import date, datetime
from pathlib import Path

from ..model import BoardBudgetRequests, BudgetRequest
from ..text import strip_tags

__all__ = [
    "BOARD_CODE_BY_BORO",
    "CATEGORY_BY_SUFFIX",
    "BudgetRequestError",
    "load_budget_requests",
    "select_publication",
]

#: `boro` runs BX, BK, MN, QN, SI — alphabetical by acronym, not the standard NYC code.
#: Mapped naively it swaps Manhattan, the Bronx and Brooklyn without any error.
BOARD_CODE_BY_BORO = {"1": "2", "2": "3", "3": "1", "4": "4", "5": "5"}

#: The tracking code's suffix is the budget category `priority` is ranked inside.
CATEGORY_BY_SUFFIX = {"C": "Capital", "CS": "Capital support", "E": "Expense"}

#: boro+board, fiscal year, a sequence number, then the category suffix.
_TRACKING_CODE = re.compile(r"^(\d{3})(\d{4})(\d{2})([A-Z]{1,2})$")


class BudgetRequestError(RuntimeError):
    """The register is present but cannot be served honestly. The build must stop."""


def _as_date(stamp: str) -> date | None:
    try:
        return datetime.strptime(stamp, "%Y%m%d").date()
    except ValueError:
        return None


def select_publication(stamps: Iterable[str], today: date) -> date:
    """The newest edition not dated in the future, failing closed when none qualifies."""
    published = sorted(
        parsed for stamp in stamps if (parsed := _as_date(str(stamp))) and parsed <= today
    )
    if not published:
        raise BudgetRequestError(
            f"vn4m-mk4t has no publication dated on or before {today.isoformat()}. "
            "Refusing to serve a future-dated register."
        )
    return published[-1]


def _board_code(row: dict) -> str | None:
    """The repo's borough-prefixed board code, or None when the row does not name one."""
    prefix = BOARD_CODE_BY_BORO.get(strip_tags(row.get("boro")).strip())
    board = strip_tags(row.get("board")).strip()
    if prefix is None or not board.isdigit():
        return None
    return prefix + board.zfill(2)


def _category(tracking_code: str) -> str | None:
    match = _TRACKING_CODE.match(tracking_code)
    return CATEGORY_BY_SUFFIX.get(match.group(4)) if match else None


def _fiscal_year(rows: list[dict]) -> str | None:
    """The one fiscal year this edition covers, or None when it does not agree on one."""
    years = {
        match.group(2)
        for row in rows
        if (match := _TRACKING_CODE.match(strip_tags(row.get("tracking_code")).strip()))
    }
    return years.pop() if len(years) == 1 else None


def _request(row: dict) -> BudgetRequest:
    """Every text field stripped of tags: register text is upstream text (§4.1)."""
    tracking_code = strip_tags(row.get("tracking_code")).strip()
    return BudgetRequest(
        priority=strip_tags(row.get("priority")).strip(),
        category=_category(tracking_code),
        tracking_code=tracking_code,
        request=strip_tags(row.get("request")).strip() or None,
        agency=strip_tags(row.get("responsible_agency")).strip() or None,
        explanation=strip_tags(row.get("explanation")).strip() or None,
        response=strip_tags(row.get("response")).strip() or None,
    )


def load_budget_requests(
    path: Path, *, today: date | None = None
) -> dict[str, BoardBudgetRequests]:
    """Per board code, the selected edition and that board's requests in priority order.

    A missing or empty register is an absence the page states; a register with nothing
    but future-dated editions is a refusal.
    """
    path = Path(path)
    if not path.exists():
        return {}
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not rows:
        return {}

    published = select_publication(
        (row.get("publication") or "" for row in rows), today or date.today()
    )
    stamp = published.strftime("%Y%m%d")
    edition = [row for row in rows if strip_tags(row.get("publication")).strip() == stamp]
    fiscal_year = _fiscal_year(edition)

    by_code: dict[str, list[BudgetRequest]] = {}
    for row in edition:
        code = _board_code(row)
        if code is not None:
            by_code.setdefault(code, []).append(_request(row))

    return {
        code: BoardBudgetRequests(
            publication=published,
            fiscal_year=fiscal_year,
            requests=tuple(sorted(requests, key=lambda r: (r.priority, r.tracking_code))),
        )
        for code, requests in by_code.items()
    }
