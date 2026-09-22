"""The XSS boundary. These are the highest-value tests in the project.

Every case here is an input shape an attacker or a broken scrape actually
produces. If `strip_tags` or `esc` regresses, a hostile committee name reaches a
page, so these assert behaviour rather than implementation.
"""

from __future__ import annotations

import pytest

from showup.text import collapse, esc, strip_tags


class TestStripTags:
    def test_plain_text_passes_through(self):
        assert strip_tags("Committee on Aging") == "Committee on Aging"

    def test_tags_are_removed(self):
        assert strip_tags("<b>Committee</b> on <i>Aging</i>") == "Committee on Aging"

    def test_script_contents_are_dropped_entirely(self):
        # Echoing the body of a script tag would reintroduce exactly what we are
        # defending against, so it must vanish rather than be escaped.
        assert "alert" not in strip_tags("<script>alert('x')</script>Finance")
        assert strip_tags("<script>alert('x')</script>Finance") == "Finance"

    def test_style_contents_are_dropped(self):
        assert strip_tags("<style>body{}</style>Parks") == "Parks"

    def test_nested_broken_script_tag(self):
        # The classic filter bypass: a naive tag-stripping regex turns
        # "<scr<script>ipt>" into "<script>". A real parser does not.
        #
        # Residual text like "ipt>alert(1)" DOES survive here, and that is
        # correct: it is inert text, and `esc` escapes it at render. What must
        # never survive is a usable tag, so that is what this asserts.
        result = strip_tags("<scr<script>ipt>alert(1)</script>Housing")
        assert "<script" not in result
        assert "<" not in result.replace("ipt>", "")
        assert esc(result).count("<") == 0

    def test_entities_decoded_exactly_once(self):
        # Double-decoding would turn this into live markup. Once keeps it as the
        # literal text the source actually contained.
        assert strip_tags("&amp;lt;script&amp;gt;") == "&lt;script&gt;"

    def test_single_decode_of_plain_entity(self):
        assert strip_tags("Parks &amp; Recreation") == "Parks & Recreation"

    def test_block_tags_become_word_breaks(self):
        # Without this, table cells collapse into "AgingFinance".
        assert strip_tags("<td>Aging</td><td>Finance</td>") == "Aging Finance"

    def test_truncated_document_does_not_raise(self):
        # A scrape cut off mid-tag must degrade, not crash the build.
        assert strip_tags('<td class="x') == ""
        assert strip_tags("<div>Health") == "Health"

    def test_unterminated_attribute_with_payload(self):
        result = strip_tags('<img src=x onerror="alert(1)">Transportation')
        assert "onerror" not in result
        assert "alert" not in result

    @pytest.mark.parametrize("value", [None, "", "   ", "\n\t"])
    def test_empty_inputs_give_empty_string(self, value):
        assert strip_tags(value) == ""

    def test_whitespace_is_collapsed(self):
        assert strip_tags("Committee   on\n\n  Aging") == "Committee on Aging"

    def test_unicode_is_preserved(self):
        # Member names include accents; mangling them is a correctness bug about
        # a real person's name.
        assert strip_tags("<b>Avilés</b>") == "Avilés"
        assert strip_tags("Ossé") == "Ossé"


class TestEsc:
    def test_escapes_angle_brackets(self):
        assert esc("<script>") == "&lt;script&gt;"

    def test_escapes_quotes_for_attribute_context(self):
        # One escaper has to be correct in both text and attribute position, or
        # a call site can pick the wrong one.
        result = esc('" onmouseover="alert(1)')
        assert '"' not in result
        assert "&quot;" in result

    def test_escapes_single_quotes(self):
        assert "'" not in esc("it's")

    def test_ampersand_escaped_first(self):
        assert esc("&lt;") == "&amp;lt;"

    def test_none_is_empty(self):
        assert esc(None) == ""

    def test_non_strings_are_coerced(self):
        assert esc(35) == "35"


class TestCollapse:
    def test_collapses_and_trims(self):
        assert collapse("  a \n b  ") == "a b"
