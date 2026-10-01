#!/usr/bin/env python3
"""Fetch the pinned axe-core build into a gitignored cache, verified before it is written.

R39 needs axe in CI. The pin lives in the three constants below rather than in 567 KB of
committed minified JavaScript: the registry's sha512 for the tarball, ours for the file.
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

#: A version bump is a three-line diff: these, and nothing else.
AXE_VERSION = "4.13.0"
AXE_TARBALL_INTEGRITY = "sha512-UzGt8zg7Ny8djbYMhxl2zuEevVa7r2gJjYY5Lwr1xM7+XU2nd6CkIWFTVcCIbAP63vSz71NaVyyuSk9lHKcy0A=="  # noqa: E501
AXE_SHA256 = "c24f097bd2f451d4f933e8bc7d8d539f8672a2ebcb5cc9f9f3eec8ca9470a0c1"

AXE_TARBALL_URL = f"https://registry.npmjs.org/axe-core/-/axe-core-{AXE_VERSION}.tgz"

REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = REPO_ROOT / ".cache" / "axe-core"
AXE_SOURCE = CACHE_DIR / "axe.min.js"

#: MPL-2.0 asks that the licence text travel with the code, so the cache carries it too.
WANTED_MEMBERS = ("package/axe.min.js", "package/LICENSE", "package/LICENSE-3RD-PARTY.txt")

DOWNLOAD_TIMEOUT_SECONDS = 60


class AxeFetchError(Exception):
    """axe could not be fetched, and nothing was written."""


class ChecksumError(AxeFetchError):
    """A payload did not match its pin, and nothing was written."""


def tarball_integrity(payload: bytes) -> str:
    """The registry's `sha512-<base64>` spelling of a payload's digest."""
    return "sha512-" + base64.b64encode(hashlib.sha512(payload).digest()).decode("ascii")


def verify_tarball(payload: bytes, expected: str = AXE_TARBALL_INTEGRITY) -> None:
    """Raise unless the payload is the tarball the registry published."""
    found = tarball_integrity(payload)
    if not hmac.compare_digest(found, expected):
        raise ChecksumError(
            f"{AXE_TARBALL_URL} does not match its published integrity.\n"
            f"  expected {expected}\n  found    {found}"
        )


def verify_axe_source(payload: bytes, expected: str = AXE_SHA256) -> None:
    """Raise unless the payload is the axe.min.js we pinned."""
    found = hashlib.sha256(payload).hexdigest()
    if not hmac.compare_digest(found, expected):
        raise ChecksumError(
            f"axe.min.js does not match its pin.\n  expected {expected}\n  found    {found}"
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
    integrity: str = AXE_TARBALL_INTEGRITY,
    sha256: str = AXE_SHA256,
) -> dict[str, bytes]:
    """The wanted members of a verified tarball, in memory, checked before any write."""
    verify_tarball(payload, integrity)
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
        members = {name: _member_bytes(archive, name) for name in WANTED_MEMBERS}
    verify_axe_source(members["package/axe.min.js"], sha256)
    return members


def cached_source_is_current() -> bool:
    """True when the cache already holds exactly the pinned bytes."""
    if not AXE_SOURCE.is_file():
        return False
    return hmac.compare_digest(hashlib.sha256(AXE_SOURCE.read_bytes()).hexdigest(), AXE_SHA256)


def download(url: str = AXE_TARBALL_URL) -> bytes:
    """The tarball, as bytes. Unverified: pass it to `read_verified_members`."""
    with urllib.request.urlopen(url, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
        return response.read()


def ensure_axe(*, force: bool = False) -> bool:
    """Make the pinned axe.min.js present in the cache. True if it had to be downloaded."""
    if not force and cached_source_is_current():
        return False
    try:
        payload = download()
    except OSError as error:
        raise AxeFetchError(f"could not download {AXE_TARBALL_URL}: {error}") from error
    try:
        members = read_verified_members(payload)
    except (tarfile.TarError, KeyError) as error:
        raise AxeFetchError(f"unreadable tarball from {AXE_TARBALL_URL}: {error}") from error
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    for name, content in members.items():
        cache_destination(name).write_bytes(content)
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch and verify the pinned axe-core build.")
    parser.add_argument(
        "--force", action="store_true", help="download again even if the cache is current"
    )
    args = parser.parse_args(argv)

    try:
        fetched = ensure_axe(force=args.force)
    except AxeFetchError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    where = AXE_SOURCE.relative_to(REPO_ROOT)
    state = "fetched and verified" if fetched else "already cached and verified"
    print(f"axe-core {AXE_VERSION} {state}: {where}")
    return 0


if __name__ == "__main__":  # pragma: no cover - entry point
    raise SystemExit(main())
