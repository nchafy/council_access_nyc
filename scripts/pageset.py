#!/usr/bin/env python3
"""Which pages the accessibility and performance gates run against.

One list shared by three gates. `REPRESENTATIVE` is every *kind* of page, including the
designed degraded states, and is what the keyboard and performance gates use because both
cost seconds per page. `every_page()` walks the built site for the axe gate, where data
differences do change results.
"""

from __future__ import annotations

from pathlib import Path

#: The document the build writes for a directory, and what `serve.py` resolves `/x/` to.
INDEX_FILE = "index.html"

#: Path -> why this page is in the list; when one fails, the reason names the promise broken.
REPRESENTATIVE: dict[str, str] = {
    "/": "the front page: both dropdowns, both plain-link lists, and the address box",
    "/district/1/": "the reference district layout, every field present",
    "/district/3/": (
        "the deliberate degraded state: no committees published, a source-conflict "
        "notice, and a seat with no current term on record"
    ),
    "/district/35/": "a district page with no Office Hours line",
    "/district/51/": "no Office Hours, and a suite number with no 'Suite'",
    "/district/": "the district index — the no-JavaScript path to all 51",
    "/board/302/": "the community board view, a different page type rather than a variant",
    "/board/": "the board index — the no-JavaScript path to all 59",
    "/references/": (
        "the sources page: every dataset identifier, fetch date and freshness window, "
        "and what every other page's source line points at"
    ),
    "/404.html": "the not-found page, which is still a page a person has to read",
}


def document_file(root: Path, path: str) -> Path:
    """The file in a built site that a server path resolves to — `every_page` inverted.

    `/` and `/district/35/` become `index.html` and `district/35/index.html`; a path that
    already names a file, like `/404.html`, comes back unchanged.
    """
    candidate = root / path.strip("/")
    if path.endswith("/") or candidate.is_dir():
        return candidate / INDEX_FILE
    return candidate


def every_page(root: Path) -> list[str]:
    """Every pre-rendered page in a built site, as server paths, front page first.

    `index.html` becomes `/district/35/`, the URL `scripts/serve.py` resolves and the
    only spelling the deployed site serves.
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
