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

## Defects found here, corrected in the host

Three accessibility defects of the shell, measured on 2026-11-09 by `make a11y` and
`make axe` against the desktop this site builds. All three are properties of any webxp host,
not of this site, so all three belong upstream. They are corrected in `src/showup/boot.mjs`
instead, and the correction is marked there with the number below.

The pin was **not** moved to carry a fix. `~/claude/webxp` is clean but its `HEAD` is
`33ce2d5` on `map-challenge-folder`, 22 commits past this pin, and that branch is another
session's work. Re-pinning to fix these would have pulled all 22 in with them, unreviewed.
Two of those commits — `92bc9fe` "stop opening the read-me on every load" and `fd5408c`
"let Clippy offer the read-me instead of taking the desktop" — read as though they are in
defect 3's territory already, so whoever next moves this pin should check 3 against the new
commit before porting the host-side correction forward.

1. **The desktop surface has no role.** It holds the page's content — the icon grid, and
   every window — so with no `main` landmark a screen-reader user has nothing to skip to, and
   axe reports the whole page as outside any landmark (its `region` rule, advisory).
2. **The shell writes no level-1 heading.** Its only heading is a window title at level 2, so
   a host document has no `h1` and its outline starts at the second level.
3. **`launch` ends in `win.takeFocus()` unconditionally**, so `autostart()` moves the caret
   into a window the reader never opened. Measured: focus landed on the folder's "City
   councils" row, and `Tab` then resumed from there rather than from the top of the document.
   The right shape is for `takeFocus` to be the caller's choice — `focus(win, {moveFocus})`
   already works that way — with autostart declining it.

   Note for whoever fixes this upstream: `blur()` is not the correction. It clears the ring,
   and `document.activeElement` reads `body` afterwards, but the browser keeps a sequential
   focus navigation starting point where the blurred element was, so the next `Tab` resumes
   mid-document. Measured: index 6 of 11 with focus apparently on `body`.

## What came across

`src/` only — nine files. The upstream `apps/`, `demo/`, `docs/` and `scripts/` are that
project's own programs, harness and examples; this site has its own under
`src/showup/apps/`.

Three stylesheets because they have three subjects: `theme.css` is the Luna palette and the
controls, `shell.css` is the desktop and the taskbar, `window.css` is the frame. Upstream's
`docs/windows.md` carries the window model and its departures from XP, including the measured
contrast corrections; `docs/apps.md` is the contract every program here is written against.
