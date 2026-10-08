"""Serial monitor core: line splitting, colouring and a monitor that survives board resets.

`ReconnectingMonitor.step()` does one unit of work (connect, read, or wait) so the CLI and
the installer window can each drive it from their own loop/thread, and tests can drive it
deterministically.
"""

from __future__ import annotations

import codecs
import contextlib
import re
import time
from enum import Enum
from pathlib import Path
from typing import IO, Any, Callable, Optional

import serial

from deskbuddy import serial_io
from deskbuddy.errors import DeskBuddyError, PortBusyError

RECONNECT_DELAY = 0.5
FLUSH_AFTER_IDLE_READS = 5
WAITING = "waiting for board..."
DISCONNECTED = "board disconnected - waiting for board..."

_ANSI = {"red": "\x1b[31m", "green": "\x1b[32m", "yellow": "\x1b[33m", "blue": "\x1b[34m"}
_RESET = "\x1b[0m"
_ERROR_RE = re.compile(r"error|CRASH|assert|FAILED|panic|Guru Meditation|BROWNOUT|abort\(\)", re.IGNORECASE)


def line_colour(line: str) -> Optional[str]:
    """Colour name for a firmware log line: errors red, [BLE] blue, [WiFi] green, [OLED] yellow."""
    if _ERROR_RE.search(line):
        return "red"
    if "[BLE]" in line:
        return "blue"
    if "[WiFi]" in line:
        return "green"
    if "[OLED]" in line:
        return "yellow"
    return None


def colourise(line: str, enabled: bool) -> str:
    colour = line_colour(line) if enabled else None
    return f"{_ANSI[colour]}{line}{_RESET}" if colour else line


class LineBuffer:
    """Turns a byte stream into text lines (UTF-8, CRLF/LF), keeping partial lines."""

    def __init__(self, max_len: int = 4096) -> None:
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._partial = ""
        self._max_len = max_len

    def feed(self, data: bytes) -> list[str]:
        text = self._partial + self._decoder.decode(data)
        *lines, self._partial = text.split("\n")
        if len(self._partial) > self._max_len:
            lines.append(self._partial)
            self._partial = ""
        return [line.rstrip("\r") for line in lines]

    def flush(self) -> list[str]:
        rest = (self._partial + self._decoder.decode(b"", final=True)).rstrip("\r")
        self._partial = ""
        return [rest] if rest else []


class State(Enum):
    WAITING = "waiting"
    CONNECTED = "connected"
    PAUSED = "paused"
    CLOSED = "closed"


class ReconnectingMonitor:
    """Reads lines from the board and reconnects automatically after resets/unplugging."""

    def __init__(
        self,
        resolve_port: Callable[[], Optional[str]],
        on_line: Callable[[str], None],
        on_status: Callable[[str], None],
        opener: Optional[Callable[[str], Any]] = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._resolve_port = resolve_port
        self._opener = opener or serial_io.open_serial
        self._on_line = on_line
        self._on_status = on_status
        self._sleep = sleep
        self._ser: Any = None
        self._buffer = LineBuffer()
        self._ever_connected = False
        self._announced_wait = False
        self._idle_reads = 0
        self.state = State.WAITING
        self.port: Optional[str] = None

    def step(self) -> State:
        if self.state in (State.PAUSED, State.CLOSED):
            self._sleep(RECONNECT_DELAY / 5)
            return self.state
        if self.state is State.CONNECTED:
            self._read_once()
        else:
            self._try_connect()
        return self.state

    def _try_connect(self) -> None:
        port = self._resolve_port()
        if port is None:
            self._wait()
            return
        try:
            self._ser = self._opener(port)
        except PortBusyError:
            if not self._ever_connected:
                raise  # first open: somebody else really holds the port
            self._wait()
            return
        except (DeskBuddyError, serial.SerialException, OSError):
            self._wait()
            return
        self.port = port
        self.state = State.CONNECTED
        self._ever_connected = True
        self._announced_wait = False
        self._buffer = LineBuffer()
        self._on_status(f"connected to {port}")

    def _wait(self) -> None:
        self.state = State.WAITING
        if not self._announced_wait:
            self._on_status(WAITING)
            self._announced_wait = True
        self._sleep(RECONNECT_DELAY)

    def _read_once(self) -> None:
        try:
            data = self._ser.read(max(1, self._ser.in_waiting))
        except (serial.SerialException, OSError):
            self._drop(DISCONNECTED)
            return
        if data:
            self._idle_reads = 0
            lines = self._buffer.feed(data)
        else:
            # flush a partial line only after ~0.5 s of silence, not on every 100 ms read gap
            self._idle_reads += 1
            lines = self._buffer.flush() if self._idle_reads == FLUSH_AFTER_IDLE_READS else []
        for line in lines:
            self._on_line(line)

    def _drop(self, message: str) -> None:
        for line in self._buffer.flush():
            self._on_line(line)
        self._close_port()
        self.state = State.WAITING
        self._announced_wait = True
        self._on_status(message)

    def _close_port(self) -> None:
        if self._ser is not None:
            with contextlib.suppress(serial.SerialException, OSError):
                self._ser.close()
            self._ser = None

    def send(self, text: str) -> bool:
        if self.state is not State.CONNECTED:
            self._on_status("not connected - command not sent")
            return False
        try:
            serial_io.send_line(self._ser, text)
        except (serial.SerialException, OSError):
            self._drop(DISCONNECTED)
            return False
        return True

    def pause(self) -> None:
        """Release the port (e.g. while flashing)."""
        self._close_port()
        self.state = State.PAUSED

    def resume(self) -> None:
        if self.state is State.PAUSED:
            self.state = State.WAITING
            self._announced_wait = False

    def close(self) -> None:
        self._close_port()
        self.state = State.CLOSED


class LogWriter:
    """Optional append-only log file for monitor output (UTF-8, one line per row)."""

    def __init__(self, path: Optional[Path]) -> None:
        self._path = path
        self._handle: Optional[IO[str]] = None

    def __enter__(self) -> LogWriter:
        if self._path is not None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._handle = self._path.open("a", encoding="utf-8", newline="\n")
        return self

    def write(self, line: str) -> None:
        if self._handle is not None:
            self._handle.write(line + "\n")
            self._handle.flush()

    def __exit__(self, *exc: object) -> None:
        if self._handle is not None:
            self._handle.close()
            self._handle = None
