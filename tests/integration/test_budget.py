"""R40's page-weight budget: gzip the document and everything it blocks on, under 60 KB.

Arithmetic over bytes built from committed fixtures, so it needs no browser and cannot
be flaky. `tests/browser/test_perf.py` carries the timed half of R40.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from pageset import REPRESENTATIVE
from perf import BUDGET_FILE, budget, gzipped_size, page_weight, weigh

from showup.build import build_site

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def site(tmp_path_factory, raw_dir_session) -> Path:
    out = tmp_path_factory.mktemp("budget-site")
    build_site(raw_dir_session, out, today=date(2026, 9, 22))
    return out


class TestPageWeight:
    def test_every_page_type_is_inside_the_budget(self, site):
        limit = budget()["page_weight_gzip_bytes"]
        over_budget = [
            (weight.path, weight.total, weight.parts)
            for weight in weigh(site, list(REPRESENTATIVE))
            if weight.total > limit
        ]
        assert not over_budget, f"over the {limit}-byte budget: {over_budget}"

    def test_the_heaviest_page_uses_under_three_quarters_of_the_budget(self, site):
        """A budget met at 99% is a budget about to be missed."""
        limit = budget()["page_weight_gzip_bytes"]
        heaviest = max(weigh(site, list(REPRESENTATIVE)), key=lambda weight: weight.total)
        assert heaviest.total < limit * 0.75, (
            f"{heaviest.path} is at {heaviest.total} of {limit} bytes, with little room "
            f"left. Parts: {heaviest.parts}"
        )

    def test_all_the_javascript_together_stays_small(self, site):
        """A second, tighter ceiling: a framework would hide inside the 60 KB page budget."""
        limit = budget()["script_gzip_bytes"]
        weight = page_weight(site, "/")
        scripts = {name: size for name, size in weight.parts.items() if name.endswith(".js")}
        assert sum(scripts.values()) <= limit, (
            f"script totals {sum(scripts.values())} bytes gzipped, over the {limit} "
            f"ceiling: {scripts}"
        )


class TestGeometryIsOffTheCriticalPath:
    def test_no_page_references_the_geometry_as_a_subresource(self, site):
        for html_file in site.rglob("*.html"):
            text = html_file.read_text(encoding="utf-8")
            for tag_start in ("<link", "<script"):
                for text_after_tag_start in text.split(tag_start)[1:]:
                    tag = text_after_tag_start.split(">")[0]
                    assert "districts.geo.json" not in tag, (
                        f"{html_file.relative_to(site)} loads the geometry as a subresource"
                    )

    def test_the_geometry_exists_and_is_only_fetched_by_script(self, site):
        assert (site / "data" / "districts.geo.json").is_file()
        address_js = (REPO_ROOT / "src" / "showup" / "assets" / "address.js").read_text()
        assert "/data/districts.geo.json" in address_js


class TestTheBudgetFileItself:
    def test_the_page_weight_budget_is_r40s_60_kb(self):
        assert budget()["page_weight_gzip_bytes"] == 60 * 1024

    def test_the_geometry_budget_is_6as_300_kb(self):
        assert budget()["geometry_gzip_bytes"] == 300 * 1024

    def test_the_cold_load_threshold_is_sla_4s_3_seconds(self):
        assert budget()["cold_load_ms_p95"] == 3000

    def test_at_least_20_runs_are_required_for_the_p95(self):
        assert budget()["runs"] >= 20

    def test_the_gating_profile_exists_and_is_throttled(self):
        settings = budget()
        profile = settings["profiles"][settings["gating_profile"]]
        assert profile["cpu"] >= 4, "the reference device is a mid-tier Android, not a laptop"
        assert profile["latency_ms"] > 0
        assert profile["download_bps"] <= 250_000, "faster than 2 Mbit/s is not 3G"

    def test_every_threshold_records_where_its_number_came_from(self):
        settings = json.loads(BUDGET_FILE.read_text(encoding="utf-8"))
        for key in ("page_weight", "script", "geometry", "runs", "profile"):
            assert f"_{key}_note" in settings, f"{key} has no recorded reasoning"


class TestGzipMeasurementIsStable:
    def test_the_same_bytes_always_measure_the_same(self):
        """`gzipped_size` zeroes mtime; without that a near-threshold page would flake."""
        payload = b"the next five Council meetings" * 100
        assert gzipped_size(payload) == gzipped_size(payload)

    def test_it_measures_compressed_not_raw(self):
        payload = b"a" * 10_000
        assert gzipped_size(payload) < 200
