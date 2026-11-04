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

from showup.build import BASEMAP_FILES, VENDOR_FILES, BuildError, _copy_vendor

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from fetch_maplibre import (
    MAPLIBRE_SHA256,
    ChecksumError,
    read_verified_members,
    tarball_integrity,
    verify_member,
    verify_tarball,
)


def _cache_with(tmp_path: Path, names, *, dirname: str = "maplibre-gl") -> Path:
    cache = tmp_path / dirname
    cache.mkdir(exist_ok=True)
    for name in names:
        (cache / name).write_bytes(b"x" * 16)
    return cache


def _stub_caches(tmp_path, monkeypatch, *, maplibre=None, basemap=None) -> None:
    """Point both vendor caches at fixtures, and skip the policy check.

    `_copy_vendor` also asserts `connect-src` covers what the base map fetches, which reads
    the real pinned file. These tests are about copying, so the stub base map carries no
    hosts and the assertion is stubbed out rather than fed a fake policy.
    """
    monkeypatch.setattr(
        "showup.build.VENDOR_CACHE",
        _cache_with(tmp_path, VENDOR_FILES if maplibre is None else maplibre),
    )
    monkeypatch.setattr(
        "showup.build.BASEMAP_CACHE",
        _cache_with(
            tmp_path,
            BASEMAP_FILES if basemap is None else basemap,
            dirname="basemap",
        ),
    )
    monkeypatch.setattr("showup.build._assert_policy_covers_basemap", lambda: None)


class TestTheBuildRefusesAMapWithoutItsLibrary:
    def test_every_file_is_copied(self, tmp_path, monkeypatch):
        _stub_caches(tmp_path, monkeypatch)
        staging = tmp_path / "site"
        staging.mkdir()
        _copy_vendor(staging)
        assert {path.name for path in (staging / "vendor").iterdir()} == {
            *VENDOR_FILES,
            *BASEMAP_FILES,
        }

    def test_an_absent_base_map_fails_the_build(self, tmp_path, monkeypatch):
        """A map route whose base map 404s is worse than a build that stopped."""
        _stub_caches(tmp_path, monkeypatch, basemap=[])
        staging = tmp_path / "site"
        staging.mkdir()
        with pytest.raises(BuildError, match="no vendored base map"):
            _copy_vendor(staging)

    def test_an_empty_cache_fails_the_build(self, tmp_path, monkeypatch):
        _stub_caches(tmp_path, monkeypatch, maplibre=[])
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


class TestThePolicyMustCoverTheBaseMap:
    """Nothing else compares `connect-src` against what the vendored base map requests, so
    without this a new upstream tile host ships a map that passes every local check and is
    blocked in a reader's browser."""

    def test_the_pinned_base_map_is_covered_by_the_real_policy(self):
        from showup.build import _assert_policy_covers_basemap

        _assert_policy_covers_basemap()

    def test_the_fetch_origins_exclude_attribution_links(self):
        """The base map names Esri, OpenStreetMap and Creative Commons in links a reader
        clicks. A link is not a fetch, and putting those in `connect-src` would widen the
        policy for nothing."""
        from showup.build import _basemap_fetch_origins

        origins = _basemap_fetch_origins()
        assert "https://www.openstreetmap.org" not in origins
        assert "https://creativecommons.org" not in origins
        assert "https://tiles.openfreemap.org" in origins

    @pytest.mark.parametrize(
        ("origin", "hosts", "allowed"),
        [
            ("https://a.example.org", ["https://a.example.org"], True),
            ("https://a.example.org", ["https://b.example.org"], False),
            # A templated subdomain matches any one host under the same domain.
            ("https://${s}.tile.example.org", ["https://a.tile.example.org"], True),
            ("https://${s}.tile.example.org", ["https://a.tile.evil.org"], False),
            ("https://${s}.tile.example.org", [], False),
        ],
    )
    def test_which_origins_a_policy_allows(self, origin, hosts, allowed):
        from showup.build import _origin_allowed

        assert _origin_allowed(origin, hosts) is allowed

    def test_an_uncovered_host_names_itself_in_the_refusal(self, tmp_path, monkeypatch):
        """The message has to be enough to make the fix from."""
        from showup.build import _assert_policy_covers_basemap

        cache = tmp_path / "basemap"
        cache.mkdir()
        (cache / "basemap.mjs").write_text(
            "const T = 'https://tiles.example.test/styles/x';", encoding="utf-8"
        )
        monkeypatch.setattr("showup.build.BASEMAP_CACHE", cache)
        with pytest.raises(BuildError, match=r"tiles\.example\.test"):
            _assert_policy_covers_basemap()
