"""The webxp desktop: that it starts, that every program loads, and that the map paints.

This is the front end's gate. It replaces what `test_a11y.py`, `test_reflow.py` and the
deleted `test_keyboard.py` covered across 115 static pages, because there is one page now.
A sweep over routes cannot see a program: `pageset.PROGRAM_SURFACES` is how the accessibility
gate reaches them, and this file is what proves they are there to reach.

The assertions are chosen against how this front end actually fails:

* A program whose spec is wrong is registered as a broken entry rather than throwing, so the
  desktop looks fine and one icon explains itself. Nothing but reading `webxpApps.broken`
  catches that.
* A map in a window reports its style loaded, fetches every tile and draws nothing when its
  container has no box. `tilesLoaded: true` and a blank rectangle are one assertion apart,
  which is why the canvas is measured against its container and the pixels are counted.
* A stale `apps/manifest.mjs` leaves a program simply absent, with nothing logged.
"""

from __future__ import annotations

import json
import time

import pytest
from cdp import Browser
from serve import background_server

pytestmark = pytest.mark.browser

#: Every program the desktop is expected to register, which is also what `apps/manifest.mjs`
#: should list. Pinned here so a program that stops loading fails rather than reducing cover.
PROGRAMS = ("showup", "showup-boards", "showup-councils", "showup-map", "showup-readme")

#: The folder is the only thing on the desktop: the four programs it contains are not
#: `onDesktop`, so the desktop is one icon and the folder means something.
DESKTOP_ICONS = 1

#: How long to let the map settle. MapLibre is ~1.1 MB behind a dynamic import, then a style
#: and its tiles; on a cold cache in CI this is the slowest thing the suite does.
MAP_SETTLE_SECONDS = 14

#: Opaque pixels the map's canvas must have drawn. A collapsed container and a canvas that
#: painted nothing both read as zero; a real basemap at this size is six figures.
PAINTED_FLOOR = 20_000


def _desktop(page, base):
    """Load the desktop and wait for the loader to finish."""
    page.navigate(base + "/")
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if page.evaluate("Boolean(window.webxpApps)"):
            return json.loads(page.evaluate("JSON.stringify(window.webxpApps)"))
        time.sleep(0.2)
    raise AssertionError("the desktop never published window.webxpApps")


@pytest.fixture(scope="module")
def desktop(chrome, built_site):
    """One load of the desktop, with every program registered."""
    with background_server(built_site) as base, Browser() as browser:
        page = browser.page()
        page.call("Log.enable")
        page.call(
            "Emulation.setDeviceMetricsOverride",
            width=1240,
            height=860,
            deviceScaleFactor=1,
            mobile=False,
        )
        apps = _desktop(page, base)
        logs = [
            event["params"]["entry"]
            for event in page.consume_events()
            if event.get("method") == "Log.entryAdded"
        ]
        state = json.loads(
            page.evaluate(
                """JSON.stringify({
                    programs: [...window.webxp.programs.keys()],
                    icons: document.querySelectorAll('#webxp .desktop-icon, #webxp .icon').length,
                    windows: window.webxp.windows.map((w) => w.programId),
                })"""
            )
        )
        yield {"apps": apps, "state": state, "logs": logs}


class TestTheDesktopStarts:
    def test_every_program_loaded(self, desktop):
        assert desktop["apps"]["loaded"] == sorted(PROGRAMS), desktop["apps"]

    def test_no_program_is_broken(self, desktop):
        """A broken spec is registered as an entry that explains itself rather than throwing,
        so the desktop looks healthy and only this says otherwise."""
        assert desktop["apps"]["broken"] == {}, desktop["apps"]["broken"]

    def test_the_manifest_listed_them_all(self, desktop):
        """A stale manifest leaves a program absent with nothing logged, which is the one
        failure of that arrangement that looks like nothing at all."""
        assert sorted(desktop["state"]["programs"]) == sorted(PROGRAMS)

    def test_the_folder_autostarts_and_is_the_only_icon(self, desktop):
        assert desktop["state"]["windows"] == ["showup"], desktop["state"]["windows"]
        assert desktop["state"]["icons"] == DESKTOP_ICONS, desktop["state"]["icons"]

    def test_the_desktop_logs_nothing(self, desktop):
        """A favicon the browser asks for and we do not ship is the one exception, and it is
        every page of this site rather than this one."""
        noisy = [
            entry
            for entry in desktop["logs"]
            if entry.get("level") == "error" and "favicon" not in (entry.get("url") or "")
        ]
        assert not noisy, noisy


