#!/usr/bin/env python3
"""Fail if any page logs a console error or trips its own Content-Security-Policy.

The gate that should have existed already. A CSP violation is not a crash: Chrome
refuses the request, writes a line to the console, and the page carries on looking
fine. That is how `connect-src` came to forbid the site's own `/data/lookup.json`
without anything going red — the feature degraded quietly into its fallback path, and
the fallback path happened to be the one that sends more data to a third party.

So the check is the crude one, and crude is the point: load every page behind the real
`_headers`, collect everything the browser complains about, and fail on any of it.
There is no allowlist. A site with zero third parties and 4 KB of first-party script
has no reason to log anything, so the moment it does, something is wrong.

    python3 scripts/console_check.py              # every page type
    python3 scripts/console_check.py --all        # every pre-rendered page

`tests/unit/test_csp.py` checks the same property statically, from the policy side.
Both exist because they fail differently: the static one catches a directive that
forbids a URL in the source, this one catches a request the source does not spell out.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

from cdp import Browser, CDPError, Session, find_chrome
from pageset import REPRESENTATIVE, every_page
from serve import background_server

REPO_ROOT = Path(__file__).resolve().parent.parent

#: How long to keep listening after load. The fetches that matter here are kicked off
#: by script after first paint — the manifest, the lookup index — so a check that
#: stopped at `load` would miss exactly the violations this exists to catch.
SETTLE_SECONDS = 1.5

#: The one class of complaint that is not ours: requests the browser invents for a
#: resource no page references.
#:
#: Chrome asks every origin for /favicon.ico whether or not it is mentioned. Shipping
#: one would silence it, but a favicon is a mark on every tab and project identity is
#: an open owner decision (docs/phase-1-scope.md §7.3), so inventing one here would be
#: answering a question that was deliberately left open. It costs a 404 on a
#: local-only site and nothing else. When §7.3 is decided, delete this and the gate
#: will hold the site to shipping the file.
BROWSER_PROBES = ("/favicon.ico",)


def _interesting(entry: dict[str, Any]) -> bool:
    """Console entries worth failing on: errors, and anything the policy refused.

    Security violations arrive at level `error` with source `security`, but a
    `violation` level also exists and a blocked resource can surface as a network
    error, so the filter is by severity rather than by source.
    """
    if entry.get("level") not in {"error", "warning"}:
        return False
    url = entry.get("url") or ""
    return not any(url.endswith(probe) for probe in BROWSER_PROBES)


def check(root: Path, paths: list[str]) -> dict[str, list[dict[str, Any]]]:
    """Load each path and return the complaints, keyed by path."""
    complaints: dict[str, list[dict[str, Any]]] = {}
    with background_server(root) as base, Browser() as browser:
        page = browser.page()
        page.call("Log.enable")
        page.call("Runtime.enable")
        for path in paths:
            page.drain_events()
            page.navigate(base + path)
            time.sleep(SETTLE_SECONDS)
            # Ask for something trivial: the round trip flushes any events Chrome has
            # queued but not yet delivered, without needing a reader thread.
            page.evaluate("1")
            complaints[path] = _drain_complaints(page)
    return complaints


def _drain_complaints(page: Session) -> list[dict[str, Any]]:
    found = []
    for event in page.consume_events():
        if event["method"] == "Log.entryAdded":
            entry = event["params"]["entry"]
            if _interesting(entry):
                found.append(
                    {
                        "level": entry.get("level"),
                        "source": entry.get("source"),
                        "text": entry.get("text", "")[:300],
                        "url": entry.get("url"),
                    }
                )
        elif event["method"] == "Runtime.exceptionThrown":
            details = event["params"].get("exceptionDetails") or {}
            found.append(
                {
                    "level": "exception",
                    "source": "javascript",
                    "text": (details.get("exception") or {}).get("description")
                    or details.get("text", ""),
                    "url": details.get("url"),
                }
            )
    return found


def format_report(complaints: dict[str, list[dict[str, Any]]]) -> str:
    lines = []
    total = 0
    for path, found in complaints.items():
        for item in found:
            total += 1
            lines.append(f"FAIL {path}  [{item['level']}/{item['source']}] {item['text']}")
    lines.append(f"{len(complaints)} pages loaded: {total} console complaints")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="site")
    parser.add_argument("--all", action="store_true", help="every pre-rendered page")
    args = parser.parse_args(argv)

    root = (REPO_ROOT / args.root).resolve()
    if not (root / "index.html").exists():
        print(f"error: no built site at {root} — run `make build` first", file=sys.stderr)
        return 2
    if not find_chrome():
        print("error: no Chrome or Chromium found, so nothing was checked", file=sys.stderr)
        return 2

    paths = every_page(root) if args.all else list(REPRESENTATIVE)
    try:
        complaints = check(root, paths)
    except CDPError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    print(format_report(complaints))
    return 1 if any(complaints.values()) else 0


if __name__ == "__main__":  # pragma: no cover - entry point
    raise SystemExit(main())
