# webxp, vendored

The Windows XP shell and its window manager: the desktop, the taskbar, the Start menu, the
window frame and the program loader. This directory is `src/` from the `webxp` repository,
copied verbatim.

| | |
| --- | --- |
| Commit | `27e60429db6335b4400bf86b13508cb86a5ca560` |
| Subject | `locate the street pipeline's leftover speed in its short traversals` |
| Refs | `main` pointed at it |
| Source | `~/claude/webxp` — **local only, no remote** |
| Copied | 2026-11-09 |

The commit is what identifies this copy, not a branch, and the files are read with
`git show <commit>:src/<name>` rather than off the disk. That matters here twice over. The
checkout is shared — it had 42 modified files when this copy was taken, including seven of
these nine — and reading the working tree would have vendored another session's unfinished
work under a commit that does not contain it.

### The previous pin is gone

This directory was pinned to `b8825ff7241a0452aa43341bb16b85835259e7b7` from 2026-11-07. On
2026-11-09 that commit no longer existed in the source repository: neither it nor
`33ce2d5`, read from the same checkout hours earlier, resolves, and the branch
`map-challenge-folder` that carried both is gone. The history was rewritten or the
repository recreated.

`make webxp-check` reported `UNVERIFIABLE` rather than a match, which is the outcome it was
built for. A repository with no remote has no second copy of its history, so a pin here is
only as durable as one machine's `.git` — recorded so the next reader knows this can happen
again rather than treating it as a one-off.

## Licence

**MIT**, `Copyright (c) 2026 Nick Chafy`. The text is beside the code as `LICENSE`, taken
from the pinned commit's repository root, and `scripts/check_webxp.py` verifies it from the
pin like every other file: a licence nobody checks is one that can quietly become a
different licence.

This is an improvement on what was here before. The earlier pin carried no licence file at
all, and this document recorded the absence rather than reading it as permission.

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

   All three were re-checked against this pin on 2026-11-09, when it moved from
   `b8825ff` to `27e6042`, and all three are unchanged: the surface still carries no role,
   the shell still writes no `h1`, and `launch` still ends in an unconditional
   `win.takeFocus()`. The corrections in `boot.mjs` are therefore still load-bearing.

   Note for whoever fixes this upstream: `blur()` is not the correction. It clears the ring,
   and `document.activeElement` reads `body` afterwards, but the browser keeps a sequential
   focus navigation starting point where the blurred element was, so the next `Tab` resumes
   mid-document. Measured: index 6 of 11 with focus apparently on `body`.

## What came across

`src/` only — nine files — plus `LICENSE` from the repository root. The upstream `apps/`,
`demo/`, `docs/` and `scripts/` are that project's own programs, harness and examples; this
site has its own under `src/showup/apps/`.

Upstream now carries thirty-odd programs of its own on that desktop — the 30 Day Map
Challenge days, a base map, a notepad, a terminal. None of them are this site's, and this
site's five are not there: the dependency runs one way.

Three stylesheets because they have three subjects: `theme.css` is the Luna palette and the
controls, `shell.css` is the desktop and the taskbar, `window.css` is the frame. Upstream's
`docs/windows.md` carries the window model and its departures from XP, including the measured
contrast corrections; `docs/apps.md` is the contract every program here is written against.
