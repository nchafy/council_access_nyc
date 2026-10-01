"""The template environment, which is where the escaping boundary now lives.

`test_template_safety.py` holds the invariant that spans both renderers — no opt-outs,
autoescape on. This file pins what the environment itself has to do for that invariant
to mean anything: find its templates, escape, refuse a misspelled name, and spell the
two quote entities the way `text.esc` spelled them.
"""

from __future__ import annotations

import pytest
from jinja2 import UndefinedError

from showup import templates


class TestTheEnvironment:
    def test_the_templates_ship_inside_the_package(self):
        # PackageLoader reads from the installed package, so a template left out of
        # the wheel would only fail after install, never in the source tree.
        assert templates.environment().get_template("layout.html")

    def test_escaping_is_on_without_asking(self):
        rendered = (
            templates.environment()
            .from_string("{{ value }}")
            .render(value="<script>alert(1)</script>")
        )
        assert rendered == "&lt;script&gt;alert(1)&lt;/script&gt;"

    def test_a_misspelled_name_is_an_error_not_a_silent_blank(self):
        with pytest.raises(UndefinedError):
            templates.environment().from_string("{{ tyop }}").render()


class TestQuoteEntities:
    def test_quotes_are_spelled_the_way_html_escape_spelled_them(self):
        """MarkupSafe writes `&#39;` and `&#34;`; both spellings are inert, and keeping
        `html.escape`'s is what makes the migration provably byte-identical."""
        assert templates.fragment("em", 'Hell\'s "Kitchen"') == (
            "<em>Hell&#x27;s &quot;Kitchen&quot;</em>"
        )


class TestPercentFilter:
    def test_a_share_becomes_a_whole_number_percentage(self):
        assert templates.environment().filters["percent"](0.444) == "44%"
