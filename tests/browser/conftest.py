"""Shared setup for the gates that need a real browser.

Builds one site from committed fixtures for the whole session, and finds Chrome.

Why a fixture-built site rather than `site/`. `etl/raw/` is gitignored, so a CI runner
has no upstream cache and cannot build the real site; a gate that only ran where the
cache happens to exist would not be a gate. Building from `tests/fixtures/` makes these
run anywhere, hermetically, with the real district markup. What it cannot cover is the
size of the real simplified geometry, because the fixture geometry is 51 synthetic
squares — `scripts/perf.py --root site` covers that locally, and
`tests/unit/test_geo.py` pins the tolerance it came from.
"""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "tests" / "fixtures"


@pytest.fixture(scope="session")
def chrome() -> str:
    """Skip the whole module when there is no browser, and say so out loud.

    Skipping is right locally — not every contributor has Chrome — and wrong in CI,
    where a silently skipped gate reports success. The CI job therefore asserts
    Chrome exists as its own step before pytest runs, so the skip can never be the
    reason CI is green.
    """
    from cdp import find_chrome

    path = find_chrome()
    if not path:
        pytest.skip("no local Chrome or Chromium; see tests/browser/conftest.py")
    return path


@pytest.fixture(scope="session")
def built_site(raw_dir_session, tmp_path_factory) -> Path:
    """A whole site built from committed fixtures, once per session.

    `today` is pinned to the same date the integration tests use, so the calendar
    window and the deadline arithmetic are the ones those tests already assert.
    """
    from showup.build import build_site

    out = tmp_path_factory.mktemp("built-site")
    build_site(raw_dir_session, out, today=date(2026, 9, 22))
    return out


@pytest.fixture(scope="session")
def broken_site(tmp_path_factory) -> Path:
    """A one-page site serving the deliberately inaccessible fixture as its index.

    Copied rather than served in place so the fixture's `/broken.css` resolves at the
    server root, which is what the real site's `/assets/site.css` does too.
    """
    out = tmp_path_factory.mktemp("broken-site")
    shutil.copytree(FIXTURES / "a11y_broken", out, dirs_exist_ok=True)
    return out
