"""R39: WCAG 2.2 AA SC 1.4.10 Reflow, at 320 px and at 390 px.

`TestTheGateCanFail` is what makes a clean sweep mean anything. It matters more here than
for axe: the measurement is a single number from the page, and a viewport override that
silently did not apply would report every page clean.
"""

from __future__ import annotations

import pytest
from pageset import every_page
from reflow_check import TOLERANCE_PX, WIDTHS, check, format_report

pytestmark = pytest.mark.browser


@pytest.fixture(scope="module")
def reflow_report(chrome, built_site):
    """One sweep of the whole fixture-built site at every gated width."""
    return check(built_site, every_page(built_site))


@pytest.fixture(scope="module")
def unreflowable_report(chrome, unreflowable_site):
    """The same code path, run against the fixture that cannot reflow."""
    return check(unreflowable_site, ["/"])


class TestReflow:
    def test_every_page_reflows_at_every_width(self, reflow_report):
        failed = {key: result for key, result in reflow_report["pages"].items() if result["failed"]}
        assert not failed, "\n" + format_report(
            {**reflow_report, "pages": failed}
        )

    def test_it_really_checked_every_page_at_every_width(self, reflow_report, built_site):
        # 115 pages x 2 widths.
        assert len(reflow_report["pages"]) == len(every_page(built_site)) * len(WIDTHS)

    def test_the_requested_width_was_applied(self, reflow_report):
        """The viewport the page reports must be the one asked for, or nothing was measured
        at a phone width and the sweep proves nothing."""
        for key, result in reflow_report["pages"].items():
            width = int(key.rpartition("@")[2])
            assert result["inner_width"] == pytest.approx(width, abs=TOLERANCE_PX), (
                f"{key} reports a {result['inner_width']} px viewport"
            )

    def test_the_gated_widths_include_the_wcag_requirement(self):
        """320 px is the SC 1.4.10 figure; dropping it would leave the criterion ungated."""
        assert 320 in WIDTHS


class TestTheGateCanFail:
    def test_the_unreflowable_fixture_fails(self, unreflowable_report):
        assert unreflowable_report["violations"] >= 1

    def test_it_fails_at_320_and_names_the_criterion(self, unreflowable_report):
        assert unreflowable_report["pages"]["/@320"]["failed"]
        assert "SC 1.4.10" in format_report(unreflowable_report)

    def test_the_failure_names_the_unbreakable_token(self, unreflowable_report):
        """A bare "this page overflows" does not say what to change."""
        report_text = format_report(unreflowable_report)
        assert "unbreakable" in report_text
        assert "averylongunbreakablepathsegment" in report_text

    def test_the_widened_viewport_is_the_signal(self, unreflowable_report):
        """The viewport widening past the requested width is the measurement that fails.

        On the real pages this is the *only* signal: once the layout viewport has widened,
        every element fits inside the widened value and a per-element check reports clean.
        """
        assert unreflowable_report["pages"]["/@320"]["inner_width"] > 320 + TOLERANCE_PX
