"""The template environment — the one place escaping is configured.

`autoescape=True` inverts the risk from "forgot to escape" to "opted out", and
`tests/unit/test_template_safety.py` fails the build on every opt-out. Undefined names
are fatal, because a typo'd variable rendering as nothing is a missing fact.
"""

from __future__ import annotations

from functools import lru_cache

from jinja2 import Environment, PackageLoader, StrictUndefined
from markupsafe import escape

from .text import esc

__all__ = ["environment", "render"]

#: MarkupSafe and `text.esc` disagree on the two quotes. Both spellings are inert; keeping
#: `esc`'s is what makes the site byte-identical. Derived so the two cannot drift.
_ENTITIES = tuple((str(escape(quote)), esc(quote)) for quote in "'\"")


def _respell(html: str) -> str:
    """Rewrite MarkupSafe's quote entities into the spelling the site already ships."""
    for produced, wanted in _ENTITIES:
        html = html.replace(produced, wanted)
    return html


@lru_cache(maxsize=1)
def environment() -> Environment:
    """The project's only Jinja environment. Escaping on, missing names fatal."""
    return Environment(
        loader=PackageLoader("showup", "templates"),
        autoescape=True,
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )


def render(name: str, **context: object) -> str:
    """Render a whole page template."""
    return _respell(environment().get_template(name).render(**context))
