"""Cross-check the CSP in `_headers` against every URL the frontend fetches.

`tests/browser/test_console.py` asserts the same property from the browser end.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HEADERS = REPO_ROOT / "_headers"
ASSETS = REPO_ROOT / "src" / "showup" / "assets"
FRONTEND = ("site.js", "address.js")

LITERAL_FETCH_TARGET_PATTERNS = (
    r'fetch\(\s*"([^"]+)"',
    r'loadJSON\(\s*"([^"]+)"',
    r'"(https://[^"]+)"',
)
VARIABLE_FETCH_CALL_PATTERN = r"fetch\(\s*[a-zA-Z_$]"


def csp_directives() -> dict[str, list[str]]:
    """The `/*` Content-Security-Policy from `_headers`, as directive -> sources."""
    text = HEADERS.read_text(encoding="utf-8")
    match = re.search(r"^\s+Content-Security-Policy:\s*(.+)$", text, re.MULTILINE)
    assert match, "_headers carries no Content-Security-Policy"
    directives = {}
    for clause in match.group(1).split(";"):
        tokens = clause.split()
        if not tokens:
            continue
        directive_name, *sources = tokens
        directives[directive_name] = sources
    return directives


def fetched_urls() -> dict[str, str]:
    """Every URL the frontend fetches literally, as url -> the file that fetches it.

    Targets assembled at runtime are invisible here;
    `test_there_are_only_two_variable_fetch_call_sites` fails if a new one appears.
    """
    url_to_source_file = {}
    for source_file in FRONTEND:
        source = (ASSETS / source_file).read_text(encoding="utf-8")
        for pattern in LITERAL_FETCH_TARGET_PATTERNS:
            for match in re.finditer(pattern, source):
                url_to_source_file[match.group(1)] = source_file
    return url_to_source_file


class TestConnectSrc:
    def test_every_fetched_url_is_allowed(self):
        connect_src = csp_directives().get("connect-src", [])
        for url, source_file in fetched_urls().items():
            if url.startswith("/"):
                assert "'self'" in connect_src, (
                    f"{source_file} fetches the same-origin {url}, but connect-src is "
                    f"{connect_src!r} and does not include 'self'. Under this policy the "
                    "request is refused and the feature silently does nothing."
                )
            else:
                scheme, _, host = url.split("/")[:3]
                origin = f"{scheme}//{host}"
                assert any(allowed.startswith(origin) for allowed in connect_src), (
                    f"{source_file} fetches {url}, which connect-src {connect_src!r} forbids"
                )

    def test_connect_src_allows_nothing_but_self_and_the_geocoder(self):
        connect_src = csp_directives().get("connect-src", [])
        assert sorted(connect_src) == ["'self'", "https://geosearch.planninglabs.nyc"], (
            f"connect-src is {connect_src!r}; zero third parties means exactly one host"
        )

    def test_the_geocoder_is_the_only_external_host_anywhere(self):
        for directive_name, sources in csp_directives().items():
            for source_expression in sources:
                if source_expression.startswith(("http://", "https://")):
                    assert source_expression == "https://geosearch.planninglabs.nyc", (
                        f"{directive_name} names {source_expression}, a second external origin"
                    )


class TestTheRestOfThePolicyIsStillClosed:
    @pytest.mark.parametrize("directive", ["default-src", "form-action", "base-uri"])
    def test_the_directive_stays_none(self, directive):
        assert csp_directives().get(directive) == ["'none'"], (
            f"{directive} must remain 'none'; widening it is a security decision"
        )

    @pytest.mark.parametrize("directive", ["script-src", "style-src", "img-src"])
    def test_the_directive_is_self_and_nothing_more(self, directive):
        assert csp_directives().get(directive) == ["'self'"]

    def test_no_unsafe_inline_or_eval_anywhere(self):
        for directive_name, sources in csp_directives().items():
            for source_expression in sources:
                assert source_expression not in {"'unsafe-inline'", "'unsafe-eval'"}, (
                    f"{directive_name} allows {source_expression}"
                )


class TestTheCrossCheckStillSeesEverything:
    """Guards this file's own premise: that every fetch target is greppable."""

    def test_the_same_origin_fetch_targets_are_exactly_these_three(self):
        same_origin = {url for url in fetched_urls() if url.startswith("/")}
        assert same_origin == {
            "/manifest.json",
            "/data/lookup.json",
            "/data/districts.geo.json",
        }, f"the set of same-origin fetches changed: {sorted(same_origin)}"

    def test_there_are_only_two_variable_fetch_call_sites(self):
        variable_call_sites = []
        for source_file in FRONTEND:
            source = (ASSETS / source_file).read_text(encoding="utf-8")
            variable_call_sites += [
                f"{source_file}:{source[: match.start()].count('\n') + 1}"
                for match in re.finditer(VARIABLE_FETCH_CALL_PATTERN, source)
            ]
        assert len(variable_call_sites) == 2, (
            f"expected two variable fetch call sites (the loadJSON wrapper and the "
            f"geocoder), found {len(variable_call_sites)}: {variable_call_sites}. A new "
            "one needs a matching entry in this file, or the CSP cross-check no longer "
            "covers it."
        )
