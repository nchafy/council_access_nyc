"""The map route, and the rule that it is the only page paying for the map.

`docs/dependencies.md` allows a vendored browser dependency on condition that it is
load-gated. That condition is only real if something checks it, so this file is the check:
one page may name MapLibre, and the map must not be the only way to reach a district.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from pageset import every_page
from perf import budget, gzipped_size

from showup.build import VENDOR_FILES, build_site
from showup.model import DISTRICT_COUNT

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def site(tmp_path_factory, raw_dir_session) -> Path:
    out = tmp_path_factory.mktemp("map-site")
    build_site(raw_dir_session, out, today=date(2026, 9, 22))
    return out


class TestTheRouteExists:
    def test_the_map_page_is_built(self, site):
        assert (site / "map" / "index.html").is_file()

    def test_it_is_in_the_page_set(self, site):
        assert "/map/" in every_page(site)

    def test_every_vendored_file_ships(self, site):
        assert {path.name for path in (site / "vendor").iterdir()} == set(VENDOR_FILES)

    def test_the_licence_ships_beside_the_library(self, site):
        """BSD-3-Clause travels with the code or we are not complying with it."""
        licence = (site / "vendor" / "LICENSE.txt").read_text(encoding="utf-8")
        assert "BSD" in licence or "Copyright" in licence


class TestOnlyTheMapPaysForTheMap:
    def test_no_other_page_mentions_maplibre(self, site):
        """The load-gating condition in docs/dependencies.md, enforced."""
        offenders = [
            path
            for path in every_page(site)
            if path != "/map/"
            and "maplibre"
            in (
                site / path.strip("/") / "index.html"
                if path.endswith("/")
                else site / path.strip("/")
            )
            .read_text(encoding="utf-8")
            .lower()
        ]
        assert not offenders, f"these pages would download the map library: {offenders}"

    def test_the_map_page_does_not_block_on_the_library(self, site):
        """The library is imported from the module, never as a blocking script tag, so the
        document's own weight stays inside R40's page budget."""
        html = (site / "map" / "index.html").read_text(encoding="utf-8")
        assert 'src="/vendor/maplibre-gl.mjs"' not in html
        assert 'src="/assets/map.mjs"' in html

    def test_the_library_is_inside_its_own_budget(self, site):
        """It is excluded from the page and script budgets, so it needs its own number."""
        total = sum(
            gzipped_size(path.read_bytes()) for path in (site / "vendor").glob("maplibre-gl*")
        )
        assert total <= budget()["map_library_gzip_bytes"]


class TestTheMapIsNeverTheOnlyWay:
    def test_all_51_districts_are_plain_links_on_the_map_page(self, site):
        """R6's location-free path. A WebGL canvas is not a navigation route."""
        html = (site / "map" / "index.html").read_text(encoding="utf-8")
        for number in range(1, DISTRICT_COUNT + 1):
            assert f'href="/district/{number}/"' in html

    def test_the_status_line_says_what_is_needed_before_any_script_runs(self, site):
        """Rendered into the document, so a reader with no JavaScript still reads it."""
        html = (site / "map" / "index.html").read_text(encoding="utf-8")
        assert "needs JavaScript and WebGL" in html

    def test_the_zoom_buttons_ship_hidden(self, site):
        """They do nothing until the map draws, and a control that lies is worse than none."""
        html = (site / "map" / "index.html").read_text(encoding="utf-8")
        assert '<div class="map-zoom" hidden' in html

    def test_the_front_page_links_to_it(self, site):
        assert 'href="/map/"' in (site / "index.html").read_text(encoding="utf-8")


class TestTheMapRefusesToRank:
    def test_the_page_says_districts_are_not_ranked(self, site):
        """product-brief.md §5: a shaded map reads as a ranking whatever the legend says."""
        html = (site / "map" / "index.html").read_text(encoding="utf-8")
        assert "scored or ranked" in html

    def test_the_fill_does_not_vary_by_any_datum(self):
        """One fill for every district, and one more only for what the reader selected."""
        source = (REPO_ROOT / "src" / "showup" / "assets" / "map.mjs").read_text(encoding="utf-8")
        assert "'fill-color'" in source
        # A data-driven fill would need one of these against a property.
        for ramp in ("interpolate", "step", "match"):
            assert f"'{ramp}'" not in source, f"a {ramp} fill expression shades by value"

    def test_the_geometry_it_draws_is_the_one_already_shipped(self, site):
        """No second geometry artifact: display reuses the resolution file."""
        html = (site / "map" / "index.html").read_text(encoding="utf-8")
        assert 'data-geometry="/data/districts.geo.json"' in html
        assert (site / "data" / "districts.geo.json").is_file()

    def test_the_geometry_carries_every_district(self, site):
        geometry = json.loads((site / "data" / "districts.geo.json").read_text(encoding="utf-8"))
        districts = {feature["properties"]["coundist"] for feature in geometry["features"]}
        assert len(districts) == DISTRICT_COUNT
