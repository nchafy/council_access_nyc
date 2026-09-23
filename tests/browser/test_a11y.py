"""The accessibility gate: axe over every pre-rendered page, and the negative control.

R39 asks for axe over every pre-rendered page in CI. That is what
`test_every_page_is_clean` does — all 114 of them, against a site built from
committed fixtures so it runs on a machine that has never fetched anything.

`TestTheGateCanFail` is the test that makes the rest trustworthy. The site passed
axe on the first run it was ever given, and "clean" is indistinguishable from
"nothing ran" unless something proves the gate can still fail. It runs the same code
path against `tests/fixtures/a11y_broken.html` and asserts each planted defect is
found by name.

Marked `browser`: needs a real Chrome. Run with `make browser`, or `make axe` for
the same check against the real `site/`.
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
        offenders = {
            path: result["violations"]
            for path, result in axe_report["pages"].items()
            if result["violations"]
        }
        assert not offenders, "\n" + format_report(
            {**axe_report, "pages": {path: axe_report["pages"][path] for path in offenders}}
        )

    def test_it_really_checked_every_page(self, axe_report, built_site):
        """A sweep that silently skipped half the site would still report clean."""
        assert set(axe_report["pages"]) == set(every_page(built_site))
        # 51 districts + 59 boards + two indexes + the front page + 404.
        assert len(axe_report["pages"]) == 114

    def test_every_page_actually_exercised_rules(self, axe_report):
        for path, result in axe_report["pages"].items():
            assert result["exercised"] >= MINIMUM_RULES_EXERCISED, (
                f"{path} exercised only {result['exercised']} rules"
            )

    def test_the_conformance_target_is_wcag_22_aa(self):
        """The tags are the requirement. Narrowing them would weaken the gate
        silently, so the list is asserted rather than merely used."""
        assert set(GATING_TAGS) == {
            "wcag2a",
            "wcag2aa",
            "wcag21a",
            "wcag21aa",
            "wcag22a",
            "wcag22aa",
        }


class TestTheGateCanFail:
    """Prove the gate detects what it claims to detect."""

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
        found = {violation["id"] for violation in broken_report["pages"]["/"]["violations"]}
        assert rule in found, f"the gate missed {rule}; found {sorted(found)}"

    def test_the_report_is_a_failing_one(self, broken_report):
        assert broken_report["violations"] >= 6

    def test_the_failure_message_names_the_page_and_the_rule(self, broken_report):
        text = format_report(broken_report)
        assert "FAIL /" in text
        assert "https://dequeuniversity.com" in text, "a finding must link its own explanation"


class TestPageSet:
    """The page list is itself a promise; assert it covers what it says it covers."""

    def test_the_representative_set_covers_every_page_type(self, built_site):
        assert set(REPRESENTATIVE) <= set(every_page(built_site))

    def test_it_includes_the_degraded_district(self):
        """`district-3` is the designed degraded state. A page-type list that omitted
        it would leave the states most likely to be broken unchecked."""
        assert "/district/3/" in REPRESENTATIVE

    def test_every_entry_says_why_it_is_there(self):
        for path, reason in REPRESENTATIVE.items():
            assert len(reason) > 20, f"{path} has no stated reason for being in the set"
