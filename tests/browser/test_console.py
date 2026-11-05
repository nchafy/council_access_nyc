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
        # Where the pin's drawn tip is, against where MapLibre put the coordinate. The
        # resolved transform matrix already includes `translate(-50%, -100%)` for a bottom
        # anchor, so the coordinate is at (e + width/2, f + height).
        pin_geometry = json.loads(
            page.evaluate(
                """(function () {
                    var pin = document.querySelector('.map-pin');
                    if (!pin) return JSON.stringify({present: false});
                    var nums = (getComputedStyle(pin).transform.match(/-?[\\d.]+/g) || [])
                        .map(Number);
                    var box = pin.getBoundingClientRect();
                    var frame = document.getElementById('map').getBoundingClientRect();
                    var width = box.width;
                    var height = box.height;
                    return JSON.stringify({
                        present: true,
                        tag: pin.tagName.toLowerCase(),
                        pointX: nums[4] + width / 2,
                        pointY: nums[5] + height,
                        tipX: box.left - frame.left + width / 2,
                        tipY: box.top - frame.top + height,
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
            "pin": pin_geometry,
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

    def test_the_pin_points_at_the_address(self, loaded_map):
        """The tip marks the coordinate, not the middle of the teardrop.

        This regressed invisibly once: `.map-pin` was a div rotated 45deg in CSS, and
        MapLibre writes its own `transform` onto a marker element, so the rotation never
        applied. The shape rendered unrotated with its sharp corner down and to the left,
        and that corner is what a reader takes for the address.
        """
        pin = loaded_map["pin"]
        assert pin["present"], "no pin was dropped for a geocoded address"
        assert abs(pin["tipX"] - pin["pointX"]) < 1.0, pin
        assert abs(pin["tipY"] - pin["pointY"]) < 1.0, pin

    def test_the_pin_carries_its_own_geometry(self, loaded_map):
        """An SVG path, so no CSS transform has to survive MapLibre writing over it."""
        assert loaded_map["pin"]["tag"] == "svg"


@pytest.fixture(scope="module")
def autocomplete(chrome, built_site):
    """Type into the address box and record both the suggestions and every request made.

    The recording is the point: suggestions are built from `lookup.json` alone so that the
    submit-only promise in docs/phase-1-scope.md §6 still holds, and the only way to show
    that is to watch the network while the keys go in.
    """
    with background_server(built_site) as base, Browser() as browser:
        page = browser.page()
        page.call("Page.enable")
        page.call(
            "Page.addScriptToEvaluateOnNewDocument",
            source="""
            window.__requests = [];
            (function () {
              const original = window.fetch;
              window.fetch = function (...args) {
                window.__requests.push(String((args[0] && args[0].url) || args[0]));
                return original.apply(this, args);
              };
            })();
            """,
        )
        page.navigate(base + "/")

        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if not page.evaluate(
                "document.getElementById('address-section').hasAttribute('hidden')"
            ):
                break
            time.sleep(0.1)

        probe = """(function () {
            var input = document.getElementById('address-input');
            var list = document.getElementById('address-suggest');
            return JSON.stringify({
                expanded: input.getAttribute('aria-expanded'),
                active: input.getAttribute('aria-activedescendant'),
                options: Array.prototype.map.call(
                    list.querySelectorAll('[role="option"]'),
                    function (option) { return option.textContent; }
                ),
            });
        })()"""
        reset = """(function () {
            var input = document.getElementById('address-input');
            input.value = '';
            input.dispatchEvent(new Event('input'));
        })()"""

        seen = {}
        for query in ("fort gr", "35", "112", "350 jay street"):
            page.evaluate("document.getElementById('address-input').focus()")
            page.evaluate(reset)
            page.type_text(query)
            time.sleep(0.6)
            seen[query] = json.loads(page.evaluate(probe))

        # Arrow then Enter, which is the whole point of the pattern.
        page.evaluate(reset)
        page.type_text("fort gr")
        time.sleep(0.6)
        page.press("ArrowDown")
        time.sleep(0.2)
        arrowed = json.loads(page.evaluate(probe))

        requests = json.loads(page.evaluate("JSON.stringify(window.__requests)"))
        yield {"seen": seen, "arrowed": arrowed, "requests": requests}


class TestTheAddressBoxCompletesLocally:
    def test_a_neighbourhood_suggests_a_district_and_a_board(self, autocomplete):
        options = autocomplete["seen"]["fort gr"]["options"]
        assert any("Council District 35" in option for option in options), options
        assert any("Community Board 2" in option for option in options), options

    def test_a_small_number_suggests_that_district(self, autocomplete):
        options = autocomplete["seen"]["35"]["options"]
        assert any(option.startswith("Council District 35") for option in options), options

    def test_a_zip_prefix_suggests_whole_zips(self, autocomplete):
        options = autocomplete["seen"]["112"]["options"]
        assert options and all(option.startswith("ZIP 112") for option in options), options

    def test_a_street_address_gets_no_local_guess(self, autocomplete):
        """Only the geocoder can answer it, and it is not asked until submit."""
        entry = autocomplete["seen"]["350 jay street"]
        assert entry["options"] == []
        assert entry["expanded"] == "false"

    def test_arrowing_names_the_active_option(self, autocomplete):
        """`aria-activedescendant` is how a screen reader is told which row is current;
        focus itself stays in the text box."""
        assert autocomplete["arrowed"]["active"] == "address-suggest-0"

    def test_typing_never_reaches_the_geocoder(self, autocomplete):
        """The promise in docs/phase-1-scope.md §6, now that there is a keystroke handler
        at all: suggestions come from `lookup.json` and nothing else."""
        offenders = [url for url in autocomplete["requests"] if GEOCODER_HOST in url]
        assert not offenders, offenders

    def test_only_our_own_origin_was_fetched(self, autocomplete):
        """And the index is fetched once, not once per keystroke."""
        external = [url for url in autocomplete["requests"] if url.startswith("http")]
        assert not external, external
        assert autocomplete["requests"].count("/data/lookup.json") == 1, autocomplete["requests"]


@pytest.fixture(scope="module")
def pin_lifecycle(chrome, built_site):
    """Count the pins through a sequence of lookups.

    The pin answers "where is this address". Every other kind of lookup makes it a
    leftover pointing at a previous question, so it has to go — and it has to come back
    when the next address arrives, which is the half that a naive fix breaks.
    """
    with background_server(built_site) as base, Browser() as browser:
        page = browser.page()
        page.call(
            "Emulation.setDeviceMetricsOverride",
            width=1280,
            height=860,
            deviceScaleFactor=1,
            mobile=False,
        )
        page.navigate(base + "/map/")

        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if not page.evaluate("(document.getElementById('map-toggle') || {}).hidden !== false"):
                break
            time.sleep(0.25)

        address = (
            "document.dispatchEvent(new CustomEvent('showup:located',"
            "{detail:{district:33, lon:-73.9870, lat:40.6926}, cancelable:true}))"
        )
        counts = {}

        def run(label, script):
            page.evaluate(script)
            time.sleep(2.0)
            counts[label] = page.evaluate("document.querySelectorAll('.map-pin').length")

        run("address", address)
        run(
            "other district",
            "document.dispatchEvent(new CustomEvent('showup:located',"
            "{detail:{district:35}, cancelable:true}))",
        )
        run("address again", address)
        run(
            "zip",
            "document.dispatchEvent(new CustomEvent('showup:located',"
            "{detail:{zip:'11217', zcta:'11217', districts:[39,35,33],"
            " boards:['306','302','308']}, cancelable:true}))",
        )
        run("address once more", address)
        run("closed", "document.getElementById('map-card-close').click()")
        yield counts


class TestThePinBelongsToOneLookup:
    def test_an_address_drops_a_pin(self, pin_lifecycle):
        assert pin_lifecycle["address"] == 1

    def test_selecting_another_district_takes_it_away(self, pin_lifecycle):
        assert pin_lifecycle["other district"] == 0

    def test_a_zip_lookup_takes_it_away(self, pin_lifecycle):
        assert pin_lifecycle["zip"] == 0

    def test_closing_the_panel_takes_it_away(self, pin_lifecycle):
        assert pin_lifecycle["closed"] == 0

    def test_the_next_address_still_gets_one(self, pin_lifecycle):
        """Clearing on selection is only correct if the address path re-pins afterwards:
        it drops the pin *after* selecting for exactly this reason."""
        assert pin_lifecycle["address again"] == 1
        assert pin_lifecycle["address once more"] == 1

    def test_only_ever_one_pin(self, pin_lifecycle):
        assert max(pin_lifecycle.values()) == 1, pin_lifecycle


#: The real built site, not the fixture one. The browser fixtures' geometry is synthetic
#: squares at latitude 40.5, longitude -73.5 — open Atlantic off Jones Beach — so a camera
#: or layer-order check against them measures water. `test_geo.py` sets the precedent for a
#: test that needs real data and skips without it.
REAL_SITE = REPO_ROOT / "site"

#: Floors on the selected district's painted pixels, measured at 1280x820.
#:
#: The bug this exists for is the fill inserted beneath the basemap's land polygons, which
#: on 2026-10-31 dropped the correct 192,377 pixels at four zoom steps to 78,206, and the
#: correct 20,064 at six steps to **0**. The six-step floor is the decisive one — nothing
#: else distinguishes zero — and it has not moved.
#:
#: The four-step floor dropped from 150,000 to 95,000 on 2026-11-04, when the basemap became
#: liberty. It is not a weakened gate: the same four clicks on the new basemap land at a
#: wider zoom, so the district occupies less of the viewport and paints 107,119 pixels while
#: being, if anything, easier to read — the whole district and its neighbours are visible
#: where the old framing was deep inside it. The floor still sits above the buried figure of
#: 78,206, so the bug remains visible to it.
PAINTED_FLOOR = {4: 95_000, 6: 10_000}

#: How far the painted centroid may sit from the middle of the visible map. Correct is
#: +42 px at four steps and -14 px at six; centring the bounding box instead of the
#: centroid put it -163 px out at six, because district 35 runs north-west to south-east
#: and the middle of its box is mostly other districts.
CENTROID_TOLERANCE_PX = 90


def _painted_selection(browser, base, zoom_steps):
    """Select district 35 at a zoom and measure the pixels the map painted for it."""
    width, height = 1280, 820
    page = browser.page()
    page.call(
        "Emulation.setDeviceMetricsOverride",
        width=width,
        height=height,
        deviceScaleFactor=1,
        mobile=False,
    )
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
              (r) => { window.__tiles.push(url + ' -> ' + r.status); return r; },
              (e) => { window.__tiles.push(url + ' -> threw'); throw e; },
            );
          };
        })();
        """,
    )
    page.navigate(base + "/map/")

    deadline = time.monotonic() + 40
    while time.monotonic() < deadline:
        if not page.evaluate("(document.getElementById('map-toggle') || {}).hidden !== false"):
            break
        time.sleep(0.25)

    for _ in range(zoom_steps):
        page.evaluate("document.querySelector('#map-zoom button').click()")
        time.sleep(0.5)
    time.sleep(1.0)
    page.evaluate(
        "document.dispatchEvent(new CustomEvent('showup:located',"
        "{detail:{district:35}, cancelable:true}))"
    )
    time.sleep(3.5)

    tiles = json.loads(page.evaluate("JSON.stringify(window.__tiles)"))
    shot = page.call("Page.captureScreenshot", format="png")["data"]
    # Read the DOM before navigating away: `browser.page()` returns the same tab.
    panel_left = page.evaluate(
        "Math.round(document.getElementById('map-card').getBoundingClientRect().left)"
    )
    frame_top = page.evaluate(
        "Math.round(document.getElementById('map').getBoundingClientRect().top)"
    )
    frame_bottom = page.evaluate(
        "Math.round(document.getElementById('map').getBoundingClientRect().bottom)"
    )

    # Measured on about:blank, where our own CSP does not forbid a `data:` image.
    # Concatenated, not formatted: the script is full of braces and every formatting
    # scheme wants them escaped.
    args = ", ".join(
        [
            json.dumps("data:image/png;base64," + shot),
            str(width),
            str(height),
            str(panel_left),
            str(frame_top),
            str(frame_bottom),
        ]
    )
    measure = (
        "(function (url, w, h, x1, y0, y1) {"
        "  return new Promise(function (resolve) {"
        "    var img = new Image();"
        "    img.onload = function () {"
        "      var canvas = document.createElement('canvas');"
        "      canvas.width = w; canvas.height = h;"
        "      var ctx = canvas.getContext('2d');"
        "      ctx.drawImage(img, 0, 0);"
        "      var data = ctx.getImageData(0, 0, w, h).data;"
        "      var n = 0, sx = 0;"
        "      for (var y = y0; y < y1; y++) {"
        "        for (var x = 0; x < x1; x++) {"
        "          var i = (y * w + x) * 4;"
        "          var r = data[i], g = data[i + 1], b = data[i + 2];"
        "          if (r > 180 && r - g > 45 && r - b > 45) { n++; sx += x; }"
        "        }"
        "      }"
        "      resolve(JSON.stringify(n ? {n: n, cx: sx / n} : {n: 0}));"
        "    };"
        "    img.src = url;"
        "  });"
        "})(" + args + ")"
    )

    blank = browser.page()
    blank.navigate("about:blank")
    time.sleep(0.5)
    found = json.loads(blank.evaluate(measure, await_promise=True))
    return {"found": found, "free_centre": panel_left / 2, "tiles": tiles}


@pytest.fixture(scope="module")
def real_map_pixels(chrome):
    """What the real map actually painted for a selected district, at two zooms.

    This is the only gate that looks at the rendered pixels. Bugs in this file's history
    that every other gate passed: a silently rejected paint expression, land polygons
    painting over the fill, a pin anchored on its middle, and three separate camera faults.

    Two zooms because one is not enough — the layer-order bug is invisible in the centroid
    and the centring bug is invisible in the pixel count.
    """
    if not (REAL_SITE / "data" / "districts.geo.json").is_file():
        pytest.skip("no built site/ (run `make build`); the fixture geometry is in the ocean")

    with background_server(REAL_SITE) as base, Browser() as browser:
        yield {steps: _painted_selection(browser, base, steps) for steps in (4, 6)}


class TestTheMapDrewTheSelection:
    def test_the_real_basemap_style_was_accepted(self, real_map_pixels):
        """An invalid paint expression makes MapLibre discard the whole style and fall
        back, logging nothing — on 2026-10-27 that shipped a map with district outlines
        and no basemap while every gate stayed green.

        The evidence is the style's *dependencies*: its TileJSON, its sprite sheet and its
        glyphs. The fallback style requests none of them.

        Deliberately not "a vector tile came back": MapLibre fetches tiles in a Web
        Worker, so wrapping `window.fetch` on the page never sees one, and the only `.pbf`
        files that do reach the page are font glyphs — which is how an earlier version of
        this check passed by accident.
        """
        requested = real_map_pixels[4]["tiles"]
        # Any one of them is enough to tell the two styles apart, and requiring all three
        # made this flake: the module loads `/map/` a dozen times and the tile host starts
        # throttling, so an individual dependency can come back 429 or from cache.
        wanted = ("tiles.openfreemap.org/planet", "/sprites/", "/fonts/")
        satisfied = [
            line
            for line in requested
            if any(needle in line for needle in wanted) and ("-> 2" in line or "-> 304" in line)
        ]
        assert satisfied, (
            "none of the basemap style's dependencies loaded, so the style was rejected "
            f"and MapLibre fell back: {requested}"
        )

    @pytest.mark.parametrize("steps", [4, 6])
    def test_the_selected_district_is_actually_painted(self, real_map_pixels, steps):
        """Catches a fill buried under the basemap's land polygons, which halved the
        painted area at four steps and hid it completely at six."""
        found = real_map_pixels[steps]["found"]
        assert found["n"] >= PAINTED_FLOOR[steps], (steps, found)

    @pytest.mark.parametrize("steps", [4, 6])
    def test_it_is_centred_in_the_map_the_panel_leaves_visible(self, real_map_pixels, steps):
        """At six steps the district fits the frame, so this is a real centring check."""
        case = real_map_pixels[steps]
        error = case["found"]["cx"] - case["free_centre"]
        assert abs(error) < CENTROID_TOLERANCE_PX, (
            f"at {steps} zoom steps the selected district's centroid is {error:.0f} px "
            f"from the centre of the visible map: {case}"
        )


#: Controls the vendored base map binds itself. Binding them here as well puts two
#: listeners on one button, and the press does its job twice.
BASE_MAP_OWNED_CONTROLS = ("map-zoom-in", "map-zoom-out")


def _click_listener_counts(browser, base, ids):
    """How many click listeners each element carries, read over CDP."""
    page = browser.page()
    page.navigate(base + "/map/")
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline:
        if not page.evaluate("(document.getElementById('map-toggle') || {}).hidden !== false"):
            break
        time.sleep(0.25)
    time.sleep(2.0)

    counts = {}
    for element_id in ids:
        handle = page.call(
            "Runtime.evaluate",
            expression=f"document.getElementById({element_id!r})",
            returnByValue=False,
        )
        object_id = handle["result"].get("objectId")
        if not object_id:
            counts[element_id] = None
            continue
        listeners = page.call("DOMDebugger.getEventListeners", objectId=object_id)["listeners"]
        counts[element_id] = sum(1 for one in listeners if one["type"] == "click")
    return counts


class TestTheBaseMapOwnsItsControls:
    """The base map binds the zoom buttons. This module binding them too gave each one two
    click listeners, so a single press zoomed two steps — invisible to every other gate,
    because the painted-pixels floor is a minimum and more zoom only paints more.
    """

    def test_each_zoom_button_has_exactly_one_click_listener(self, chrome):
        with background_server(REAL_SITE) as base, Browser() as browser:
            counts = _click_listener_counts(browser, base, BASE_MAP_OWNED_CONTROLS)
        assert counts == dict.fromkeys(BASE_MAP_OWNED_CONTROLS, 1), counts
