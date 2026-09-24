"""R39's keyboard pass and screen-reader surface, one named assertion per check.

Each check from `scripts/a11y_audit.py` is asserted individually, and asserted to have
*run*, so an audit that silently stopped collecting a check cannot pass this file.
"""

from __future__ import annotations

import pytest
from a11y_audit import audit
from pageset import REPRESENTATIVE

pytestmark = pytest.mark.browser

#: Pinned so a renamed or deleted check fails loudly rather than reducing coverage.
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
        failed_checks = [check for check in checks if not check.ok]
        assert not failed_checks, "\n".join(
            f"{check.page}  {check.name}: {check.detail}" for check in failed_checks
        )

    @pytest.mark.parametrize("name", PER_PAGE_CHECKS)
    def test_the_check_ran_on_every_page_and_passed(self, checks, name):
        pages_that_ran_it = {check.page for check in checks if check.name == name}
        assert pages_that_ran_it == set(REPRESENTATIVE), (
            f"{name!r} did not run on {sorted(set(REPRESENTATIVE) - pages_that_ran_it)}"
        )
        assert all(check.ok for check in checks if check.name == name)

    @pytest.mark.parametrize("name", FRONT_PAGE_CHECKS)
    def test_the_front_page_check_ran_and_passed(self, checks, name):
        matching_checks = [check for check in checks if check.name == name]
        assert matching_checks, f"{name!r} never ran"
        assert all(check.ok for check in matching_checks), matching_checks[0].detail


class TestTheAuditCoversWhatItClaims:
    def test_it_checked_every_page_type(self, checks):
        assert {check.page for check in checks} >= set(REPRESENTATIVE)

    def test_the_degraded_district_page_was_included(self, checks):
        """District 3 is the designed degraded state: vacant seat, no committees."""
        assert any(check.page == "/district/3/" for check in checks)

    def test_no_check_is_produced_that_this_file_does_not_assert(self, checks):
        produced_names = {check.name for check in checks}
        asserted_names = (
            set(PER_PAGE_CHECKS)
            | set(FRONT_PAGE_CHECKS)
            | {
                "the address box is reachable by Tab"  # only emitted on the failure path
            }
        )
        assert produced_names <= asserted_names, (
            f"unasserted checks exist: {sorted(produced_names - asserted_names)}"
        )
        assert set(PER_PAGE_CHECKS) <= produced_names, (
            f"checks stopped being produced: {sorted(set(PER_PAGE_CHECKS) - produced_names)}"
        )
