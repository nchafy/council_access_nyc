# webxp, vendored

The Windows XP shell and its window manager: the desktop, the taskbar, the Start menu, the
window frame and the program loader. This directory is `src/` from the `webxp` repository,
copied verbatim.

| | |
| --- | --- |
| Commit | `b8825ff7241a0452aa43341bb16b85835259e7b7` |
| Subject | `port the base map in as the first real app` |
| Refs | `main` and `map-challenge-folder` both point at it |
| Source | `~/claude/webxp` — **local only, no remote** |
| Copied | 2026-11-07 |

The commit is what identifies this copy, not a branch. That checkout is shared and was on
`map-challenge-folder` with a third party's uncommitted refactor in it when these files were
taken, so `make webxp-check` was run immediately: nine files, byte-identical to the commit
above. The working tree is not the pin, and that is the whole reason the check exists.

## Licence

**There is no licence file in that repository, and none is assumed here.** It is first-party:
the same author as this site, and itself extracted from the 30 Day Map Challenge base map
this project already vendors. So there is no third-party grant to confirm — but the absence
is recorded rather than read as permission, because an unstated licence is not an open one.

## Why this is copied and not fetched

Every other vendored dependency here is fetched from a URL and verified against a pinned
sha256 (`scripts/fetch_basemap.py`, `scripts/fetch_maplibre.py`). That is not possible for
this one: the repository has no remote, so there is no URL to fetch and no immutable object to
pin against. A relative path out of this repository would break the first time anyone cloned
this one on its own.

So the files are committed here, and the commit above is the only thing recording what they
are. Two consequences worth stating:

- A `git log` in `~/claude/webxp` is the only way to audit this copy. If that repository is
  gone, the table above is unverifiable.
- `make webxp-check` compares this directory against that commit when the repository is
  reachable, and says so plainly when it is not. A check that silently passes because it
  could not find what it was comparing against is worse than no check.

The 30 Day Map Challenge repository takes the same bargain with the same code, for the same
reason.

## Rules

The files here **MUST NOT be edited**. A change belongs upstream, after which this directory
is re-copied and the commit above updated. A local edit makes the commit a lie, and the commit
is the only provenance this code has.

## What came across

`src/` only — nine files. The upstream `apps/`, `demo/`, `docs/` and `scripts/` are that
project's own programs, harness and examples; this site has its own under
`src/showup/apps/`.

Three stylesheets because they have three subjects: `theme.css` is the Luna palette and the
controls, `shell.css` is the desktop and the taskbar, `window.css` is the frame. Upstream's
`docs/windows.md` carries the window model and its departures from XP, including the measured
contrast corrections; `docs/apps.md` is the contract every program here is written against.
