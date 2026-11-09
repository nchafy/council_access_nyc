#!/usr/bin/env python3
"""Opening one of `pageset.PROGRAM_SURFACES` in a loaded desktop.

Shared by the accessibility sweep and the console sweep, which both had the same blind spot
for the same reason: the front end is one document and seven windows, so a gate that visits
routes reaches the wallpaper, the taskbar and the folder that autostarts, and none of the
windows a reader reads. A program that throws inside `mount` or `ready` is invisible to a
route sweep — the shell catches it and the window says so, which nothing loading `/` sees.

One copy, because two gates hand-syncing the same launch sequence is how they drift apart.
"""

from __future__ import annotations

from typing import Any

from cdp import CDPError
from pageset import Surface

#: Elements a window must contain before a clean result from it means anything. A window that
#: mounted nothing still answers its selector, and a sweep over an empty div reports nothing
#: wrong. Measured over the five programs: the map is the thinnest at 29 — a canvas and its
#: controls — then the folder 36, the Readme 58, and the two lists 208 and 243.
MINIMUM_WINDOW_ELEMENTS = 10


def open_surface(page: Any, surface: Surface) -> str:
    """Launch `surface`'s program, press its click if it has one, and return its selector.

    `launch` resolves after the program's own `ready` hook, so awaiting it is the readiness
    signal for a window and no settling time is guessed. It answers null for a program that
    is not registered, which is a stale `apps/manifest.mjs` and must fail here.
    """
    scope = f".app-{surface.program}"
    opened = page.evaluate(
        f"window.webxp.launch({surface.program!r}).then((win) => Boolean(win))",
        await_promise=True,
    )
    if not opened:
        raise CDPError(
            f"{surface.name}: the desktop has no program {surface.program!r}, so nothing was "
            "checked. `apps/manifest.mjs` is probably stale — run `make apps`."
        )

    # A window that mounted nothing answers its own selector, so this is asserted directly
    # rather than inferred from how much a checker found to say about it.
    held = page.evaluate(
        f"(() => {{ const el = document.querySelector({scope!r});"
        " return el ? el.querySelectorAll('*').length : -1; })()"
    )
    if held < MINIMUM_WINDOW_ELEMENTS:
        raise CDPError(
            f"{surface.name}: {scope} holds {held} elements, expected at least "
            f"{MINIMUM_WINDOW_ELEMENTS}. The window is empty or absent, so a clean result "
            "from it would be meaningless."
        )

    if surface.click:
        # Loud rather than skipped: a selector that matches nothing would otherwise leave this
        # surface checked in its empty state under the name of its populated one.
        hit = page.evaluate(
            f"(() => {{ const el = document.querySelector({scope + ' ' + surface.click!r});"
            " if (!el) return false; el.click(); return true; })()"
        )
        if not hit:
            raise CDPError(
                f"{surface.name}: nothing matched {surface.click!r} inside {scope}, so the "
                "surface was never put into the state it is named for."
            )
    return scope
