"""Shared setup for the gates that need a real browser: one built site, and Chrome.

The site is built from `tests/fixtures/` rather than `site/` because `etl/raw/` is
gitignored, so a CI runner has no upstream cache and could not build the real site.
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
    """Path to a local Chrome, skipping the module when there is none.

    The CI job asserts Chrome exists as its own step, so a skip can never be the
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

    `today` is pinned to the date the integration tests use, so the calendar window
    and the deadline arithmetic are the ones those tests already assert.
    """
    from showup.build import build_site

    out = tmp_path_factory.mktemp("built-site")
    build_site(raw_dir_session, out, today=date(2026, 9, 22))
    return out


@pytest.fixture(scope="session")
def broken_site(tmp_path_factory) -> Path:
    """The deliberately inaccessible fixture as a one-page site.

    Copied rather than served in place so the fixture's `/broken.css` resolves at the
    server root, as the real site's `/assets/site.css` does.
    """
    out = tmp_path_factory.mktemp("broken-site")
    shutil.copytree(FIXTURES / "a11y_broken", out, dirs_exist_ok=True)
    return out
