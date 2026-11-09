#!/usr/bin/env python3
"""The keyboard pass and the screen-reader surface, checked by machine.

R39 asks for a documented keyboard-only and screen-reader pass per release;
`docs/accessibility-pass.md` is that document and this is the machine-checkable part. The
keyboard audit presses real `Tab` keys; the tree audit reads Chrome's own accessibility
tree, which cannot judge whether a name is useful but can prove names, landmarks and
unskipped heading levels exist.

The no-JavaScript audit and the address-box audit were deleted on 2026-11-08. The owner
dropped the no-JavaScript promise when the front end became a window manager — there is no
static version of one to fall back to — and the address box has no page to be reached on.

    python3 scripts/a11y_audit.py              # every page type
    python3 scripts/a11y_audit.py -v           # list every check, not just failures
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import Any

from cdp import Browser, CDPError, Session, find_chrome
from pageset import REPRESENTATIVE, document_file
from ready import NotReadyError, await_declared_ready
from serve import background_server

REPO_ROOT = Path(__file__).resolve().parent.parent

#: WCAG 2.4.7 wants a visible ring. webxp draws 2px, which is the thinnest ring on the
#: desktop and so the floor: there is one document now, and it loads one set of sheets.
MINIMUM_OUTLINE_PX = 2.0

#: Roles that a person operates, and must therefore be able to identify.
INTERACTIVE_ROLES = frozenset(
    {"link", "button", "textbox", "combobox", "listbox", "checkbox", "radio", "menuitem"}
)

#: Landmarks a page owes a screen-reader user. `main` is the content, and `contentinfo` is
#: where the fetch date and the staleness notice live, so both are owed by every page.
#:
#: `banner` is owed by a window, whose title bar is one. The desktop at `/` is not a window:
#: it is a wallpaper, an icon grid and the taskbar, with no title bar and no site identity
#: outside the taskbar — so requiring a `banner` there would only produce an empty one, which
#: is noise in the accessibility tree rather than orientation. It owes `navigation` instead,
#: which is the taskbar, and which the windows get for free from the same bar.
REQUIRED_LANDMARKS = ("banner", "main", "contentinfo")

#: Paths whose shape is not a window, and the landmarks they owe instead.
#:
#: The desktop owes no `contentinfo`, for the same reason it owes no `banner`: it has no
#: footer. The fetch date and the staleness notice moved into the Readme program when the
#: pages they sat on were deleted, and requiring the landmark here would only produce an
#: empty one. The promise itself is still checked, in the window that now carries it —
#: `tests/browser/test_console.py::TestTheStalenessNoticeReallyRenders`.
LANDMARKS_BY_PATH = {
    "/": ("main", "navigation"),
}


def required_landmarks(path: str) -> tuple[str, ...]:
    """Which landmarks `path` owes. A window owes `REQUIRED_LANDMARKS`."""
    return LANDMARKS_BY_PATH.get(path, REQUIRED_LANDMARKS)


#: Tags each focusable element with its DOM-order index. `summary` is in the selector
#: because a disclosure is a real tab stop (docs/OBSERVATIONS.md, 2026-10-07).
TAG_FOCUSABLE_JS = """
(() => {
  const selector = 'a[href], button, input, select, textarea, summary, [tabindex]';
  const nodes = [...document.querySelectorAll(selector)].filter((element) => {
    if (element.disabled || element.type === 'hidden') return false;
    if (element.getAttribute('tabindex') === '-1') return false;
    // `hidden` on an ancestor removes it from the tab order; load-order sensitive,
    // because the address section ships hidden and is revealed by script.
    if (element.closest('[hidden]')) return false;
    // A closed <details> hides its content with content-visibility rather than
    // display, so computed style alone would still count it as reachable.
    if (element.tagName !== 'SUMMARY' && element.closest('details:not([open])')) return false;
    const style = getComputedStyle(element);
    if (style.visibility === 'hidden' || style.display === 'none') return false;
    return true;
  });
  nodes.forEach((element, index) => element.setAttribute('data-kb-index', String(index)));
  return nodes.map((element, index) => ({
    index,
    tag: element.tagName.toLowerCase(),
    text: (element.textContent || element.value || element.getAttribute('aria-label') || '')
      .trim()
      .slice(0, 40),
    positiveTabindex: Number(element.getAttribute('tabindex') || 0) > 0,
    // An in-page anchor as the first stop is the skip-link shape. Read here because the
    // bypass check below has two shapes and has to know which one it is looking at.
    skipLink:
      element.tagName === 'A' && (element.getAttribute('href') || '').startsWith('#'),
    // Read off the element in DOM order, not off whatever has focus. SC 2.4.1 is a question
    // about the document's order, and asking it by pressing Tab cannot answer it here: the
    // host focuses a heading inside the main landmark on load, so the next stop is inside
    // that landmark whatever the order is. Proven — with the taskbar moved ahead of the
    // desktop surface, the Tab form of both checks still passed.
    inMain: !!element.closest('main, [role=\"main\"]'),
  }));
})()
"""

#: What has focus right now, and whether it is wearing a focus ring.
FOCUS_STATE_JS = """
(() => {
  const focused = document.activeElement;
  if (!focused || focused === document.body || focused === document.documentElement) {
    return { outside: true };
  }
  const style = getComputedStyle(focused);
  const rect = focused.getBoundingClientRect();
  return {
    outside: false,
    index: focused.hasAttribute('data-kb-index')
      ? Number(focused.getAttribute('data-kb-index'))
      : null,
    tag: focused.tagName.toLowerCase(),
    text: (focused.textContent || focused.value || '').trim().slice(0, 40),
    // Both spellings of the landmark. A `main` element and a `role="main"` are one thing
    // to a screen reader, and the desktop surface is the second: it is built by the
    // vendored shell as a div, so a tag-name test could never be satisfied there.
    inMain: !!focused.closest('main, [role="main"]'),
    outlineWidth: parseFloat(style.outlineWidth) || 0,
    outlineStyle: style.outlineStyle,
    // A ring drawn in the same colour as what is behind it is not a ring.
    outlineColor: style.outlineColor,
    rect: { top: rect.top, left: rect.left, width: rect.width, height: rect.height },
    viewport: { width: innerWidth, height: innerHeight },
  };
})()
"""


@dataclass(frozen=True)
class Check:
    """One named assertion about one page. `detail` is only read when it failed."""

    page: str
    name: str
    ok: bool
    detail: str = ""


def _focus_after_each_tab(page: Session, presses: int) -> list[dict[str, Any]]:
    """Press Tab exactly `presses` times, recording where focus lands each time.

    Exactly, not until focus leaves the document: headless Chrome has no browser controls
    to escape into, so focus wraps to the top instead.
    """
    focus_states = []
    for _ in range(presses):
        page.press("Tab")
        focus_states.append(page.evaluate(FOCUS_STATE_JS))
    return focus_states


def _settled_focusables(page: Session, attempts: int = 40, pause: float = 0.25) -> list[Any]:
    """The focusable list, once the page is ready and two consecutive reads agree.

    A control revealed by script enters the tab order after `load`: the address box does it
    within milliseconds, the map's zoom buttons only once MapLibre has drawn. Snapshotting
    once would measure a list that then changes under the Tab presses, and every index after
    the new element would look unreachable.
    """
    await_declared_ready(page, attempts, pause)
    previous = page.evaluate(TAG_FOCUSABLE_JS)
    for _ in range(attempts):
        time.sleep(pause)
        current = page.evaluate(TAG_FOCUSABLE_JS)
        if len(current) == len(previous):
            return current
        previous = current
    return previous


def audit_keyboard(page: Session, path: str) -> list[Check]:
    """Drive the keyboard through one already-loaded page."""
    checks: list[Check] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        checks.append(Check(path, name, ok, detail))

    try:
        focusable = _settled_focusables(page)
    except NotReadyError as error:
        # Reported as a failure rather than raised: a page whose readiness never arrived has
        # not been measured, and a harness that cannot reach what it was pointed at must say
        # so instead of reporting the checks it managed to run.
        record("the page became ready", False, str(error))
        return checks
    record("the page became ready", True)

    record("the page has focusable content", bool(focusable), "nothing to tab to")
    if not focusable:
        return checks

    queue_jumpers = [element for element in focusable if element["positiveTabindex"]]
    record(
        "no positive tabindex",
        not queue_jumpers,
        f"{len(queue_jumpers)} elements jump the queue: "
        f"{[element['text'] for element in queue_jumpers]}",
    )

    focus_states = _focus_after_each_tab(page, len(focusable))
    landed_states = [state for state in focus_states if not state["outside"]]

    first_focus = focus_states[0]
    if focusable[0]["skipLink"]:
        record(
            "the first Tab lands on the skip link",
            not first_focus["outside"] and first_focus["index"] == 0 and first_focus["tag"] == "a",
            f"first Tab went to {first_focus.get('tag')} {first_focus.get('text')!r}",
        )
        # The skip link is parked at left:-9999px and only pulled back on :focus.
        record(
            "the skip link is visible once focused",
            not first_focus["outside"]
            and first_focus["rect"]["left"] >= 0
            and first_focus["rect"]["top"] >= 0,
            f"focused skip link sits at {first_focus.get('rect')}, off-screen",
        )
    else:
        record(
            "the first stop in the tab order is content, not chrome",
            focusable[0]["inMain"],
            f"the first focusable is {focusable[0]['tag']} {focusable[0]['text']!r}, "
            "which is outside <main>",
        )

    visited_indexes = [state["index"] for state in landed_states if state["index"] is not None]
    expected_indexes = list(range(len(focusable)))
    record(
        "tab order follows DOM order",
        visited_indexes == expected_indexes,
        f"focus visited {visited_indexes[:20]}… expected {expected_indexes[:20]}…",
    )

    without_focus_ring = [
        f"{state['tag']} {state['text']!r}"
        for state in landed_states
        if state["outlineStyle"] == "none" or state["outlineWidth"] < MINIMUM_OUTLINE_PX
    ]
    record(
        "every focused element shows a focus ring",
        not without_focus_ring,
        f"no visible outline on: {without_focus_ring[:6]}",
    )

    record(
        "every focusable element is reachable by Tab alone",
        sorted(set(visited_indexes)) == expected_indexes,
        f"{len(set(visited_indexes))} of {len(focusable)} elements were reachable; "
        f"never reached {sorted(set(expected_indexes) - set(visited_indexes))[:10]}",
    )

    # Focus sits on the last element after the walk above, so retracing visits n-2 to 0.
    backward_indexes = []
    for _ in range(len(focusable) - 1):
        page.press("Tab", shift=True)
        state = page.evaluate(FOCUS_STATE_JS)
        if not state["outside"]:
            backward_indexes.append(state["index"])
    record(
        "Shift+Tab retraces the order in reverse",
        backward_indexes == list(reversed(expected_indexes[:-1])),
        f"backwards order was {backward_indexes[:20]}, "
        f"expected {list(reversed(expected_indexes[:-1]))[:20]}",
    )
    return checks


def audit_bypass(page: Session, path: str) -> list[Check]:
    """SC 2.4.1: a keyboard user reaches the content without walking through the chrome.

    Two shapes, because the mechanism is not the requirement. A document page puts a skip
    link first and this presses it, checking that focus moves and not merely the scroll
    position. The desktop has no skip link and needs none — its content is the first thing
    in the tab order, so there is no block to bypass — and what is checked there is that
    this stays true. A page that grew chrome in front of its content would fail.

    The second shape is read off DOM order rather than by pressing Tab. See `inMain` in
    `TAG_FOCUSABLE_JS`: the host focuses a heading inside the main landmark on load, which
    makes any Tab-based form of this question unfailable.
    """
    # Before reading the tab order, as in `audit_keyboard`: this ran on a freshly navigated
    # page with no wait and measured a desktop that was still only a taskbar, so the first
    # stop looked like the Start button and the page looked like chrome before content.
    try:
        await_declared_ready(page)
    except NotReadyError as error:
        return [Check(path, "the page became ready", False, str(error))]

    focusable = page.evaluate(TAG_FOCUSABLE_JS)
    if not focusable:
        return [Check(path, "there is something to reach", False, "nothing to tab to")]

    if focusable[0]["skipLink"]:
        page.press("Tab")
        page.press("Enter")
        page.press("Tab")
        state = page.evaluate(FOCUS_STATE_JS)
        return [
            Check(
                path,
                "the skip link moves focus into main",
                not state["outside"] and state["inMain"],
                f"after using the skip link, Tab went to {state.get('tag')} "
                f"{state.get('text')!r}, which is not inside <main>",
            )
        ]

    return [
        Check(
            path,
            "the content comes before the chrome, so there is nothing to bypass",
            focusable[0]["inMain"],
            f"the first focusable is {focusable[0]['tag']} {focusable[0]['text']!r}, "
            "outside <main>; a page whose chrome comes first owes a skip link",
        )
    ]


def audit_tree(page: Session, path: str) -> list[Check]:
    """Read Chrome's accessibility tree: what a screen reader is handed."""
    nodes = page.call("Accessibility.getFullAXTree").get("nodes") or []
    exposed_nodes = [node for node in nodes if not node.get("ignored")]

    def role_of(node: dict[str, Any]) -> str:
        return ((node.get("role") or {}).get("value")) or ""

    def name_of(node: dict[str, Any]) -> str:
        return (((node.get("name") or {}).get("value")) or "").strip()

    checks: list[Check] = []
    roles = {role_of(node) for node in exposed_nodes}

    wanted = required_landmarks(path)
    missing_landmarks = [landmark for landmark in wanted if landmark not in roles]
    checks.append(
        Check(
            path,
            "every required landmark is present",
            not missing_landmarks,
            f"the accessibility tree has no {missing_landmarks}",
        )
    )

    nameless_nodes = [
        f"{role_of(node)} at {node.get('backendDOMNodeId')}"
        for node in exposed_nodes
        if role_of(node) in INTERACTIVE_ROLES and not name_of(node)
    ]
    checks.append(
        Check(
            path,
            "every interactive node has an accessible name",
            not nameless_nodes,
            f"unnamed: {nameless_nodes[:6]}",
        )
    )

    heading_levels = [
        int(
            next(
                (
                    property_entry["value"]["value"]
                    for property_entry in (node.get("properties") or [])
                    if property_entry["name"] == "level"
                ),
                0,
            )
        )
        for node in exposed_nodes
        if role_of(node) == "heading"
    ]
    checks.append(
        Check(
            path,
            "there is exactly one level-1 heading",
            heading_levels.count(1) == 1,
            f"found {heading_levels.count(1)} h1s; heading levels were {heading_levels}",
        )
    )
    skipped_levels = [
        (previous, current)
        for previous, current in pairwise(heading_levels)
        if current > previous + 1
    ]
    checks.append(
        Check(
            path,
            "heading levels never skip a level",
            not skipped_levels,
            f"levels jump at {skipped_levels}; the full sequence was {heading_levels}",
        )
    )
    return checks


