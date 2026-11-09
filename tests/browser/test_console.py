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
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cdp import Browser
from console_check import check
from pageset import PROGRAM_SURFACES, REPRESENTATIVE, every_page
from ready import await_declared_ready
from serve import background_server

pytestmark = pytest.mark.browser

GEOCODER_HOST = "geosearch.planninglabs.nyc"
REPO_ROOT = Path(__file__).resolve().parents[2]


#: The one page that offers the address box. It was the landing page until 2026-11-06, which
#: is now a desktop of icons.
ADDRESS_PAGE = "/map/"


@pytest.fixture(scope="module")
def complaints(chrome, built_site):
    """One load of each page type. A policy violation appears identically on all 115."""
    return check(built_site, list(REPRESENTATIVE))


class TestTheConsoleIsSilent:
    def test_no_page_logs_an_error(self, complaints):
        noisy = {path: found for path, found in complaints.items() if found}
        assert not noisy, "\n".join(
            f"{path}: [{entry['level']}/{entry['source']}] {entry['text']}"
            for path, found in noisy.items()
            for entry in found
        )

    def test_it_looked_at_every_surface(self, complaints):
        """One document and every program's window. Four of the five programs are not
        autostarted, so a sweep of routes never runs their `mount` or `ready` — which is
        where a program throws, and where the shell catches it and `console.error`s it."""
        assert set(complaints) == set(REPRESENTATIVE) | {
            surface.name for surface in PROGRAM_SURFACES
        }

    def test_the_routes_it_looked_at_are_all_real_pages(self, complaints, built_site):
        """The route half only. A surface is a window, not a file, so it has no page to be."""
        routes = set(complaints) & set(REPRESENTATIVE)
        assert routes <= set(every_page(built_site))
        assert routes, "the sweep visited no route at all"


@pytest.fixture(scope="module")
def desktop_trace(chrome, built_site):
    """Every URL the landing page requests, with nothing typed."""
    with background_server(built_site) as base_url, Browser() as browser:
        page = browser.page()
        page.call("Network.enable")
        page.drain_events()
        page.navigate(base_url + "/")
        time.sleep(3.0)
        return [
            event["params"]["request"]["url"]
            for event in page.consume_events()
            if event["method"] == "Network.requestWillBeSent"
        ]


class TestTheEntryPageIsCheap:
    """What the landing page costs a reader who has asked for nothing yet.

    This replaces an assertion that the front page fetched no geometry while resolving a
    district number. That check was about page composition rather than about `address.js`,
    and its subject moved: the address box is on `/map/` since 2026-11-06, where the geometry
    and the basemap are fetched for the map's own reasons. The promise it protected — the way
    in costs almost nothing — belongs to the desktop now, and is stronger there.
    """

    def test_no_geometry(self, desktop_trace):
        """226 KB gzipped across both layers, and the desktop needs neither."""
        assert not [url for url in desktop_trace if ".geo.json" in url], desktop_trace

    def test_no_maplibre(self, desktop_trace):
        """449 KB gzipped, paid for only by a reader who opens the map."""
        assert not [url for url in desktop_trace if "maplibre" in url], desktop_trace

    def test_nothing_off_our_own_origin(self, desktop_trace):
        """No basemap here, so the strong version of the promise holds: opening the site
        discloses nothing to anyone but us."""
        external = [url for url in desktop_trace if not url.startswith("http://127.0.0.1")]
        assert not external, external

    def test_it_really_loaded_the_desktop(self, desktop_trace):
        """A trace of nothing would pass all three above, so this is what makes them mean
        something: the boot module is the one request that turns this page into a desktop."""
        assert any(url.endswith("/assets/boot.mjs") for url in desktop_trace), desktop_trace
        assert any("/vendor/webxp/" in url for url in desktop_trace), desktop_trace


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
def fresh_site(built_site, tmp_path_factory):
    """A copy whose manifest claims every source was fetched a minute ago.

    The real fixture build is already past its own windows — its calendar was fetched on
    2026-10-07 with a 12-hour window — so the fresh branch is unreachable without forging
    one, and the two branches have to be compared to show the text tells them apart.
    """
    fresh = tmp_path_factory.mktemp("fresh-site")
    shutil.copytree(built_site, fresh, dirs_exist_ok=True)
    manifest_path = fresh / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    just_now = datetime.now(UTC) - timedelta(minutes=1)
    for source in manifest["sources"].values():
        source["fetched_at"] = just_now.isoformat(timespec="seconds")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return fresh


