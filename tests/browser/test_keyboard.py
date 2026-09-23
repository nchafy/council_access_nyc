"""The keyboard pass and the screen-reader surface, as named assertions.

R39's second clause. Each check from `scripts/a11y_audit.py` is asserted individually so
a failure names itself — the pattern `test_address_box.py` already uses, for the same
reason: a single aggregate assertion tells you the page is broken, not which promise
broke.

Also asserts that each check *ran*. A check that silently stopped being collected is as
much a problem as one that failed, and an audit that returns an empty list would
otherwise pass every test in this file.

`docs/accessibility-pass.md` records the human half, which is the part no assertion here
replaces.
"""

from __future__ import annotations

import pytest
from a11y_audit import audit
from pageset import REPRESENTATIVE

pytestmark = pytest.mark.browser

#: Every check the audit is expected to produce for a page, by name. Pinned so that a
#: renamed or deleted check fails loudly rather than reducing coverage in silence.
PER_PAGE_CHECKS = (
    "the page has focusable content",
    "no positive tabindex",
    "the first Tab lands on the skip link",
    "the skip link is visible once focused",
    "tab order follows DOM order",
    "every focused element shows a focus ring",
    "every focusable element is reachable by Tab alone",
    "Shift+Tab retraces the order in reverse",
    "the skip link moves focus into main",
    "every required landmark is present",
    "every interactive node has an accessible name",
    "there is exactly one level-1 heading",
    "heading levels never skip a level",
)

FRONT_PAGE_CHECKS = (
    "script really was disabled",
    "all 51 districts are reachable as plain links",
    "all 59 boards are reachable as plain links",
    "the address box stays hidden without JavaScript",
    "the address box submits from the keyboard alone",
)


@pytest.fixture(scope="module")
def checks(chrome, built_site):
    return audit(built_site, list(REPRESENTATIVE))


class TestEveryCheckPasses:
    def test_nothing_failed(self, checks):
        failures = [check for check in checks if not check.ok]
        assert not failures, "\n".join(
            f"{check.page}  {check.name}: {check.detail}" for check in failures
        )

    @pytest.mark.parametrize("name", PER_PAGE_CHECKS)
    def test_the_check_ran_on_every_page_and_passed(self, checks, name):
        ran = {check.page for check in checks if check.name == name}
        assert ran == set(REPRESENTATIVE), (
            f"{name!r} did not run on {sorted(set(REPRESENTATIVE) - ran)}"
        )
        assert all(check.ok for check in checks if check.name == name)

    @pytest.mark.parametrize("name", FRONT_PAGE_CHECKS)
    def test_the_front_page_check_ran_and_passed(self, checks, name):
        matching = [check for check in checks if check.name == name]
        assert matching, f"{name!r} never ran"
        assert all(check.ok for check in matching), matching[0].detail


class TestTheAuditCoversWhatItClaims:
    def test_it_checked_every_page_type(self, checks):
        assert {check.page for check in checks} >= set(REPRESENTATIVE)

    def test_the_degraded_district_page_was_included(self, checks):
        """District 3 is the designed degraded state — vacant-seat handling, missing
        committees, the source-conflict notice. Its empty states are exactly where a
        heading level or a landmark goes missing."""
        assert any(check.page == "/district/3/" for check in checks)

    def test_no_check_is_silently_absent(self, checks):
        """Every name the audit can produce is one this file knows about, and the other
        way round. A new check that nothing asserts is a new check nobody reads."""
        produced = {check.name for check in checks}
        known = (
            set(PER_PAGE_CHECKS)
            | set(FRONT_PAGE_CHECKS)
            | {
                "the address box is reachable by Tab"  # only emitted on the failure path
            }
        )
        assert produced <= known, f"unasserted checks exist: {sorted(produced - known)}"
        assert set(PER_PAGE_CHECKS) <= produced, (
            f"checks stopped being produced: {sorted(set(PER_PAGE_CHECKS) - produced)}"
        )
