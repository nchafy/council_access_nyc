from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
REPO_ROOT = Path(__file__).resolve().parents[1]

# The a11y and perf gates live in `scripts/` as operator tools; the tests drive that
# same code rather than a second copy, so CI and `make axe` can never disagree.
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))


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


# A plain function with two fixtures over it, because the same cache is needed with two
# lifetimes: per-session for the browser gates, per-test for the build tests.
def write_raw_cache(raw: Path, calendar_html: str, district_page_html: dict[int, str]) -> Path:
    """Populate `raw` with a cache that clears every source floor. Returns `raw`."""
    (raw / "legistar_calendar.html").write_text(calendar_html, encoding="utf-8")

    # All 51 pages must be present to clear the district_pages floor; reuse the
    # four real fixtures cyclically for the rest.
    available = sorted(district_page_html)
    pages = {str(n): district_page_html[available[(n - 1) % len(available)]] for n in range(1, 52)}
    (raw / "district_pages.json").write_text(json.dumps(pages), encoding="utf-8")

    members = [
        {
            "name": f"Member {n}",
            "council_member_id": str(1000 + n),
            "district": str(n),
            "term_start": "2026-01-01T00:00:00.000",
            "term_end": "2029-12-31T00:00:00.000",
        }
        for n in range(1, 52)
    ]
    # Pad past the members floor with historical rows, as the real dataset has.
    members += [
        {
            "name": f"Former Member {i}",
            "council_member_id": str(2000 + i),
            "district": str((i % 51) + 1),
            "term_start": "2014-01-01T00:00:00.000",
            "term_end": "2017-12-31T00:00:00.000",
        }
        for i in range(300)
    ]
    (raw / "members.json").write_text(json.dumps(members), encoding="utf-8")

    # Real community-board rows: 59 of them, needed to clear the boards floor and
    # to carry the real chair / district-manager names the privacy test checks.
    # From tests/fixtures, NOT etl/raw — the cache is gitignored, and reading it
    # here made these tests pass locally and error in CI.
    shutil.copy2(FIXTURES / "community_boards.json", raw / "community_boards.json")

    # Synthetic district geometry: 51 disjoint squares. The build needs 51 features
    # to emit site/data/districts.geo.json, and nothing here depends on the shapes
    # being real — the accuracy of the real simplification is covered separately by
    # tests/unit/test_geo.py::TestSimplifiedGeometryAgrees, which runs against the
    # actual DCP file. Committing a 3.8 MB geojson to satisfy a smoke test would be
    # the wrong trade.
    features = []
    for n in range(1, 52):
        x0 = -74.3 + (n - 1) * 0.02
        y0 = 40.5
        features.append(
            {
                "type": "Feature",
                "properties": {"coundist": str(n)},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [x0, y0],
                            [x0 + 0.018, y0],
                            [x0 + 0.018, y0 + 0.018],
                            [x0, y0 + 0.018],
                            [x0, y0],
                        ]
                    ],
                },
            }
        )
    (raw / "districts.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8"
    )
    return raw


@pytest.fixture
def raw_dir(tmp_path, calendar_html, district_page_html) -> Path:
    """A fresh floor-passing raw cache per test, so a test may corrupt it."""
    raw = tmp_path / "raw"
    raw.mkdir()
    return write_raw_cache(raw, calendar_html, district_page_html)


@pytest.fixture(scope="session")
def raw_dir_session(tmp_path_factory, calendar_html, district_page_html) -> Path:
    """The same cache, built once for the session, for the browser gates."""
    return write_raw_cache(
        tmp_path_factory.mktemp("raw-session"), calendar_html, district_page_html
    )
