#!/usr/bin/env python3
"""Drive a real Chrome over the DevTools Protocol, using nothing but the stdlib.

A rendered accessibility tree, real `Tab` keypresses, and the browser's own clock
under the browser's own throttling cannot be obtained from outside a browser. CDP is
JSON over a loopback WebSocket, so the useful subset is small enough to own outright
instead of depending on Playwright. Used as a library by `axe_check`, `a11y_audit`,
`console_check` and `perf`. Run directly for a smoke test:

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

#: Shared by every browser-driving script here, so there is one list to update.
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
    continuation frames reassembled and pings answered. No TLS and no extensions,
    because Chrome's debugging endpoint is plain `ws://` on 127.0.0.1.
    """

    OPCODE_TEXT = 0x1
    OPCODE_CLOSE = 0x8
    OPCODE_PING = 0x9
    OPCODE_PONG = 0xA

    #: Generous — trees run to megabytes; it turns a corrupt length into an error, not an alloc.
    MAX_FRAME_BYTES = 256 * 1024 * 1024

    def __init__(self, url: str, timeout: float = 30.0) -> None:
        url_parts = urlsplit(url)
        if url_parts.scheme != "ws":
            raise CDPError(f"expected a ws:// url, got {url!r}")
        host, port = url_parts.hostname or "127.0.0.1", url_parts.port or 80
        self._socket = socket.create_connection((host, port), timeout=timeout)
        self._socket.settimeout(timeout)
        self._buffer = b""

        key = base64.b64encode(secrets.token_bytes(16)).decode("ascii")
        target = url_parts.path or "/"
        if url_parts.query:
            target = f"{target}?{url_parts.query}"
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
        status_line = self._read_until(b"\r\n\r\n").split(b"\r\n", 1)[0]
        if b" 101 " not in status_line:
            raise CDPError(f"websocket upgrade refused: {status_line!r}")

    def _read_until(self, marker: bytes) -> bytes:
        while marker not in self._buffer:
            chunk = self._socket.recv(65536)
            if not chunk:
                raise CDPError("connection closed during the handshake")
            self._buffer += chunk
        before_marker, _, after_marker = self._buffer.partition(marker)
        self._buffer = after_marker
        return before_marker

    def _read_exactly(self, count: int) -> bytes:
        while len(self._buffer) < count:
            chunk = self._socket.recv(max(65536, count - len(self._buffer)))
            if not chunk:
                raise CDPError("connection closed mid-frame")
            self._buffer += chunk
        requested, self._buffer = self._buffer[:count], self._buffer[count:]
        return requested

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
        # Big-int XOR keeps the ~600 KB axe.min.js masking loop in C, not in Python.
        repeated_mask = mask * (length // 4) + mask[: length % 4]
        masked_payload = (
            int.from_bytes(payload, "big") ^ int.from_bytes(repeated_mask, "big")
        ).to_bytes(length, "big")
        self._socket.sendall(bytes(header) + masked_payload)

    def send_text(self, text: str) -> None:
        self._send_frame(self.OPCODE_TEXT, text.encode("utf-8"))

    def recv_text(self) -> str:
        """The next complete text message, reassembling continuation frames."""
        chunks: list[bytes] = []
        while True:
            flags_byte, length_byte = self._read_exactly(2)
            is_final_frame = bool(flags_byte & 0x80)
            opcode = flags_byte & 0x0F
            if length_byte & 0x80:
                raise CDPError("a server frame must not be masked")
            length = length_byte & 0x7F
            if length == 126:
                length = struct.unpack("!H", self._read_exactly(2))[0]
            elif length == 127:
                length = struct.unpack("!Q", self._read_exactly(8))[0]
            if length > self.MAX_FRAME_BYTES:
                raise CDPError(f"refusing a {length}-byte frame")
            payload = self._read_exactly(length)

            if opcode == self.OPCODE_CLOSE:
                raise CDPError("Chrome closed the connection")
            if opcode == self.OPCODE_PING:
                # Unanswered pings make Chrome eventually hang up.
                self._send_frame(self.OPCODE_PONG, payload)
                continue
            if opcode == self.OPCODE_PONG:
                continue
            chunks.append(payload)
            if is_final_frame:
                return b"".join(chunks).decode("utf-8")

    def close(self) -> None:
        """Close the socket, tolerating a Chrome that has already gone."""
        with contextlib.suppress(OSError):
            self._send_frame(self.OPCODE_CLOSE, b"")
        self._socket.close()


class Session:
    """A CDP session against one page target.

    Every `call` is synchronous, buffering events that arrive before the matching
    response so a later `wait_for` can still find them. Because there is never more
    than one request in flight, no reader thread or future registry is needed.
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

        For callers that want everything that happened rather than the first match.
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

        A page exception is raised, not returned as None, so a check that could not
        run cannot report clean.
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

    #: Key name -> (virtual key code, the text the key inserts, if it inserts any).
    KEYS: ClassVar[dict[str, tuple[int, str]]] = {
        "Tab": (9, ""),
        "Enter": (13, "\r"),
        "Escape": (27, ""),
        "Space": (32, " "),
    }

    @staticmethod
    def _event_type_for_key(inserted_text: str) -> str:
        """`keyDown` for a key that inserts text, `rawKeyDown` for one that does not.

        A text-less `keyDown` leaves Chrome waiting for a `char` event and Tab never
        moves focus; Enter as `rawKeyDown` skips Blink's implicit form submission.
        """
        return "keyDown" if inserted_text else "rawKeyDown"

    def press(self, key: str, *, shift: bool = False) -> None:
        """Dispatch a real keypress."""
        if key not in self.KEYS:
            raise CDPError(f"no virtual key code recorded for {key!r}")
        virtual_key_code, inserted_text = self.KEYS[key]
        for event_type in (self._event_type_for_key(inserted_text), "keyUp"):
            params = {
                "type": event_type,
                "key": key,
                "code": key,
                "windowsVirtualKeyCode": virtual_key_code,
                "nativeVirtualKeyCode": virtual_key_code,
                "modifiers": 8 if shift else 0,
            }
            if inserted_text and event_type == "keyDown":
                params["text"] = inserted_text
                params["unmodifiedText"] = inserted_text
            self.call("Input.dispatchKeyEvent", **params)

    def type_text(self, text: str) -> None:
        """Put text into the focused field in one `Input.insertText`.

        No code path listens for keystrokes: the address box is submit-only.
        """
        self.call("Input.insertText", text=text)

    def throttle(self, *, download_bps: float, upload_bps: float, latency_ms: float, cpu: float):
        """Shape the network and CPU to the reference profile.

        Both halves matter: an unthrottled developer CPU parses and styles a document
        several times faster than the mid-tier Android the budget is written for.
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
    """A headless Chrome on a throwaway profile, as a context manager.

    The profile directory is temporary and removed on exit, which is what makes
    `clear_cache` believable and keeps a run out of the developer's own Chrome state.
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
                # Port 0 asks the OS for a free one; a fixed port collides across runs.
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
        """Read the debugging port Chrome writes to `DevToolsActivePort` once listening."""
        assert self._profile is not None
        port_file = self._profile / "DevToolsActivePort"
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            if self._process is not None and self._process.poll() is not None:
                raise CDPError(f"Chrome exited with {self._process.returncode} before listening")
            if port_file.exists():
                lines = port_file.read_text(encoding="utf-8").splitlines()
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
