#!/usr/bin/env python3
"""Drive a real Chrome over the DevTools Protocol, with nothing but the stdlib.

Why this exists. Three of the four things M5 has to prove cannot be proved from
outside a browser:

- **axe** needs the rendered accessibility tree, not the HTML we emitted.
- **The keyboard pass** needs real `Tab` keypresses moving real focus. Reading
  `tabindex` out of the markup proves nothing about what a browser does with it.
- **The 3 s throttled-3G budget** needs the browser's own clock while the browser's
  own network stack is shaped. A number computed as bytes ÷ bandwidth is a model,
  and R40 asks for a measurement.

Why not Playwright or Selenium. `pyproject.toml` explains the dependency posture:
every dependency is attack surface, and this project's primary threat is untrusted
upstream content. Playwright would add a package that downloads and executes its
own browser binaries, for a build that today needs no secrets and pulls nothing at
run time. CDP is a JSON protocol over a WebSocket on loopback, and the useful
subset is small enough to own outright — which is what this file is.

The existing `shot.py` and `tests/browser/test_address_box.py` drive Chrome through
one-shot command lines instead, because a screenshot and a
report-over-HTTP harness need nothing better. They keep doing that; this is for the
cases where we have to ask the page a question and read the answer back.

Used as a library by `scripts/axe_check.py`, `scripts/a11y_keyboard.py` and
`scripts/perf.py`. Run directly for a smoke test:

    python3 scripts/cdp.py https://example.com
"""

from __future__ import annotations

import base64
import contextlib
import json
import secrets
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from types import TracebackType
from typing import Any, ClassVar
from urllib.parse import urlsplit

#: Where Chrome lives. Shared by every browser-driving script in this repo so
#: there is one list to update, not three that drift.
CHROME_CANDIDATES = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    shutil.which("google-chrome") or "",
    shutil.which("google-chrome-stable") or "",
    shutil.which("chromium") or "",
    shutil.which("chromium-browser") or "",
)


class CDPError(RuntimeError):
    """Chrome, or the channel to it, did something we cannot continue from."""


def find_chrome() -> str | None:
    """The first Chrome or Chromium on this machine, or None."""
    return next((path for path in CHROME_CANDIDATES if path and Path(path).exists()), None)


