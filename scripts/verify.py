#!/usr/bin/env python3
"""End-to-end self-check against a running local server, with the real headers applied.

Asserts what breaks silently and is expensive to find later: that the security headers are
served rather than merely written, that no inline script or style attribute survives, that
every internal link resolves, that no href names a host outside the allowlist, that every
file the desktop needs at runtime is actually there, that the payloads carry what they
promise, and that a missing path 404s.

Everything here is a *response*, which is the whole point of this file and the one thing the
pytest suite cannot do: the CSP is a header, and a policy that is written and not served is
a deploy-time surprise. It deliberately asserts nothing about what the window manager draws
— that is a browser's job and `tests/browser/test_webxp.py` does it.

Non-zero exit on the first failure, so `make verify` gates a commit.

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

from pageset import document_file  # noqa: E402
from serve import parse_headers_file  # noqa: E402

sys.path.insert(0, str(REPO_ROOT / "src"))
from showup.model import BOARD_COUNT, DISTRICT_COUNT  # noqa: E402
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
            str(site),
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

    # The desktop is a mount point: `webxp` builds the shell, the taskbar and every window at
    # runtime. So the page is checked for the hooks the shell needs and nothing more.
    check('id="webxp"' in index, "index carries no #webxp mount point")
    check('src="/assets/boot.mjs"' in index, "index does not load the boot module")
    check("<noscript>" in index, "index offers a reader without a script nothing at all")
    _check_markup_safety(base + "/", index)
    _check_links(base + "/", index, site)

    # Each one 404s the whole desktop rather than degrading it, and the document references
    # none of them by name, so a missing file is invisible until the screen stays blank.
    for path in (
        "/assets/boot.mjs",
        "/apps/manifest.mjs",
        "/vendor/webxp/webxp.mjs",
        "/vendor/webxp/apps.mjs",
        "/vendor/webxp/desktop.mjs",
    ):
        status, module_headers, _ = fetch(base + path)
        check(status == 200, f"{path} returned {status}")
        check("Content-Security-Policy" in module_headers, f"{path} served without CSP")
    print("GET the shell's modules  5 of 5")

    # Every program the manifest names, and the two files the loader asks each one for. The
    # manifest is generated, so a folder renamed without regenerating it fails here.
    status, _, manifest_module = fetch(base + "/apps/manifest.mjs")
    # Parsed out of the `APPS` array rather than off the whole module: a bare quoted-word
    # regex also matches the prose in the header comment, which had this fetching
    # `/apps/the/app.mjs` and calling it a program.
    body = re.search(r"export const APPS = \[(.*?)\]", manifest_module, re.S)
    programs = re.findall(r"['\"]([a-z][a-z0-9-]*)['\"]", body.group(1) if body else "")
    check(
        programs == sorted(programs) and len(programs) == len(set(programs)),
        f"the app manifest is not a sorted unique list: {programs}",
    )
    check(
        2 <= len(programs) <= 20,
        f"the app manifest parsed {len(programs)} programs, which is not a plausible "
        f"count — the parse is picking up something that is not a program: {programs[:8]}",
    )
    for program in programs:
        for name in ("app.mjs", "app.css"):
            path = f"/apps/{program}/{name}"
            status, _, _ = fetch(base + path)
            check(status == 200, f"{path} returned {status}")
    print(f"GET every program's module and stylesheet  {len(programs)} programs")

    status, _, geo = fetch(base + "/data/districts.geo.json")
    check(status == 200, f"districts.geo.json returned {status}")
    geo_json = json.loads(geo)
    check(
        len(geo_json.get("features", [])) == DISTRICT_COUNT,
        f"district geometry has {len(geo_json.get('features', []))} features, "
        f"expected {DISTRICT_COUNT}",
    )
    gz = len(gzip.compress(geo.encode(), 9))
    # §6A.3 budget: geometry must stay under 300 KB gzipped.
    check(gz < 300 * 1024, f"district geometry is {gz // 1024} KB gzipped, budget is 300 KB")
    print(f"GET /data/districts.geo.json  {status}  {gz // 1024} KB gzipped (budget 300)")

    status, _, boards_geo = fetch(base + "/data/boards.geo.json")
    check(status == 200, f"boards.geo.json returned {status}")
    check(
        len(json.loads(boards_geo).get("features", [])) == BOARD_COUNT,
        f"board geometry does not carry all {BOARD_COUNT} boards",
    )

    status, _, lookup = fetch(base + "/data/lookup.json")
    check(status == 200, f"lookup.json returned {status}")
    lookup_json = json.loads(lookup)
    check(len(lookup_json.get("districts", [])) == DISTRICT_COUNT, "lookup is missing districts")
    check(len(lookup_json.get("boards", [])) == BOARD_COUNT, "lookup is missing boards")
    check(len(lookup_json.get("zips", {})) > 150, "lookup has suspiciously few ZIP codes")
    print(
        f"GET /data/lookup.json  {status}  "
        f"{len(lookup_json['zips'])} ZIPs resolvable without the network"
    )

    # The one artifact every program reads. Each program renders the table specs it finds
    # here, so a missing district is a pane that silently says nothing.
    status, _, preview = fetch(base + "/data/preview.json")
    check(status == 200, f"preview.json returned {status}")
    preview_json = json.loads(preview)
    check(
        len(preview_json.get("districts", {})) == DISTRICT_COUNT,
        f"preview covers {len(preview_json.get('districts', {}))} districts, "
        f"expected {DISTRICT_COUNT}",
    )
    check(
        len(preview_json.get("boards", {})) == BOARD_COUNT,
        f"preview covers {len(preview_json.get('boards', {}))} boards, expected {BOARD_COUNT}",
    )
    check(bool(preview_json.get("as_of")), "preview carries no as_of, so no pane can be dated")
    print(f"GET /data/preview.json  {status}  {len(preview) // 1024} KB")

    status, _, schedules = fetch(base + "/data/board-meetings.json")
    check(status == 200, f"board-meetings.json returned {status}")
    schedule_json = json.loads(schedules)
    check(
        len(schedule_json.get("boards", {})) == BOARD_COUNT,
        "the board schedule artifact does not list all 59 boards, so a consumer cannot "
        "tell 'no meetings scheduled' from 'this board cannot be read'",
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

    # A route this site once had. The deployed host has no rewrite rule, so anything other
    # than 404 would mean a stale page is still being served.
    status, _, _ = fetch(base + "/district/99/")
    check(status == 404, f"/district/99/ returned {status}, expected 404")
    print(f"GET /district/99/  {status}  (expected 404)")

    # `address.js` ships and no page loads it: the feature is unported, deliberately kept.
    # Its privacy promises are asserted anyway, because the file is reachable and R33 is
    # about what the code does with a typed address, not about which page hosts it.
    status, _, address_js = fetch(base + "/assets/address.js")
    check(status == 200, f"address.js returned {status}")
    address_code = _strip_comments(address_js)
    # R33: the geocoder must be asked not to log the query.
    check("private=true" in address_code, "address.js omits private=true")
    for banned in ("localStorage", "sessionStorage", "pushState", "document.cookie"):
        check(banned not in address_code, f"address.js touches {banned}")
    check("innerHTML" not in address_code, "address.js uses innerHTML")

    # Every module a reader runs, checked for the one sink that turns scraped text into
    # markup. `tests/unit/test_template_safety.py` greps the same set in the source tree;
    # this reads what the server actually serves.
    #
    # The status is asserted, not discarded. Without it a renamed module returned a 404 page
    # whose body happens to contain none of the four sinks, so all four checks passed and
    # this printed "7 shipped modules checked" while two programs failed to resolve in the
    # browser. `/apps/shared/data.mjs` is the one that mattered: it is imported by both list
    # programs and is in no other check, because it is a library rather than an entry in
    # `APPS`.
    module_paths = ["/assets/boot.mjs", "/apps/shared/data.mjs"] + [
        f"/apps/{program}/app.mjs" for program in programs
    ]
    for path in module_paths:
        status, _, module_source = fetch(base + path)
        check(status == 200, f"{path} returned {status}, so nothing about it was checked")
        for sink in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write"):
            check(
                sink not in _strip_comments(module_source),
                f"{path} uses {sink}, which puts scraped upstream text into the page "
                f"as markup (docs/phase-1-scope.md §4.1)",
            )
    print(f"markup sinks: {len(module_paths)} shipped modules checked, all served")

    # The committed fixture, not the gitignored cache, so this runs on a fresh clone.
    boards = json.loads((REPO_ROOT / "tests" / "fixtures" / "community_boards.json").read_text())
    names = {
        (row.get(field) or "").strip()
        for row in boards
        for field in ("cb_chair", "cb_district_manager")
        if len((row.get(field) or "").strip()) > 4
    }
    check(bool(names), "the fixture carries no officer names, so nothing was checked")

    # Structural first, and this is the assertion that carries the promise: the build must not
    # emit a chair or district-manager field at all. A string sweep can be argued with; a
    # missing field cannot.
    _, _, preview_body = fetch(base + "/data/preview.json")
    preview_doc = json.loads(preview_body)
    emitted_fields = {key for record in preview_doc.get("boards", {}).values() for key in record}
    forbidden = emitted_fields & {"cb_chair", "cb_district_manager", "chair", "district_manager"}
    check(not forbidden, f"the board payload emits officer fields: {sorted(forbidden)}")

    # Then the string sweep, over the text this project authors. Two exclusions, both
    # measured rather than assumed:
    #
    # * A Council Member's name is rendered on purpose — they are an elected official and
    #   naming them is the point of the site. The two sets genuinely overlap: Frank Morano is
    #   the Member for District 51 *and* a `cb_chair` in the City's board dataset, so a bare
    #   string sweep flags the site's own intended output.
    # * `board-meetings.json` carries each board's own calendar titles verbatim, and a board
    #   that publishes "OUTDOOR DINING WORKING GROUP - Valerie De La Rosa, Chair" has named
    #   its own officer in its own publication. Rewriting that would mangle the board's words
    #   to enforce a rule about the City's dataset. The promise is that *we* do not republish
    #   those fields, not that the name can never reach a reader from anywhere.
    members = {
        (record.get("member") or {}).get("name", "").strip()
        for record in preview_doc.get("districts", {}).values()
    }
    ours = names - {name for name in members if name}
    leaked = []
    checked = 0
    for served in ("/index.html", "/data/preview.json", "/data/lookup.json"):
        _, _, body = fetch(base + served)
        checked += 1
        leaked += [f"{name} in {served}" for name in ours if name in body]
    check(not leaked, f"board chair/district-manager names leaked: {leaked[:3]}")
    print(
        f"privacy: no officer fields emitted; {len(ours)} of {len(names)} names swept over "
        f"{checked} artifacts ({len(names) - len(ours)} also hold an elected seat)"
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
        check(
            document_file(site, target).exists(),
            f"{url} links to missing internal path {target}",
        )


if __name__ == "__main__":
    raise SystemExit(main())
