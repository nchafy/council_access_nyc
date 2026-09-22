"""Drive the real address box in a real browser.

Marked `browser`, so it is excluded from the default run and from CI — a GitHub
runner has no Chrome we control and this is not the place to install one. Run it
locally with `make browser` after touching `assets/address.js`.

Why a browser at all: `address.js` is the one piece of this project that only
exists at runtime. Its local-resolution path — district number, ZIP, neighbourhood
name — needs no network, which makes it genuinely testable headlessly, and those
are the branches where a mistake sends someone to the wrong council member.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar
from urllib.parse import parse_qs, urlsplit

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HARNESS = Path(__file__).parent / "harness.html"

CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    shutil.which("google-chrome") or "",
    shutil.which("chromium") or "",
]

pytestmark = pytest.mark.browser


def _chrome() -> str | None:
    return next((path for path in CHROME_CANDIDATES if path and Path(path).exists()), None)


class _Recorder(SimpleHTTPRequestHandler):
    """Static file server that also records the harness's result.

    The harness cannot report through the DOM: this Chrome build's `--dump-dom`
    serialises the page's original source rather than the live DOM, so the report
    element always reads "running…". Reporting over HTTP sidesteps that entirely
    and does not depend on any Chrome behaviour beyond running a script.
    """

    received: ClassVar[list[dict[str, list[str]]]] = []

    def do_GET(self) -> None:
        if self.path.startswith("/__result"):
            self.received.append(parse_qs(urlsplit(self.path).query))
            self.send_response(204)
            self.end_headers()
            return
        super().do_GET()

    def log_message(self, fmt: str, *args: object) -> None:
        pass


@pytest.fixture(scope="module")
def harness_output():
    """Run the harness in real Chrome and return (verdict, detail)."""
    chrome = _chrome()
    if not chrome:
        pytest.skip("no local Chrome")

    site = REPO_ROOT / "site"
    if not (site / "data" / "lookup.json").exists():
        pytest.skip("site/ not built — run `make build` first")

    # Served from the same origin as /data/lookup.json, or the script's own
    # fetches fail on CORS and the test would pass or fail for the wrong reason.
    shutil.copy2(HARNESS, site / "_harness.html")
    _Recorder.received.clear()
    handler = partial(_Recorder, directory=str(site))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        subprocess.run(
            [
                chrome,
                "--headless=new",
                "--disable-gpu",
                "--no-first-run",
                "--no-default-browser-check",
                # Long enough for the harness's staged submits to finish.
                "--virtual-time-budget=8000",
                f"http://127.0.0.1:{port}/_harness.html",
            ],
            capture_output=True,
            text=True,
            timeout=90,
        )
        # Chrome exits when the virtual time budget expires; give the final
        # report request a moment to land.
        for _ in range(40):
            if _Recorder.received:
                break
            time.sleep(0.1)
    finally:
        server.shutdown()
        server.server_close()
        (site / "_harness.html").unlink(missing_ok=True)

    if not _Recorder.received:
        pytest.fail(
            "the harness never reported. Chrome ran but /__result was not requested — "
            "check assets/address.js for a runtime error."
        )
    query = _Recorder.received[-1]
    verdict = (query.get("verdict") or ["MISSING"])[0]
    detail = "\n".join((query.get("lines") or [""])[0].split("|"))
    return verdict, detail


def test_harness_reports_ok(harness_output):
    verdict, detail = harness_output
    assert verdict == "OK", f"browser checks failed:\n{detail}"


@pytest.mark.parametrize(
    "check",
    [
        "section revealed",
        "empty input prompts",
        "multi-district ZIP offers a choice",
        "ZIP choice links districts",
        "neighbourhood name matches",
        "matches link to real pages",
        "non-NYC ZIP is refused by name",
        "address not in URL",
        "nothing written to localStorage",
        "nothing written to sessionStorage",
        "no cookies set",
    ],
)
def test_each_check_ran_and_passed(harness_output, check):
    """Assert each named check individually, so a failure names itself.

    Also guards against the harness silently skipping a case: a check that never
    ran is as much a problem as one that failed.
    """
    _, detail = harness_output
    assert f"PASS {check}" in detail, f"{check!r} did not pass:\n{detail}"


def _strip_js_comments(source: str) -> str:
    """Remove // and /* */ comments so a grep sees code, not prose.

    Needed because these files *document* the rules they follow: address.js has a
    comment saying "never innerHTML" and names the geocoder host in a privacy
    docblock. Grepping raw source flagged both as violations — the check was
    failing on its own documentation.
    """
    without_block = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    # Strip line comments, but not inside a string literal. These two files have
    # no // inside strings, and a full JS tokeniser is not worth it here.
    return "\n".join(re.sub(r"(^|\s)//.*$", "", line) for line in without_block.splitlines())


class TestSourceInvariants:
    """Properties easier to assert on the source than through a browser.

    All three run against comment-stripped source: the files describe their own
    rules, so a naive grep matches the documentation.
    """

    def test_the_geocoder_is_called_from_exactly_one_place(self):
        """R33, stated the way the code is actually shaped.

        An earlier version of this test looked for `private=true` within 800
        characters of the host name. That was wrong: the host is a constant at the
        top of the file and the URL is built ~200 lines later, so the check failed
        on correct code. The invariant that matters is that there is exactly ONE
        place constructing a geocoder URL, and that place carries `private=true` —
        which is both easier to audit and harder to regress than proximity.
        """
        source = _strip_js_comments(
            (REPO_ROOT / "src" / "showup" / "assets" / "address.js").read_text()
        )
        # One URL-shaped mention, i.e. one place that could actually contact it.
        # The bare host also appears in a user-facing string, because R40c requires
        # the slow-dependency message to name it — so count the scheme'd form only.
        as_url = source.count("https://geosearch.planninglabs.nyc")
        assert as_url == 1, f"the geocoder URL is constructed in {as_url} places"
        uses = re.findall(r"\bGEOCODER\b", source)
        assert len(uses) == 2, (
            f"GEOCODER referenced {len(uses)} times (declaration + 1 use expected)"
        )

        # The one function that builds the URL must ask not to be logged.
        builder = re.search(r"function search\(query\)\s*\{(.*?)\n  \}", source, re.DOTALL)
        assert builder, "could not find the geocoder URL builder"
        assert "private=true" in builder.group(1), "the geocoder URL omits private=true"

    def test_no_other_network_destination_is_contacted(self):
        """The CSP allows exactly one external host; the code must not want more."""
        source = _strip_js_comments(
            (REPO_ROOT / "src" / "showup" / "assets" / "address.js").read_text()
        )
        for match in re.finditer(r"""["'](https?://[^"']+)["']""", source):
            assert "geosearch.planninglabs.nyc" in match.group(1), (
                f"address.js references {match.group(1)}, which the CSP does not allow"
            )

    def test_no_innerhtml_anywhere_in_the_frontend(self):
        for name in ("address.js", "site.js"):
            source = _strip_js_comments(
                (REPO_ROOT / "src" / "showup" / "assets" / name).read_text()
            )
            for banned in (
                "innerHTML",
                "outerHTML",
                "insertAdjacentHTML",
                "document.write",
                "eval(",
            ):
                assert banned not in source, f"{name} uses {banned}"

    def test_navigation_is_guarded_by_a_district_pattern(self):
        source = _strip_js_comments(
            (REPO_ROOT / "src" / "showup" / "assets" / "address.js").read_text()
        )
        # The navigating branch cannot be exercised headlessly, so assert the guard
        # exists: a redirect built from data must be validated before use.
        assert "location.assign" in source
        assert re.search(r"/\^\\/district\\/.*\\/\$/", source), "navigation target is unguarded"
