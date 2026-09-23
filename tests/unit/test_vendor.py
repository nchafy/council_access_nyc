"""Pin the one committed third-party file.

`vendor/axe-core/axe.min.js` is 567 KB of minified JavaScript we did not write and
cannot review line by line. What makes that acceptable is that it cannot change
without this test failing, so a replacement arrives as a reviewable diff naming its
own checksum rather than as an unexplained blob.

`vendor/axe-core/PROVENANCE.md` records where it came from and how to update it.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
AXE = REPO_ROOT / "vendor" / "axe-core" / "axe.min.js"
PROVENANCE = REPO_ROOT / "vendor" / "axe-core" / "PROVENANCE.md"

#: Keep these three in step with PROVENANCE.md when bumping the pin.
AXE_VERSION = "4.13.0"
AXE_SHA256 = "c24f097bd2f451d4f933e8bc7d8d539f8672a2ebcb5cc9f9f3eec8ca9470a0c1"


class TestVendoredAxe:
    def test_the_file_is_present(self):
        assert AXE.is_file(), f"{AXE} is missing; see vendor/axe-core/PROVENANCE.md"

    def test_the_checksum_is_the_pinned_one(self):
        digest = hashlib.sha256(AXE.read_bytes()).hexdigest()
        assert digest == AXE_SHA256, (
            "vendor/axe-core/axe.min.js does not match its pin.\n"
            f"  expected {AXE_SHA256}\n  found    {digest}\n"
            "If the change is intended, update AXE_SHA256 here and PROVENANCE.md "
            "in the same commit, and expect new axe findings."
        )

    def test_the_file_reports_the_pinned_version(self):
        """Belt and braces: the checksum already fixes the bytes, but a mismatch
        between the pin and the library's own self-reported version is the failure
        that would otherwise be reported as a mysterious missing rule."""
        head = AXE.read_text(encoding="utf-8")[:4096]
        found = re.search(r'axe\.version\s*=\s*"([\d.]+)"', head) or re.search(
            r'version:"([\d.]+)"', head
        )
        assert found, "could not find a version string in axe.min.js"
        assert found.group(1) == AXE_VERSION

    def test_the_license_travels_with_it(self):
        """MPL-2.0 requires the licence text to be distributed with the code."""
        for name in ("LICENSE", "LICENSE-3RD-PARTY.txt"):
            assert (AXE.parent / name).is_file(), f"vendor/axe-core/{name} is missing"

    def test_provenance_records_the_same_pin(self):
        """A stale PROVENANCE.md is how a vendored file loses its paper trail."""
        text = PROVENANCE.read_text(encoding="utf-8")
        assert AXE_VERSION in text
        assert AXE_SHA256 in text


class TestAxeIsDevOnly:
    def test_no_page_references_it(self):
        """It must never reach a user. The CSP is `script-src 'self'` and axe is
        injected over the DevTools protocol, so nothing we publish should name it."""
        for directory in ("src/showup", "site"):
            root = REPO_ROOT / directory
            if not root.is_dir():
                continue  # site/ is build output and may not exist yet
            for path in root.rglob("*"):
                if path.is_file() and path.suffix in {".html", ".js", ".css", ".py"}:
                    assert "axe.min.js" not in path.read_text(encoding="utf-8", errors="ignore"), (
                        f"{path.relative_to(REPO_ROOT)} references axe.min.js; "
                        "axe is a development tool and must not be shipped"
                    )
