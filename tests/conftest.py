from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def fixtures() -> Path:
    return FIXTURES


@pytest.fixture(scope="session")
def calendar_html() -> str:
    """A real Legistar calendar trimmed to 60 dated rows.

    `__VIEWSTATE` was replaced with a marker rather than kept: it is hundreds of
    kilobytes, this parser never reads it, and its absence in the fixture
    documents that we never POST it for pagination.
    """
    return (FIXTURES / "calendar_60rows.html").read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def district_page_html() -> dict[int, str]:
    """Real district pages for the observed pathological cases.

    1  — the reference layout, all fields present
    3  — no committees published (one of 3, 5, 9, 14, 25, 26)
    35 — no `Office Hours` line
    51 — no `Office Hours`, and "250 Broadway, 1551" with no "Suite"
    """
    pages = {}
    for number in (1, 3, 35, 51):
        path = FIXTURES / "district_pages" / f"{number}.html"
        if path.exists():
            pages[number] = path.read_text(encoding="utf-8")
    return pages
