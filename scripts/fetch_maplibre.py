#!/usr/bin/env python3
"""Fetch the pinned MapLibre GL build into a gitignored cache, verified before it is written.

The map needs MapLibre in the browser, which makes it the first dependency this project
ships to a reader — an owner decision recorded in `product-brief.md` and
`docs/dependencies.md`, not a side effect of this file. The pin lives in the constants
below rather than in 1.6 MB of committed minified JavaScript, on the same reasoning as
`scripts/fetch_axe.py`: the registry's sha512 for the tarball, ours for each file taken
out of it.

`showup build` copies the cached files into `site/vendor/`, so the reader fetches them from
our own origin and no third party sees the request.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import io
import sys
import tarfile
import urllib.request
from pathlib import Path

#: A version bump is a five-line diff: these, and nothing else.
MAPLIBRE_VERSION = "6.15.0"
MAPLIBRE_TARBALL_INTEGRITY = "sha512-kxFetbvUHDOVaAP1CYb226Mdk2QhzIPddqM0xJTFD35wu78Mpd6NM7+H68ALjc6Oa0kAOX5EAdMKyvD2u3qfcg=="  # noqa: E501

#: sha256 per member, because the tarball digest covers 28 MB we do not ship. Only these
#: four files reach `site/vendor/`.
MAPLIBRE_SHA256 = {
    "package/dist/maplibre-gl.mjs": (
        "41198b23679a7d8892183408bbef2eabdc74745beb90261f6be0f660b7aeb2fd"
    ),
    "package/dist/maplibre-gl-worker.mjs": (
        "1c69066368331aae63967ed24a9affcf962cf55fcc6d8f532a8b040f736dbcfa"
    ),
    "package/dist/maplibre-gl.css": (
        "a90798a1953017790e590f7e1bd35ff103a8a4263972cb47290b78adf86f8c20"
    ),
    "package/LICENSE.txt": ("ee5fc05a0677eaf69601d2c7db0d9ecd6cc27c3abc1d0733bc9ed34707cf8ef2"),
}

#: BSD-3-Clause asks that the licence text travel with the code, so the cache carries it.
WANTED_MEMBERS = tuple(MAPLIBRE_SHA256)

MAPLIBRE_TARBALL_URL = (
    f"https://registry.npmjs.org/maplibre-gl/-/maplibre-gl-{MAPLIBRE_VERSION}.tgz"
)

REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = REPO_ROOT / ".cache" / "maplibre-gl"
MAPLIBRE_SOURCE = CACHE_DIR / "maplibre-gl.mjs"

DOWNLOAD_TIMEOUT_SECONDS = 120


class MapLibreFetchError(Exception):
    """MapLibre could not be fetched, and nothing was written."""


class ChecksumError(MapLibreFetchError):
    """A payload did not match its pin, and nothing was written."""


def tarball_integrity(payload: bytes) -> str:
    """The registry's `sha512-<base64>` spelling of a payload's digest."""
    return "sha512-" + base64.b64encode(hashlib.sha512(payload).digest()).decode("ascii")


def verify_tarball(payload: bytes, expected: str = MAPLIBRE_TARBALL_INTEGRITY) -> None:
    """Raise unless the payload is the tarball the registry published."""
    found = tarball_integrity(payload)
    if not hmac.compare_digest(found, expected):
        raise ChecksumError(
            f"{MAPLIBRE_TARBALL_URL} does not match its published integrity.\n"
            f"  expected {expected}\n  found    {found}"
        )


def verify_member(name: str, payload: bytes, expected: str) -> None:
    """Raise unless one extracted file is the one we pinned."""
    found = hashlib.sha256(payload).hexdigest()
    if not hmac.compare_digest(found, expected):
        raise ChecksumError(
            f"{name} does not match its pin.\n  expected {expected}\n  found    {found}"
        )


def _member_bytes(archive: tarfile.TarFile, name: str) -> bytes:
    """Read one named plain file out of the archive; refuse links, devices, directories."""
    member = archive.getmember(name)
    if not member.isfile():
        raise ChecksumError(f"{name} in the tarball is not a plain file")
    stream = archive.extractfile(member)
    if stream is None:
        raise ChecksumError(f"{name} in the tarball has no contents")
    with stream:
        return stream.read()


def cache_destination(name: str) -> Path:
    """Where an archive member lands: its basename, inside the cache, never above it."""
    target = CACHE_DIR / Path(name).name
    if CACHE_DIR.resolve() != target.resolve().parent:
        raise ChecksumError(f"{name} would be written outside {CACHE_DIR}")
    return target


def read_verified_members(
    payload: bytes,
    *,
    integrity: str = MAPLIBRE_TARBALL_INTEGRITY,
    sha256: dict[str, str] | None = None,
) -> dict[str, bytes]:
    """The wanted members of a verified tarball, in memory, checked before any write."""
    pins = MAPLIBRE_SHA256 if sha256 is None else sha256
    verify_tarball(payload, integrity)
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
        members = {name: _member_bytes(archive, name) for name in pins}
    for name, content in members.items():
        verify_member(name, content, pins[name])
    return members


def cached_source_is_current() -> bool:
    """True when the cache already holds exactly the pinned bytes, for every member."""
    for name, expected in MAPLIBRE_SHA256.items():
        cached = CACHE_DIR / Path(name).name
        if not cached.is_file():
            return False
        found = hashlib.sha256(cached.read_bytes()).hexdigest()
        if not hmac.compare_digest(found, expected):
            return False
    return True


def download(url: str = MAPLIBRE_TARBALL_URL) -> bytes:
    """The tarball, as bytes. Unverified: pass it to `read_verified_members`."""
    with urllib.request.urlopen(url, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
        return response.read()


def ensure_maplibre(*, force: bool = False) -> bool:
    """Make the pinned MapLibre files present in the cache. True if it had to download."""
    if not force and cached_source_is_current():
        return False
    try:
        payload = download()
    except OSError as error:
        raise MapLibreFetchError(f"could not download {MAPLIBRE_TARBALL_URL}: {error}") from error
    try:
        members = read_verified_members(payload)
    except (tarfile.TarError, KeyError) as error:
        raise MapLibreFetchError(
            f"unreadable tarball from {MAPLIBRE_TARBALL_URL}: {error}"
        ) from error
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    for name, content in members.items():
        cache_destination(name).write_bytes(content)
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch and verify the pinned MapLibre build.")
    parser.add_argument(
        "--force", action="store_true", help="download again even if the cache is current"
    )
    args = parser.parse_args(argv)

    try:
        fetched = ensure_maplibre(force=args.force)
    except MapLibreFetchError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    state = "fetched and verified" if fetched else "already cached and verified"
    print(f"maplibre-gl {MAPLIBRE_VERSION} {state}: {CACHE_DIR.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":  # pragma: no cover - entry point
    raise SystemExit(main())