def _freshness_text(base_url: str) -> str:
    """The Readme program's freshness line, from a desktop served at `base_url`."""
    with Browser() as browser:
        page = browser.page()
        page.navigate(base_url + "/")
        await_declared_ready(page)
        page.evaluate(
            'window.webxp.launch("showup-readme").then((w) => Boolean(w))', await_promise=True
        )
        deadline = time.monotonic() + 20
        text = ""
        while time.monotonic() < deadline:
            text = page.evaluate(
                "(() => { const el = document.querySelector('.readme-freshness');"
                " return el ? el.textContent : ''; })()"
            )
            if text and "Reading" not in text:
                break
            time.sleep(0.2)
        return text


@pytest.fixture(scope="module")
def fresh_notice(chrome, fresh_site):
    with background_server(fresh_site) as base_url:
        return _freshness_text(base_url)


@pytest.fixture(scope="module")
def staleness_notice(chrome, aged_site):
    """The Readme program's freshness line, against a manifest aged to 2019.

    On the Readme program since 2026-11-09. It was proven on `/district/35/`, where `site.js`
    inserted the notice into the page's footer; both are deleted and the promise moved with
    the program that now reads the manifest.
    """
    with background_server(aged_site) as base_url, Browser() as browser:
        page = browser.page()
        page.navigate(base_url + "/")
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if page.evaluate("Boolean(window.webxpApps)"):
                break
            time.sleep(0.2)
        page.evaluate('window.webxp.launch("showup-readme")')

        deadline = time.monotonic() + 20
        text = ""
        while time.monotonic() < deadline:
            text = page.evaluate(
                "(() => { const el = document.querySelector('.readme-freshness');"
                " return el ? el.textContent : ''; })()"
            )
            if text and "Reading" not in text:
                break
            time.sleep(0.2)
        return text


class TestTheStalenessNoticeReallyRenders:
    """§2.12: staleness is computed at read time, which is what keeps an abandoned site
    honest. A build cannot know how old it will be when somebody opens it."""

    def test_an_aged_manifest_produces_a_visible_notice(self, staleness_notice):
        assert staleness_notice

    def test_it_states_the_fetch_time(self, staleness_notice):
        # The aged fixture claims 2019-01-01T00:00:00+00:00 for every source, so the stamp is
        # that instant in the reader's own zone — the arithmetic §2.12 wants at read time.
        assert staleness_notice.startswith("Data fetched ")
        assert "2018" in staleness_notice or "2019" in staleness_notice
        assert re.search(r"\b\d{1,2}:\d{2}\b", staleness_notice), "no time of day"

    def test_it_names_the_source_the_stamp_belongs_to(self, staleness_notice):
        """ "Something is stale" is not an answer a reader can act on."""
        assert "legistar calendar" in staleness_notice

    def test_the_two_states_differ_in_words_and_not_only_in_colour(
        self, staleness_notice, fresh_notice
    ):
        """SC 1.4.1. The stale branch wears `--urgent-bg`/`--urgent-ink` and the fresh one
        does not; for a reader in forced colours, in monochrome, or using a screen reader,
        that fill is nothing. So the text has to carry it — and did not until 2026-11-09,
        when both branches read `Data fetched <stamp>` and differed only by the fill.

        No automated gate catches 1.4.1, which is why this is asserted here by hand.
        """
        assert fresh_notice, "the fresh branch rendered nothing, so nothing was compared"
        assert staleness_notice != fresh_notice
        assert "stated window" in staleness_notice, staleness_notice
        assert "stated window" not in fresh_notice, fresh_notice

    def test_the_stated_window_is_the_sources_own_number(self, staleness_notice):
        """The calendar's window is 12 hours in the manifest, and stating any other number
        would be this site inventing a threshold the data did not declare."""
        assert "Its stated window is 12 hours." in staleness_notice, staleness_notice

    def test_it_carries_no_verdict_and_no_instruction(self, staleness_notice):
        for ours in ("out of date", "stale", "was last fetched", "days ago", "should"):
            assert ours not in staleness_notice, (
                f"{ours!r} is our verdict on the number rather than the number"
            )
