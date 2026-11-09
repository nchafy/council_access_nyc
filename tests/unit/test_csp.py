"""Cross-check the CSP in `_headers` against every URL the frontend fetches.

`tests/browser/test_console.py` asserts the same property from the browser end.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HEADERS = REPO_ROOT / "_headers"
PACKAGE = REPO_ROOT / "src" / "showup"
ASSETS = PACKAGE / "assets"


def frontend_sources() -> dict[str, str]:
    """Every script this project ships that could fetch, as a label -> its text.

    `vendor/` is excluded: it is pinned third-party code, and the hosts it reaches are
    recorded in `ALLOWED_ORIGINS` as owner decisions rather than discovered here.

    This read `("address.js",)` until 2026-11-09 — one file that no page loads, while the
    five programs that actually fetch at runtime went unparsed. The patterns below were the
    reason: they were double-quote-only, and the programs are written with single quotes, so
    widening the list without widening them would have reported clean over files it never
    read.
    """
    sources = {}
    for path in [
        ASSETS / "address.js",
        PACKAGE / "boot.mjs",
        *sorted((PACKAGE / "apps").rglob("*.mjs")),
    ]:
        if "vendor" in path.relative_to(PACKAGE).parts or path.name == "manifest.mjs":
            continue
        sources[path.relative_to(PACKAGE).as_posix()] = path.read_text(encoding="utf-8")
    return sources


#: Every absolute URL the frontend names, in either quote style.
#:
#: Read off string literals rather than off `fetch(` call sites, which is the second attempt
#: at this. Matching call sites looked tighter and covered almost nothing: every program
#: holds its target in a constant — `const LOOKUP = '/data/lookup.json'`, `BUILT_AT_URL`,
#: `LAYERS.council.url` — so a call-site pattern saw `fetch(url)` and learned nothing, and
#: this check still read only `address.js` after its file list was widened to all of them.
#:
#: It over-collects: a module specifier like `/vendor/webxp/webxp.mjs` is an import, not a
#: fetch. That is the safe direction. Same-origin URLs are satisfied by `'self'` either way,
#: and what matters is that no *external* host appears without a decision behind it.
NAMED_URL_PATTERN = r"""['"]((?:/|https://)[^'"]*)['"]"""

#: Every external origin the frontend writes as a link rather than fetching. Navigation, so
#: outside `connect-src` — but still a host this site sends a reader to, which is a decision.
LINKED_ORIGINS = (
    "https://council.nyc.gov",
    "https://communityprofiles.planning.nyc.gov",
)

#: Any external literal, wherever it appears, for the sweep that holds the two lists total.
EXTERNAL_LITERAL_PATTERN = r"""['"](https://[^'"]+)['"]"""
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


def named_urls() -> dict[str, str]:
    """Every absolute URL the frontend names, as url -> the file that names it.

    A URL assembled at runtime is invisible here;
    `test_every_variable_fetch_site_is_a_wrapper_over_a_named_url` is what keeps that set
    from growing unnoticed.
    """
    url_to_source_file = {}
    for source_file, source in frontend_sources().items():
        for match in re.finditer(NAMED_URL_PATTERN, source):
            url_to_source_file[match.group(1)] = source_file
    return url_to_source_file


class TestConnectSrc:
    def test_every_named_url_is_allowed(self):
        connect_src = csp_directives().get("connect-src", [])
        for url, source_file in named_urls().items():
            if url.startswith(LINKED_ORIGINS):
                continue  # navigation, which no fetch directive governs
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

    #: Every external origin the policy may name, and why it is there. Each one was an owner
    #: decision: the geocoder because an address cannot be resolved without it, the tile host
    #: on 2026-10-22 in exchange for a basemap (product-brief.md §5). A third needs the same
    #: deliberate decision, which is what this list exists to force.
    ALLOWED_ORIGINS = (
        "https://geosearch.planninglabs.nyc",
        "https://tiles.openfreemap.org",
        # The vendored base map's Satellite and Geography types. `build` fails rather than
        # letting this list drift from what that base map actually fetches.
        "https://server.arcgisonline.com",
        "https://a.tile.opentopomap.org",
        "https://b.tile.opentopomap.org",
        "https://c.tile.opentopomap.org",
    )

    def test_connect_src_names_exactly_the_decided_hosts(self):
        connect_src = csp_directives().get("connect-src", [])
        assert sorted(connect_src) == ["'self'", *sorted(self.ALLOWED_ORIGINS)], (
            f"connect-src is {connect_src!r}; each external host is a recorded decision"
        )

    def test_no_other_directive_names_an_external_host(self):
        """The basemap needed `connect-src` and nothing else — measured 2026-10-22. If a
        later change puts a host in `img-src` or `worker-src`, that is a widening nobody
        asked for."""
        for directive_name, sources in csp_directives().items():
            if directive_name == "connect-src":
                continue
            for source_expression in sources:
                assert not source_expression.startswith(("http://", "https://")), (
                    f"{directive_name} names {source_expression}; only connect-src may"
                )

    def test_every_named_origin_is_https(self):
        for sources in csp_directives().values():
            for source_expression in sources:
                assert not source_expression.startswith("http://"), (
                    f"{source_expression} is plaintext"
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
    """Guards this file's own premise: that every URL the frontend names is greppable."""

    #: Every JSON artifact the frontend reads, and which build writes it. Pinned so that a
    #: new one is a visible change rather than a line in a diff: each is a request a reader
    #: makes, and each has to survive the CSP and exist in the built site.
    DATA_TARGETS = (
        "/data/lookup.json",
        "/data/districts.geo.json",
        "/data/boards.geo.json",
        "/data/preview.json",
        "/data/board-meetings.json",
        "/data/references.json",
        "/manifest.json",
    )

    def test_the_data_targets_are_the_ones_pinned_here(self):
        found = {url for url in named_urls() if url.startswith("/data/") or url == "/manifest.json"}
        assert found == set(self.DATA_TARGETS), (
            f"the set of data the frontend reads changed: {sorted(found)}"
        )

    def test_the_sweep_reaches_past_the_one_unreachable_script(self):
        """This check read `address.js` alone until 2026-11-09 — the one file no page loads —
        while the five programs that fetch at runtime went unparsed."""
        by_file: dict[str, set[str]] = {}
        for url, source_file in named_urls().items():
            by_file.setdefault(source_file, set()).add(url)
        assert "apps/shared/data.mjs" in by_file, sorted(by_file)
        assert "apps/showup-readme/app.mjs" in by_file, sorted(by_file)
        assert "/manifest.json" in by_file["apps/showup-readme/app.mjs"]

    def test_every_variable_fetch_site_is_a_wrapper_over_a_named_url(self):
        """A `fetch(url)` is fine when `url` arrives from a literal this file can read. The
        count is pinned so that a sixth has to be looked at: if it fetches something
        assembled at runtime, nothing here covers it."""
        variable_call_sites = []
        for source_file, source in frontend_sources().items():
            newline = chr(10)
            variable_call_sites += [
                f"{source_file}:{source[: match.start()].count(newline) + 1}"
                for match in re.finditer(VARIABLE_FETCH_CALL_PATTERN, source)
            ]
        assert len(variable_call_sites) == 6, (
            f"expected six wrappers — address.js's loadJSON and geocoder, shared/data.mjs's "
            f"cache, the map's fetchJson, and the Readme's manifest and source-list reads — "
            f"found {len(variable_call_sites)}: {variable_call_sites}. A new one needs its "
            "target named by a literal, or the cross-check no longer covers it."
        )


