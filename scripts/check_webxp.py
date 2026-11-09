#!/usr/bin/env python3
"""Compare the vendored webxp against the commit `PROVENANCE.md` pins it to.

The copy is `src/` plus the licence from the repository root — see `ROOT_FILES`.

Every other vendored dependency here is verified against a sha256 at fetch time. webxp cannot
be: its repository has no remote, so there is nothing to fetch and no immutable object to pin.
The files are committed instead, and this is what keeps the commit in `PROVENANCE.md` honest.

    python3 scripts/check_webxp.py

Three outcomes, and the middle one is the point:

* **match** — every file is byte-identical to that commit. Exit 0.
* **unverifiable** — the source repository is not on this machine, or the commit is not in it.
  Exit 0 with a message saying so, because a clone of this site is expected not to have it.
  What it MUST NOT do is report a match.
* **drift** — a file differs, is missing, or is new. Exit 1, naming each one.

Drift is a failure rather than a note because the rule in `PROVENANCE.md` is that these files
are not edited locally. A local edit makes the pin a lie, and the pin is the only provenance
this code has.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VENDORED = REPO_ROOT / "src" / "showup" / "vendor" / "webxp"
PROVENANCE = VENDORED / "PROVENANCE.md"

#: Where the source repository is expected to be. Recorded in `PROVENANCE.md` too; it is
#: local-only, so this is a convention rather than an address anyone else can resolve.
SOURCE_REPO = Path("~/claude/webxp").expanduser()

#: The subdirectory of that repository this one was copied from.
SOURCE_SUBDIR = "src"

#: Not part of the copy: this file is ours, and the pin cannot describe itself.
OURS = {"PROVENANCE.md"}

#: Files taken from the source repository's root rather than from `src/`. The licence has to
#: travel with the code it covers, and it is verified from the pin like everything else —
#: a licence nobody checks is a licence that can be swapped for a different one.
ROOT_FILES = ("LICENSE",)


class DriftError(RuntimeError):
    """The vendored copy does not match the commit it claims to be."""


def pinned_commit(text: str) -> str:
    """The commit `PROVENANCE.md` names, or raise."""
    match = re.search(r"^\|\s*Commit\s*\|\s*`([0-9a-f]{40})`\s*\|", text, re.M)
    if not match:
        raise DriftError(f"{PROVENANCE} names no 40-character commit in its table")
    return match.group(1)


def _git(*args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(["git", "-C", str(SOURCE_REPO), *args], capture_output=True, check=False)


def source_files(commit: str) -> dict[str, bytes] | None:
    """Every file of `SOURCE_SUBDIR` at `commit`, or None if that cannot be read."""
    if not (SOURCE_REPO / ".git").exists():
        return None
    listing = _git("ls-tree", "-r", "--name-only", commit, f"{SOURCE_SUBDIR}/")
    if listing.returncode != 0:
        return None
    names = [line for line in listing.stdout.decode().splitlines() if line.strip()]
    if not names:
        return None

    out: dict[str, bytes] = {}
    for name in [*names, *ROOT_FILES]:
        blob = _git("show", f"{commit}:{name}")
        if blob.returncode != 0:
            return None
        out[Path(name).name] = blob.stdout
    return out


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()[:12]


def compare(ours: dict[str, bytes], theirs: dict[str, bytes]) -> list[str]:
    """Every disagreement, as a line naming the file and what is wrong with it."""
    problems = []
    for name in sorted(set(theirs) - set(ours)):
        problems.append(f"missing: {name} is in the pinned commit and not here")
    for name in sorted(set(ours) - set(theirs)):
        problems.append(f"extra:   {name} is here and not in the pinned commit")
    for name in sorted(set(ours) & set(theirs)):
        if ours[name] != theirs[name]:
            problems.append(
                f"differs: {name} is {digest(ours[name])} here, {digest(theirs[name])} at the pin"
            )
    return problems


def main() -> int:
    if not VENDORED.is_dir():
        print(f"no vendored webxp at {VENDORED}", file=sys.stderr)
        return 1
    commit = pinned_commit(PROVENANCE.read_text(encoding="utf-8"))

    theirs = source_files(commit)
    if theirs is None:
        # Said plainly, and not as a pass. A clone of this site is not expected to carry the
        # source repository, and the alternative — treating "cannot compare" as "matches" —
        # is the one outcome that would make this check worthless.
        print(
            f"webxp UNVERIFIABLE: {SOURCE_REPO} is not a readable git repository containing "
            f"{commit[:12]}.\n"
            f"The vendored copy is unchecked. It is local-only by design; see "
            f"{PROVENANCE.relative_to(REPO_ROOT)}."
        )
        return 0

    ours = {path.name: path.read_bytes() for path in VENDORED.iterdir() if path.is_file()}
    ours = {name: payload for name, payload in ours.items() if name not in OURS}

    problems = compare(ours, theirs)
    if problems:
        print(f"webxp DRIFT from {commit[:12]}:", file=sys.stderr)
        for line in problems:
            print(f"  {line}", file=sys.stderr)
        print(
            "\nThese files are not edited locally. Make the change in "
            f"{SOURCE_REPO}, then re-copy and update the commit in PROVENANCE.md.",
            file=sys.stderr,
        )
        return 1

    print(f"webxp matches {commit[:12]}: {len(ours)} files byte-identical")
    return 0


if __name__ == "__main__":
    sys.exit(main())
