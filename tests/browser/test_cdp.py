"""The CDP channel's own properties, independent of any page under test.

The browser gates exercise `cdp.py` at typical sizes; these assert the two edges a gate
would only fail on intermittently — a message past a library's usual read limit, and
multi-byte UTF-8 inside one.
"""

from __future__ import annotations

import pytest
from cdp import Browser

pytestmark = pytest.mark.browser


class TestTheChannelCarriesLargeMessages:
    """`axe.min.js` goes in at ~567 KB and a full AX tree comes back in megabytes, so a
    read limit near 1 MB would fail only on the largest pages."""

    def test_a_multi_megabyte_expression_reaches_the_page(self, chrome):
        characters = 4 * 1024 * 1024
        with Browser() as browser:
            page = browser.page()
            assert page.evaluate(f"'{'x' * characters}'.length") == characters

    def test_a_multi_megabyte_result_comes_back_intact(self, chrome):
        repeats = 700_000
        with Browser() as browser:
            page = browser.page()
            returned = page.evaluate(f"'Avilés'.repeat({repeats})")
        assert len(returned) == repeats * 6
        assert returned.startswith("Avilés")
        assert returned.endswith("Avilés")

    def test_the_channel_reports_the_title_it_loaded(self, chrome):
        with Browser() as browser:
            page = browser.page()
            page.navigate("data:text/html,<title>channel works</title>")
            assert page.evaluate("document.title") == "channel works"
