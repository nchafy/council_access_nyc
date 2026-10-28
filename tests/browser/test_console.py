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
        """226 KB gzipped across both layers; only a street address needs any of it.

        This held, then briefly did not: with the map on the landing page every visit
        fetched both layers. Moving the map to `/map/` put the promise back, which is a
        second reason that route exists.
        """
        _, requested = network_trace
        assert not [url for url in requested if ".geo.json" in url]


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

    def test_it_states_the_fetch_time(self, staleness_notice):
        # The aged fixture claims 2019-01-01T00:00:00+00:00 for every source, so the stamp
        # is that instant in the reader's own zone — the arithmetic §2.12 wants at read time.
        assert staleness_notice.startswith("Data fetched ")
        assert "2018" in staleness_notice or "2019" in staleness_notice
        assert re.search(r"\b\d{1,2}:\d{2}\b", staleness_notice), "no time of day"

    def test_it_names_the_source_the_stamp_belongs_to(self, staleness_notice):
        assert "legistar calendar" in staleness_notice

    def test_it_carries_no_verdict_and_no_instruction(self, staleness_notice):
        for ours in ("out of date", "stale", "was last fetched", "days ago", "should"):
            assert ours not in staleness_notice, (
                f"{ours!r} is our verdict on the number rather than the number"
            )


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
            page = browser.page()
            landed, status = _submit_address(page, base_url, "350 Jay Street", settle_seconds=12.0)
            selection = page.evaluate(
                "(() => { const a = document.getElementById('map-selection');"
                " return a && !a.hidden ? a.getAttribute('href') : null; })()"
            )
        # A street address highlights on the map rather than navigating, so the page stays
        # put and the selection link is the resolved district. With no map loaded the old
        # behaviour still applies, which is why either outcome passes.
        resolved = selection if landed == "/" else landed
        assert resolved and re.fullmatch(r"/district/\d{1,2}/", resolved), (
            f"a real street address left path {landed!r}, selection {selection!r}, "
            f"status {status!r}"
        )


@pytest.fixture(scope="module")
def loaded_map(chrome, built_site):
    """`/map/` after the geometry has had time to arrive, with the panel opened."""
    with background_server(built_site) as base, Browser() as browser:
        page = browser.page()
        # Wrap `fetch` before the module runs, so the basemap's own requests are visible.
        # MapLibre reports a rejected style by falling back silently, and the only
        # external evidence is that no vector tile is ever fetched.
        page.call("Page.enable")
        page.call(
            "Page.addScriptToEvaluateOnNewDocument",
            source="""
            window.__tiles = [];
            (function () {
              const original = window.fetch;
              window.fetch = function (...args) {
                const url = String((args[0] && args[0].url) || args[0]);
                return original.apply(this, args).then(
                  (response) => {
                    window.__tiles.push(url + ' -> ' + response.status);
                    return response;
                  },
                  (error) => {
                    window.__tiles.push(url + ' -> threw');
                    throw error;
                  },
                );
              };
            })();
            """,
        )
        page.call(
            "Emulation.setDeviceMetricsOverride",
            width=1440,
            height=900,
            deviceScaleFactor=1,
            mobile=False,
        )
        page.navigate(base + "/map/")

        deadline = time.monotonic() + 30
        state = {}
        while time.monotonic() < deadline:
            state = json.loads(
                page.evaluate(
                    """JSON.stringify({
                        status: (document.getElementById('map-status') || {}).textContent || '',
                        toggleHidden: (document.getElementById('map-toggle') || {}).hidden,
                    })"""
                )
            )
            if not state.get("toggleHidden"):
                break
            time.sleep(0.25)

        # Wait for a vector tile rather than sleeping: the tile host's latency is not ours
        # to assume, and a fixed sleep turns this gate into a coin toss.
        tile_deadline = time.monotonic() + 25
        while time.monotonic() < tile_deadline:
            if json.loads(page.evaluate("JSON.stringify(window.__tiles)")) and any(
                ".pbf" in line
                for line in json.loads(page.evaluate("JSON.stringify(window.__tiles)"))
            ):
                break
            time.sleep(0.25)

        # Re-dispatch until the panel opens. The listener is bound at the end of module
        # start-up, so a single dispatch can land before anything is listening.
        open_deadline = time.monotonic() + 15
        while time.monotonic() < open_deadline:
            page.evaluate(
                """document.dispatchEvent(new CustomEvent('showup:located',
                    {detail: {district: 35, lon: -73.9549, lat: 40.6736}, cancelable: true}))"""
            )
            time.sleep(0.05)
            opening = page.evaluate(
                "getComputedStyle(document.getElementById('map-card')).transform"
            )
            time.sleep(1.0)
            if page.evaluate("!document.getElementById('map-card').hidden") is True:
                break
        time.sleep(1.0)
        after = json.loads(
            page.evaluate(
                """(() => {
                    const card = document.getElementById('map-card');
                    const box = card.hidden ? null : card.getBoundingClientRect();
                    const frame = document.getElementById('map').getBoundingClientRect();
                    return JSON.stringify({
                        cardOpen: !card.hidden,
                        groups: document.querySelectorAll('#map-card-body .group').length,
                        tables: document.querySelectorAll('#map-card-body .group-table').length,
                        headers: [...document.querySelectorAll('#map-card-body th[scope="col"]')]
                            .map((th) => th.textContent),
                        pins: document.querySelectorAll('.map-pin').length,
                        panelLeft: box ? Math.round(box.left) : null,
                        frameWidth: Math.round(frame.width),
                    });
                })()"""
            )
        )
        tiles = json.loads(page.evaluate("JSON.stringify(window.__tiles)"))

        # The slide, sampled rather than described: a transform read 50 ms after the class
        # lands is the only evidence that the panel travels instead of snapping.
        probe = """(() => {
            const card = document.getElementById('map-card');
            return JSON.stringify({
                hidden: card.hidden,
                isOpen: card.classList.contains('is-open'),
                transform: getComputedStyle(card).transform,
            });
        })()"""
        page.evaluate("document.getElementById('map-card-close').click()")
        time.sleep(0.05)
        closing = json.loads(page.evaluate(probe))
        time.sleep(0.9)
        shut = json.loads(page.evaluate(probe))

        yield {
            **state,
            **after,
            "tiles": tiles,
            "openingTransform": opening,
            "closing": closing,
            "shut": shut,
        }