class WebSocket:
    """The smallest RFC 6455 client that can carry CDP.

    Deliberately partial: a text channel over an unencrypted loopback socket, with
    continuation frames reassembled and pings answered. No TLS, no extensions, no
    permessage-deflate — Chrome's debugging endpoint is plain `ws://` on 127.0.0.1,
    and negotiating nothing means there is nothing to negotiate wrong.
    """

    #: A full accessibility tree for the index page is a few megabytes, so the
    #: cap has to be generous. It exists to turn a corrupt length field into an
    #: error instead of an allocation.
    MAX_FRAME_BYTES = 256 * 1024 * 1024

    def __init__(self, url: str, timeout: float = 30.0) -> None:
        parts = urlsplit(url)
        if parts.scheme != "ws":
            raise CDPError(f"expected a ws:// url, got {url!r}")
        host, port = parts.hostname or "127.0.0.1", parts.port or 80
        self._socket = socket.create_connection((host, port), timeout=timeout)
        self._socket.settimeout(timeout)
        self._buffer = b""

        key = base64.b64encode(secrets.token_bytes(16)).decode("ascii")
        target = parts.path or "/"
        if parts.query:
            target = f"{target}?{parts.query}"
        self._socket.sendall(
            "\r\n".join(
                [
                    f"GET {target} HTTP/1.1",
                    f"Host: {host}:{port}",
                    "Upgrade: websocket",
                    "Connection: Upgrade",
                    f"Sec-WebSocket-Key: {key}",
                    "Sec-WebSocket-Version: 13",
                    "",
                    "",
                ]
            ).encode("ascii")
        )
        status = self._read_until(b"\r\n\r\n").split(b"\r\n", 1)[0]
        if b" 101 " not in status:
            raise CDPError(f"websocket upgrade refused: {status!r}")

    def _read_until(self, marker: bytes) -> bytes:
        while marker not in self._buffer:
            chunk = self._socket.recv(65536)
            if not chunk:
                raise CDPError("connection closed during the handshake")
            self._buffer += chunk
        head, _, rest = self._buffer.partition(marker)
        self._buffer = rest
        return head

    def _read_exactly(self, count: int) -> bytes:
        while len(self._buffer) < count:
            chunk = self._socket.recv(max(65536, count - len(self._buffer)))
            if not chunk:
                raise CDPError("connection closed mid-frame")
            self._buffer += chunk
        head, self._buffer = self._buffer[:count], self._buffer[count:]
        return head

    def _send_frame(self, opcode: int, payload: bytes) -> None:
        header = bytearray([0x80 | opcode])
        length = len(payload)
        # The mask bit is mandatory for a client, whatever the length.
        if length < 126:
            header.append(0x80 | length)
        elif length < 65536:
            header.append(0x80 | 126)
            header += struct.pack("!H", length)
        else:
            header.append(0x80 | 127)
            header += struct.pack("!Q", length)
        mask = secrets.token_bytes(4)
        header += mask
        # axe.min.js goes over this channel, so the masking loop runs over ~600 KB.
        # int.from_bytes/to_bytes does it in C rather than a Python-level loop.
        masked = (
            int.from_bytes(payload, "big")
            ^ int.from_bytes(mask * (length // 4) + mask[: length % 4], "big")
        ).to_bytes(length, "big")
        self._socket.sendall(bytes(header) + masked)

    def send_text(self, text: str) -> None:
        self._send_frame(0x1, text.encode("utf-8"))

    def recv_text(self) -> str:
        """The next complete text message, reassembling continuation frames."""
        chunks: list[bytes] = []
        while True:
            first, second = self._read_exactly(2)
            final, opcode = bool(first & 0x80), first & 0x0F
            if second & 0x80:
                raise CDPError("a server frame must not be masked")
            length = second & 0x7F
            if length == 126:
                length = struct.unpack("!H", self._read_exactly(2))[0]
            elif length == 127:
                length = struct.unpack("!Q", self._read_exactly(8))[0]
            if length > self.MAX_FRAME_BYTES:
                raise CDPError(f"refusing a {length}-byte frame")
            payload = self._read_exactly(length)

            if opcode == 0x8:
                raise CDPError("Chrome closed the connection")
            if opcode == 0x9:  # ping — answer it or Chrome eventually hangs up
                self._send_frame(0xA, payload)
                continue
            if opcode == 0xA:  # unsolicited pong
                continue
            chunks.append(payload)
            if final:
                return b"".join(chunks).decode("utf-8")

    def close(self) -> None:
        # Best-effort by design: if Chrome has already gone, there is nothing to
        # say goodbye to and the socket still needs closing.
        with contextlib.suppress(OSError):
            self._send_frame(0x8, b"")
        self._socket.close()


class Session:
    """A CDP session against one page target.

    Every `call` is synchronous: it writes a request and reads until the matching
    id comes back, buffering any events that arrive in between so a later
    `wait_for` can still find them. That ordering is the whole reason this stays
    simple — there is never more than one request in flight, so there is no need
    for a reader thread or a future registry.
    """

    def __init__(self, websocket: WebSocket) -> None:
        self._websocket = websocket
        self._last_id = 0
        self._events: list[dict[str, Any]] = []

    def call(self, method: str, **params: Any) -> dict[str, Any]:
        self._last_id += 1
        request_id = self._last_id
        self._websocket.send_text(
            json.dumps({"id": request_id, "method": method, "params": params})
        )
        while True:
            message = json.loads(self._websocket.recv_text())
            if message.get("id") == request_id:
                if "error" in message:
                    raise CDPError(f"{method}: {message['error'].get('message')}")
                return message.get("result") or {}
            if "method" in message:
                self._events.append(message)

    def drain_events(self) -> None:
        """Forget buffered events, so a `wait_for` cannot match a stale one."""
        self._events.clear()

    def consume_events(self) -> list[dict[str, Any]]:
        """Take every buffered event, leaving the buffer empty.

        For callers that want the events themselves rather than to wait for one —
        console complaints, network requests — where the interesting thing is
        everything that happened, not the first match.
        """
        events, self._events = self._events, []
        return events

    def wait_for(self, method: str, timeout: float = 30.0) -> dict[str, Any]:
        for index, message in enumerate(self._events):
            if message["method"] == method:
                return self._events.pop(index).get("params") or {}
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            message = json.loads(self._websocket.recv_text())
            if message.get("method") == method:
                return message.get("params") or {}
            if "method" in message:
                self._events.append(message)
        raise CDPError(f"timed out after {timeout}s waiting for {method}")

    # --- the handful of domain calls every caller needs ---------------------

    def evaluate(self, expression: str, *, await_promise: bool = False) -> Any:
        """Run JavaScript in the page and return the value.

        A page exception is raised here rather than returned, because every caller
        treats "the check could not run" as a failure. Silently returning None
        would let a broken check report clean.
        """
        result = self.call(
            "Runtime.evaluate",
            expression=expression,
            returnByValue=True,
            awaitPromise=await_promise,
        )
        if "exceptionDetails" in result:
            details = result["exceptionDetails"]
            description = (details.get("exception") or {}).get("description")
            raise CDPError(f"page script failed: {description or details.get('text')}")
        return (result.get("result") or {}).get("value")

    def navigate(self, url: str, timeout: float = 60.0) -> None:
        self.call("Page.enable")
        self.drain_events()
        self.call("Page.navigate", url=url)
        self.wait_for("Page.loadEventFired", timeout=timeout)

    #: Virtual key code, and the text the key inserts if it inserts any.
    #:
    #: The text matters more than it looks. A key with no text is dispatched as
    #: `rawKeyDown`, because a `keyDown` for a non-text key makes Chrome wait for a
    #: following `char` event and Tab then never moves focus. But Enter *does* carry
    #: text, and dispatching it as `rawKeyDown` means Blink never runs the implicit
    #: form submission — the address box took the typed text and then sat there,
    #: which read exactly like a broken form rather than a broken test.
    KEYS: ClassVar[dict[str, tuple[int, str]]] = {
        "Tab": (9, ""),
        "Enter": (13, "\r"),
        "Escape": (27, ""),
        "Space": (32, " "),
    }

    def press(self, key: str, *, shift: bool = False) -> None:
        """Dispatch a real keypress."""
        if key not in self.KEYS:
            raise CDPError(f"no virtual key code recorded for {key!r}")
        code, text = self.KEYS[key]
        for event_type in ("keyDown" if text else "rawKeyDown", "keyUp"):
            params = {
                "type": event_type,
                "key": key,
                "code": key,
                "windowsVirtualKeyCode": code,
                "nativeVirtualKeyCode": code,
                "modifiers": 8 if shift else 0,
            }
            if text and event_type == "keyDown":
                params["text"] = text
                params["unmodifiedText"] = text
            self.call("Input.dispatchKeyEvent", **params)

    def type_text(self, text: str) -> None:
        """Put text into the focused field.

        `Input.insertText`, not per-character key events: the address box is
        submit-only by the privacy decision in §4.4, so no code path listens for
        keystrokes and simulating them would only be slower.
        """
        self.call("Input.insertText", text=text)

    def throttle(self, *, download_bps: float, upload_bps: float, latency_ms: float, cpu: float):
        """Shape the network and CPU to the reference profile.

        Both halves matter: R40's budget is a *cold load on a mid-tier Android*,
        and an unthrottled CPU on a developer laptop parses and styles a document
        several times faster than the device the budget is written for.
        """
        self.call("Network.enable")
        self.call(
            "Network.emulateNetworkConditions",
            offline=False,
            latency=latency_ms,
            downloadThroughput=download_bps,
            uploadThroughput=upload_bps,
        )
        self.call("Emulation.setCPUThrottlingRate", rate=cpu)

    def clear_cache(self) -> None:
        """Make the next load genuinely cold."""
        self.call("Network.enable")
        self.call("Network.clearBrowserCache")
        self.call("Network.setCacheDisabled", cacheDisabled=True)


class Browser:
    """A headless Chrome, launched on a throwaway profile, as a context manager.

    The profile directory is temporary and removed on exit, which is what makes
    `clear_cache` believable and keeps a test run from inheriting the developer's
    own Chrome state — or writing to it.
    """

    def __init__(self, *, extra_args: tuple[str, ...] = (), timeout: float = 30.0) -> None:
        self.timeout = timeout
        self._extra_args = extra_args
        self._process: subprocess.Popen[bytes] | None = None
        self._profile: Path | None = None
        self._sockets: list[WebSocket] = []
        self.port = 0

    def __enter__(self) -> Browser:
        chrome = find_chrome()
        if not chrome:
            raise CDPError("no Chrome or Chromium found")
        self._profile = Path(tempfile.mkdtemp(prefix="showup-chrome-"))
        self._process = subprocess.Popen(
            [
                chrome,
                "--headless=new",
                # Port 0 asks the OS for a free one and Chrome writes it to
                # DevToolsActivePort. Hard-coding a port makes parallel runs
                # collide, which fails as a mysterious timeout.
                "--remote-debugging-port=0",
                f"--user-data-dir={self._profile}",
                "--disable-gpu",
                "--no-first-run",
                "--no-default-browser-check",
                "--hide-scrollbars",
                # Small /dev/shm on CI runners makes Chrome crash on navigation.
                "--disable-dev-shm-usage",
                *self._extra_args,
                "about:blank",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.port = self._await_port()
        return self

    def _await_port(self) -> int:
        assert self._profile is not None
        marker = self._profile / "DevToolsActivePort"
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            if self._process is not None and self._process.poll() is not None:
                raise CDPError(f"Chrome exited with {self._process.returncode} before listening")
            if marker.exists():
                lines = marker.read_text(encoding="utf-8").splitlines()
                if lines and lines[0].strip().isdigit():
                    return int(lines[0].strip())
            time.sleep(0.05)
        raise CDPError("Chrome never reported a debugging port")

    def page(self) -> Session:
        """A session against Chrome's initial `about:blank` page target."""
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{self.port}/json/list", timeout=self.timeout
                ) as response:
                    targets = json.loads(response.read())
            except (urllib.error.URLError, OSError):
                time.sleep(0.05)
                continue
            for target in targets:
                if target.get("type") == "page" and target.get("webSocketDebuggerUrl"):
                    websocket = WebSocket(target["webSocketDebuggerUrl"], timeout=self.timeout)
                    self._sockets.append(websocket)
                    return Session(websocket)
            time.sleep(0.05)
        raise CDPError("Chrome never offered a page target")

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        for websocket in self._sockets:
            websocket.close()
        if self._process is not None:
            self._process.terminate()
            try:
                self._process.wait(timeout=10)
            except subprocess.TimeoutExpired:  # pragma: no cover - Chrome ignoring SIGTERM
                self._process.kill()
        if self._profile is not None:
            shutil.rmtree(self._profile, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - smoke test only
    """Load a URL and print its title, to prove the channel works end to end."""
    url = (argv or sys.argv[1:] or ["about:blank"])[0]
    with Browser() as browser:
        page = browser.page()
        page.navigate(url)
        print(page.evaluate("document.title"))
    return 0


if __name__ == "__main__":  # pragma: no cover - entry point
    raise SystemExit(main())
