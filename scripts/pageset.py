#!/usr/bin/env python3
"""Which pages the accessibility and performance gates run against, and why.

One list, three gates. Keeping it here rather than in each script means a new page
type gets checked by all of them at once, and a page nobody thought to test shows up
as a diff to this file.

Two scopes, deliberately different:

- `REPRESENTATIVE` is every *kind* of page, including the designed degraded states.
  It is what the keyboard and performance gates use, because those measure
  interaction and load and both cost seconds per page — running them over 114 pages
  would buy nothing, since districts 7 and 8 differ only in their data.
- `every_page()` walks the built site, so the axe gate can do what R39 actually
  says: *every* pre-rendered page. Data differences do change axe results — an
  unusually long committee name can overflow, a missing section can leave a heading
  level orphaned — so here the full sweep is worth its runtime.
"""

from __future__ import annotations

from pathlib import Path

#: Path -> why this page is in the list. The reason is not decoration: when one of
#: these starts failing, the reason is what tells you which promise broke.
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
    "/404.html": "the not-found page, which is still a page a person has to read",
}


def every_page(root: Path) -> list[str]:
    """Every pre-rendered page in a built site, as server paths, in a stable order.

    `index.html` becomes `/district/35/` rather than `/district/35/index.html`,
    because that is the URL a person and a search engine both use, and it is the one
    `scripts/serve.py` resolves. Testing the other spelling would exercise a path
    the deployed site never serves.
    """
    paths: list[str] = []
    for html in sorted(root.rglob("*.html")):
        relative = html.relative_to(root)
        if html.name == "index.html":
            parent = relative.parent.as_posix()
            paths.append("/" if parent == "." else f"/{parent}/")
        else:
            paths.append(f"/{relative.as_posix()}")
    # Sort so the front page leads and a failure list reads in a predictable order.
    return sorted(paths, key=lambda path: (path.count("/"), path))
