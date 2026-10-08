#!/usr/bin/env python3
"""Screenshot the built site with headless Chrome.

A layout regression, an unstyled page, or an empty region is invisible to an HTTP
assertion and obvious in an image. Rendering through a real browser also proves the CSP
does not block our own stylesheet or script. Uses the Chrome already on the machine,
because `docs/dependencies.md` refuses a dependency that installs its own browser.

    python3 scripts/shot.py [--port 8098] [--out screenshots]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from cdp import find_chrome

REPO_ROOT = Path(__file__).resolve().parent.parent

#: 500 and not a true phone width, because macOS clamps a Chrome window below ~500 px and
#: a narrower request silently crops (docs/OBSERVATIONS.md, 2026-09-23). Still under the
#: 34rem breakpoint, so it exercises the single-column path; the gap is recorded in
#: docs/accessibility-pass.md.
VIEWPORTS = {"narrow": (500, 1400), "desktop": (1280, 1600)}

PAGES = {
    "index": "/",
    "district-35": "/district/35/",
    # The deliberate degraded-state page (CLAUDE.md).
    "district-3": "/district/3/",
    "board-302": "/board/302/",
    "references": "/references/",
}


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
