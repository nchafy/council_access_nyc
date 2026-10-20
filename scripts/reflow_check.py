#!/usr/bin/env python3
"""Fail on content that cannot reflow to a phone-width viewport.

WCAG 2.2 AA SC 1.4.10 Reflow: no two-dimensional scrolling at 320 CSS px wide, which is
1280 px at 400% zoom. `make shot` cannot reach that width — macOS clamps a Chrome window
at ~500 px and crops silently rather than reporting it — so this gate sets the viewport
over CDP instead, where the width is honoured at any value.

The signal is the layout viewport, not an element rect: content too wide to fit widens the
initial containing block, after which every element "fits" inside the widened value and a
per-element check reports clean. `window.innerWidth` above the requested width *is* the
violation. The culprit is then named by measuring unbreakable text runs, because the usual
cause is one long token — a URL, an email address — that has nowhere to break.

    python3 scripts/reflow_check.py              # every page type, both widths
    python3 scripts/reflow_check.py --all        # every pre-rendered page
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from cdp import Browser, CDPError, find_chrome
from pageset import REPRESENTATIVE, document_file, every_page
from serve import background_server

REPO_ROOT = Path(__file__).resolve().parent.parent

#: 320 is the SC 1.4.10 requirement. 390 is the logical width of the phones most people
#: hold, and is checked separately so a 320-only failure cannot be mistaken for one.
WIDTHS = (320, 390)

#: Viewport height; tall enough that the pages do not paginate during measurement.
HEIGHT = 844

#: Subpixel layout rounds, so an exact comparison reports a violation that is not one.
TOLERANCE_PX = 1

#: Below this, a token is ordinary prose and will not be the thing forcing the viewport.
MIN_TOKEN_CHARS = 12

#: A probe, as a JS function of the requested width, returning the measurement and the
#: narrowest explanation for it that the page can give.
PROBE = """(target => {
  const inner = window.innerWidth;
  const scroller = document.scrollingElement;

  // Elements that start inside the viewport and end outside it. A negative left is the
  // off-canvas hiding idiom the skip link uses, not an overflow.
  const elements = [];
  for (const element of document.querySelectorAll('body *')) {
    const rect = element.getBoundingClientRect();
    if (rect.width === 0 && rect.height === 0) continue;
    if (rect.left < 0) continue;
    if (rect.right <= target + 1) continue;
    let childAlsoOver = false;
    for (const child of element.children) {
      if (child.getBoundingClientRect().right > target + 1) { childAlsoOver = true; break; }
    }
    if (childAlsoOver) continue;
    elements.push({
      tag: element.tagName.toLowerCase(),
      cls: (element.className || '').toString().slice(0, 40),
      width: Math.round(rect.width),
      right: Math.round(rect.right)
    });
  }

  // Unbreakable text runs wider than the viewport. A run that already occupies more than
  // one client rect has wrapped, so it is not unbreakable.
  const tokens = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let node;
  while ((node = walker.nextNode())) {
    const text = node.nodeValue;
    if (!text || !text.trim()) continue;
    const pattern = /\\S+/g;
    let match;
    while ((match = pattern.exec(text))) {
      if (match[0].length < MIN_TOKEN_CHARS) continue;
      const range = document.createRange();
      range.setStart(node, match.index);
      range.setEnd(node, match.index + match[0].length);
      const rects = range.getClientRects();
      if (rects.length !== 1) continue;
      if (rects[0].width <= target) continue;
      const parent = node.parentElement;
      tokens.push({
        token: match[0].slice(0, 70),
        width: Math.round(rects[0].width),
        parent: parent ? parent.tagName.toLowerCase() : '',
        style: parent ? getComputedStyle(parent).overflowWrap : ''
      });
    }
  }
  tokens.sort((a, b) => b.width - a.width);

  return {
    inner_width: inner,
    scroll_width: scroller.scrollWidth,
    client_width: scroller.clientWidth,
    elements: elements.slice(0, 5),
    tokens: tokens.slice(0, 5)
  };
})"""


def _probe_source(target: int) -> str:
    return f"({PROBE.replace('MIN_TOKEN_CHARS', str(MIN_TOKEN_CHARS))})({target})"


def _violates(measurement: dict[str, Any], target: int) -> bool:
    """A page fails if the viewport had to widen, or if it scrolls horizontally within it."""
    widened = measurement["inner_width"] > target + TOLERANCE_PX
    scrolls = measurement["scroll_width"] > measurement["client_width"] + TOLERANCE_PX
    return widened or scrolls


def check(root: Path, paths: list[str], widths: tuple[int, ...] = WIDTHS) -> dict[str, Any]:
    """Measure every path at every width. One browser and one server for all of them."""
    report: dict[str, Any] = {"widths": list(widths), "pages": {}, "violations": 0}
    with background_server(root) as base, Browser() as browser:
        page = browser.page()
        for width in widths:
            page.emulate_device(width=width, height=HEIGHT)
            for path in paths:
                page.navigate(base + path)
                measurement = page.evaluate(_probe_source(width))
                # A width the browser never applied would make every page pass.
                if measurement["inner_width"] < width - TOLERANCE_PX:
                    raise CDPError(
                        f"{path}: asked for a {width} px viewport and the page reports "
                        f"{measurement['inner_width']} px. The override did not apply, so a "
                        "clean result here would be meaningless."
                    )
                failed = _violates(measurement, width)
                report["pages"][f"{path}@{width}"] = {**measurement, "failed": failed}
                report["violations"] += int(failed)
    return report


def format_report(report: dict[str, Any]) -> str:
    lines: list[str] = []
    for key, result in report["pages"].items():
        if not result["failed"]:
            continue
        path, _, width = key.partition("@")
        lines.append(
            f"FAIL {path} at {width} px: viewport widened to {result['inner_width']} px "
            f"(SC 1.4.10 Reflow)"
        )
        for token in result["tokens"]:
            lines.append(
                f"     unbreakable {token['width']} px in <{token['parent']}> "
                f"(overflow-wrap: {token['style']}): {token['token']}"
            )
        for element in result["elements"]:
            lines.append(
                f"     <{element['tag']} class={element['cls']!r}> "
                f"{element['width']} px, right edge {element['right']}"
            )
    checked = len(report["pages"])
    widths = ", ".join(f"{width} px" for width in report["widths"])
    lines.append(
        f"{checked} page-width pairs checked at {widths}: {report['violations']} reflow violations"
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="site", help="built site to check")
    parser.add_argument(
        "--all", action="store_true", help="every pre-rendered page, not one of each type"
    )
    parser.add_argument("--json", dest="json_out", help="write the full report here")
    args = parser.parse_args(argv)

    root = (REPO_ROOT / args.root).resolve()
    if not document_file(root, "/").exists():
        print(f"error: no built site at {root} — run `make build` first", file=sys.stderr)
        return 2
    if not find_chrome():
        # Loud, not skipped: a gate that quietly does nothing reports success.
        print("error: no Chrome or Chromium found, so nothing was checked", file=sys.stderr)
        return 2

    paths = every_page(root) if args.all else list(REPRESENTATIVE)
    try:
        report = check(root, paths)
    except CDPError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    print(format_report(report))
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"full report: {args.json_out}")
    return 1 if report["violations"] else 0


if __name__ == "__main__":  # pragma: no cover - entry point
    raise SystemExit(main())
