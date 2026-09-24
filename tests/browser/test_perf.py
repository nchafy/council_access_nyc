"""SLA-4: cold load to interactive, p95 under 3 s on the throttled 3G reference profile.

A synthetic measurement on a reference profile, never an observed field percentile —
analytics are banned, so there is no field data. Profile and threshold come from the
committed `perf-budget.json`.
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
    """The gating profile only; the reported-only profile is for `make perf`."""
    profile = settings["profiles"][settings["gating_profile"]]
    return measure_cold_load(built_site, TIMED_PAGES, profile, settings["runs"])


class TestColdLoad:
    def test_every_timed_page_meets_the_p95(self, cold_samples, settings):
        threshold = settings["cold_load_ms_p95"]
        over_threshold = {
            path: round(percentile(samples_ms, 0.95))
            for path, samples_ms in cold_samples.items()
            if percentile(samples_ms, 0.95) > threshold
        }
        assert not over_threshold, f"p95 over the {threshold} ms threshold: {over_threshold} ms"

    def test_it_took_the_required_number_of_samples(self, cold_samples, settings):
        for path, samples_ms in cold_samples.items():
            assert len(samples_ms) == settings["runs"], f"{path} produced {len(samples_ms)} samples"

    def test_every_page_type_that_a_reader_lands_on_is_timed(self, cold_samples):
        assert set(cold_samples) == set(TIMED_PAGES)
        assert "/" in cold_samples, "the front page is the cold-load case that matters most"

    def test_no_sample_is_implausibly_fast(self, cold_samples):
        for path, samples_ms in cold_samples.items():
            assert min(samples_ms) > 50, f"{path} reported an implausible {min(samples_ms)} ms"

    def test_the_measurement_is_actually_throttled(self, cold_samples, settings):
        """A navigation cannot finish faster than one round trip, so a sample below the
        profile's latency means the shaping never took effect and the gate is unfailable."""
        latency = settings["profiles"][settings["gating_profile"]]["latency_ms"]
        for path, samples_ms in cold_samples.items():
            assert min(samples_ms) > latency, (
                f"{path} loaded in {min(samples_ms)} ms with a {latency} ms round trip "
                "configured — the network shaping did not take effect"
            )


class TestPercentile:
    def test_it_takes_the_nearest_rank_and_does_not_interpolate(self):
        nineteen_fast_one_slow = [100.0] * 19 + [9000.0]
        assert percentile(nineteen_fast_one_slow, 0.95) == 100.0
        eighteen_fast_two_slow = [100.0] * 18 + [9000.0, 9000.0]
        assert percentile(eighteen_fast_two_slow, 0.95) == 9000.0

    def test_it_handles_a_single_sample(self):
        assert percentile([42.0], 0.95) == 42.0

    def test_it_never_runs_off_the_end(self):
        assert percentile([1.0, 2.0], 1.0) == 2.0
