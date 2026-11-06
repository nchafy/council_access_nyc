#!/usr/bin/env python3
"""Download the pinned base map and window chrome into `.cache/`, verified.

Owner's decision, 2026-11-04: the base map is the `30daymapchallenge` repo. Its
`assets/basemap.mjs`, `assets/chrome.mjs` and `assets/xp.css` are the shared foundation —
an early-2000s satnav inside a Windows XP window — and this site's districts and boards
become layers on it rather than a second basemap maintained here.

**Pinned to a commit, not a branch.** A branch would mean the bytes this site serves change
when somebody else pushes, which is the thing a checksum exists to prevent: the same
argument `docs/dependencies.md` makes for MapLibre, and the reason neither is hot-linked.
Updating is a four-line diff — the pin and three digests — and the digests are printed on a
mismatch so the diff can be made from the error.

    python3 scripts/fetch_basemap.py            # idempotent; verifies an existing cache
    python3 scripts/fetch_basemap.py --force    # re-download even when current

The repository is public, so the build needs no credential. §4.5 holds: nothing in this
build is worth exfiltrating from a pull request.
"""

from __future__ import annotations

import argparse
import hashlib
import urllib.error
import urllib.request
from pathlib import Path

#: A version bump is a five-line diff: this, and the four digests below.
BASEMAP_COMMIT = "4f97759a084402bf50c3cf4c9e5d032e3736fc11"

#: sha256 per file. Taken at the pin above on 2026-11-04 and verified on every run, so a
#: silently rewritten upstream file fails the fetch instead of reaching a reader.
#:
#: `days.mjs` is the map challenge's thirty themes, which this site has no use for. It is here
#: because `chrome.mjs` imports it at the top level, for one function — `renderDayList`,
#: reachable only from a Start menu, which `/map/` deliberately does not have. A missing file
#: there is not a degraded Start menu: the import fails, the module graph fails with it, and
#: `map.mjs` never runs at all (measured 2026-11-05 — a 404 on `/vendor/days.mjs` left the
#: page with no map and no controls). Vendoring what we import is the honest fix until
#: `mountChrome` upstream takes its menu as data.
BASEMAP_SHA256 = {
    "basemap.mjs": "9114df4beff968a87ec51c6986af6b28c28c90065996c1b29a309b739fcd5720",
    "chrome.mjs": "d4b680d644829b81c171f49f9cb29ac01c6274fe9db88c0f7216359485c54cda",
    "days.mjs": "bcb2b21a95192664f0bea349e75996ae3b2e1bb6d7117cf3dcfa1e5adb55ce18",
    "xp.css": "825c1fdf3355710b60b02d439df56790d486ef32ba8f6e8f89c2bf5af8bbb75b",
}

BASEMAP_SOURCE = "https://raw.githubusercontent.com/nchafy/30daymapchallenge"

REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = REPO_ROOT / ".cache" / "basemap"

DOWNLOAD_TIMEOUT_SECONDS = 60

#: The same User-Agent the ETL uses, for the same reason: say who we are.
USER_AGENT = (
    "showup-nyc/0.1 (civic data ETL for a public-interest site; repo nchafy/council_access_nyc)"
)


class ChecksumError(RuntimeError):
    """A downloaded file did not match its pinned digest, or could not be fetched."""


def source_url(name: str) -> str:
    """Where one file lives at the pinned commit."""
    return f"{BASEMAP_SOURCE}/{BASEMAP_COMMIT}/assets/{name}"


def verify(name: str, payload: bytes) -> None:
    """Fail unless `payload` matches the digest pinned for `name`."""
    expected = BASEMAP_SHA256[name]
    found = hashlib.sha256(payload).hexdigest()
    if found != expected:
        raise ChecksumError(
            f"{name} does not match its pin.\n"
            f"  expected {expected}\n"
            f"  found    {found}\n"
            f"If the upstream change is wanted, update BASEMAP_COMMIT and this digest."
        )


def destination(name: str) -> Path:
    """Where one file is cached, refusing a name that would escape the cache."""
    target = CACHE_DIR / Path(name).name
    if CACHE_DIR.resolve() != target.resolve().parent:
        raise ChecksumError(f"{name} would be written outside {CACHE_DIR}")
    return target


def cached_is_current() -> bool:
    """Whether every pinned file is already cached and still matches its digest."""
    for name in BASEMAP_SHA256:
        target = destination(name)
        if not target.is_file():
            return False
        try:
            verify(name, target.read_bytes())
        except ChecksumError:
            return False
    return True


def download(name: str) -> bytes:
    """One file from the pin, verified before it is returned."""
    request = urllib.request.Request(source_url(name), headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
            payload = response.read()
    except (urllib.error.URLError, OSError) as error:
        raise ChecksumError(f"{name} could not be downloaded: {error}") from error
    verify(name, payload)
    return payload


def fetch(*, force: bool = False) -> list[Path]:
    """Cache every pinned file, and return where they landed."""
    if not force and cached_is_current():
        print(f"base map pinned at {BASEMAP_COMMIT[:12]} already cached and verified")
        return [destination(name) for name in BASEMAP_SHA256]

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    written = []
    for name in BASEMAP_SHA256:
        target = destination(name)
        target.write_bytes(download(name))
        written.append(target)
        print(f"  {name}: {target.stat().st_size} bytes, verified")
    print(f"base map cached from {BASEMAP_COMMIT[:12]} -> {CACHE_DIR}")
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="re-download even when current")
    args = parser.parse_args(argv)
    try:
        fetch(force=args.force)
    except ChecksumError as error:
        print(f"error: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
