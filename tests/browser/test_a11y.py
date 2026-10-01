"""R39: axe over every pre-rendered page, plus a negative control that must fail.

`TestTheGateCanFail` is what makes a clean sweep mean anything — "clean" is otherwise
indistinguishable from "nothing ran".
"""

from __future__ import annotations

import pytest
from axe_check import GATING_TAGS, MINIMUM_RULES_EXERCISED, check, format_report
from pageset import REPRESENTATIVE, every_page

pytestmark = pytest.mark.browser


@pytest.fixture(scope="module")
def axe_report(chrome, built_site):
    """One axe sweep of the whole fixture-built site, shared by the tests below."""
    return check(built_site, every_page(built_site))


@pytest.fixture(scope="module")
def broken_report(chrome, broken_site):
    """The same code path, run against the deliberately inaccessible fixture."""
    return check(broken_site, ["/"])


class TestAxe:
    def test_every_page_is_clean(self, axe_report):
        pages_with_violations = {
            path: result["violations"]
            for path, result in axe_report["pages"].items()
            if result["violations"]
        }
        assert not pages_with_violations, "\n" + format_report(
            {
                **axe_report,
                "pages": {path: axe_report["pages"][path] for path in pages_with_violations},
            }
        )

    def test_it_really_checked_every_page(self, axe_report, built_site):
        assert set(axe_report["pages"]) == set(every_page(built_site))
        # 51 districts + 59 boards + two indexes + the front page + 404.
        assert len(axe_report["pages"]) == 114

    def test_every_page_actually_exercised_rules(self, axe_report):
        for path, result in axe_report["pages"].items():
            assert result["exercised"] >= MINIMUM_RULES_EXERCISED, (
                f"{path} exercised only {result['exercised']} rules"
            )

    def test_the_conformance_target_is_wcag_22_aa(self):
        assert set(GATING_TAGS) == {
            "wcag2a",
            "wcag2aa",
            "wcag21a",
            "wcag21aa",
            "wcag22a",
            "wcag22aa",
        }


class TestTheGateCanFail:
    @pytest.mark.parametrize(
        "rule",
        [
            "html-has-lang",
            "document-title",
            "image-alt",
            "label",
            "color-contrast",
            "link-name",
        ],
    )
    def test_each_planted_defect_is_found(self, broken_report, rule):
        reported_rules = {
            violation["id"] for violation in broken_report["pages"]["/"]["violations"]
        }
        assert rule in reported_rules, f"the gate missed {rule}; found {sorted(reported_rules)}"

    def test_the_report_is_a_failing_one(self, broken_report):
        assert broken_report["violations"] >= 6

    def test_the_failure_message_names_the_page_and_the_rule(self, broken_report):
        report_text = format_report(broken_report)
        assert "FAIL /" in report_text
        assert "https://dequeuniversity.com" in report_text, (
            "a finding must link its own explanation"
        )


class TestPageSet:
    def test_the_representative_set_covers_every_page_type(self, built_site):
        assert set(REPRESENTATIVE) <= set(every_page(built_site))

    def test_it_includes_the_degraded_district(self):
        """`district-3` is the designed degraded state, where empty states go wrong."""
        assert "/district/3/" in REPRESENTATIVE

    def test_every_entry_says_why_it_is_there(self):
        for path, reason in REPRESENTATIVE.items():
            assert len(reason) > 20, f"{path} has no stated reason for being in the set"
