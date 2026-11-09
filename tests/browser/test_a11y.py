"""R39: axe over every pre-rendered page and every program's window, plus negative controls.

`TestTheGateCanFail` is what makes a clean sweep mean anything — "clean" is otherwise
indistinguishable from "nothing ran".

A sweep of routes alone stopped meaning anything when the front end became a window manager:
116 pages became one document, and the 51 districts, 59 boards and both indexes became
windows built in the browser. `pageset.PROGRAM_SURFACES` is the other half of the list, and
`TestPageSet` is what stops a program from being added without one.
"""

from __future__ import annotations

import pytest
from axe_check import (
    GATING_TAGS,
    MINIMUM_RULES_EXERCISED,
    MINIMUM_WINDOW_RULES,
    check,
    format_report,
)
from pageset import PROGRAM_SURFACES, REPRESENTATIVE, every_page
from test_webxp import PROGRAMS

pytestmark = pytest.mark.browser


@pytest.fixture(scope="module")
def axe_report(chrome, built_site):
    """One axe sweep of the whole fixture-built site, shared by the tests below."""
    return check(built_site, every_page(built_site))


@pytest.fixture(scope="module")
def broken_report(chrome, broken_site):
    """The same code path, run against the deliberately inaccessible fixture.

    No surfaces: the fixture is a plain document with planted defects, not a desktop, so
    there is no program to launch. Spelled out rather than defaulted, because a silent empty
    sweep here would disarm every control below.
    """
    return check(broken_site, ["/"], surfaces=())


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

    def test_it_really_checked_every_surface(self, axe_report, built_site):
        """One document and seven windows. A sweep that quietly lost a surface would
        otherwise report the same clean result over less of the site."""
        assert set(axe_report["pages"]) == set(every_page(built_site)) | {
            surface.name for surface in PROGRAM_SURFACES
        }
        assert len(axe_report["pages"]) == 1 + len(PROGRAM_SURFACES)

    def test_every_surface_actually_exercised_rules(self, axe_report, built_site):
        """A window is a scoped fragment, so it has no `document-title` or `html-has-lang`
        to run and legitimately exercises fewer rules than the document holding it."""
        routes = set(every_page(built_site))
        for name, result in axe_report["pages"].items():
            floor = MINIMUM_RULES_EXERCISED if name in routes else MINIMUM_WINDOW_RULES
            assert result["exercised"] >= floor, (
                f"{name} exercised only {result['exercised']} rules, expected {floor}"
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

    def test_every_program_has_a_surface(self):
        """The replacement for "116 pages were checked". A program added without a surface
        here is simply never looked at, and the sweep still reports clean."""
        assert {surface.program for surface in PROGRAM_SURFACES} == set(PROGRAMS)

    def test_it_includes_the_degraded_district(self):
        """`district-3` is the designed degraded state, where empty states go wrong. It was
        `/district/3/`; it is a selection inside the councils program now."""
        assert any(
            surface.program == "showup-councils" and surface.click == '.pick[data-district="3"]'
            for surface in PROGRAM_SURFACES
        ), [surface.name for surface in PROGRAM_SURFACES]

    def test_every_surface_name_is_distinct(self):
        """Two surfaces sharing a name would overwrite each other in the report, so one would
        be checked and both would look checked."""
        names = [surface.name for surface in PROGRAM_SURFACES]
        assert len(names) == len(set(names)), names

    def test_every_entry_says_why_it_is_there(self):
        for path, reason in REPRESENTATIVE.items():
            assert len(reason) > 20, f"{path} has no stated reason for being in the set"
        for surface in PROGRAM_SURFACES:
            assert len(surface.reason) > 20, f"{surface.name} has no stated reason"
