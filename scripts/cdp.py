"""Chrome DevTools Protocol client — re-exported from the package.

The implementation moved to `showup.cdp` when the browser became a way of *loading* a
board's schedule and not only a way of testing the site: a loader in `showup.sources`
cannot import out of `scripts/`, and production code must not be reaching into a directory
that happens to be on `sys.path` because a conftest put it there.

This shim stays so that the operator tools beside it, and the browser gates, keep importing
`cdp` as they always have.
"""

from __future__ import annotations

from showup.cdp import (
    CHROME_CANDIDATES,
    Browser,
    CDPError,
    Session,
    WebSocket,
    find_chrome,
    main,
)

__all__ = [
    "CHROME_CANDIDATES",
    "Browser",
    "CDPError",
    "Session",
    "WebSocket",
    "find_chrome",
    "main",
]

if __name__ == "__main__":  # pragma: no cover - smoke test only
    raise SystemExit(main())
