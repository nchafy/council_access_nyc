#!/usr/bin/env python3
"""End-to-end self-check against a running local server.

This is the script that lets a change be *validated* rather than assumed. It
starts the real server, requests real pages, and asserts the things that are easy
to break silently and expensive to discover later:

  - the security headers are actually served (a CSP in a file is not a CSP)
  - no inline <script> or style attribute survives, which the CSP would block in
    a browser but which is cheaper to catch here with a clear message
  - pages contain the facts they are supposed to contain
  - every internal link resolves, so a rename cannot leave a dead end
  - no upstream host appears in an href outside the allowlist
  - the not-found path returns 404 rather than a 200 with an empty page

Exit code is non-zero on the first failure, so `make verify` gates a commit.

    python3 scripts/verify.py [--port 8099]
"""

from __future__ import annotations

import argparse
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
from showup.urls import ALLOWED_HOSTS  # noqa: E402

REQUIRED_HEADERS = {
    "Content-Security-Policy": "default-src 'none'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
}

# Imported, never re-listed. A second copy of the allowlist is a copy that drifts:
# this check passed for weeks and then failed the moment the real list grew, which
# is the wrong way round for a security assertion.
ALLOWED_LINK_HOSTS = ALLOWED_HOSTS

_INLINE_SCRIPT = re.compile(r"<script(?![^>]*\bsrc=)[^>]*>\s*\S", re.IGNORECASE)
_STYLE_ATTR = re.compile(r"\sstyle\s*=\s*[\"']", re.IGNORECASE)
_HREF = re.compile(r"""href\s*=\s*["']([^"']+)["']""", re.IGNORECASE)

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
    # --- the headers file itself agrees with what is served -----------------
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

    # --- index content ------------------------------------------------------
    check("what your city government is doing" in index.lower(), "index missing its heading")
    check(index.count('href="/district/') >= 51, "index does not link all 51 districts")
    check("<select" in index, "index has no dropdown")

    # --- every district page, checked for real ------------------------------
    sampled = [1, 3, 25, 35, 51]
    for number in sampled:
        url = f"{base}/district/{number}/"
        status, page_headers, page = fetch(url)
        check(status == 200, f"{url} returned {status}")
        check(f"Council District {number}" in page, f"{url} missing its heading")
        check("How to be heard" in page, f"{url} missing the participation block")
        check(
            "IN-PERSON" in page.upper() or "In person: no pre-registration" in page,
            f"{url} does not state the no-pre-registration fact",
        )
        check("hearings@council.nyc.gov" in page, f"{url} missing the hearings contact")
        check("Community Board" in page, f"{url} missing the community board block")
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

    # --- the board view, the second of the two views -------------------------
    for code in ("101", "302", "503"):
        url = f"{base}/board/{code}/"
        status, board_headers, page = fetch(url)
        flat = " ".join(page.split())
        check(status == 200, f"{url} returned {status}")
        check("Community Board" in page, f"{url} missing its heading")
        check("Content-Security-Policy" in board_headers, f"{url} served without CSP")
        # The route that justifies this view existing at all.
        check("non-Board (public) members" in flat, f"{url} missing the public-member route")
        check("up to 50 unsalaried members" in flat, f"{url} missing the appointment facts")
        # Refusals, not guesses.
        check(
            "could not find an official source" in flat,
            f"{url} does not refuse the unpublished facts (term length, age, cadence)",
        )
        check(
            'href="/district/' in page,
            f"{url} does not link the council districts covering it",
        )
        check("of this board" in flat, f"{url} share is not labelled as of-the-board")
        _check_markup_safety(url, page)
        _check_links(url, page, site)
        print(f"GET /board/{code}/  {status}  {len(page)} bytes")

    board_dirs = [p for p in (site / "board").iterdir() if p.is_dir()]
    check(len(board_dirs) == 59, f"expected 59 board pages, found {len(board_dirs)}")

    # Both views must be reachable from the front page.
    check('id="district-select"' in index, "index has no council district picker")
    check('id="board-select"' in index, "index has no community board picker")
    check(index.count('href="/board/') >= 59, "index does not link all 59 boards")

    # --- the built 404 path -------------------------------------------------
    status, _, missing = fetch(base + "/district/99/")
    check(status == 404, f"/district/99/ returned {status}, expected 404")
    check("not found" in missing.lower(), "404 page has no not-found message")
    print(f"GET /district/99/  {status}  (expected 404)")

    # --- manifest -----------------------------------------------------------
    status, _, manifest = fetch(base + "/manifest.json")
    check(status == 200, f"manifest.json returned {status}")
    check('"fetched_at"' in manifest, "manifest has no fetched_at")
    check('"max_age_hours"' in manifest, "manifest has no max_age_hours")
    check(
        '"degraded"' not in manifest and '"age_hours"' not in manifest,
        "manifest bakes in a staleness verdict; it must carry inputs only",
    )
    print(f"GET /manifest.json  {status}")

    # --- the privacy line: no community board chair or district manager --------
    # The committed fixture, not the gitignored cache, so this check works on a
    # fresh clone and in CI.
    boards = json.loads((REPO_ROOT / "tests" / "fixtures" / "community_boards.json").read_text())
    names = {
        (row.get(field) or "").strip()
        for row in boards
        for field in ("cb_chair", "cb_district_manager")
        if len((row.get(field) or "").strip()) > 4
    }
    # Scoped to the boards section, not the whole page. A person can hold both
    # roles: Frank Morano is the Council Member for District 51 *and* chair of
    # Staten Island CB 3, so his name legitimately appears in the member block.
    # An unscoped check flags that as a leak, which is a bug in the check.
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
                host in ALLOWED_LINK_HOSTS,
                f"{url} links to non-allowlisted host {host!r} ({href})",
            )
            continue
        # Internal link: it must exist on disk.
        target = urljoin("/", href).split("?")[0].split("#")[0]
        candidate = site / target.lstrip("/")
        if target.endswith("/"):
            candidate = candidate / "index.html"
        check(candidate.exists(), f"{url} links to missing internal path {target}")


if __name__ == "__main__":
    raise SystemExit(main())
