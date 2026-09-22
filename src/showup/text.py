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
from html.parser import HTMLParser

__all__ = ["collapse", "esc", "strip_tags"]

_WS = re.compile(r"\s+")


def collapse(value: str) -> str:
    """Collapse all whitespace runs to single spaces and trim."""
    return _WS.sub(" ", value).strip()


class _TextExtractor(HTMLParser):
    """Collect only the text nodes of a document, discarding all markup.

    We use stdlib html.parser rather than a regex because a regex that strips
    tags is defeated by malformed markup — `<scr<script>ipt>` and unterminated
    attributes are exactly the inputs an attacker reaches for, and a real parser
    resolves them the way a browser would. Script and style *contents* are
    dropped entirely: they are never display text, and echoing them would
    reintroduce what we are defending against.
    """

    _SKIP = frozenset({"script", "style", "template", "noscript"})
    # Tags whose boundaries imply a word break, so "<td>A</td><td>B</td>" does
    # not collapse into "AB".
    _BREAK = frozenset(
        {"br", "p", "div", "tr", "td", "th", "li", "h1", "h2", "h3", "h4", "h5", "h6", "table"}
    )

    def __init__(self) -> None:
        # convert_charrefs=True decodes entities in text nodes for us, once.
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: object) -> None:  # noqa: ARG002
        if tag in self._SKIP:
            self._skip_depth += 1
        elif tag in self._BREAK:
            self._parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag in self._BREAK:
            self._parts.append(" ")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self._parts.append(data)

    @property
    def text(self) -> str:
        return collapse("".join(self._parts))


def strip_tags(markup: str | None) -> str:
    """Reduce untrusted markup to collapsed plain text.

    Never returns HTML. A malformed or hostile fragment yields the visible text
    a browser would have shown, with script and style contents dropped.
    """
    if not markup:
        return ""
    parser = _TextExtractor()
    # A truncated document (a scrape cut off mid-tag) must not raise; feeding
    # then closing recovers whatever text was complete.
    parser.feed(str(markup))
    parser.close()
    return parser.text


class _LineExtractor(_TextExtractor):
    """Like `_TextExtractor` but emits a newline at block boundaries.

    This exists because splitting raw HTML on block tags *before* stripping is
    broken in a way that matters: the `<script>` open tag and its body end up on
    different lines, so the skip logic never sees that it is inside a script, and
    jQuery and CSS turn up as "visible text". Doing the split inside the parser
    keeps the skip state intact across line boundaries.
    """

    def handle_starttag(self, tag: str, attrs: object) -> None:  # noqa: ARG002
        if tag in self._SKIP:
            self._skip_depth += 1
        elif tag in self._BREAK:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag in self._BREAK:
            self._parts.append("\n")

    @property
    def lines(self) -> list[str]:
        joined = "".join(self._parts)
        return [line for raw in joined.split("\n") if (line := collapse(raw))]


def text_lines(markup: str | None) -> list[str]:
    """Reduce untrusted markup to its visible text lines, script/style dropped."""
    if not markup:
        return []
    parser = _LineExtractor()
    parser.feed(str(markup))
    parser.close()
    return parser.lines


def esc(value: object) -> str:
    """Escape a value for interpolation into HTML, including attribute context.

    `quote=True` escapes `"` and `'` as well as `&<>`, so one function is correct
    in both text and quoted-attribute positions. Having a single escaper removes
    the chance of picking the wrong one.
    """
    if value is None:
        return ""
    return html.escape(str(value), quote=True)
