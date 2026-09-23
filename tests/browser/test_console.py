"""No page may complain in the console, and local resolution must stay local.

The second half is the one that matters. `docs/phase-1-scope.md` §4.4 promises that a
ZIP, a neighbourhood or a district number resolves from a committed index and never
reaches the geocoder. That promise was broken in production configuration for as long
as the address box has existed — `connect-src` omitted `'self'`, the index could not be
fetched, and every query fell through to the geocoder instead. The promise was tested,
but only against a server that sent no CSP, so the test and the shipped policy
disagreed and nothing compared them.

`test_a_district_number_never_touches_the_geocoder` closes that by watching the network
rather than the code: it asserts what requests the browser actually made, behind the
real headers. A regression in the policy, the code, or the data all fail it the same
way.
"""

from __future__ import annotations

import time

import pytest
from cdp import Browser
from console_check import check
from pageset import REPRESENTATIVE, every_page
from serve import background_server

pytestmark = pytest.mark.browser

GEOCODER_HOST = "geosearch.planninglabs.nyc"


@pytest.fixture(scope="module")
def complaints(chrome, built_site):
    """One load of each page type, not all 114.

    Unlike axe, this check does not vary with data: every page loads the same two
    scripts and the same stylesheet, and a policy violation appears identically on all
    of them — when `connect-src` was wrong, all nine pages reported it. The full sweep
    costs three minutes for nine distinct findings, so it stays an operator command
    (`python3 scripts/console_check.py --all`) and is listed in the release procedure
    in docs/accessibility-pass.md.
    """
    return check(built_site, list(REPRESENTATIVE))


class TestTheConsoleIsSilent:
    def test_no_page_logs_an_error(self, complaints):
        noisy = {path: found for path, found in complaints.items() if found}
        assert not noisy, "\n".join(
            f"{path}: [{item['level']}/{item['source']}] {item['text']}"
            for path, found in noisy.items()
            for item in found
        )

    def test_it_looked_at_every_page_type(self, complaints):
        assert set(complaints) == set(REPRESENTATIVE)

    def test_the_page_types_are_all_real_pages(self, complaints, built_site):
        """Guards against a typo in the page set quietly reducing coverage to nothing:
        a path that does not exist is served the 404 body, which logs nothing."""
        assert set(complaints) <= set(every_page(built_site))


@pytest.fixture(scope="module")
def network_trace(chrome, built_site):
    """Every URL the front page requests, from load through an address submit.

    Driven with a district number, which §4.4 says must resolve locally. `35` is used
    rather than a street address precisely because a street address is the one input
    that *is* allowed to reach the geocoder.
    """
    with background_server(built_site) as base, Browser() as browser:
        page = browser.page()
        page.call("Network.enable")
        page.drain_events()
        page.navigate(base + "/")

        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if not page.evaluate(
                "document.getElementById('address-section').hasAttribute('hidden')"
            ):
                break
            time.sleep(0.1)

        page.evaluate("document.getElementById('address-input').focus()")
        page.type_text("35")
        page.press("Enter")

        landed = "/"
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            landed = page.evaluate("location.pathname")
            if landed != "/":
                break
            time.sleep(0.1)

        requested = [
            event["params"]["request"]["url"]
            for event in page.consume_events()
            if event["method"] == "Network.requestWillBeSent"
        ]
    return landed, requested


class TestLocalResolutionStaysLocal:
    def test_a_district_number_resolves(self, network_trace):
        landed, _ = network_trace
        assert landed == "/district/35/", (
            f"typing 35 landed on {landed!r}. If this is '/', the local index was "
            "probably not fetchable — check connect-src in _headers."
        )

    def test_a_district_number_never_touches_the_geocoder(self, network_trace):
        _, requested = network_trace
        leaked = [url for url in requested if GEOCODER_HOST in url]
        assert not leaked, (
            f"resolving a district number contacted the geocoder: {leaked}. §4.4 says "
            "everything except a street address resolves from the committed index."
        )

    def test_the_local_index_really_was_fetched(self, network_trace):
        """Otherwise the test above passes by the site doing nothing at all."""
        _, requested = network_trace
        assert any("/data/lookup.json" in url for url in requested), (
            f"the local index was never requested; the trace was {requested}"
        )

    def test_geometry_is_not_fetched_for_a_district_number(self, network_trace):
        """districts.geo.json is 132 KB gzipped and only a street address needs it.

        Pulling it for a district number would blow the R40 budget on the one path
        that needs no network at all.
        """
        _, requested = network_trace
        assert not [url for url in requested if "districts.geo.json" in url], (
            "the 132 KB geometry was fetched to resolve a district number"
        )
