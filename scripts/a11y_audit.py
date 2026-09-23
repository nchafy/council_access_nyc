#!/usr/bin/env python3
"""The keyboard pass and the screen-reader surface, checked by machine.

R39's second clause asks for "a documented keyboard-only and screen-reader pass per
release". `docs/accessibility-pass.md` is that document; this is the part of it a
machine can do, so that the human pass spends its time on the things only a human can
judge — whether the reading order makes sense, whether a link means anything out of
context, whether an error message tells you what to do next.

Two audits, against a real browser:

**The keyboard audit** presses real `Tab` keys through the page and records where focus
actually lands. Reading `tabindex` out of the markup proves nothing: what matters is
what the browser does, including whether the focus ring is visible when it gets there
and whether focus can get back out again.

**The tree audit** reads Chrome's own accessibility tree — the same computed roles,
names and levels a screen reader consumes. It is not a screen reader, and it cannot
tell you whether "council.nyc.gov" is a useful link name. It can tell you that every
interactive node has *some* name, that the landmarks exist, and that heading levels do
not skip, which is where most screen-reader defects actually live.

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

#: WCAG 2.4.7 wants a visible focus indicator; 2.4.13 (AAA) sets a thickness. The
#: stylesheet uses a 3px outline, so anything thinner means a rule stopped applying.
MINIMUM_OUTLINE_PX = 2.0

#: Roles that a person operates, and must therefore be able to identify.
INTERACTIVE_ROLES = frozenset(
    {"link", "button", "textbox", "combobox", "listbox", "checkbox", "radio", "menuitem"}
)

#: Landmarks every page owes a screen-reader user. `contentinfo` is the footer, which
#: is where the staleness notice and every source's fetch date live — losing it would
#: strand the honesty machinery somewhere unreachable.
REQUIRED_LANDMARKS = ("banner", "main", "contentinfo")

#: Collects the focusable elements in DOM order and tags each with its index, so the
#: element that receives focus can be identified rather than merely described.
TAG_FOCUSABLE_JS = """
(() => {
  const selector = 'a[href], button, input, select, textarea, [tabindex]';
  const nodes = [...document.querySelectorAll(selector)].filter((el) => {
    if (el.disabled || el.type === 'hidden') return false;
    if (el.getAttribute('tabindex') === '-1') return false;
    // `hidden` on an ancestor removes it from the tab order; the address section
    // ships hidden and is revealed by script, so this is load-order sensitive.
    if (el.closest('[hidden]')) return false;
    const style = getComputedStyle(el);
    if (style.visibility === 'hidden' || style.display === 'none') return false;
    return true;
  });
  nodes.forEach((el, index) => el.setAttribute('data-kb-index', String(index)));
  return nodes.map((el, index) => ({
    index,
    tag: el.tagName.toLowerCase(),
    text: (el.textContent || el.value || el.getAttribute('aria-label') || '').trim().slice(0, 40),
    positiveTabindex: Number(el.getAttribute('tabindex') || 0) > 0,
  }));
})()
"""

#: What has focus right now, and whether it is wearing a focus ring.
FOCUS_STATE_JS = """
(() => {
  const el = document.activeElement;
  if (!el || el === document.body || el === document.documentElement) {
    return { outside: true };
  }
  const style = getComputedStyle(el);
  const rect = el.getBoundingClientRect();
  return {
    outside: false,
    index: el.hasAttribute('data-kb-index') ? Number(el.getAttribute('data-kb-index')) : null,
    tag: el.tagName.toLowerCase(),
    text: (el.textContent || el.value || '').trim().slice(0, 40),
    inMain: !!el.closest('main'),
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
    """Evaluate until the value satisfies `until`, or give up and return the last one.

    Returning rather than raising on timeout is deliberate: the caller turns the value
    into a named check with a useful message, and an exception here would report "the
    audit crashed" instead of "the address box did not submit".
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


def _tab_walk(page: Session, presses: int) -> list[dict[str, Any]]:
    """Press Tab exactly `presses` times, recording where focus lands each time.

    Exactly, not "until focus leaves the document". A first version tabbed past the
    end expecting focus to escape into the browser's own controls, which is what
    happens in a windowed browser — headless Chrome has no chrome to escape into, so
    focus wraps to the top instead and every page looked like a focus trap. The
    property worth asserting is reachability: n presses must visit n distinct
    elements. A real trap fails that, and wrapping does not.
    """
    states = []
    for _ in range(presses):
        page.press("Tab")
        states.append(page.evaluate(FOCUS_STATE_JS))
    return states


def audit_keyboard(page: Session, path: str) -> list[Check]:
    """Drive the keyboard through one already-loaded page."""
    checks: list[Check] = []
    focusable = page.evaluate(TAG_FOCUSABLE_JS)

    def record(name: str, ok: bool, detail: str = "") -> None:
        checks.append(Check(path, name, ok, detail))

    record("the page has focusable content", bool(focusable), "nothing to tab to")
    if not focusable:
        return checks

    positive = [item for item in focusable if item["positiveTabindex"]]
    record(
        "no positive tabindex",
        not positive,
        # A positive tabindex hoists an element above everything else on the page,
        # so the order a sighted keyboard user experiences stops matching the order
        # a screen-reader user hears.
        f"{len(positive)} elements jump the queue: {[item['text'] for item in positive]}",
    )

    states = _tab_walk(page, len(focusable))
    landed = [state for state in states if not state["outside"]]

    first = states[0]
    record(
        "the first Tab lands on the skip link",
        not first["outside"] and first["index"] == 0 and first["tag"] == "a",
        f"first Tab went to {first.get('tag')} {first.get('text')!r}",
    )
    # The skip link is parked at left:-9999px and only pulled back on :focus. If that
    # rule ever stops applying, a keyboard user's first Tab goes somewhere invisible.
    record(
        "the skip link is visible once focused",
        not first["outside"] and first["rect"]["left"] >= 0 and first["rect"]["top"] >= 0,
        f"focused skip link sits at {first.get('rect')}, off-screen",
    )

    order = [state["index"] for state in landed if state["index"] is not None]
    expected = list(range(len(focusable)))
    record(
        "tab order follows DOM order",
        order == expected,
        f"focus visited {order[:20]}… expected {expected[:20]}…",
    )

    ringless = [
        f"{state['tag']} {state['text']!r}"
        for state in landed
        if state["outlineStyle"] == "none" or state["outlineWidth"] < MINIMUM_OUTLINE_PX
    ]
    record(
        "every focused element shows a focus ring",
        not ringless,
        f"no visible outline on: {ringless[:6]}",
    )

    record(
        "every focusable element is reachable by Tab alone",
        # This is the assertion a focus trap fails: a trap makes focus stop advancing,
        # so the same index repeats and the set of visited elements is short of the
        # set that exists.
        sorted(set(order)) == expected,
        f"{len(set(order))} of {len(focusable)} elements were reachable; "
        f"never reached {sorted(set(expected) - set(order))[:10]}",
    )

    # Shift+Tab is a separate code path in the browser, and a forward order that does
    # not reverse cleanly is a real, repeatedly-reported class of bug. Focus is on the
    # last element after the walk above, so retracing should visit n-2 down to 0.
    backward = []
    for _ in range(len(focusable) - 1):
        page.press("Tab", shift=True)
        state = page.evaluate(FOCUS_STATE_JS)
        if not state["outside"]:
            backward.append(state["index"])
    record(
        "Shift+Tab retraces the order in reverse",
        backward == list(reversed(expected[:-1])),
        f"backwards order was {backward[:20]}, expected {list(reversed(expected[:-1]))[:20]}",
    )
    return checks


def audit_skip_link(page: Session, path: str) -> list[Check]:
    """Press the skip link and check it actually skips.

    The common failure is a skip link that moves the scroll position but not focus,
    so the next Tab drops the reader back into the header they were trying to escape.
    """
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
    live = [node for node in nodes if not node.get("ignored")]

    def role_of(node: dict[str, Any]) -> str:
        return ((node.get("role") or {}).get("value")) or ""

    def name_of(node: dict[str, Any]) -> str:
        return (((node.get("name") or {}).get("value")) or "").strip()

    checks: list[Check] = []
    roles = {role_of(node) for node in live}

    missing = [landmark for landmark in REQUIRED_LANDMARKS if landmark not in roles]
    checks.append(
        Check(
            path,
            "every required landmark is present",
            not missing,
            f"the accessibility tree has no {missing}",
        )
    )

    nameless = [
        f"{role_of(node)} at {node.get('backendDOMNodeId')}"
        for node in live
        if role_of(node) in INTERACTIVE_ROLES and not name_of(node)
    ]
    checks.append(
        Check(
            path,
            "every interactive node has an accessible name",
            not nameless,
            # A screen reader reads the name. Without one it says "link", which is
            # the accessibility equivalent of a button labelled "button".
            f"unnamed: {nameless[:6]}",
        )
    )

    levels = [
        int(
            next(
                (
                    property_["value"]["value"]
                    for property_ in (node.get("properties") or [])
                    if property_["name"] == "level"
                ),
                0,
            )
        )
        for node in live
        if role_of(node) == "heading"
    ]
    checks.append(
        Check(
            path,
            "there is exactly one level-1 heading",
            levels.count(1) == 1,
            f"found {levels.count(1)} h1s; heading levels were {levels}",
        )
    )
    jumps = [
        (previous, current) for previous, current in pairwise(levels) if current > previous + 1
    ]
    checks.append(
        Check(
            path,
            "heading levels never skip a level",
            not jumps,
            # Screen-reader users navigate by heading. A jump from h2 to h4 reads as
            # a missing section rather than a style choice.
            f"levels jump at {jumps}; the full sequence was {levels}",
        )
    )
    return checks


def audit_without_javascript(browser: Browser, base: str) -> list[Check]:
    """R39: all procedural content must work with JavaScript disabled.

    Checked by turning script execution off in the browser rather than by trusting
    that the markup looks static. The front page is the one that matters: the
    dropdowns need script to navigate, so the plain link lists below them are the
    real no-JavaScript path, and the address box — which cannot work without
    script — must stay hidden rather than sit there taking input that goes nowhere.
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

    A district number resolves locally, with no geocoder call, so this stays
    hermetic: the one path that touches the network is deliberately not exercised
    here — `tests/browser/test_address_box.py` covers the resolution logic.
    """
    page = browser.page()
    page.navigate(base + "/")
    # The section ships `hidden` and script reveals it, so waiting for it is also the
    # readiness signal: before that, tabbing to the box is not even possible.
    _poll(page, "!document.getElementById('address-section').hasAttribute('hidden')")

    # Reach it with the keyboard, not by clicking: that is the property under test.
    for _ in range(40):
        page.press("Tab")
        if page.evaluate("document.activeElement.id") == "address-input":
            break
    else:
        return [Check("/", "the address box is reachable by Tab", False, "never focused it")]

    page.type_text("35")
    page.press("Enter")
    # Submitting fetches /data/lookup.json before it can resolve anything, so the
    # navigation is two async hops away. Poll for it rather than assume.
    landed = _poll(page, "location.pathname", until=lambda value: value != "/") or "/"
    return [
        Check(
            "/",
            "the address box submits from the keyboard alone",
            landed == "/district/35/",
            f"Enter in the address box landed on {landed!r}, expected '/district/35/'",
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
