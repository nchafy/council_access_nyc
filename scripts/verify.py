#!/usr/bin/env python3
"""End-to-end self-check against a running local server, with the real headers applied.

Asserts what breaks silently and is expensive to find later: that the security headers
are served rather than merely written, that no inline script or style attribute survives,
that pages carry their facts, that every internal link resolves, that no href names a host
outside the allowlist, and that a missing district 404s. Non-zero exit on the first
failure, so `make verify` gates a commit.

    python3 scripts/verify.py [--port 8099]
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urljoin, urlsplit

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from serve import parse_headers_file  # noqa: E402

sys.path.insert(0, str(REPO_ROOT / "src"))
from showup.urls import host_allowed  # noqa: E402

REQUIRED_HEADERS = {
    "Content-Security-Policy": "default-src 'none'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
}

# The allowlist is imported above, never re-listed here: a second copy drifts.

_INLINE_SCRIPT = re.compile(r"<script(?![^>]*\bsrc=)[^>]*>\s*\S", re.IGNORECASE)
_STYLE_ATTR = re.compile(r"\sstyle\s*=\s*[\"']", re.IGNORECASE)
_HREF = re.compile(r"""href\s*=\s*["']([^"']+)["']""", re.IGNORECASE)


def _strip_comments(source: str) -> str:
    """Comment-free source, so a grep does not match a file's own documentation."""
    without_block = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return "\n".join(re.sub(r"(^|\s)//.*$", "", line) for line in without_block.splitlines())


failures: list[str] = []
checks = 0


def check(condition: bool, message: str) -> None:
    global checks
    checks += 1
    if not condition:
        failures.append(message)


def fetch(url: str) -> tuple[int, dict[str, str], str]:
    request = urllib.request.Request(url, headers={"User-Agent": "showup-verify/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return (
                response.status,
                dict(response.headers),
                response.read().decode("utf-8", "replace"),
            )
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers), error.read().decode("utf-8", "replace")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8099)
    parser.add_argument("--root", default="site")
    args = parser.parse_args(argv)

    site = REPO_ROOT / args.root
    if not site.is_dir():
        print(f"error: {site} missing — run `make build` first", file=sys.stderr)
        return 2

    base = f"http://127.0.0.1:{args.port}"
    server = subprocess.Popen(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "serve.py"),
            "--port",
            str(args.port),
            "--root",
            args.root,
            "--quiet",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        _wait_for(base, server)
        _run_checks(base, site)
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()

    print()
    if failures:
        print(f"FAILED {len(failures)} of {checks} checks:")
        for failure in failures:
            print(f"  ✗ {failure}")
        return 1
    print(f"OK — {checks} checks passed")
    return 0


def _wait_for(base: str, server: subprocess.Popen) -> None:
    for _ in range(50):
        if server.poll() is not None:
            stderr = server.stderr.read().decode() if server.stderr else ""
            raise SystemExit(f"server exited early:\n{stderr}")
        try:
            fetch(base + "/")
            return
        except OSError:
            time.sleep(0.1)
    raise SystemExit("server did not come up")


