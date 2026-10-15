"""The template environment, where the escaping boundary lives.

`test_template_safety.py` holds the no-opt-out invariant; this pins what the environment
must do for it to mean anything: find its templates, escape, refuse a misspelled name, and
spell the two quote entities as `text.esc` does.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from jinja2 import UndefinedError

from showup import templates

TEMPLATE_DIR = Path(templates.__file__).parent / "templates"

#: Every template that ships, pinned so a new one cannot quietly skip the voice guard.
TEMPLATES = {
    "board.html",
    "district.html",
    "index.html",
    "layout.html",
    "macros.html",
    "not_found.html",
    "references.html",
}


class TestTheEnvironment:
    def test_the_templates_ship_inside_the_package(self):
        # A template left out of the wheel would only fail after install.
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


class TestVoice:
    """docs/voice.md, over the shipped page copy.

    Second person is mechanical and gated. Mood is not, so what is gated instead is that
    the sentences already cut do not come back.
    """

    SECOND_PERSON = re.compile(r"\b(you|your|yours|yourself|you're)\b", re.IGNORECASE)

    #: Deleted on the owner's instruction, 2026-10-07: direction, an interrogative heading,
    #: or a catalogue of what the City does not publish.
    CUT = (
        "What this board asked the City for",
        "When it meets",
        "Council districts covering this board",
        "Public participation",
        "How to get involved",
        "Things the City does not publish",
        "could not find an official source",
        "measures public opinion",
        "Two things nobody publishes",
        "Asked of",
        "The board&#39;s words",
        "The reply, quoted",
        "Treat this as a hint",
        "Choose one",
    )

    @pytest.mark.parametrize("name", sorted(TEMPLATES))
    def test_no_second_person(self, name):
        found = self.SECOND_PERSON.findall((TEMPLATE_DIR / name).read_text(encoding="utf-8"))
        assert not found, f"{name} addresses the reader: {found}"

    @pytest.mark.parametrize("cut", CUT)
    def test_a_cut_sentence_does_not_come_back(self, cut):
        offenders = [
            name
            for name in TEMPLATES
            if cut.lower() in (TEMPLATE_DIR / name).read_text(encoding="utf-8").lower()
        ]
        assert not offenders, f"{cut!r} is back in {offenders}"

    def test_the_templates_checked_are_the_ones_that_ship(self):
        """A guard that stops running when a template is added is not a guard."""
        assert {path.name for path in TEMPLATE_DIR.glob("*.html")} == TEMPLATES
        assert "references.html" in TEMPLATES
