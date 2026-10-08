"""The guard for the HTML-parsing library.

Handing untrusted markup to a library turns the risk from "the state machine has a hole"
into "the wrong backend" and "the parser handed back markup". Both are asserted here.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import bs4
import pytest
import soupsieve

from showup.sources.calendar import parse_calendar
from showup.sources.districts import parse_district_page
from showup.text import element_text, esc, parse_html, strip_tags, text_lines

MARKUP_SUFFIXES = {".so", ".pyd", ".dylib", ".dll"}


class TestTheBackendIsTheStdlibOne:
    """Which tree builder runs decides how malformed markup resolves."""

    def test_the_builder_is_html_parser(self):
        assert parse_html("<p>x</p>").builder.NAME == "html.parser"

    @pytest.mark.parametrize("name", ["lxml", "html5lib"])
    def test_no_alternative_backend_is_installed(self, name):
        """A compiled backend would change tree-building and the install surface."""
        assert importlib.util.find_spec(name) is None, f"{name} would silently change parsing"

    @pytest.mark.parametrize("module", [bs4, soupsieve])
    def test_the_parser_ships_no_compiled_extension(self, module):
        """Rule 5 in docs/dependencies.md, checked rather than assumed."""
        root = Path(module.__file__).parent
        binaries = [path.name for path in root.rglob("*") if path.suffix in MARKUP_SUFFIXES]
        assert binaries == []


class TestTheParserNeverHandsBackMarkup:
    """Whatever the library returns, what we store has to be plain text."""

    @pytest.mark.parametrize(
        "markup",
        [
            "<?xml version='1.0'?><a>Aging</a>",
            "<scr<script>ipt>alert(1)</script>Housing",
            "<!--[if IE]><b>x</b><![endif]-->Parks",
            "<template><b>hidden</b></template>Finance",
            '<td class="x',
        ],
    )
    def test_hostile_and_malformed_input_is_inert_once_escaped(self, markup):
        assert "<" not in esc(strip_tags(markup)).replace("&lt;", "")
        for line in text_lines(markup):
            assert "<" not in esc(line).replace("&lt;", "")

    def test_an_xml_declaration_does_not_raise(self):
        """bs4 warns about an XML document; a warning is an error under pytest."""
        assert strip_tags("<?xml version='1.0'?><a>Aging</a>") == "Aging"

    def test_element_text_flattens_a_parsed_node(self):
        cell = parse_html("<td><a href='x'>Committee</a> on <b>Aging</b></td>")
        assert element_text(cell) == "Committee on Aging"


class TestEntitiesAreDecodedExactlyOnceInAttributes:
    """The regex reader never decoded an href, so `&amp;` reached the site."""

    def test_a_legistar_detail_url_has_its_ampersands_decoded(self, calendar_html):
        urls = [m.detail_url for m in parse_calendar(calendar_html) if m.detail_url]
        assert urls, "fixture should carry detail links"
        for url in urls:
            assert "&amp;" not in url, "an href was taken raw instead of parsed"
        assert any("&GUID=" in url for url in urls), "the query string lost its parameters"

    def test_district_page_urls_are_still_allowlisted(self, district_page_html):
        result = parse_district_page(1, district_page_html[1])
        assert result["page_url"].startswith("https://council.nyc.gov/")