def _run_checks(base: str, site: Path) -> None:
    rules = parse_headers_file(REPO_ROOT / "_headers")
    check(bool(rules), "_headers parsed no rules")

    status, headers, index = fetch(base + "/")
    check(status == 200, f"GET / returned {status}")
    print(f"GET /  {status}  {len(index)} bytes")

    for name, expected_fragment in REQUIRED_HEADERS.items():
        value = headers.get(name, "")
        check(bool(value), f"header {name} not served")
        check(
            expected_fragment in value,
            f"header {name} missing {expected_fragment!r} (got {value!r})",
        )
    csp = headers.get("Content-Security-Policy", "")
    check("unsafe-inline" not in csp, "CSP contains unsafe-inline")
    check("unsafe-eval" not in csp, "CSP contains unsafe-eval")

    check("<h1>Districts and boards</h1>" in index, "index missing its heading")
    check(index.count('href="/district/') >= 51, "index does not link all 51 districts")
    check("<select" in index, "index has no dropdown")

    sampled = [1, 3, 25, 35, 51]
    for number in sampled:
        url = f"{base}/district/{number}/"
        status, page_headers, page = fetch(url)
        check(status == 200, f"{url} returned {status}")
        check(f"Council District {number}" in page, f"{url} missing its heading")
        check("Testimony and attendance" in page, f"{url} missing the participation block")
        check(
            "IN-PERSON" in page.upper() or "In person: no pre-registration" in page,
            f"{url} does not state the no-pre-registration fact",
        )
        check("hearings@council.nyc.gov" in page, f"{url} missing the hearings contact")
        check("Community Board" in page, f"{url} missing the community board block")
        check('href="/references/"' in page, f"{url} does not link its sources")
        check(
            "community board" in page.lower() and "council district" in page.lower(),
            f"{url} does not distinguish council district from community board",
        )
        check(
            "Only Council Members can introduce legislation" in page,
            f"{url} does not lead with the no-petition truth",
        )
        check(
            "Content-Security-Policy" in page_headers,
            f"{url} served without CSP",
        )
        _check_markup_safety(url, page)
        _check_links(url, page, site)
        print(f"GET /district/{number}/  {status}  {len(page)} bytes")

    for code in ("101", "302", "503"):
        url = f"{base}/board/{code}/"
        status, board_headers, page = fetch(url)
        flat = " ".join(page.split())
        check(status == 200, f"{url} returned {status}")
        check("Community Board" in page, f"{url} missing its heading")
        check("Content-Security-Policy" in board_headers, f"{url} served without CSP")
        check("non-Board (public) members" in flat, f"{url} missing the public-member route")
        check("up to 50 unsalaried members" in flat, f"{url} missing the appointment facts")
        check(
            "The City's dataset records the board office, not the meeting venue" in flat,
            f"{url} presents the board office as the meeting venue",
        )
        check('href="/references/"' in page, f"{url} does not link its sources")
        check(
            'href="/district/' in page,
            f"{url} does not link the council districts covering it",
        )
        check("of this board" in flat, f"{url} share is not labelled as of-the-board")
        check("Fiscal Year Requests" in flat, f"{url} missing the budget requests")
        check(
            page.count("<details>") == page.count("<summary>") == 5,
            f"{url} does not carry five collapsible request cards",
        )
        for field in ("Requestee", "Request", "Response"):
            check(f"<dt>{field}</dt>" in page, f"{url} request cards have no {field} field")
        check("/d/vn4m-mk4t" in page, f"{url} does not link the register it quotes")
        check(
            "there is no single top request" in flat,
            f"{url} does not say why priority numbers repeat",
        )
        check(
            "not a commitment and not a funded outcome" in flat,
            f"{url} presents a budget request as an outcome",
        )
        _check_markup_safety(url, page)
        _check_links(url, page, site)
        print(f"GET /board/{code}/  {status}  {len(page)} bytes")

    board_dirs = [p for p in (site / "board").iterdir() if p.is_dir()]
    check(len(board_dirs) == 59, f"expected 59 board pages, found {len(board_dirs)}")

    check('id="district-select"' in index, "index has no council district picker")
    check('id="board-select"' in index, "index has no community board picker")
    check(index.count('href="/board/') >= 59, "index does not link all 59 boards")

    status, _, missing = fetch(base + "/district/99/")
    check(status == 404, f"/district/99/ returned {status}, expected 404")
    check("not found" in missing.lower(), "404 page has no not-found message")
    print(f"GET /district/99/  {status}  (expected 404)")

    check('id="address-input"' in index, "index has no address box")
    check(
        'id="address-section"' in index and "hidden" in index,
        "address box is not hidden by default",
    )
    check('src="/assets/address.js"' in index, "index does not load address.js")

    status, _, address_js = fetch(base + "/assets/address.js")
    check(status == 200, f"address.js returned {status}")
    address_code = _strip_comments(address_js)
    # R33: the geocoder must be asked not to log the query.
    check("private=true" in address_code, "address.js omits private=true")
    for banned in ("localStorage", "sessionStorage", "pushState", "document.cookie"):
        check(banned not in address_code, f"address.js touches {banned}")
    check("innerHTML" not in address_code, "address.js uses innerHTML")

    status, _, geo = fetch(base + "/data/districts.geo.json")
    check(status == 200, f"districts.geo.json returned {status}")
    geo_json = json.loads(geo)
    check(
        len(geo_json.get("features", [])) == 51,
        f"district geometry has {len(geo_json.get('features', []))} features, expected 51",
    )
    gz = len(gzip.compress(geo.encode(), 9))
    # §6A.3 budget: geometry must stay under 300 KB gzipped.
    check(gz < 300 * 1024, f"district geometry is {gz // 1024} KB gzipped, budget is 300 KB")
    print(f"GET /data/districts.geo.json  {status}  {gz // 1024} KB gzipped (budget 300)")

    status, _, lookup = fetch(base + "/data/lookup.json")
    check(status == 200, f"lookup.json returned {status}")
    lookup_json = json.loads(lookup)
    check(len(lookup_json.get("districts", [])) == 51, "lookup is missing districts")
    check(len(lookup_json.get("boards", [])) == 59, "lookup is missing boards")
    check(len(lookup_json.get("zips", {})) > 150, "lookup has suspiciously few ZIP codes")
    print(
        f"GET /data/lookup.json  {status}  "
        f"{len(lookup_json['zips'])} ZIPs resolvable without the network"
    )

    status, _, manifest = fetch(base + "/manifest.json")
    check(status == 200, f"manifest.json returned {status}")
    check('"fetched_at"' in manifest, "manifest has no fetched_at")
    check('"max_age_hours"' in manifest, "manifest has no max_age_hours")
    check(
        '"degraded"' not in manifest and '"age_hours"' not in manifest,
        "manifest bakes in a staleness verdict; it must carry inputs only",
    )
    print(f"GET /manifest.json  {status}")

    # Provenance may be relocated and must never be lost, so every identifier and caveat
    # moved off a page is asserted to have landed here.
    url = base + "/references/"
    status, reference_headers, references = fetch(url)
    flat = " ".join(references.split())
    check(status == 200, f"{url} returned {status}")
    check("Content-Security-Policy" in reference_headers, f"{url} served without CSP")
    check("<h1>Sources</h1>" in references, f"{url} missing its heading")
    for dataset in (
        "Calendar.aspx",
        "uvw5-9znb",
        "ruf7-3wgc",
        "vn4m-mk4t",
        "872g-cjhh",
        "5crt-au7u",
        "pri4-ifjk",
        "dg92-zbpx",
    ):
        check(dataset in flat, f"{url} does not name the source {dataset}")
    for relocated in (
        "a few dozen land-use hearing notices a year across all 59 community boards",
        "no City dataset publishes a dated board calendar",
        "disagree with what boards publish on their own sites",
        "records the board office address, not the meeting venue",
        "rounded to a whole number and approximate",
        "nominate half of the board's members",
    ):
        check(relocated in flat, f"{url} lost the relocated provenance {relocated!r}")
    check(flat.count("<dt>Fetched</dt>") >= 6, f"{url} does not date every fetched source")
    check(
        flat.count("<dt>Freshness window</dt>") >= 8,
        f"{url} does not state a freshness window per source",
    )
    _check_markup_safety(url, references)
    _check_links(url, references, site)
    print(f"GET /references/  {status}  {len(references)} bytes")

    # The committed fixture, not the gitignored cache, so this runs on a fresh clone.
    boards = json.loads((REPO_ROOT / "tests" / "fixtures" / "community_boards.json").read_text())
    names = {
        (row.get(field) or "").strip()
        for row in boards
        for field in ("cb_chair", "cb_district_manager")
        if len((row.get(field) or "").strip()) > 4
    }
    # Scoped to the boards section: Frank Morano is the Council Member for District 51
    # and chair of Staten Island CB 3, so an unscoped check calls his name a leak.
    boards_section = re.compile(
        r'<section class="boards">(.*?)</section>', re.IGNORECASE | re.DOTALL
    )
    leaked = []
    checked_pages = 0
    for page in (site / "district").rglob("index.html"):
        match = boards_section.search(page.read_text())
        if not match:
            continue
        checked_pages += 1
        leaked += [
            f"{name} in district/{page.parent.name}" for name in names if name in match.group(1)
        ]
    check(checked_pages >= 51, f"only {checked_pages} district pages had a boards section")

    # Board pages are entirely about one board, so the whole page is in scope.
    board_pages = 0
    for page in (site / "board").rglob("index.html"):
        board_pages += 1
        html = page.read_text()
        leaked += [f"{name} in board/{page.parent.name}" for name in names if name in html]
    check(board_pages >= 59, f"only {board_pages} board pages checked")
    check(not leaked, f"board chair/district-manager names leaked: {leaked[:3]}")
    print(
        f"privacy: {len(names)} board officer names checked against the boards "
        f"section of {checked_pages} pages"
    )


