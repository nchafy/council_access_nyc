#!/usr/bin/env python3
"""The keyboard pass and the screen-reader surface, checked by machine.

R39 asks for a documented keyboard-only and screen-reader pass per release;
`docs/accessibility-pass.md` is that document and this is the part a machine can do.
The keyboard audit presses real `Tab` keys and records where focus actually lands. The
tree audit reads Chrome's own accessibility tree — the computed roles, names and levels
a screen reader consumes — which cannot judge whether a link name is useful but can
prove that names exist, landmarks exist, and heading levels do not skip.

    python3 scripts/a11y_audit.py              # every page type
    python3 scripts/a11y_audit.py -v           # list every check, not just failures
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import Any

from cdp import Browser, CDPError, Session, find_chrome
from pageset import REPRESENTATIVE
from serve import background_server

REPO_ROOT = Path(__file__).resolve().parent.parent

#: WCAG 2.4.7 wants a visible ring; the stylesheet's is 3px, so thinner means a rule broke.
MINIMUM_OUTLINE_PX = 2.0

#: Roles that a person operates, and must therefore be able to identify.
INTERACTIVE_ROLES = frozenset(
    {"link", "button", "textbox", "combobox", "listbox", "checkbox", "radio", "menuitem"}
)

#: Landmarks every page owes a screen-reader user; `contentinfo` holds the staleness notice.
REQUIRED_LANDMARKS = ("banner", "main", "contentinfo")

#: Tags each focusable element with its DOM-order index, so focus can be identified by index.
TAG_FOCUSABLE_JS = """
(() => {
  const selector = 'a[href], button, input, select, textarea, [tabindex]';
  const nodes = [...document.querySelectorAll(selector)].filter((element) => {
    if (element.disabled || element.type === 'hidden') return false;
    if (element.getAttribute('tabindex') === '-1') return false;
    // `hidden` on an ancestor removes it from the tab order; load-order sensitive,
    // because the address section ships hidden and is revealed by script.
    if (element.closest('[hidden]')) return false;
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
    inMain: !!focused.closest('main'),
    outlineWidth: parseFloat(style.outlineWidth) || 0,
    outlineStyle: style.outlineStyle,
    // A ring drawn in the same colour as what is behind it is not a ring.
    outlineColor: style.outlineColor,
    rect: { top: rect.top, left: rect.left, width: rect.width, height: rect.height },
    viewport: { width: innerWidth, height: innerHeight },
  };
})()
"""


def _poll(
    page: Session,
    expression: str,
    *,
    until: Callable[[Any], bool] = bool,
    timeout: float = 15.0,
) -> Any:
    """Evaluate until the value satisfies `until`, then return it.

    On timeout it returns the last value rather than raising, so the caller can report
    a named failing check instead of a crashed audit.
    """
    deadline = time.monotonic() + timeout
    value = None
    while time.monotonic() < deadline:
        value = page.evaluate(expression)
        if until(value):
            return value
        time.sleep(0.1)
    return value


@dataclass(frozen=True)
class Check:
    """One named assertion about one page. `detail` is only read when it failed."""

    page: str
    name: str
    ok: bool
    detail: str = ""


def _focus_after_each_tab(page: Session, presses: int) -> list[dict[str, Any]]:
    """Press Tab exactly `presses` times, recording where focus lands each time.

    Exactly, not until focus leaves the document: headless Chrome has no browser
    controls to escape into, so focus wraps to the top instead.
    """
    focus_states = []
    for _ in range(presses):
        page.press("Tab")
        focus_states.append(page.evaluate(FOCUS_STATE_JS))
    return focus_states


def audit_keyboard(page: Session, path: str) -> list[Check]:
    """Drive the keyboard through one already-loaded page."""
    checks: list[Check] = []
    focusable = page.evaluate(TAG_FOCUSABLE_JS)

    def record(name: str, ok: bool, detail: str = "") -> None:
        checks.append(Check(path, name, ok, detail))

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


def audit_skip_link(page: Session, path: str) -> list[Check]:
    """Press the skip link and check it moves focus, not merely the scroll position."""
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

    missing_landmarks = [landmark for landmark in REQUIRED_LANDMARKS if landmark not in roles]
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


def audit_without_javascript(browser: Browser, base: str) -> list[Check]:
    """R39: all procedural content must work with JavaScript disabled.

    Script execution is turned off in the browser rather than inferred from the markup.
    The front page is the one that matters: the plain link lists are the real
    no-JavaScript path, and the address box must stay hidden rather than take input.
    """
    page = browser.page()
    page.call("Emulation.setScriptExecutionDisabled", value=True)
    try:
        page.navigate(base + "/")
        districts = page.evaluate("document.querySelectorAll('a[href^=\"/district/\"]').length")
        boards = page.evaluate("document.querySelectorAll('a[href^=\"/board/\"]').length")
        address_hidden = page.evaluate(
            "!!document.getElementById('address-section')"
            " && document.getElementById('address-section').hasAttribute('hidden')"
        )
        scripts_off = page.evaluate("typeof window.__ranScript === 'undefined'")
    finally:
        page.call("Emulation.setScriptExecutionDisabled", value=False)

    return [
        Check("/", "script really was disabled", bool(scripts_off), "scripts still ran"),
        Check(
            "/",
            "all 51 districts are reachable as plain links",
            districts >= 51,
            f"only {districts} district links without JavaScript",
        ),
        Check(
            "/",
            "all 59 boards are reachable as plain links",
            boards >= 59,
            f"only {boards} board links without JavaScript",
        ),
        Check(
            "/",
            "the address box stays hidden without JavaScript",
            bool(address_hidden),
            "the address form is offered but cannot work — it needs script to submit",
        ),
    ]


def audit_address_box_by_keyboard(browser: Browser, base: str) -> list[Check]:
    """Reach the address box, type into it and submit, using only the keyboard.

    A district number resolves locally with no geocoder call, so this stays hermetic;
    `tests/browser/test_address_box.py` covers the resolution logic.
    """
    page = browser.page()
    page.navigate(base + "/")
    # The section ships `hidden`, so its reveal is also the readiness signal.
    _poll(page, "!document.getElementById('address-section').hasAttribute('hidden')")

    for _ in range(40):
        page.press("Tab")
        if page.evaluate("document.activeElement.id") == "address-input":
            break
    else:
        return [Check("/", "the address box is reachable by Tab", False, "never focused it")]

    page.type_text("35")
    page.press("Enter")
    # Submitting fetches /data/lookup.json first, so the navigation is two async hops away.
    landed_path = _poll(page, "location.pathname", until=lambda value: value != "/") or "/"
    return [
        Check(
            "/",
            "the address box submits from the keyboard alone",
            landed_path == "/district/35/",
            f"Enter in the address box landed on {landed_path!r}, expected '/district/35/'",
        )
    ]


def audit(root: Path, paths: list[str]) -> list[Check]:
    checks: list[Check] = []
    with background_server(root) as base, Browser() as browser:
        page = browser.page()
        for path in paths:
            page.navigate(base + path)
            checks += audit_keyboard(page, path)
            checks += audit_tree(page, path)
            page.navigate(base + path)  # a fresh load, so focus starts at the top
            checks += audit_skip_link(page, path)
        checks += audit_without_javascript(browser, base)
        checks += audit_address_box_by_keyboard(browser, base)
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
    if not (root / "index.html").exists():
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
