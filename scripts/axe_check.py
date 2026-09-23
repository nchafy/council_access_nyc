#!/usr/bin/env python3
"""Run axe-core over the built site and fail on any WCAG 2.2 AA violation.

R39. The site is served with its real `_headers`, so the policy that will be in
force at deploy is in force here: a stylesheet blocked by a CSP mistake would change
every colour-contrast result, and in the flattering direction.

axe itself is injected over the DevTools protocol rather than added to the page.
That matters for two reasons. The CSP is `script-src 'self'` with no
`unsafe-inline`, so a `<script>` tag carrying axe could not run without weakening
the policy we are trying to test; and injecting nothing into the document means the
page under test is byte-identical to the page we publish.

    python3 scripts/axe_check.py                  # every page type, ~10 pages
    python3 scripts/axe_check.py --all            # every pre-rendered page
    python3 scripts/axe_check.py --json out.json  # the full result, for triage

**What this does not prove.** Automated checking reaches a minority of WCAG —
Deque's own figure for axe is around a third to a half of issues, and the ones it
cannot see are the ones that matter most: whether the reading order makes sense,
whether a link's text means anything out of context, whether an error message tells
you what to do. `docs/accessibility-pass.md` carries the human pass that covers
those, and this gate is the floor beneath it, not a substitute for it.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from cdp import Browser, CDPError, find_chrome
from pageset import REPRESENTATIVE, every_page
from serve import background_server

REPO_ROOT = Path(__file__).resolve().parent.parent
AXE_SOURCE = REPO_ROOT / "vendor" / "axe-core" / "axe.min.js"

#: The conformance target, as tags axe understands. R39 says WCAG 2.2 AA, and 2.2
#: conformance implies 2.1 and 2.0, so all six tags are the one requirement spelled
#: out — not a widening of it.
GATING_TAGS = ("wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22a", "wcag22aa")

#: Run these too, and report them, but do not fail the build on them. They are
#: house style rather than conformance, and a gate that fails on advice is a gate
#: people learn to disable.
ADVISORY_TAGS = ("best-practice",)

#: The floor on rules that must actually have run — passed, failed or been left for
#: review. The simplest page in the set, the 404, exercised 11 when this was written
#: and a district page exercised 14. If a page reports fewer, axe did not really
#: inspect it and "0 violations" is not a result.
MINIMUM_RULES_EXERCISED = 8


def _run_axe(page: Any, tags: tuple[str, ...]) -> dict[str, Any]:
    """Evaluate axe in the page and return its raw result for the given tags."""
    options = json.dumps({"runOnly": {"type": "tag", "values": list(tags)}})
    return page.evaluate(f"axe.run(document, {options})", await_promise=True)


def _summarise(result: dict[str, Any]) -> list[dict[str, Any]]:
    """Reduce axe's result to what a failure message needs.

    axe returns the full DOM snippet for every node; a page with one bad colour pair
    in a repeated component produces hundreds of kilobytes of near-identical JSON.
    Keep the rule, why it failed, and the first few selectors — enough to find it,
    with `--json` available when it is not.
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


def check(root: Path, paths: list[str]) -> dict[str, Any]:
    """Run axe over each path. One browser, one server, one page target for all of them."""
    axe_source = AXE_SOURCE.read_text(encoding="utf-8")
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
            # "Incomplete" is axe declining to decide — usually contrast against an
            # image or a gradient. Not a failure, but silence about it would be a
            # way to pass by not looking.
            incomplete = [item["id"] for item in (conformance.get("incomplete") or [])]
            # Rules *exercised*, not rules passed: a rule that failed was still run,
            # and counting only passes made a correctly-detected broken page look
            # like a page that had not been inspected.
            exercised = len(conformance.get("passes") or []) + len(gating) + len(incomplete)
            if exercised < MINIMUM_RULES_EXERCISED:
                # The failure mode this guards against is the quiet one: axe fails to
                # inject, or a navigation silently lands on the 404, and the page
                # reports zero violations because zero rules ran. A clean result only
                # means something if we can say what it was clean against.
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
    if not AXE_SOURCE.exists():
        print(f"error: {AXE_SOURCE} is missing; see vendor/axe-core/PROVENANCE.md", file=sys.stderr)
        return 2
    if not find_chrome():
        # Loud, not skipped. A gate that quietly does nothing is worse than no gate,
        # because it reports success.
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
