"""SLA-4: cold load to interactive, p95 under 3 s on throttled 3G.

The timed half of R40. `tests/integration/test_budget.py` carries the byte half, which
is arithmetic and runs everywhere; this one shapes Chrome's network and CPU to the
reference profile and measures.

Marked `browser` and `slow`, and honest about what it is: twenty throttled cold loads of
three pages is around a minute of wall clock, and the number it produces is a synthetic
measurement on a reference profile, never an observed field percentile. There is no field
data because analytics are banned, and §2 would rather say that than imply otherwise.

The profile and the threshold come from the committed `perf-budget.json`, so a change to
either is a reviewable diff instead of an edited constant.
"""

from __future__ import annotations

import pytest
from perf import TIMED_PAGES, budget, measure_cold_load, percentile

pytestmark = [pytest.mark.browser, pytest.mark.slow]


@pytest.fixture(scope="module")
def settings():
    return budget()


@pytest.fixture(scope="module")
def cold_samples(chrome, built_site, settings):
    """The gating profile only. The reported-only profile is for `make perf`.

    Running both here would double a minute-long test to produce a number that, by the
    budget file's own note, is not allowed to fail anything.
    """
    profile = settings["profiles"][settings["gating_profile"]]
    return measure_cold_load(built_site, TIMED_PAGES, profile, settings["runs"])


class TestColdLoad:
    def test_every_timed_page_meets_the_p95(self, cold_samples, settings):
        threshold = settings["cold_load_ms_p95"]
        over = {
            path: round(percentile(values, 0.95))
            for path, values in cold_samples.items()
            if percentile(values, 0.95) > threshold
        }
        assert not over, f"p95 over the {threshold} ms threshold: {over} ms"

    def test_it_took_the_required_number_of_samples(self, cold_samples, settings):
        """§6A asks for p95 over at least 20 runs; four fast runs would not be a p95."""
        for path, values in cold_samples.items():
            assert len(values) == settings["runs"], f"{path} produced {len(values)} samples"

    def test_every_page_type_that_a_reader_lands_on_is_timed(self, cold_samples):
        assert set(cold_samples) == set(TIMED_PAGES)
        assert "/" in cold_samples, "the front page is the cold-load case that matters most"

    def test_the_samples_are_plausible(self, cold_samples):
        """A throttled load cannot be instant, and a zero would mean the timing was
        read before the navigation it describes — a passing number for no reason."""
        for path, values in cold_samples.items():
            assert min(values) > 50, f"{path} reported an implausible {min(values)} ms"

    def test_the_measurement_is_actually_throttled(self, cold_samples, settings):
        """The gate's own premise. If throttling silently failed, every page would load
        in a few tens of milliseconds and the 3 s threshold would be unfailable.

        The floor is the round-trip latency of the gating profile: the browser cannot
        finish a navigation faster than one round trip, so a median below that means the
        shaping was not applied and the result means nothing.
        """
        latency = settings["profiles"][settings["gating_profile"]]["latency_ms"]
        for path, values in cold_samples.items():
            assert min(values) > latency, (
                f"{path} loaded in {min(values)} ms with a {latency} ms round trip "
                "configured — the network shaping did not take effect"
            )


class TestPercentile:
    """The p95 helper, checked directly: it decides whether the gate passes."""

    def test_it_takes_the_nearest_rank_and_does_not_interpolate(self):
        # 20 values, 19 fast and one slow: the p95 is the 19th ordered value, so one
        # slow run does not pass the gate and does not get averaged away either.
        values = [100.0] * 19 + [9000.0]
        assert percentile(values, 0.95) == 100.0
        values = [100.0] * 18 + [9000.0, 9000.0]
        assert percentile(values, 0.95) == 9000.0

    def test_it_handles_a_single_sample(self):
        assert percentile([42.0], 0.95) == 42.0

    def test_it_never_runs_off_the_end(self):
        assert percentile([1.0, 2.0], 1.0) == 2.0
