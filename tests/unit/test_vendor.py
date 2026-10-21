"""The vendored browser dependency: the build refuses to ship a map route without it, and
the fetcher refuses bytes that are not the ones we pinned.

`docs/dependencies.md` allows a browser dependency only when it is vendored and pinned, so
the pin is the thing worth testing: a tarball that verifies but carries a swapped file must
not be written.
"""

from __future__ import annotations

import hashlib
import io
import sys
import tarfile
from pathlib import Path

import pytest

from showup.build import VENDOR_FILES, BuildError, _copy_vendor

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from fetch_maplibre import (
    MAPLIBRE_SHA256,
    ChecksumError,
    read_verified_members,
    tarball_integrity,
    verify_member,
    verify_tarball,
)


def _cache_with(tmp_path: Path, names) -> Path:
    cache = tmp_path / "maplibre-gl"
    cache.mkdir()
    for name in names:
        (cache / name).write_bytes(b"x" * 16)
    return cache


class TestTheBuildRefusesAMapWithoutItsLibrary:
    def test_every_file_is_copied(self, tmp_path, monkeypatch):
        monkeypatch.setattr("showup.build.VENDOR_CACHE", _cache_with(tmp_path, VENDOR_FILES))
        staging = tmp_path / "site"
        staging.mkdir()
        _copy_vendor(staging)
        assert {path.name for path in (staging / "vendor").iterdir()} == set(VENDOR_FILES)

    def test_an_empty_cache_fails_the_build(self, tmp_path, monkeypatch):
        monkeypatch.setattr("showup.build.VENDOR_CACHE", _cache_with(tmp_path, []))
        staging = tmp_path / "site"
        staging.mkdir()
        with pytest.raises(BuildError, match="no vendored MapLibre"):
            _copy_vendor(staging)

    def test_one_missing_file_fails_the_build_and_names_it(self, tmp_path, monkeypatch):
        """A partial cache is the dangerous case: the route would render and the import 404."""
        partial = [name for name in VENDOR_FILES if name != "maplibre-gl-worker.mjs"]
        monkeypatch.setattr("showup.build.VENDOR_CACHE", _cache_with(tmp_path, partial))
        staging = tmp_path / "site"
        staging.mkdir()
        with pytest.raises(BuildError, match=r"maplibre-gl-worker\.mjs"):
            _copy_vendor(staging)

    def test_the_licence_travels_with_the_code(self):
        """BSD-3-Clause asks for it, so it is part of the vendored set, not an extra."""
        assert "LICENSE.txt" in VENDOR_FILES


def _tarball(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, payload in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
    return buffer.getvalue()


class TestThePinIsEnforced:
    def test_a_tarball_that_is_not_ours_is_refused(self):
        with pytest.raises(ChecksumError, match="published integrity"):
            verify_tarball(b"not the tarball")

    def test_the_integrity_spelling_is_the_registry_s(self):
        assert tarball_integrity(b"").startswith("sha512-")

    def test_a_swapped_file_is_refused_even_inside_a_tarball_we_trust(self):
        """The tarball digest covers 28 MB we do not ship, so each file carries its own."""
        members = dict.fromkeys(MAPLIBRE_SHA256, b"swapped")
        payload = _tarball(members)
        with pytest.raises(ChecksumError, match="does not match its pin"):
            read_verified_members(payload, integrity=tarball_integrity(payload))

    def test_a_file_matching_its_pin_is_accepted(self):
        members = dict.fromkeys(MAPLIBRE_SHA256, b"swapped")
        payload = _tarball(members)
        pins = {name: hashlib.sha256(b"swapped").hexdigest() for name in MAPLIBRE_SHA256}
        read = read_verified_members(payload, integrity=tarball_integrity(payload), sha256=pins)
        assert set(read) == set(MAPLIBRE_SHA256)

    def test_verify_member_names_the_file_it_rejected(self):
        with pytest.raises(ChecksumError, match=r"maplibre-gl\.mjs"):
            verify_member("maplibre-gl.mjs", b"wrong", "0" * 64)

    def test_a_link_in_the_tarball_is_refused(self):
        """A symlink member could write outside the cache; only plain files are read."""
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
            info = tarfile.TarInfo("package/dist/maplibre-gl.mjs")
            info.type = tarfile.SYMTYPE
            info.linkname = "../../../etc/passwd"
            archive.addfile(info)
        payload = buffer.getvalue()
        with pytest.raises(ChecksumError, match="not a plain file"):
            read_verified_members(payload, integrity=tarball_integrity(payload))
