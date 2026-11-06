"""Guards that apply to every unit test.

A unit test must not launch a browser. One board's schedule is read by driving Chrome, and
`load_browser` starts it directly rather than asking `request.get` — so monkeypatching the
fetcher's getter does not contain it, and any test that calls `_fetch_board_meetings`
without saying otherwise really did start a browser and wait on a live Airtable view.

This makes that a loud failure instead of a slow test. A test that wants a browser stubs
one itself; the browser gates under `tests/browser` are where a real one is driven.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _no_browser_in_unit_tests(monkeypatch):
    import showup.cdp as cdp

    def refuse(*_args, **_kwargs):
        raise cdp.CDPError(
            "a unit test tried to launch a browser; stub `showup.cdp.Browser` instead"
        )

    monkeypatch.setattr(cdp, "Browser", refuse)
