#!/usr/bin/env python3
"""WCAG contrast ratios for a stylesheet's custom properties.

The site's dark steps are asserted rather than judged: `tests/unit/test_contrast.py` reads
the values out of `assets/showup.css` itself and fails if a colour is edited without the
ratio still clearing its threshold. Run this file directly to see the table.

    python3 scripts/contrast.py

The formula is WCAG 2.1's relative luminance and contrast ratio
(https://www.w3.org/TR/WCAG21/#dfn-relative-luminance).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

#: SC 1.4.3, normal-size body text.
TEXT_MINIMUM = 4.5

#: SC 1.4.11, a boundary that identifies a control or a state.
NON_TEXT_MINIMUM = 3.0

ASSETS = Path(__file__).resolve().parent.parent / "src" / "showup" / "assets"


def _channel(value: int) -> float:
    fraction = value / 255
    return fraction / 12.92 if fraction <= 0.03928 else ((fraction + 0.055) / 1.055) ** 2.4


def luminance(colour: str) -> float:
    """Relative luminance of a `#rgb` or `#rrggbb` colour."""
    digits = colour.lstrip("#")
    if len(digits) == 3:
        digits = "".join(digit * 2 for digit in digits)
    if len(digits) != 6:
        raise ValueError(f"not a hex colour: {colour!r}")
    red, green, blue = (int(digits[index : index + 2], 16) for index in (0, 2, 4))
    return 0.2126 * _channel(red) + 0.7152 * _channel(green) + 0.0722 * _channel(blue)


def ratio(foreground: str, background: str) -> float:
    """Contrast ratio between two colours, 1.0 to 21.0."""
    first, second = luminance(foreground), luminance(background)
    lighter, darker = max(first, second), min(first, second)
    return (lighter + 0.05) / (darker + 0.05)


def tokens(css: str, *, dark: bool) -> dict[str, str]:
    """The hex-valued custom properties of a stylesheet's light or dark `:root` block.

    Non-hex values — `rgb(...)`, a length — are skipped: this reads colours, and a caller
    asking for a ratio against a length should get a `KeyError` rather than a number.
    """
    blocks = re.findall(r":root\s*\{([^}]*)\}", css)
    if not blocks:
        raise ValueError("no :root block found")
    # The dark block is the one inside `@media (prefers-color-scheme: dark)`, which in this
    # project is the last `:root` in the file. Asserted by the caller's own test rather than
    # trusted: a file with one `:root` and `dark=True` must not silently return the light set.
    if dark and len(blocks) < 2:
        raise ValueError("no dark :root block found")
    block = blocks[-1] if dark else blocks[0]
    found = dict(re.findall(r"(--[a-z0-9-]+)\s*:\s*(#[0-9a-fA-F]{3,6})\s*;", block))
    if not found:
        raise ValueError("the :root block declares no hex colours")
    return found


#: Foreground, background, threshold, and what the pair is. Read against the dark block of
#: `showup.css`, which is the one set of steps this project chose rather than inherited.
DARK_PAIRS: tuple[tuple[str, str, float, str], ...] = (
    ("--ink", "--face", TEXT_MINIMUM, "body text on a control or panel face"),
    ("--ink", "--bg", TEXT_MINIMUM, "text in an input"),
    ("--ink", "--panel", TEXT_MINIMUM, "text on a record's face"),
    ("--muted", "--face", TEXT_MINIMUM, "the provenance line"),
    ("--accent", "--face", TEXT_MINIMUM, "a link in the panel"),
    ("--accent", "--bg", TEXT_MINIMUM, "a link in an input"),
    ("--rule", "--face", NON_TEXT_MINIMUM, "a control border"),
    ("--rule", "--bg", NON_TEXT_MINIMUM, "an input's edge"),
    ("--rule", "--panel", NON_TEXT_MINIMUM, "a group box's edge"),
    ("--sunken", "--face", NON_TEXT_MINIMUM, "the pressed tab's border"),
    ("--sunken", "--bg", NON_TEXT_MINIMUM, "an input's border"),
    ("--legend", "--face", TEXT_MINIMUM, "a card's heading"),
    ("--legend", "--panel", TEXT_MINIMUM, "a group box's legend"),
)


#: Pairs whose foreground is ours and whose background is the pinned shell's. Measured here
#: because nothing else can: `--on-title-dim` is declared in `showup.css` and the two title
#: blues in `vendor/webxp/theme.css`, so a check reading one file sees half the pair — and
#: the half it misses is the one a pin bump changes.
#:
#: Both blues are scheme-invariant by that stylesheet's own choice, so one measurement each
#: covers light and dark.
PINNED_PAIRS: tuple[tuple[str, str, float, str], ...] = (
    ("--on-title-dim", "--title-b", TEXT_MINIMUM, "a selected row's second line"),
    ("--on-title-dim", "--title-a", TEXT_MINIMUM, "a hovered row's second line"),
)

#: The vendored shell's own palette, which `PINNED_PAIRS` reads the background out of.
VENDOR_THEME = ASSETS.parent / "vendor" / "webxp" / "theme.css"


def report() -> int:
    """Print the table and return a process exit status.

    `showup.css` carries the steps this project chose. The Luna title bars are the pinned
    shell's and are not re-stepped here — white on `--title-a` is 14.25:1 and is that
    stylesheet's own to keep — but the text this project puts *on* them is ours, so
    `PINNED_PAIRS` measures across the two files.
    """
    css = (ASSETS / "showup.css").read_text(encoding="utf-8")
    dark, light = tokens(css, dark=True), tokens(css, dark=False)

    failures = 0
    print("dark steps, from src/showup/assets/showup.css")
    for foreground, background, need, why in DARK_PAIRS:
        measured = ratio(dark[foreground], dark[background])
        ok = measured >= need
        failures += not ok
        print(
            f"  {foreground:9s} on {background:8s} {measured:5.2f}:1  "
            f"need {need}  {'PASS' if ok else 'FAIL'}  {why}"
        )

    print("\nours on the pinned shell's title blues")
    shell = tokens(VENDOR_THEME.read_text(encoding="utf-8"), dark=False)
    for foreground, background, need, why in PINNED_PAIRS:
        measured = ratio(light[foreground], shell[background])
        ok = measured >= need
        failures += not ok
        print(
            f"  {foreground:14s} on {background:10s} {measured:5.2f}:1  "
            f"need {need}  {'PASS' if ok else 'FAIL'}  {why}"
        )

    print("\nthe warning fill, whose both steps are ours")
    for name, values in (("light", light), ("dark", dark)):
        measured = ratio(values["--warn-ink"], values["--warn-bg"])
        ok = measured >= TEXT_MINIMUM
        failures += not ok
        print(
            f"  {name:5s} --warn-ink on --warn-bg {measured:5.2f}:1  "
            f"need {TEXT_MINIMUM}  {'PASS' if ok else 'FAIL'}"
        )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(report())
