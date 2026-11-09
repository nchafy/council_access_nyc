#!/usr/bin/env python3
"""Which pages the accessibility and performance gates run against.

One list shared by three gates. `REPRESENTATIVE` is every *kind* of page, and is what the
accessibility and performance gates use because both cost seconds per page. `every_page()`
walks the built site, which is how a gate notices a page nobody listed here.

The build writes one document as of 2026-11-08, so the two agree. They are still separate:
`every_page` is a measurement of what shipped and `REPRESENTATIVE` is a claim about what
kinds exist, and a gate that conflated them would stop noticing a new route.

`PROGRAM_SURFACES` is the other half, and the reason one document is not one surface: the
51 district pages, the 59 board pages and both indexes are windows built in the browser now.
A sweep over routes can reach the desktop and nothing else, so the accessibility gate would
have gone from 116 pages to one and still reported clean.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

#: The document the build writes for a directory, and what `serve.py` resolves `/x/` to.
INDEX_FILE = "index.html"

#: Path -> why this page is in the list; when one fails, the reason names the promise broken.
#:
#: One entry, because the build writes one document. The 51 district pages, the 59 board
#: pages, both indexes, `/references/` and the 404 were deleted when the front end became a
#: window manager: every surface that was a page is a program built in the browser now, and
#: `tests/browser/test_webxp.py` is what drives those.
REPRESENTATIVE: dict[str, str] = {
    "/": "the desktop: the taskbar, the folder that opens on load, and every program's window",
}


@dataclass(frozen=True)
class Surface:
    """One thing a reader can be looking at that is not a route.

    `program` is the id a desktop launches. `click` is an optional selector, scoped to the
    program's own window by the caller, pressed once the window is ready — because a program
    sitting on its empty state and the same program showing a selection are two surfaces,
    and the second is where empty states and tables actually go wrong.
    """

    name: str
    program: str
    reason: str
    click: str | None = None


#: Every surface the accessibility gate checks beyond the one document, in the order it opens
#: them. `name` is what a failure is reported against, so two states of one program are two
#: entries rather than one checked twice.
PROGRAM_SURFACES: tuple[Surface, ...] = (
    Surface(
        name="showup",
        program="showup",
        reason="the folder that autostarts: the only icon, and the way into everything else",
    ),
    Surface(
        name="showup-councils",
        program="showup-councils",
        reason="the district list before a pick, which is 51 rows and an empty detail pane",
    ),
    Surface(
        name="showup-councils/district-3",
        program="showup-councils",
        reason="district 3 is the designed degraded state, where empty states go wrong",
        click='.pick[data-district="3"]',
    ),
    Surface(
        name="showup-boards",
        program="showup-boards",
        reason="the board list before a pick, which is 59 rows and an empty detail pane",
    ),
    Surface(
        name="showup-boards/board-302",
        program="showup-boards",
        reason="a board with a calendar, a phone number and a budget table, all populated",
        click='.pick[data-board="302"]',
    ),
    Surface(
        name="showup-readme",
        program="showup-readme",
        reason="the sources, and the staleness line computed at read time",
    ),
    Surface(
        name="showup-map",
        program="showup-map",
        reason="the map window: a canvas, a layer toggle, four controls and a facts card",
    ),
)


def document_file(root: Path, path: str) -> Path:
    """The file in a built site that a server path resolves to — `every_page` inverted.

    `/` and `/a/b/` become `index.html` and `a/b/index.html`; a path that already names a
    file comes back unchanged.
    """
    candidate = root / path.strip("/")
    if path.endswith("/") or candidate.is_dir():
        return candidate / INDEX_FILE
    return candidate


def every_page(root: Path) -> list[str]:
    """Every pre-rendered page in a built site, as server paths, front page first.

    `a/b/index.html` becomes `/a/b/`, the URL `scripts/serve.py` resolves and the only
    spelling the deployed site serves.
    """
    server_paths: list[str] = []
    for html_file in sorted(root.rglob("*.html")):
        relative = html_file.relative_to(root)
        if html_file.name == INDEX_FILE:
            parent = relative.parent.as_posix()
            server_paths.append("/" if parent == "." else f"/{parent}/")
        else:
            server_paths.append(f"/{relative.as_posix()}")
    return sorted(server_paths, key=lambda path: (path.count("/"), path))
