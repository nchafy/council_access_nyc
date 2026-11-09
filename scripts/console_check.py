#!/usr/bin/env python3
"""Fail if any page logs a console error or trips its own Content-Security-Policy.

A CSP violation is not a crash: Chrome refuses the request, writes a console line, and the
page carries on looking fine. So this is crude on purpose — load every page behind the
real `_headers` and fail on anything the browser complains about, with no allowlist.
`tests/unit/test_csp.py` checks the same property statically, from the policy side.

    python3 scripts/console_check.py              # every page type
    python3 scripts/console_check.py --all        # every pre-rendered page
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

from cdp import Browser, CDPError, Session, find_chrome
from pageset import PROGRAM_SURFACES, REPRESENTATIVE, Surface, document_file, every_page
from ready import await_declared_ready
from serve import background_server
from surface import open_surface

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Listen this long past `load`: the fetches that matter start after first paint.
SETTLE_SECONDS = 1.5

#: Invented by the browser, not referenced by any page; unshipped pending phase-1-scope §7.3.
BROWSER_PROBES = ("/favicon.ico",)

#: Emitted by the test environment's renderer, not by any page. The gates run Chrome with
#: `--use-angle=swiftshader` so the map has WebGL2 at all (scripts/cdp.py), and the software
#: renderer narrates its own performance on a map that draws. A machine with a GPU never
#: prints these. Matched on the renderer's own prefix and on `source == "rendering"`, so a
#: real WebGL error — which arrives as `javascript` or as a page exception — still fails.
SOFTWARE_RENDERER_NOISE = ("GL Driver Message",)


def _is_software_renderer_noise(entry: dict[str, Any]) -> bool:
    text = entry.get("text") or ""
    return entry.get("source") == "rendering" and any(
        marker in text for marker in SOFTWARE_RENDERER_NOISE
    )


def _is_complaint_worth_failing_on(entry: dict[str, Any]) -> bool:
    """Console entries worth failing on: errors, and anything the policy refused.

    Filtered by severity rather than source, because a blocked resource can surface as
    a `security` violation or as a plain network error.
    """
    if entry.get("level") not in {"error", "warning"}:
        return False
    if _is_software_renderer_noise(entry):
        return False
    url = entry.get("url") or ""
    return not any(url.endswith(probe) for probe in BROWSER_PROBES)


def check(
    root: Path,
    paths: list[str],
    surfaces: tuple[Surface, ...] = PROGRAM_SURFACES,
) -> dict[str, list[dict[str, Any]]]:
    """Load each path, then open each program, and return the complaints keyed by surface.

    The programs are opened for the same reason the accessibility sweep opens them: four of
    the five are not autostarted, so loading `/` never runs their `mount` or `ready`. A
    program that throws in either is caught by the shell, which puts "could not start" in the
    window and `console.error`s the stack — measured, and invisible to a sweep of routes.
    """
    complaints: dict[str, list[dict[str, Any]]] = {}
    with background_server(root) as base, Browser() as browser:
        page = browser.page()
        page.call("Log.enable")
        page.call("Runtime.enable")
        for path in paths:
            page.drain_events()
            page.navigate(base + path)
            time.sleep(SETTLE_SECONDS)
            # A trivial round trip flushes events Chrome queued but has not delivered.
            page.evaluate("1")
            complaints[path] = _drain_complaints(page)

        if surfaces:
            page.navigate(base + "/")
            await_declared_ready(page)
            for surface in surfaces:
                page.drain_events()
                open_surface(page, surface)
                page.evaluate("1")
                complaints[surface.name] = _drain_complaints(page)
    return complaints


def _drain_complaints(page: Session) -> list[dict[str, Any]]:
    complaints = []
    for event in page.consume_events():
        if event["method"] == "Log.entryAdded":
            entry = event["params"]["entry"]
            if _is_complaint_worth_failing_on(entry):
                complaints.append(
                    {
                        "level": entry.get("level"),
                        "source": entry.get("source"),
                        "text": entry.get("text", "")[:300],
                        "url": entry.get("url"),
                    }
                )
        elif event["method"] == "Runtime.consoleAPICalled":
            # `console.error` from a script is neither of the two above: not a browser Log
            # entry, and not an uncaught exception. The shell catches a program's mount or
            # ready failure and reports it this way, so without this branch a desktop whose
            # program died said so only in devtools.
            if event["params"].get("type") in ("error", "assert"):
                complaints.append(
                    {
                        "level": event["params"]["type"],
                        "source": "console",
                        "text": " ".join(
                            str(argument.get("value", argument.get("description", "")))
                            for argument in event["params"].get("args") or []
                        )[:300],
                        "url": (event["params"].get("stackTrace") or {})
                        .get("callFrames", [{}])[0]
                        .get("url"),
                    }
                )
        elif event["method"] == "Runtime.exceptionThrown":
            details = event["params"].get("exceptionDetails") or {}
            complaints.append(
                {
                    "level": "exception",
                    "source": "javascript",
                    "text": (details.get("exception") or {}).get("description")
                    or details.get("text", ""),
                    "url": details.get("url"),
                }
            )
    return complaints


def format_report(complaints: dict[str, list[dict[str, Any]]]) -> str:
    lines = []
    total = 0
    for path, page_complaints in complaints.items():
        for complaint in page_complaints:
            total += 1
            lines.append(
                f"FAIL {path}  [{complaint['level']}/{complaint['source']}] {complaint['text']}"
            )
    lines.append(f"{len(complaints)} surfaces loaded: {total} console complaints")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="site")
    parser.add_argument("--all", action="store_true", help="every pre-rendered page")
    args = parser.parse_args(argv)

    root = (REPO_ROOT / args.root).resolve()
    if not document_file(root, "/").exists():
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
