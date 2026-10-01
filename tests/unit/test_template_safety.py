"""The escaping boundary, asserted on the source rather than through a browser.

`render.py` currently escapes by hand at 75 call sites, so the risk is a forgotten
`esc()`. A template engine inverts that: escaping becomes the default and the risk
becomes the opt-outs. This file holds the invariant that covers both arrangements, so it
is in place before any migration rather than after.

Hermetic and unmarked, so it runs on every commit — unlike the `innerHTML` grep in
`tests/browser/test_address_box.py`, which is `browser`-marked and skips by default.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE = REPO_ROOT / "src" / "showup"

#: Ways to opt out of automatic escaping. Each one hands unescaped text to the page, and
#: every value this project renders is either scraped from a third party or typed by a
#: clerk — see docs/phase-1-scope.md §4.1.
ESCAPE_OPT_OUTS = ("|safe", "| safe", "Markup(", "autoescape false", "autoescape False")

#: Sinks that turn a string into markup in the browser. Mirrors the frontend rule.
BROWSER_MARKUP_SINKS = ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(")


def _python_and_template_sources() -> list[Path]:
    return [
        path for pattern in ("*.py", "*.html", "*.jinja", "*.j2") for path in PACKAGE.rglob(pattern)
    ]


def _without_comments(source: str) -> str:
    """Drop `#` comments and docstrings so a grep sees code, not prose about the rule."""
    source = re.sub(r'""".*?"""', "", source, flags=re.DOTALL)
    return "\n".join(re.sub(r"(^|\s)#.*$", "", line) for line in source.splitlines())


class TestNoEscapeOptOuts:
    @pytest.mark.parametrize("opt_out", ESCAPE_OPT_OUTS)
    def test_the_opt_out_appears_nowhere_in_the_package(self, opt_out):
        offenders = [
            path.relative_to(REPO_ROOT)
            for path in _python_and_template_sources()
            if opt_out in _without_comments(path.read_text(encoding="utf-8"))
        ]
        assert not offenders, (
            f"{opt_out!r} disables automatic escaping, and every value rendered here is "
            f"scraped or clerk-typed: {offenders}"
        )


class TestEscapingIsOnByDefault:
    def test_either_there_is_no_template_engine_or_autoescape_is_on(self):
        """The invariant that spans both arrangements.

        Before a migration this passes because there is no engine. After one it passes
        only if the environment escapes by default, so the migration cannot land without
        the guard being satisfied.
        """
        try:
            from showup import templates
        except ImportError:
            pytest.skip("no template engine yet; the opt-out grep above is the live guard")

        environment = templates.environment()
        assert environment.autoescape, (
            "the template environment must escape by default; without it a single "
            "forgotten filter puts scraped upstream text into the page as markup"
        )


class TestFrontendMarkupSinksStayBanned:
    """Duplicates the `browser`-marked grep so it also runs in the default suite."""

    @pytest.mark.parametrize("sink", BROWSER_MARKUP_SINKS)
    def test_the_sink_is_absent_from_every_shipped_script(self, sink):
        offenders = []
        for script in (PACKAGE / "assets").glob("*.js"):
            source = re.sub(r"/\*.*?\*/", "", script.read_text(encoding="utf-8"), flags=re.DOTALL)
            source = "\n".join(re.sub(r"(^|\s)//.*$", "", line) for line in source.splitlines())
            if sink in source:
                offenders.append(script.name)
        assert not offenders, f"{sink} in {offenders}"
