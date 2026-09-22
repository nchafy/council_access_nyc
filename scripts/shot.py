#!/usr/bin/env python3
"""Screenshot the built site with headless Chrome.

The point is not pretty pictures: it is that a layout regression, an unstyled
page (CSS blocked by a CSP mistake), or an empty region is invisible to an HTTP
assertion and obvious in an image. Rendering through a real browser also proves
the CSP does not block our own stylesheet or script — the most likely
self-inflicted CSP failure.

Uses the Chrome already on the machine rather than adding Playwright, keeping the
dependency count at zero.

    python3 scripts/shot.py [--port 8098] [--out screenshots]
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    shutil.which("google-chrome") or "",
    shutil.which("chromium") or "",
]

#: Mobile-first, so the narrow shot is the primary one.
#
#: The narrow width is 500, not a true phone width like 390, because macOS clamps a
#: Chrome window's minimum width somewhere below 500: asking for 390 produced a
#: 390-pixel-wide *image* of a ~704-pixel-wide *layout*, i.e. a silently cropped
#: screenshot that looked like a CSS overflow bug. 500 is the narrowest width the
#: layout is actually honoured at, and it still sits below the 34rem (544px)
#: breakpoint, so it exercises the single-column mobile path. Verifying true
#: 390px layout needs CDP emulation (Playwright), which Phase 1 does not carry.
VIEWPORTS = {"narrow": (500, 1400), "desktop": (1280, 1600)}

PAGES = {"index": "/", "district-35": "/district/35/", "district-3": "/district/3/"}


def find_chrome() -> str | None:
    return next((path for path in CHROME_CANDIDATES if path and Path(path).exists()), None)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8098)
    parser.add_argument("--root", default="site")
    parser.add_argument("--out", default="screenshots")
    args = parser.parse_args(argv)

    chrome = find_chrome()
    if not chrome:
        print("no Chrome found; skipping screenshots (not a failure)", file=sys.stderr)
        return 0

    out_dir = REPO_ROOT / args.out
    out_dir.mkdir(exist_ok=True)

    base = f"http://127.0.0.1:{args.port}"
    server = subprocess.Popen(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "serve.py"),
            "--port",
            str(args.port),
            "--root",
            args.root,
            "--quiet",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    written: list[Path] = []
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen(base + "/", timeout=5)
                break
            except OSError:
                time.sleep(0.1)
        else:
            print("server did not come up", file=sys.stderr)
            return 1

        for name, path in PAGES.items():
            for viewport, (width, height) in VIEWPORTS.items():
                target = out_dir / f"{name}-{viewport}.png"
                subprocess.run(
                    [
                        chrome,
                        "--headless=new",
                        "--disable-gpu",
                        "--hide-scrollbars",
                        "--no-first-run",
                        "--no-default-browser-check",
                        f"--window-size={width},{height}",
                        f"--screenshot={target}",
                        base + path,
                    ],
                    check=False,
                    capture_output=True,
                    timeout=60,
                )
                if target.exists() and target.stat().st_size > 2000:
                    written.append(target)
                    print(f"  {target.relative_to(REPO_ROOT)}  {target.stat().st_size // 1024} KB")
                else:
                    print(f"  FAILED {target.name}", file=sys.stderr)
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()

    expected = len(PAGES) * len(VIEWPORTS)
    print(f"{len(written)}/{expected} screenshots written to {args.out}/")
    return 0 if len(written) == expected else 1


if __name__ == "__main__":
    raise SystemExit(main())
