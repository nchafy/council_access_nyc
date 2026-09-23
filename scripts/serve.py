#!/usr/bin/env python3
"""Serve the built site locally with the real response headers.

`python -m http.server` sends no CSP, so developing against it would mean every
policy violation surfaces for the first time at deploy — which is exactly when it
gets waived under pressure. This server parses the same `_headers` file Cloudflare
Pages will read, so the policy is exercised in a browser from day one.

Stdlib only, no dependencies, matching the project's dependency posture.

    python3 scripts/serve.py [--root site] [--port 8000]
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

REPO_ROOT = Path(__file__).resolve().parent.parent


def parse_headers_file(path: Path) -> list[tuple[str, dict[str, str]]]:
    """Parse Cloudflare's `_headers` format into [(path_pattern, {header: value})].

    Format: a line at column 0 is a path pattern; indented `Name: value` lines
    below it apply to that pattern. `#` comments and blank lines are ignored.
    """
    rules: list[tuple[str, dict[str, str]]] = []
    if not path.exists():
        return rules

    current: dict[str, str] | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        if raw_line[0] not in " \t":
            current = {}
            rules.append((raw_line.strip(), current))
        elif current is not None and ":" in raw_line:
            name, _, value = raw_line.strip().partition(":")
            current[name.strip()] = value.strip()
    return rules


def matches(pattern: str, path: str) -> bool:
    """Support the only two forms we use: `/*` and an exact path."""
    if pattern == "/*":
        return True
    if pattern.endswith("/*"):
        return path.startswith(pattern[:-1])
    return path == pattern


class HeaderApplyingHandler(SimpleHTTPRequestHandler):
    """Static file handler that applies `_headers` and resolves clean URLs."""

    header_rules: list[tuple[str, dict[str, str]]] = []
    quiet: bool = False

    def end_headers(self) -> None:
        for pattern, headers in self.header_rules:
            if matches(pattern, self.path.split("?", 1)[0]):
                for name, value in headers.items():
                    self.send_header(name, value)
        # Local development must never be cached, or a rebuilt site shows stale.
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def send_head(self):
        """Serve `/district/35/` from `district/35/index.html`, and fall back to
        the built 404 page so the not-found path is exercised too."""
        result = super().send_head()
        if result is None and self.command in {"GET", "HEAD"}:
            return self._serve_404()
        return result

    def _serve_404(self):
        page = Path(self.directory) / "404.html"
        if not page.exists():
            return
        body = page.read_bytes()
        self.send_response(404)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command == "GET":
            self.wfile.write(body)
        return

    def log_message(self, fmt: str, *args: object) -> None:
        if not self.quiet:
            super().log_message(fmt, *args)


@contextmanager
def background_server(root: Path, headers: Path | None = None) -> Iterator[str]:
    """Serve `root` with the real headers for the life of the block; yield its base URL.

    The accessibility and performance gates all need the same thing: the built site,
    on a real port, behind the real `Content-Security-Policy`. Running them against a
    bare `SimpleHTTPRequestHandler` would measure a site that does not exist — a
    stylesheet blocked by a policy mistake changes both the colour-contrast result
    and the load time, and changes them in the flattering direction.

    The port is OS-assigned, so two gates can run at once without colliding. The
    handler's configuration is class-level, which is how `http.server` is meant to be
    parameterised but does mean two servers in *one* process would share it. No
    caller does that; this note is here so nobody starts.
    """
    rules = parse_headers_file(headers or REPO_ROOT / "_headers")
    if not rules:
        raise RuntimeError("no header rules found; refusing to serve a site without its CSP")
    HeaderApplyingHandler.header_rules = rules
    HeaderApplyingHandler.quiet = True
    handler = partial(HeaderApplyingHandler, directory=str(root))
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="site", help="directory to serve (default: site)")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--headers", default="_headers")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    root = (REPO_ROOT / args.root).resolve()
    if not root.is_dir():
        print(f"error: {root} does not exist — run `make build` first", file=sys.stderr)
        return 2

    rules = parse_headers_file(REPO_ROOT / args.headers)
    if not rules:
        print(f"warning: no header rules found in {args.headers}", file=sys.stderr)

    HeaderApplyingHandler.header_rules = rules
    HeaderApplyingHandler.quiet = args.quiet
    handler = partial(HeaderApplyingHandler, directory=str(root))

    with ThreadingHTTPServer(("127.0.0.1", args.port), handler) as httpd:
        applied = sum(len(headers) for _, headers in rules)
        print(f"serving {root} on http://127.0.0.1:{args.port}  ({applied} headers applied)")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
