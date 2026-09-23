"""Cross-check the CSP in `_headers` against what the frontend actually fetches.

This exists because of a bug it would have caught. `connect-src` named the geocoder
and nothing else, omitting `'self'`, so under the real policy every same-origin fetch
the site makes was refused: `/data/lookup.json`, `/data/districts.geo.json` and
`/manifest.json`. Nothing noticed, because the only browser test served the site with
no CSP at all and the manifest was otherwise only fetched over plain HTTP by
`scripts/verify.py`.

The consequences were not cosmetic. Local resolution of a ZIP, a neighbourhood or a
district number is the privacy feature — those answers are supposed to come from a
committed index and never reach the geocoder. With the index unfetchable, every query
fell through to the geocoder instead, which inverts §4.4. And the staleness notice,
the mechanism that keeps an abandoned site honest, silently never appeared.

So this test asserts the general property rather than the instance: every URL the
frontend fetches must be permitted by the policy that will be served with it. It is
hermetic and needs no browser, so it runs in the default suite;
`tests/browser/test_console.py` checks the same thing from the other end, in a real
browser, where a mistake shows up as a refused request.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HEADERS = REPO_ROOT / "_headers"
ASSETS = REPO_ROOT / "src" / "showup" / "assets"
FRONTEND = ("site.js", "address.js")


def csp_directives() -> dict[str, list[str]]:
    """The `/*` Content-Security-Policy from `_headers`, as directive -> sources."""
    text = HEADERS.read_text(encoding="utf-8")
    match = re.search(r"^\s+Content-Security-Policy:\s*(.+)$", text, re.MULTILINE)
    assert match, "_headers carries no Content-Security-Policy"
    directives = {}
    for part in match.group(1).split(";"):
        tokens = part.split()
        if tokens:
            directives[tokens[0]] = tokens[1:]
    return directives


def fetched_urls() -> dict[str, str]:
    """Every URL the frontend fetches, as url -> the file that fetches it.

    Matches the two call shapes the frontend actually uses — `fetch("…")` and the
    `loadJSON("…")` wrapper over it — plus any absolute URL in a string literal. A
    fetch built entirely from runtime pieces would slip through; there is none today,
    and `test_every_fetch_call_site_is_a_literal` fails if one appears.
    """
    found = {}
    for name in FRONTEND:
        source = (ASSETS / name).read_text(encoding="utf-8")
        for pattern in (r'fetch\(\s*"([^"]+)"', r'loadJSON\(\s*"([^"]+)"', r'"(https://[^"]+)"'):
            for match in re.finditer(pattern, source):
                found[match.group(1)] = name
    return found


class TestConnectSrc:
    def test_every_fetched_url_is_allowed(self):
        connect = csp_directives().get("connect-src", [])
        for url, source in fetched_urls().items():
            if url.startswith("/"):
                assert "'self'" in connect, (
                    f"{source} fetches the same-origin {url}, but connect-src is "
                    f"{connect!r} and does not include 'self'. Under this policy the "
                    "request is refused and the feature silently does nothing."
                )
            else:
                host = url.split("/")[0] + "//" + url.split("/")[2]
                assert any(allowed.startswith(host) for allowed in connect), (
                    f"{source} fetches {url}, which connect-src {connect!r} forbids"
                )

    def test_connect_src_allows_nothing_else(self):
        """The allowlist must stay exactly as wide as the code needs.

        `'self'` plus one host. If a third entry appears, it is either a new
        third-party dependency — which §4.3 forbids outright — or a leftover.
        """
        connect = csp_directives().get("connect-src", [])
        assert sorted(connect) == ["'self'", "https://geosearch.planninglabs.nyc"], (
            f"connect-src is {connect!r}; zero third parties means exactly one host"
        )

    def test_the_geocoder_is_the_only_external_host_anywhere(self):
        """No directive may name a second external origin."""
        for directive, sources in csp_directives().items():
            for source in sources:
                if source.startswith(("http://", "https://")):
                    assert source == "https://geosearch.planninglabs.nyc", (
                        f"{directive} names {source}, a second external origin"
                    )


class TestTheRestOfThePolicyIsStillClosed:
    """`'self'` had to be added to one directive; assert it was not added to others."""

    @pytest.mark.parametrize("directive", ["default-src", "form-action", "base-uri"])
    def test_stays_none(self, directive):
        assert csp_directives().get(directive) == ["'none'"], (
            f"{directive} must remain 'none'; widening it is a security decision"
        )

    @pytest.mark.parametrize("directive", ["script-src", "style-src", "img-src"])
    def test_is_self_and_nothing_more(self, directive):
        assert csp_directives().get(directive) == ["'self'"]

    def test_no_unsafe_inline_or_eval_anywhere(self):
        for directive, sources in csp_directives().items():
            for source in sources:
                assert source not in {"'unsafe-inline'", "'unsafe-eval'"}, (
                    f"{directive} allows {source}"
                )


class TestTheCrossCheckStillSeesEverything:
    """Guard this file's own premise: that the fetch targets are greppable.

    Two call sites legitimately take a variable — `loadJSON`'s body, and the geocoder
    URL assembled from the `GEOCODER` constant and the query. Everything else is a
    literal. If a third variable call site appears, the cross-check above stops seeing
    it and starts passing for the wrong reason, so the count is pinned rather than the
    shape.
    """

    def test_the_same_origin_fetch_targets_are_exactly_these_three(self):
        same_origin = {url for url in fetched_urls() if url.startswith("/")}
        assert same_origin == {
            "/manifest.json",
            "/data/lookup.json",
            "/data/districts.geo.json",
        }, f"the set of same-origin fetches changed: {sorted(same_origin)}"

    def test_there_are_only_two_variable_fetch_call_sites(self):
        sites = []
        for name in FRONTEND:
            source = (ASSETS / name).read_text(encoding="utf-8")
            sites += [
                f"{name}:{source[: match.start()].count(chr(10)) + 1}"
                for match in re.finditer(r"fetch\(\s*[a-zA-Z_$]", source)
            ]
        assert len(sites) == 2, (
            f"expected two variable fetch call sites (the loadJSON wrapper and the "
            f"geocoder), found {len(sites)}: {sites}. A new one needs a matching "
            "entry in this file, or the CSP cross-check no longer covers it."
        )
