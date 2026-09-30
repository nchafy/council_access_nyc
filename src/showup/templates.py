"""The template environment — the one place escaping is configured.

`autoescape=True` makes escaping the default rather than something 75 call sites had
to remember, so the risk inverts from "forgot to escape" to "opted out", and
`tests/unit/test_template_safety.py` fails the build on every opt-out. Undefined names
are fatal, because a typo'd variable that renders as nothing is a missing fact.
"""

from __future__ import annotations

from functools import lru_cache

from jinja2 import Environment, PackageLoader, StrictUndefined
from markupsafe import escape

from .text import esc

__all__ = ["environment", "fragment", "render"]

_MACROS = "macros.html"

#: MarkupSafe and `text.esc` agree on `&`, `<` and `>` and disagree on the two quotes.
#: Both spellings are inert; keeping `esc`'s is what makes the move off f-strings
#: byte-identical rather than merely equivalent. Derived so the two cannot drift.
_ENTITIES = tuple((str(escape(quote)), esc(quote)) for quote in "'\"")


def _percent(share: float) -> str:
    """A share of an area as a whole-number percentage, rounded once, in Python."""
    return f"{round(share * 100)}%"


def _respell(html: str) -> str:
    """Rewrite MarkupSafe's quote entities into the spelling the site already ships."""
    for produced, wanted in _ENTITIES:
        html = html.replace(produced, wanted)
    return html


@lru_cache(maxsize=1)
def environment() -> Environment:
    """The project's only Jinja environment. Escaping on, missing names fatal."""
    env = Environment(
        loader=PackageLoader("showup", "templates"),
        autoescape=True,
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
        extensions=["jinja2.ext.do"],
    )
    env.filters["percent"] = _percent
    return env


def render(name: str, **context: object) -> str:
    """Render a whole page template."""
    return _respell(environment().get_template(name).render(**context))


def fragment(macro: str, *args: object) -> str:
    """Render one shared macro on its own, for callers that want a piece of a page."""
    return _respell(str(getattr(environment().get_template(_MACROS).module, macro)(*args)))