class TestTheMapActuallyFinishesLoading:
    """A thrown exception inside the draw path leaves a canvas, no console error the
    console gate recognises, and a dead map. That happened on 2026-10-27 — a wrong key
    into `LAYERS` aborted `draw()`, every gate stayed green, and the only symptom was a
    status line still reading "Loading the map…". These assert the end state instead.
    """

    def test_the_status_line_stops_saying_loading(self, loaded_map):
        assert "Loading" not in loaded_map["status"], loaded_map["status"]

    def test_the_layer_toggle_is_revealed(self, loaded_map):
        """Revealed only once both layers are drawn, so it stands in for "draw finished"."""
        assert loaded_map["toggleHidden"] is False

    def test_selecting_opens_the_panel(self, loaded_map):
        assert loaded_map["cardOpen"]

    def test_the_panel_renders_its_groups_and_tables(self, loaded_map):
        assert loaded_map["groups"] >= 4
        assert loaded_map["tables"] >= 3

    def test_every_table_column_is_announced(self, loaded_map):
        """Real `th scope=col` cells are the whole reason the panel uses a table rather
        than an em dash between a label and its value."""
        assert "Cycle" in loaded_map["headers"]
        assert "Committee" in loaded_map["headers"]

    def test_an_address_drops_exactly_one_pin(self, loaded_map):
        assert loaded_map["pins"] == 1

    def test_the_panel_slid_in_rather_than_snapping(self, loaded_map):
        """Sampled 50 ms after opening: a non-identity translate means it is travelling.

        An identity matrix here would mean `hidden` and the class were set in the same
        frame, which gives the browser no start state and skips the animation.
        """
        assert loaded_map["openingTransform"] not in ("none", "matrix(1, 0, 0, 1, 0, 0)"), (
            loaded_map["openingTransform"]
        )

    def test_closing_slides_before_it_hides(self, loaded_map):
        """`hidden` must not land until the slide is done, or the panel vanishes instead
        of leaving. It still has to end up hidden, so it leaves the tab order."""
        assert loaded_map["closing"]["hidden"] is False
        assert loaded_map["closing"]["isOpen"] is False
        assert loaded_map["shut"]["hidden"] is True

    def test_the_basemap_really_drew(self, loaded_map):
        """An invalid paint expression makes MapLibre discard the whole style and fall
        back, with nothing logged: on 2026-10-27 a `['*', <case>, <zoom interpolate>]`
        fill-opacity left a map with district outlines and no basemap at all, and every
        gate including the console check stayed green. A fetched vector tile is the
        evidence that the real style survived.
        """
        fetched = [line for line in loaded_map["tiles"] if ".pbf" in line]
        assert fetched, (
            "no vector tile was fetched, so the basemap style was rejected or never "
            f"loaded; requests were {loaded_map['tiles']}"
        )
        assert any(line.endswith("-> 200") for line in fetched), fetched