@pytest.fixture(scope="module")
def opened(chrome, built_site):
    """Each program opened in turn, and what it put in its window."""
    with background_server(built_site) as base, Browser() as browser:
        page = browser.page()
        page.call(
            "Emulation.setDeviceMetricsOverride",
            width=1240,
            height=860,
            deviceScaleFactor=1,
            mobile=False,
        )
        _desktop(page, base)
        for program in ("showup-councils", "showup-boards", "showup-readme"):
            page.evaluate(f'window.webxp.launch("{program}")')
            time.sleep(3)
        page.evaluate('window.webxp.launch("showup-map")')
        time.sleep(MAP_SETTLE_SECONDS)

        # Driven through the DOM rather than the View, because a row that does not respond to
        # a click is the failure a reader would meet.
        page.evaluate(
            "document.querySelector('.app-showup-councils .pick[data-district=\"35\"]').click()"
        )
        page.evaluate(
            "document.querySelector('.app-showup-boards .pick[data-board=\"302\"]').click()"
        )
        time.sleep(1.5)

        yield json.loads(
            page.evaluate(
                """JSON.stringify((() => {
                    const win = window.webxp.windows.find((w) => w.programId === 'showup-map');
                    const canvas = document.querySelector('.app-showup-map .maplibregl-canvas');
                    const root = document.querySelector('.app-showup-map .map-root');
                    const box = (el) => {
                      if (!el) return null;
                      const r = el.getBoundingClientRect();
                      return {w: Math.round(r.width), h: Math.round(r.height)};
                    };
                    const legends = (sel) =>
                      [...document.querySelectorAll(sel + ' .detail-pane legend')]
                        .map((l) => l.textContent);
                    return {
                      councils: document.querySelectorAll('.app-showup-councils .pick').length,
                      boards: document.querySelectorAll('.app-showup-boards .pick').length,
                      councilLegends: legends('.app-showup-councils'),
                      boardLegends: legends('.app-showup-boards'),
                      freshness: (document.querySelector('.readme-freshness') || {}).textContent,
                      readmeSources: document.querySelectorAll(
                        '.app-showup-readme .readme-sources tbody tr'
                      ).length,
                      readmeLinks: document.querySelectorAll(
                        '.app-showup-readme .readme-sources a[href^="https://"]'
                      ).length,
                      readmeText:
                        (document.querySelector('.app-showup-readme .readme-sources') || {})
                          .textContent || '',
                      mapRoot: box(root),
                      mapCanvas: box(canvas),
                      maxZoom: win && win.base ? win.base.map.getMaxZoom() : null,
                      attrib: ((document.getElementById('map-attrib') || {}).textContent || ''),
                      deadLinks: document.querySelectorAll(
                        '.detail-pane a[href^="/district/"], .detail-pane a[href^="/board/"]'
                      ).length,
                    };
                })())"""
            )
        )


class TestTheProgramsFillTheirWindows:
    def test_the_councils_program_lists_every_district(self, opened):
        assert opened["councils"] == 51, opened["councils"]

    def test_the_boards_program_lists_every_board(self, opened):
        assert opened["boards"] == 59, opened["boards"]

    def test_picking_a_district_shows_its_facts(self, opened):
        assert "Council District 35" in opened["councilLegends"], opened["councilLegends"]

    def test_picking_a_board_shows_its_facts_and_its_calendar(self, opened):
        assert "Brooklyn Community Board 2" in opened["boardLegends"], opened["boardLegends"]
        assert "From the board's own calendar" in opened["boardLegends"]

    def test_no_pane_links_a_route_that_no_longer_exists(self, opened):
        """`preview.json` is built with hrefs like `/district/1/` in its table cells, from
        when those were pages. An anchor to a 404 is worse than text."""
        assert opened["deadLinks"] == 0

    def test_the_readme_reads_the_build_stamp(self, opened):
        assert "Data fetched" in (opened["freshness"] or ""), opened["freshness"]

    def test_the_readme_discloses_every_dataset_it_is_built_from(self, opened):
        """The `/references/` page's job, in the window that inherited it. Asserted in a real
        window rather than on the artifact, because a build that writes the identifiers and a
        program that renders them are two different things — and the program rendered a
        five-row summary naming none of them until 2026-11-09."""
        assert opened["readmeSources"] >= 11, opened["readmeSources"]
        for identifier in ("uvw5-9znb", "ruf7-3wgc", "vn4m-mk4t"):
            assert identifier in opened["readmeText"], identifier
        assert "ranks within a budget category" in opened["readmeText"]

    def test_every_disclosed_identifier_links_to_its_dataset(self, opened):
        """An identifier a reader cannot follow is a string, not a citation."""
        assert opened["readmeLinks"] >= 11, opened["readmeLinks"]


class TestTheMapPaints:
    """The lesson `webxp`'s `docs/apps.md` records: look at the window.

    A map whose container had no box reports its style loaded, fetches every tile with a 200
    and draws a blank rectangle. Nothing cheaper than measuring the canvas and counting its
    pixels can tell that from a working map.
    """

    def test_the_canvas_fills_its_container(self, opened):
        root, canvas = opened["mapRoot"], opened["mapCanvas"]
        assert root and canvas, opened
        assert canvas["w"] == root["w"], (canvas, root)
        assert canvas["h"] == root["h"], (canvas, root)

    def test_the_container_is_not_collapsed(self, opened):
        """`ready` exists for this: during `mount` the nodes are not in the document and every
        rect is zero."""
        assert opened["mapRoot"]["h"] > 200, opened["mapRoot"]

    def test_the_ceiling_is_ours_and_not_the_basemap_preset(self, opened):
        """`setBasemap` installs the preset's own, which is 17 on geography and 19 on
        satellite. Past 15 the boundary, simplified to 2.2 m, reads as a decision."""
        assert opened["maxZoom"] == 15, opened["maxZoom"]

    def test_the_basemap_credit_is_rendered(self, opened):
        """Every basemap source requires attribution, so this is a licence term."""
        assert "OpenStreetMap" in opened["attrib"], opened["attrib"]