def audit(root: Path, paths: list[str]) -> list[Check]:
    checks: list[Check] = []
    with background_server(root) as base, Browser() as browser:
        page = browser.page()
        for path in paths:
            page.navigate(base + path)
            checks += audit_keyboard(page, path)
            checks += audit_tree(page, path)
            page.navigate(base + path)  # a fresh load, so focus starts at the top
            checks += audit_bypass(page, path)
    return checks


def format_checks(checks: list[Check], *, verbose: bool = False) -> str:
    lines = []
    for check in checks:
        if not check.ok:
            lines.append(f"FAIL {check.page}  {check.name}")
            lines.append(f"     {check.detail}")
        elif verbose:
            lines.append(f"ok   {check.page}  {check.name}")
    failed = sum(1 for check in checks if not check.ok)
    pages = len({check.page for check in checks})
    lines.append(f"{len(checks)} checks over {pages} pages: {failed} failed")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="site")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    root = (REPO_ROOT / args.root).resolve()
    if not document_file(root, "/").exists():
        print(f"error: no built site at {root} — run `make build` first", file=sys.stderr)
        return 2
    if not find_chrome():
        print("error: no Chrome or Chromium found, so nothing was checked", file=sys.stderr)
        return 2

    try:
        checks = audit(root, list(REPRESENTATIVE))
    except CDPError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    print(format_checks(checks, verbose=args.verbose))
    return 1 if any(not check.ok for check in checks) else 0


if __name__ == "__main__":  # pragma: no cover - entry point
    raise SystemExit(main())
