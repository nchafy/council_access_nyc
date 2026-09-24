#!/usr/bin/env python3
"""Run axe-core over the built site and fail on any WCAG 2.2 AA violation.

R39. The site is served with its real `_headers`, and axe is injected over the DevTools
protocol rather than added to the page, so the document under test is byte-identical to
the one we publish and the CSP under test is the one in force at deploy.

    python3 scripts/axe_check.py                  # every page type, ~10 pages
    python3 scripts/axe_check.py --all            # every pre-rendered page
    python3 scripts/axe_check.py --json out.json  # the full result, for triage

Automated checking reaches a minority of WCAG. `docs/accessibility-pass.md` carries the
human pass, and this gate is the floor beneath it rather than a substitute for it.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from cdp import Browser, CDPError, find_chrome
from fetch_axe import AXE_SOURCE, AxeFetchError, ensure_axe
from pageset import REPRESENTATIVE, every_page
from serve import background_server

REPO_ROOT = Path(__file__).resolve().parent.parent

#: WCAG 2.2 AA as tags axe understands. 2.2 conformance implies 2.1 and 2.0, so all six
#: are the one requirement spelled out rather than a widening of it.
GATING_TAGS = ("wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22a", "wcag22aa")

#: Reported but never gating: house style rather than conformance.
ADVISORY_TAGS = ("best-practice",)

#: Rules that must actually have run. Fewer means axe did not inspect the page, so
#: "0 violations" is not a result. The 404 exercised 11 here, a district page 14.
MINIMUM_RULES_EXERCISED = 8


def _run_axe(page: Any, tags: tuple[str, ...]) -> dict[str, Any]:
    """Evaluate axe in the page and return its raw result for the given tags."""
    options = json.dumps({"runOnly": {"type": "tag", "values": list(tags)}})
    return page.evaluate(f"axe.run(document, {options})", await_promise=True)


def _summarise(result: dict[str, Any]) -> list[dict[str, Any]]:
    """Reduce axe's result to what a failure message needs: the rule, and where.

    axe's own output carries the full DOM snippet per node, which runs to hundreds of
    kilobytes on a repeated component. `--json` is there when the detail is wanted.
    """
    return [
        {
            "id": violation["id"],
            "impact": violation.get("impact"),
            "help": violation.get("help"),
            "url": violation.get("helpUrl"),
            "nodes": len(violation.get("nodes") or []),
            "targets": [
                target
                for node in (violation.get("nodes") or [])[:3]
                for target in (node.get("target") or [])
            ],
        }
        for violation in result.get("violations") or []
    ]


def axe_source_text() -> str:
    """The pinned axe build, fetched into the gitignored cache on first use."""
    ensure_axe()
    return AXE_SOURCE.read_text(encoding="utf-8")


def check(root: Path, paths: list[str]) -> dict[str, Any]:
    """Run axe over each path. One browser, one server, one page target for all of them."""
    axe_source = axe_source_text()
    report: dict[str, Any] = {"pages": {}, "violations": 0, "advisory": 0, "incomplete": 0}

    with background_server(root) as base, Browser() as browser:
        page = browser.page()
        for path in paths:
            started = time.monotonic()
            page.navigate(base + path)
            # Re-injected per navigation: a page load discards the previous world.
            page.evaluate(axe_source)
            conformance = _run_axe(page, GATING_TAGS)
            gating = _summarise(conformance)
            advisory = _summarise(_run_axe(page, ADVISORY_TAGS))
            # Reported, not failed: "incomplete" is axe declining to decide.
            incomplete = [item["id"] for item in (conformance.get("incomplete") or [])]
            # Exercised, not passed: a rule that failed was still run.
            exercised = len(conformance.get("passes") or []) + len(gating) + len(incomplete)
            if exercised < MINIMUM_RULES_EXERCISED:
                raise CDPError(
                    f"{path}: axe exercised only {exercised} rules, expected at least "
                    f"{MINIMUM_RULES_EXERCISED}. The page probably did not load, or "
                    "axe did not inject — a clean result here would be meaningless."
                )
            report["pages"][path] = {
                "violations": gating,
                "advisory": advisory,
                "incomplete": incomplete,
                "exercised": exercised,
                "seconds": round(time.monotonic() - started, 2),
            }
            report["violations"] += len(gating)
            report["advisory"] += len(advisory)
            report["incomplete"] += len(incomplete)
    return report


def format_report(report: dict[str, Any], *, verbose: bool = False) -> str:
    lines: list[str] = []
    for path, result in report["pages"].items():
        for violation in result["violations"]:
            lines.append(
                f"FAIL {path}  {violation['id']} ({violation['impact']}) "
                f"x{violation['nodes']}: {violation['help']}"
            )
            lines.append(f"     {', '.join(violation['targets'][:3])}")
            lines.append(f"     {violation['url']}")
        if verbose:
            for violation in result["advisory"]:
                lines.append(
                    f"advice {path}  {violation['id']} x{violation['nodes']}: {violation['help']}"
                )
            for rule in result["incomplete"]:
                lines.append(f"review {path}  {rule} — axe could not decide; check by hand")
    pages = len(report["pages"])
    lines.append(
        f"{pages} pages checked: {report['violations']} WCAG 2.2 AA violations, "
        f"{report['advisory']} advisory, {report['incomplete']} needing human review"
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="site", help="built site to check")
    parser.add_argument(
        "--all", action="store_true", help="every pre-rendered page, not one of each type"
    )
    parser.add_argument("--json", dest="json_out", help="write the full report here")
    parser.add_argument("-v", "--verbose", action="store_true", help="show advisory findings too")
    args = parser.parse_args(argv)

    root = (REPO_ROOT / args.root).resolve()
    if not (root / "index.html").exists():
        print(f"error: no built site at {root} — run `make build` first", file=sys.stderr)
        return 2
    try:
        ensure_axe()
    except AxeFetchError as error:
        # Loud, not skipped: a gate that quietly does nothing reports success.
        print(f"error: {error}", file=sys.stderr)
        print("       run `make axe-fetch` once the network is reachable", file=sys.stderr)
        return 2
    if not find_chrome():
        print("error: no Chrome or Chromium found, so nothing was checked", file=sys.stderr)
        return 2

    paths = every_page(root) if args.all else list(REPRESENTATIVE)
    try:
        report = check(root, paths)
    except CDPError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    print(format_report(report, verbose=args.verbose))
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"full report: {args.json_out}")
    return 1 if report["violations"] else 0


if __name__ == "__main__":  # pragma: no cover - entry point
    raise SystemExit(main())
