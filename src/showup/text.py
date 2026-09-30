"""Turning untrusted upstream markup into plain text, and plain text into safe HTML.

This module is the primary XSS boundary for the whole project. Everything this
site displays — committee names, meeting topics, member names, venue strings,
community board cadence — is text scraped from third parties we do not control
(docs/phase-1-scope.md §4.1). Two rules make that safe, and they are enforced
here rather than remembered at each call site:

1. Upstream markup is reduced to plain text at ingest. Tags are dropped, entities
   are decoded exactly once, and what we store is never HTML.
2. Plain text is escaped on the way into a page. Escaping happens in `render`,
   via `esc`, and no other path writes to a template.

Parsing is beautifulsoup4's, over the stdlib `html.parser` backend. A regex that
strips tags is defeated by `<scr<script>ipt>` and by unterminated attributes,
which are the inputs an attacker reaches for; a real parser resolves them the way
a browser does, and this one is far better tested than anything written here.

Decoding entities exactly once matters. `&amp;lt;script&amp;gt;` decoded twice
becomes `<script>`; decoded once it stays the literal text `&lt;script&gt;`,
which is what the source actually said.

A consequence worth knowing, found by the fuzzer: `strip_tags` output CAN contain
the characters `<script>`, because `&#60;script&#62;` decodes to exactly that and
the source genuinely said so. Stripping is therefore not the defence — **escaping
is**. Rule 2 is the one that makes a page safe, and rule 1 only guarantees that no
*markup* survives as markup. Do not "harden" `strip_tags` by deleting `<` from its
output: that would corrupt legitimate text and would not add any protection the
escaper does not already provide.
"""

from __future__ import annotations

import html
import re
import warnings

from bs4 import BeautifulSoup, UnusualUsageWarning
from bs4.element import PreformattedString, Tag

__all__ = ["collapse", "element_text", "esc", "parse_html", "strip_tags", "text_lines"]

_WS = re.compile(r"\s+")

#: Tags whose contents are never display text. Echoing a script body would
#: reintroduce exactly what this module defends against.
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
        # bs4's "did you mean a URL / a filename / XML?" advisories are aimed at a
        # human at a REPL. Here the markup is whatever a third party served, so an
        # odd shape is input to handle, not a mistake to report — and under
        # `filterwarnings = ["error"]` reporting it would raise.
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

    `quote=True` escapes `"` and `'` as well as `&<>`, so one function is correct
    in both text and quoted-attribute positions. Having a single escaper removes
    the chance of picking the wrong one.
    """
    if value is None:
        return ""
    return html.escape(str(value), quote=True)