def _check_markup_safety(url: str, page: str) -> None:
    """The CSP would block these in a browser; catching them here names the file."""
    check(not _INLINE_SCRIPT.search(page), f"{url} contains an inline <script> with content")
    check(not _STYLE_ATTR.search(page), f"{url} contains a style= attribute (CSP forbids it)")
    check("javascript:" not in page.lower(), f"{url} contains a javascript: URL")
    check(" onclick=" not in page.lower(), f"{url} contains an inline event handler")
    check("<script>alert" not in page.lower(), f"{url} contains unescaped script text")


def _check_links(url: str, page: str, site: Path) -> None:
    for href in _HREF.findall(page):
        if href.startswith("#") or href.startswith("mailto:"):
            continue
        parts = urlsplit(href)
        if parts.scheme or parts.netloc:
            check(
                parts.scheme == "https",
                f"{url} links to non-https {href}",
            )
            host = (parts.hostname or "").lower()
            check(
                host_allowed(host),
                f"{url} links to non-allowlisted host {host!r} ({href})",
            )
            continue
        target = urljoin("/", href).split("?")[0].split("#")[0]
        candidate = site / target.lstrip("/")
        if target.endswith("/"):
            candidate = candidate / "index.html"
        check(candidate.exists(), f"{url} links to missing internal path {target}")


if __name__ == "__main__":
    raise SystemExit(main())
