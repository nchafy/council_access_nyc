"""The axe-core pin, now that axe is fetched rather than committed.

Nothing here touches the network: the pin is asserted as constants, and the
verification that protects the download is exercised against in-memory payloads. The
one test that does hit the registry is marked `upstream` and excluded from CI's run.
"""

from __future__ import annotations

import base64
import hashlib
import io
import re
import tarfile
from pathlib import Path

import pytest
from fetch_axe import (
    AXE_SHA256,
    AXE_SOURCE,
    AXE_TARBALL_INTEGRITY,
    AXE_TARBALL_URL,
    AXE_VERSION,
    CACHE_DIR,
    WANTED_MEMBERS,
    ChecksumError,
    cache_destination,
    download,
    read_verified_members,
    tarball_integrity,
    verify_axe_source,
    verify_tarball,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

AXE_MEMBER = "package/axe.min.js"
STAND_IN_AXE = b"window.axe = {run: function () {}};\n"
STAND_IN_MEMBERS = {
    AXE_MEMBER: STAND_IN_AXE,
    "package/LICENSE": b"Mozilla Public License 2.0\n",
    "package/LICENSE-3RD-PARTY.txt": b"third party notices\n",
}


def _tarball(members: dict[str, bytes], *, symlinks: tuple[str, ...] = ()) -> bytes:
    """A gzipped tar built in memory, optionally carrying symlink members."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, content in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
        for name in symlinks:
            info = tarfile.TarInfo(name)
            info.type = tarfile.SYMTYPE
            info.linkname = "/etc/passwd"
            archive.addfile(info)
    return buffer.getvalue()


def _pins_for(payload: bytes, axe: bytes) -> dict[str, str]:
    return {"integrity": tarball_integrity(payload), "sha256": hashlib.sha256(axe).hexdigest()}


class TestThePinIsWellFormed:
    def test_the_version_is_a_release_number(self):
        assert re.fullmatch(r"\d+\.\d+\.\d+", AXE_VERSION)

    def test_the_url_names_the_pinned_version(self):
        assert AXE_TARBALL_URL.startswith("https://registry.npmjs.org/axe-core/-/")
        assert AXE_TARBALL_URL.endswith(f"axe-core-{AXE_VERSION}.tgz")

    def test_the_file_checksum_is_a_sha256(self):
        assert re.fullmatch(r"[0-9a-f]{64}", AXE_SHA256)

    def test_the_tarball_integrity_is_the_registry_spelling(self):
        """`sha512-<base64 of 64 raw bytes>`, which is what npm publishes."""
        assert AXE_TARBALL_INTEGRITY.startswith("sha512-")
        digest = base64.b64decode(AXE_TARBALL_INTEGRITY.removeprefix("sha512-"), validate=True)
        assert len(digest) == 64

    def test_the_licence_files_are_fetched_too(self):
        """MPL-2.0 asks that the licence text travel with the code."""
        assert set(WANTED_MEMBERS) == {
            AXE_MEMBER,
            "package/LICENSE",
            "package/LICENSE-3RD-PARTY.txt",
        }


class TestTheCacheStaysOutOfGit:
    def test_the_cache_directory_is_ignored(self):
        """The whole point of the change: these bytes must never be committed again."""
        ignored = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").split()
        assert ".cache/" in ignored

    def test_the_cache_lives_at_the_repo_root(self):
        assert CACHE_DIR == REPO_ROOT / ".cache" / "axe-core"
        assert AXE_SOURCE == CACHE_DIR / "axe.min.js"


class TestTheFetchedFileIfPresent:
    """Asserted only when the cache happens to be populated; never downloaded here."""

    @pytest.fixture
    def cached_axe(self) -> bytes:
        if not AXE_SOURCE.is_file():
            pytest.skip("no fetched axe in .cache/; run `make axe-fetch`")
        return AXE_SOURCE.read_bytes()

    def test_it_matches_the_pin(self, cached_axe):
        digest = hashlib.sha256(cached_axe).hexdigest()
        assert digest == AXE_SHA256, (
            f".cache/axe-core/axe.min.js does not match its pin.\n"
            f"  expected {AXE_SHA256}\n  found    {digest}\n"
            "Delete it and run `make axe-fetch`."
        )

    def test_it_reports_the_pinned_version(self, cached_axe):
        """A pin that disagrees with the library's own version reads as a missing rule."""
        head = cached_axe[:4096].decode("utf-8", errors="ignore")
        found = re.search(r'axe\.version\s*=\s*"([\d.]+)"', head) or re.search(
            r'version:"([\d.]+)"', head
        )
        assert found, "could not find a version string in axe.min.js"
        assert found.group(1) == AXE_VERSION

    def test_the_licences_came_with_it(self, cached_axe):
        for name in ("LICENSE", "LICENSE-3RD-PARTY.txt"):
            assert (CACHE_DIR / name).is_file(), f".cache/axe-core/{name} is missing"


class TestVerificationCannotBeBypassed:
    """The test that replaces the committed checksum: corrupt bytes must be refused."""

    def test_the_matching_integrity_is_accepted(self):
        payload = b"a tarball, for these purposes"
        verify_tarball(payload, tarball_integrity(payload))

    @pytest.mark.parametrize(
        "corrupted",
        [
            b"a tarball, for these purposes!",
            b"a tarball, for these purpose",
            b"A tarball, for these purposes",
            b"",
        ],
        ids=["appended", "truncated", "flipped-bit", "empty"],
    )
    def test_any_other_bytes_are_refused(self, corrupted):
        expected = tarball_integrity(b"a tarball, for these purposes")
        with pytest.raises(ChecksumError):
            verify_tarball(corrupted, expected)

    def test_the_real_pin_refuses_a_substituted_tarball(self):
        with pytest.raises(ChecksumError) as failure:
            verify_tarball(_tarball(STAND_IN_MEMBERS))
        assert AXE_TARBALL_INTEGRITY in str(failure.value)

    def test_the_matching_sha256_is_accepted(self):
        verify_axe_source(STAND_IN_AXE, hashlib.sha256(STAND_IN_AXE).hexdigest())

    def test_the_real_pin_refuses_a_substituted_axe(self):
        with pytest.raises(ChecksumError) as failure:
            verify_axe_source(STAND_IN_AXE)
        assert AXE_SHA256 in str(failure.value)

    def test_a_correct_tarball_carrying_the_wrong_axe_is_refused(self):
        """The two checks are independent: a registry-valid tarball is not enough."""
        tampered = {**STAND_IN_MEMBERS, AXE_MEMBER: b"axe = {};"}
        payload = _tarball(tampered)
        with pytest.raises(ChecksumError):
            read_verified_members(payload, integrity=tarball_integrity(payload), sha256=AXE_SHA256)


class TestExtractionTakesOnlyWhatItNames:
    def test_it_returns_exactly_the_wanted_members(self):
        payload = _tarball({**STAND_IN_MEMBERS, "package/package.json": b"{}"})
        members = read_verified_members(payload, **_pins_for(payload, STAND_IN_AXE))
        assert set(members) == set(WANTED_MEMBERS)
        assert members[AXE_MEMBER] == STAND_IN_AXE

    def test_a_symlinked_member_is_refused(self):
        """A tarball may name a file that is really a link out of the tree."""
        payload = _tarball(
            {name: STAND_IN_MEMBERS[name] for name in STAND_IN_MEMBERS if name != AXE_MEMBER},
            symlinks=(AXE_MEMBER,),
        )
        with pytest.raises(ChecksumError, match="not a plain file"):
            read_verified_members(payload, **_pins_for(payload, STAND_IN_AXE))

    def test_a_missing_member_is_an_error_not_a_silent_skip(self):
        payload = _tarball({AXE_MEMBER: STAND_IN_AXE})
        with pytest.raises(KeyError):
            read_verified_members(payload, **_pins_for(payload, STAND_IN_AXE))

    @pytest.mark.parametrize(
        "name",
        ["package/../../evil.js", "/etc/passwd", "package/axe.min.js"],
    )
    def test_members_can_only_land_inside_the_cache(self, name):
        assert cache_destination(name).parent == CACHE_DIR


class TestAxeIsDevOnly:
    def test_nothing_we_publish_references_it(self):
        """The CSP is `script-src 'self'`; axe is injected over CDP and never shipped."""
        needles = ("axe.min.js", "axe-core", "axe.run")
        for directory in ("src/showup", "site"):
            root = REPO_ROOT / directory
            if not root.is_dir():
                continue  # site/ is build output and may not exist yet
            for path in root.rglob("*"):
                if path.is_file() and path.suffix in {".html", ".js", ".css", ".py"}:
                    text = path.read_text(encoding="utf-8", errors="ignore")
                    found = [needle for needle in needles if needle in text]
                    assert not found, (
                        f"{path.relative_to(REPO_ROOT)} references {found}; "
                        "axe is a development tool and must not be shipped"
                    )


@pytest.mark.upstream
class TestTheRegistryStillServesThePin:
    def test_the_published_tarball_is_the_one_we_pinned(self):
        """The check the committed file used to make for free, on a schedule instead."""
        members = read_verified_members(download())
        assert set(members) == set(WANTED_MEMBERS)
