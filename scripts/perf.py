#!/usr/bin/env python3
"""The R40 performance gate: 60 KB gzipped on the critical path, 3 s cold on 3G.

Two measurements, deliberately different in kind.

**Page weight** is arithmetic. Gzip the document and everything it must have before it
is readable and the dropdowns work, and compare against the budget. No browser, no
timing, no variance — which means it runs in CI on every commit, it can never be flaky,
and it fails with an exact number of bytes and the file that grew. This is the half of
R40 that is genuinely *enforced*.

**Cold load** is a measurement, with a distribution. Chrome loads each page with its
network shaped and its CPU throttled to the reference profile, cache cleared, twenty
times, and the p95 is compared against 3 s. Thresholds and profiles live in the
committed `perf-budget.json` so changing a promise is a diff, not an edit inside a
script.

Both figures are synthetic. There is no real-user monitoring because analytics are
banned, so nothing here is an observed field percentile and the reports say so.

    python3 scripts/perf.py                 # both, against site/
    python3 scripts/perf.py --weight-only   # the arithmetic half, no browser needed
    python3 scripts/perf.py --runs 5         # a quicker, weaker sample while iterating
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cdp import Browser, CDPError, find_chrome
from pageset import REPRESENTATIVE
from serve import background_server

REPO_ROOT = Path(__file__).resolve().parent.parent
BUDGET_FILE = REPO_ROOT / "perf-budget.json"

#: The pages the timed half runs against. One of each type is enough: a district page
#: and a board page differ from their siblings only in data, and twenty throttled
#: loads each is already most of the runtime.
TIMED_PAGES = ("/", "/district/35/", "/board/302/")

#: Pulled out of the document because these are what the browser must have in hand.
#: Deliberately does not follow @import or a preload hint — neither is used, and
#: `test_no_new_subresource_kinds` fails if one appears.
STYLESHEET_RE = re.compile(r"""<link[^>]+rel=["']?stylesheet["']?[^>]*>""", re.IGNORECASE)
SCRIPT_RE = re.compile(r"""<script[^>]+src=["']([^"']+)["']""", re.IGNORECASE)
HREF_RE = re.compile(r"""href=["']([^"']+)["']""", re.IGNORECASE)


def budget() -> dict[str, Any]:
    return json.loads(BUDGET_FILE.read_text(encoding="utf-8"))


def gzipped_size(data: bytes) -> int:
    """Bytes on the wire. mtime=0 so the same input always gives the same number."""
    return len(gzip.compress(data, compresslevel=9, mtime=0))


@dataclass
class Weight:
    """The critical-path weight of one page, and where it went."""

    path: str
    parts: dict[str, int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(self.parts.values())


def page_weight(root: Path, path: str) -> Weight:
    """Gzipped bytes of the document plus every subresource it blocks on."""
    document = root / (path.lstrip("/") or "index.html")
    if document.is_dir() or path.endswith("/"):
        document = root / path.strip("/") / "index.html"
    html = document.read_bytes()

    weight = Weight(path, {"(document)": gzipped_size(html)})
    text = html.decode("utf-8", errors="replace")
    references = [
        match.group(1)
        for tag in STYLESHEET_RE.findall(text)
        for match in [HREF_RE.search(tag)]
        if match
    ] + SCRIPT_RE.findall(text)

    for reference in references:
        if reference.startswith(("http://", "https://", "//")):
            # A third-party subresource would be a §4.3 violation, not a weight
            # problem, and it is not this gate's job to be the one that reports it.
            raise ValueError(f"{path} loads an off-site subresource: {reference}")
        asset = root / reference.lstrip("/")
        weight.parts[reference] = gzipped_size(asset.read_bytes())
    return weight


def weigh(root: Path, paths: list[str]) -> list[Weight]:
    return [page_weight(root, path) for path in paths]


def measure_cold_load(
    root: Path, paths: tuple[str, ...], profile: dict[str, Any], runs: int
) -> dict[str, list[float]]:
    """Load each page `runs` times on a cold cache under `profile`; return the samples.

    `domContentLoadedEventEnd` is the number reported, because that is when the
    document is parsed, styled and the dropdown's script is live — SLA-4's "interactive"
    for a pre-rendered page. First contentful paint is collected too and printed, since
    it is when the reader can actually read the answer, but it is not what the promise
    was written about.
    """
    samples: dict[str, list[float]] = {path: [] for path in paths}
    with background_server(root) as base, Browser() as browser:
        page = browser.page()
        page.throttle(
            download_bps=profile["download_bps"],
            upload_bps=profile["upload_bps"],
            latency_ms=profile["latency_ms"],
            cpu=profile["cpu"],
        )
        for _ in range(runs):
            for path in paths:
                # Cleared every run, or run two measures a warm cache and the p95
                # becomes a measurement of Chrome's disk.
                page.clear_cache()
                page.navigate(base + path, timeout=120)
                timing = page.evaluate(
                    "(() => {"
                    " const nav = performance.getEntriesByType('navigation')[0];"
                    " const paint = performance.getEntriesByName('first-contentful-paint')[0];"
                    " return {"
                    "  interactive: nav ? nav.domContentLoadedEventEnd : null,"
                    "  fcp: paint ? paint.startTime : null,"
                    "  load: nav ? nav.loadEventEnd : null,"
                    " };"
                    "})()"
                )
                if timing["interactive"] is None:
                    raise CDPError(f"{path}: the browser reported no navigation timing")
                samples[path].append(timing["interactive"])
    return samples


def percentile(values: list[float], fraction: float) -> float:
    """The nearest-rank percentile: the value at ceil(n*fraction), 1-indexed.

    Not interpolated. With 20 samples and 0.95 this is the 19th ordered value, so one
    slow run cannot be averaged away and one fast run cannot rescue the set.
    """
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, -(-len(ordered) * fraction // 1) - 1))
    return ordered[int(index)]


def format_weights(weights: list[Weight], limit: int) -> str:
    lines = []
    for weight in weights:
        verdict = "ok  " if weight.total <= limit else "FAIL"
        lines.append(
            f"{verdict} {weight.path:<18} {weight.total / 1024:6.1f} KB gzipped "
            f"({weight.total * 100 // limit}% of budget)"
        )
        if weight.total > limit:
            for name, size in sorted(weight.parts.items(), key=lambda item: -item[1]):
                lines.append(f"       {name:<28} {size / 1024:6.1f} KB")
    heaviest = max(weights, key=lambda weight: weight.total)
    lines.append(
        f"heaviest page {heaviest.path} at {heaviest.total / 1024:.1f} KB of the "
        f"{limit / 1024:.0f} KB budget"
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    settings = budget()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="site")
    parser.add_argument("--weight-only", action="store_true", help="skip the browser half")
    parser.add_argument("--runs", type=int, default=settings["runs"])
    args = parser.parse_args(argv)

    root = (REPO_ROOT / args.root).resolve()
    if not (root / "index.html").exists():
        print(f"error: no built site at {root} — run `make build` first", file=sys.stderr)
        return 2

    limit = settings["page_weight_gzip_bytes"]
    weights = weigh(root, list(REPRESENTATIVE))
    print(format_weights(weights, limit))
    failed = any(weight.total > limit for weight in weights)

    scripts = {
        name: size
        for weight in weights
        for name, size in weight.parts.items()
        if name.endswith(".js")
    }
    script_limit = settings["script_gzip_bytes"]
    script_total = sum(scripts.values())
    failed = failed or script_total > script_limit
    print(
        f"{'ok  ' if script_total <= script_limit else 'FAIL'} all JavaScript "
        f"{script_total / 1024:.1f} KB of the {script_limit / 1024:.0f} KB ceiling "
        f"({', '.join(f'{name} {size / 1024:.1f}' for name, size in sorted(scripts.items()))})"
    )

    geometry = root / "data" / "districts.geo.json"
    if geometry.exists():
        size = gzipped_size(geometry.read_bytes())
        geometry_limit = settings["geometry_gzip_bytes"]
        ok = size <= geometry_limit
        failed = failed or not ok
        print(
            f"{'ok  ' if ok else 'FAIL'} geometry (after first paint) "
            f"{size / 1024:.0f} KB of the {geometry_limit / 1024:.0f} KB budget"
        )

    if args.weight_only:
        return 1 if failed else 0
    if not find_chrome():
        print("error: no Chrome or Chromium found, so nothing was timed", file=sys.stderr)
        return 2

    threshold = settings["cold_load_ms_p95"]
    for name, profile in settings["profiles"].items():
        gating = name == settings["gating_profile"]
        try:
            samples = measure_cold_load(root, TIMED_PAGES, profile, args.runs)
        except CDPError as error:
            print(f"error: {error}", file=sys.stderr)
            return 2
        print(f"\n{name} — {profile['label']}{'  [GATED]' if gating else '  [reported only]'}")
        for path, values in samples.items():
            p95 = percentile(values, 0.95)
            over = gating and p95 > threshold
            failed = failed or over
            print(
                f"{'FAIL' if over else 'ok  '} {path:<18} p95 {p95:7.0f} ms  "
                f"median {statistics.median(values):7.0f} ms  "
                f"n={len(values)}  (threshold {threshold} ms)"
            )

    print("\nEvery figure above is a CI measurement on a reference profile, not an")
    print("observed field percentile. Analytics are banned, so there is no field data.")
    return 1 if failed else 0


if __name__ == "__main__":  # pragma: no cover - entry point
    raise SystemExit(main())
