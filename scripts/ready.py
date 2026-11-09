#!/usr/bin/env python3
"""Waiting for a page to say it is ready, and failing when it never does.

The contract has two halves. The document declares `data-ready-when="<name>"` in its static
markup, and whatever builds the page sets `data-ready="<name>"` once it is finished. A
harness blocks on the second.

Both halves are needed. Waiting for the DOM to stop changing is not enough, because a
plateau before the work starts looks exactly like a plateau after it finished — measured on
`/map/`, where two early reads agreed and the Tab walk then ran against ten stops out of
fourteen (2026-11-05). Declaring the promise in markup rather than in script is what makes a
page whose script never ran fail here instead of sailing past an absent attribute.
"""

from __future__ import annotations

import time
from typing import Any


class NotReadyError(Exception):
    """A page that promised to declare itself ready never did."""


def await_declared_ready(page: Any, attempts: int = 40, pause: float = 0.25) -> str | None:
    """Block until `page` sets the `data-ready` it promised. Return the name it declared.

    A page carrying no promise returns `None` and is left to the caller's own settling rule.
    A page that promised and never delivered raises, because a harness that cannot reach
    what it was pointed at must say so rather than report the checks it managed to run.
    """
    promised = page.evaluate("document.documentElement.dataset.readyWhen || null")
    if not promised:
        return None
    for _ in range(attempts):
        if page.evaluate("document.documentElement.dataset.ready || null") == promised:
            return promised
        time.sleep(pause)
    raise NotReadyError(
        f"the page declares data-ready-when={promised!r} but never set data-ready; "
        f"waited {attempts * pause:.1f}s"
    )
