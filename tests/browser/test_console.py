"""Console silence, local-resolution privacy, the staleness notice, and error blame.

All four are read-time properties: they only exist in a browser behind the real
`_headers`, which is why a CSP that refused the site's own data went unnoticed until
something loaded a page that way.
"""

from __future__ import annotations

import json
import re
import shutil
import time
from pathlib import Path

import pytest
from cdp import Browser
from console_check import check
from pageset import REPRESENTATIVE, every_page
from serve import background_server

pytestmark = pytest.mark.browser

GEOCODER_HOST = "geosearch.planninglabs.nyc"
REPO_ROOT = Path(__file__).resolve().parents[2]


def _submit_address(page, base_url, query, settle_seconds=6.0):
    """Type `query` into the address box, submit, and return (path, status text)."""
    page.navigate(base_url + "/")
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if not page.evaluate("document.getElementById('address-section').hasAttribute('hidden')"):
            break
        time.sleep(0.1)

    page.evaluate("document.getElementById('address-input').focus()")
    page.type_text(query)
    page.press("Enter")
    time.sleep(settle_seconds)
    return (
        page.evaluate("location.pathname"),
        page.evaluate(
            "(() => { const el = document.getElementById('address-status');"
            " return el ? el.textContent : ''; })()"
        ),
    )


@pytest.fixture(scope="module")
def complaints(chrome, built_site):
    """One load of each page type. A policy violation appears identically on all 114."""
    return check(built_site, list(REPRESENTATIVE))


class TestTheConsoleIsSilent:
    def test_no_page_logs_an_error(self, complaints):
        noisy = {path: found for path, found in complaints.items() if found}
        assert not noisy, "\n".join(
            f"{path}: [{entry['level']}/{entry['source']}] {entry['text']}"
            for path, found in noisy.items()
            for entry in found
        )

    def test_it_looked_at_every_page_type(self, complaints):
        assert set(complaints) == set(REPRESENTATIVE)

    def test_the_page_types_are_all_real_pages(self, complaints, built_site):
        assert set(complaints) <= set(every_page(built_site))


@pytest.fixture(scope="module")
def network_trace(chrome, built_site):
    """Every URL the front page requests while resolving the district number 35."""
    with background_server(built_site) as base_url, Browser() as browser:
        page = browser.page()
        page.call("Network.enable")
        page.drain_events()
        landed, _ = _submit_address(page, base_url, "35")
        requested = [
            event["params"]["request"]["url"]
            for event in page.consume_events()
            if event["method"] == "Network.requestWillBeSent"
        ]
    return landed, requested


class TestLocalResolutionStaysLocal:
    """§4.4: everything except a street address resolves from the committed index."""

    def test_a_district_number_resolves(self, network_trace):
        landed, _ = network_trace
        assert landed == "/district/35/", (
            f"typing 35 landed on {landed!r}; if '/', the local index was not fetchable"
        )

    def test_a_district_number_never_touches_the_geocoder(self, network_trace):
        _, requested = network_trace
        assert not [url for url in requested if GEOCODER_HOST in url]

    def test_the_local_index_really_was_fetched(self, network_trace):
        _, requested = network_trace
        assert any("/data/lookup.json" in url for url in requested)

    def test_the_geometry_is_not_fetched_for_a_district_number(self, network_trace):
        """132 KB gzipped; only a street address needs it."""
        _, requested = network_trace
        assert not [url for url in requested if "districts.geo.json" in url]


@pytest.fixture(scope="module")
def aged_site(built_site, tmp_path_factory):
    """A copy of the site whose manifest claims every source was fetched in 2019."""
    aged = tmp_path_factory.mktemp("aged-site")
    shutil.copytree(built_site, aged, dirs_exist_ok=True)
    manifest_path = aged / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for source in manifest["sources"].values():
        source["fetched_at"] = "2019-01-01T00:00:00+00:00"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return aged


@pytest.fixture(scope="module")
def staleness_notice(chrome, aged_site):
    with background_server(aged_site) as base_url, Browser() as browser:
        page = browser.page()
        page.navigate(base_url + "/district/35/")
        deadline = time.monotonic() + 15
        text = ""
        while time.monotonic() < deadline:
            text = page.evaluate(
                "(() => { const el = document.querySelector('.staleness');"
                " return el ? el.textContent : ''; })()"
            )
            if text:
                break
            time.sleep(0.1)
        return text


class TestTheStalenessNoticeReallyRenders:
    """§2.12: staleness is computed at read time, which is what keeps an abandoned site
    honest. It was previously proven only over HTTP, where no CSP applies."""

    def test_an_aged_manifest_produces_a_visible_notice(self, staleness_notice):
        assert staleness_notice

    def test_it_says_not_to_rely_on_the_meeting_times(self, staleness_notice):
        assert "out of date" in staleness_notice
        assert "Do not rely on the meeting times" in staleness_notice

    def test_it_names_the_source_and_how_old_it_is(self, staleness_notice):
        assert "days ago" in staleness_notice
        assert "nyc.legistar.com" in staleness_notice


@pytest.fixture(scope="module")
def headers_without_self(tmp_path_factory):
    """The real `_headers` with `'self' ` removed from connect-src."""
    original = (REPO_ROOT / "_headers").read_text(encoding="utf-8")
    broken = re.sub(r"connect-src 'self' ", "connect-src ", original)
    assert broken != original, "connect-src no longer carries 'self'; this test is stale"
    path = tmp_path_factory.mktemp("broken-headers") / "_headers"
    path.write_text(broken, encoding="utf-8")
    return path


class TestErrorMessagesBlameTheRightThing:
    """A failure to load our own data must not be reported as the City's outage.

    It was, and the message sent the owner looking at hosting for a bug that was one
    token of CSP. Misattributed blame is a correctness defect in a product whose stated
    failure mode is confident wrongness.
    """

    def test_our_own_broken_data_is_reported_as_our_fault(
        self, chrome, built_site, headers_without_self
    ):
        with (
            background_server(built_site, headers_without_self) as base_url,
            Browser() as browser,
        ):
            landed, status = _submit_address(browser.page(), base_url, "350 Jay Street")
        assert landed == "/", "the lookup should not have succeeded with the index blocked"
        assert "fault here, not with the City" in status, status
        assert "City's address lookup did not respond" not in status, (
            "blamed the geocoder for a same-origin fetch that the CSP refused"
        )

    @pytest.mark.upstream
    def test_a_real_street_address_resolves_against_the_real_site(self, chrome):
        """End to end against the geocoder and the real geometry.

        `upstream` because it contacts geosearch.planninglabs.nyc, and against `site/`
        rather than the fixture build, whose geometry is 51 synthetic squares — a real
        Brooklyn address is correctly outside all of them.

        This is the test that answers "do we need hosting for the address box": the
        geocoder sends `access-control-allow-origin: *` and works from 127.0.0.1, so no.
        """
        real_site = REPO_ROOT / "site"
        if not (real_site / "data" / "districts.geo.json").exists():
            pytest.skip("site/ not built from real data — run `make fetch && make build`")
        with background_server(real_site) as base_url, Browser() as browser:
            landed, status = _submit_address(browser.page(), base_url, "350 Jay Street")
        assert re.fullmatch(r"/district/\d{1,2}/", landed), (
            f"a real street address landed on {landed!r} with status {status!r}"
        )
