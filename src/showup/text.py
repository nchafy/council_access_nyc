"""Turning untrusted upstream markup into plain text, and plain text into safe HTML.

The project's XSS boundary (docs/phase-1-scope.md §4.1): markup becomes plain text at
ingest, and `esc` escapes on the way into a page. **Escaping is the defence, not
stripping** — `strip_tags` output can legitimately contain the characters `<script>`, so
hardening it would corrupt text and protect nothing (tests/test_fuzz.py,
tests/corpus/strip_tags.jsonl, docs/OBSERVATIONS.md 2026-09-23).
"""

from __future__ import annotations

import html
import re
import warnings

from bs4 import BeautifulSoup, UnusualUsageWarning
from bs4.element import PreformattedString, Tag

__all__ = ["collapse", "element_text", "esc", "parse_html", "strip_tags", "text_lines"]

_WS = re.compile(r"\s+")

#: Tags whose contents are never display text.
_SKIP = frozenset({"script", "style", "template", "noscript"})
#: Tags whose boundaries imply a word break, so "<td>A</td><td>B</td>" does not
#: collapse into "AB". Inline tags deliberately do not: "<b>Avi</b>lés" is one word.
_BREAK = frozenset(
    {"br", "p", "div", "tr", "td", "th", "li", "h1", "h2", "h3", "h4", "h5", "h6", "table"}
)


def collapse(value: str) -> str:
    """Collapse all whitespace runs to single spaces and trim."""
    return _WS.sub(" ", value).strip()


def parse_html(markup: str) -> BeautifulSoup:
    """Parse untrusted markup, with the backend named rather than discovered."""
    with warnings.catch_warnings():
        # These advisories are aimed at a human at a REPL; here an odd shape is input to
        # handle, and `filterwarnings = ["error"]` would turn the advisory into a raise.
        warnings.simplefilter("ignore", UnusualUsageWarning)
        return BeautifulSoup(markup, "html.parser")


def _flatten(root: Tag, separator: str) -> str:
    """Concatenate a parsed tree's text nodes, marking every block boundary."""
    parts: list[str] = []
    # An explicit stack rather than recursion: nesting depth comes from upstream.
    pending: list[tuple[object, bool]] = [(root, False)]
    while pending:
        node, leaving = pending.pop()
        if leaving:
            parts.append(separator)
        elif isinstance(node, Tag):
            if node.name in _SKIP:
                continue
            if node.name in _BREAK:
                parts.append(separator)
                pending.append((node, True))
            pending.extend((child, False) for child in reversed(node.contents))
        elif not isinstance(node, PreformattedString):
            # Comments, doctypes and processing instructions are not display text.
            parts.append(str(node))
    return "".join(parts)


def element_text(node: Tag) -> str:
    """The collapsed visible text of an already-parsed element."""
    return collapse(_flatten(node, " "))


def strip_tags(markup: str | None) -> str:
    """Reduce untrusted markup to collapsed plain text. Never returns HTML.

    A malformed or hostile fragment yields the visible text a browser would have
    shown, with script and style contents dropped.
    """
    if not markup:
        return ""
    value = str(markup)
    if "<" not in value:
        return collapse(html.unescape(value))
    return element_text(parse_html(value))


def text_lines(markup: str | None) -> list[str]:
    """Reduce untrusted markup to its visible text lines, script/style dropped."""
    if not markup:
        return []
    value = str(markup)
    joined = html.unescape(value) if "<" not in value else _flatten(parse_html(value), "\n")
    return [line for raw in joined.split("\n") if (line := collapse(raw))]


def esc(value: object) -> str:
    """Escape a value for interpolation into HTML, including attribute context.

    `quote=True` makes one escaper correct in both text and quoted-attribute positions,
    so there is no wrong one to pick.
    """
    if value is None:
        return ""
    return html.escape(str(value), quote=True)
