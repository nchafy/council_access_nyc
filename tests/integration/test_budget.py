"""R40's page-weight budget, enforced without a browser.

This is the half of R40 that is genuinely *enforced* rather than measured. It is
arithmetic over the built bytes — gzip the document and everything it blocks on, compare
against 60 KB — so it has no variance, cannot be flaky, needs no Chrome, and therefore
runs on every commit in the default suite. `tests/browser/test_perf.py` carries the
timed half, which needs a browser and reports a distribution.

Built from committed fixtures, so the numbers here are a CI runner's numbers and not
whatever happens to be in a developer's `etl/raw/`. The one thing that cannot be checked
this way is the size of the real simplified geometry, because the fixture geometry is 51
synthetic squares; what *is* checked hermetically is the property that matters more —
that geometry is not on the critical path at all.
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
        over = [
            (weight.path, weight.total, weight.parts)
            for weight in weigh(site, list(REPRESENTATIVE))
            if weight.total > limit
        ]
        assert not over, f"over the {limit}-byte budget: {over}"

    def test_the_heaviest_page_has_headroom(self, site):
        """A budget met at 99% is a budget about to be missed.

        Not a second threshold with a second opinion: at ~14 KB the front page uses
        under a quarter of the allowance, and if that ever triples, the reason is worth
        knowing before the hard gate trips on an unrelated commit.
        """
        limit = budget()["page_weight_gzip_bytes"]
        heaviest = max(weigh(site, list(REPRESENTATIVE)), key=lambda weight: weight.total)
        assert heaviest.total < limit * 0.75, (
            f"{heaviest.path} is at {heaviest.total} of {limit} bytes, with little room "
            f"left. Parts: {heaviest.parts}"
        )

    def test_all_the_javascript_together_stays_small(self, site):
        """A separate, tighter ceiling on script alone.

        The 60 KB page budget is loose enough that a framework could hide inside it. The
        decision in §2 is vanilla ES modules, no bundler, no runtime dependency — a
        claim about the code that shows up as a number here. React and its DOM package
        alone are roughly 45 KB gzipped, so anything of that shape trips this long
        before it troubles the page budget.

        An earlier version of this test asserted the document outweighs the scripts.
        That was an invented rule and it was false: address.js is 5 KB gzipped against a
        4 KB document, because the address box is a real feature and the fixture front
        page carries less text than the real one. The bound worth having is on the
        script total, not on the ratio.
        """
        limit = budget()["script_gzip_bytes"]
        weight = page_weight(site, "/")
        scripts = {name: size for name, size in weight.parts.items() if name.endswith(".js")}
        assert sum(scripts.values()) <= limit, (
            f"script totals {sum(scripts.values())} bytes gzipped, over the {limit} "
            f"ceiling: {scripts}"
        )


class TestGeometryIsOffTheCriticalPath:
    """§6A.3 and R40: geometry loads after first paint, never with the document."""

    def test_no_page_references_the_geometry_as_a_subresource(self, site):
        """A preload hint or a synchronous script tag would silently move 132 KB onto
        the critical path while leaving the page-weight arithmetic above unchanged,
        because that arithmetic only counts what the document names."""
        for html in site.rglob("*.html"):
            text = html.read_text(encoding="utf-8")
            for tag in ("<link", "<script"):
                for fragment in text.split(tag)[1:]:
                    element = fragment.split(">")[0]
                    assert "districts.geo.json" not in element, (
                        f"{html.relative_to(site)} loads the geometry as a subresource"
                    )

    def test_the_geometry_exists_and_is_only_fetched_by_script(self, site):
        """It must still ship — the address path needs it — just not up front."""
        assert (site / "data" / "districts.geo.json").is_file()
        address_js = (REPO_ROOT / "src" / "showup" / "assets" / "address.js").read_text()
        assert "/data/districts.geo.json" in address_js


class TestTheBudgetFileItself:
    """The thresholds are a promise; a promise that can be edited quietly is not one."""

    def test_the_page_weight_budget_is_r40s_60_kb(self):
        assert budget()["page_weight_gzip_bytes"] == 60 * 1024

    def test_the_geometry_budget_is_6as_300_kb(self):
        assert budget()["geometry_gzip_bytes"] == 300 * 1024

    def test_the_cold_load_threshold_is_sla_4s_3_seconds(self):
        assert budget()["cold_load_ms_p95"] == 3000

    def test_at_least_20_runs_are_required(self):
        """§6A: p95 over at least 20 runs. Fewer samples make the p95 meaningless."""
        assert budget()["runs"] >= 20

    def test_the_gating_profile_exists_and_is_throttled(self):
        settings = budget()
        profile = settings["profiles"][settings["gating_profile"]]
        assert profile["cpu"] >= 4, "the reference device is a mid-tier Android, not a laptop"
        assert profile["latency_ms"] > 0
        assert profile["download_bps"] <= 250_000, "faster than 2 Mbit/s is not 3G"

    def test_it_is_valid_json_with_its_reasoning_attached(self):
        settings = json.loads(BUDGET_FILE.read_text(encoding="utf-8"))
        # Every threshold carries a `_note` explaining where the number came from.
        # A number without provenance is a bug, here as much as on a page.
        for key in ("page_weight", "script", "geometry", "runs", "profile"):
            assert f"_{key}_note" in settings, f"{key} has no recorded reasoning"


class TestGzipMeasurementIsStable:
    def test_the_same_bytes_always_measure_the_same(self):
        """mtime is zeroed in `gzipped_size`; without that the budget would wobble by a
        few bytes per run and a near-threshold page would fail intermittently."""
        payload = b"the next five Council meetings" * 100
        assert gzipped_size(payload) == gzipped_size(payload)

    def test_it_measures_compressed_not_raw(self):
        payload = b"a" * 10_000
        assert gzipped_size(payload) < 200