class TestExternalHostsAreDecisions:
    """Every external host the frontend names, whether it fetches it or links to it.

    `TestConnectSrc` covers what is fetched, because that is what the policy governs. This
    covers the rest: a link to a new third party is still a reader sent somewhere, and the
    point of listing hosts in this file is that adding one is deliberate.
    """

    def test_every_external_literal_is_in_one_of_the_two_lists(self):
        decided = (*TestConnectSrc.ALLOWED_ORIGINS, *LINKED_ORIGINS)
        undeclared = {}
        for source_file, source in frontend_sources().items():
            for match in re.finditer(EXTERNAL_LITERAL_PATTERN, source):
                url = match.group(1)
                if not url.startswith(decided):
                    undeclared[url] = source_file
        assert not undeclared, (
            f"these external hosts are named by the frontend and declared nowhere: "
            f"{undeclared}. A fetch target belongs in ALLOWED_ORIGINS and the CSP; a link "
            f"belongs in LINKED_ORIGINS."
        )

    def test_the_sweep_actually_found_something(self):
        """Harness honesty: a pattern that stopped matching would report clean over nothing."""
        found = [
            match.group(1)
            for source in frontend_sources().values()
            for match in re.finditer(EXTERNAL_LITERAL_PATTERN, source)
        ]
        assert found, "no external literal found at all; the pattern no longer matches"

    def test_no_linked_origin_is_also_a_fetch_target(self):
        """Two lists, one subject each. A host in both would make it unclear which decision
        was taken, and whether the CSP needs to name it."""
        assert not set(LINKED_ORIGINS) & set(TestConnectSrc.ALLOWED_ORIGINS)
