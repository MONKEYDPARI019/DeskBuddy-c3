"""Low-level serial helpers shared by the CLI and the installer window.

The ESP32-C3 uses its native USB-Serial/JTAG port. Toggling DTR/RTS on open resets
(or boot-loops) the chip, so every port is opened with both lines OFF. Commands end
with LF. After a reset the port disappears and re-enumerates, so callers wait for it.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Optional

import serial

from deskbuddy import ports as ports_mod
from deskbuddy.errors import NoBoardError, NoReplyError, port_busy

BAUD = 115200
READ_TIMEOUT = 0.1
POLL_INTERVAL = 0.25
IDLE_SECONDS = 0.8

Clock = Callable[[], float]
Sleeper = Callable[[float], None]
PortFactory = Callable[[str], Any]
Opener = Callable[[str], Any]

_BUSY_MARKERS = (
    "access is denied",
    "permissionerror",
    "resource busy",
    "device or resource busy",
    "could not exclusively lock",
    "resource temporarily unavailable",
)
_MISSING_MARKERS = (
    "filenotfounderror",
    "cannot find the file",
    "no such file or directory",
    "does not exist",
)


def _default_factory(port: str) -> Any:
    return serial.serial_for_url(port, do_not_open=True)


def open_serial(
    port: str, baud: int = BAUD, timeout: float = READ_TIMEOUT, factory: Optional[PortFactory] = None
) -> Any:
    """Open `port` with DTR and RTS off (lesson: toggling them resets the C3)."""
    ser = (factory or _default_factory)(port)
    if "://" not in port:
        ser.port = port
    ser.baudrate = baud
    ser.timeout = timeout
    ser.dtr = False
    ser.rts = False
    try:
        ser.open()
    except (serial.SerialException, OSError) as exc:
        raise describe_open_error(port, exc) from exc
    return ser


def describe_open_error(port: str, exc: BaseException) -> Exception:
    text = str(exc).lower()
    if any(marker in text for marker in _BUSY_MARKERS):
        return port_busy(port)
    if any(marker in text for marker in _MISSING_MARKERS):
        return NoBoardError(f"{port} not found", "Check the USB cable, then run 'deskbuddy ports' to see the boards.")
    return NoBoardError(f"Cannot open {port}: {exc}", "Unplug and re-plug the board, then try again.")


def send_line(ser: Any, text: str) -> None:
    """Send one command terminated by LF (the firmware expects '\\n' and does not echo)."""
    ser.write(text.strip().encode("utf-8") + b"\n")
    ser.flush()


def read_until_idle(
    ser: Any,
    idle: float = IDLE_SECONDS,
    timeout: float = 5.0,
    clock: Clock = time.monotonic,
    on_data: Optional[Callable[[bytes], None]] = None,
) -> bytes:
    """Read until no bytes arrived for `idle` seconds (after the first byte) or `timeout` expires."""
    start = clock()
    last_data: Optional[float] = None
    buf = bytearray()
    while True:
        chunk = ser.read(max(1, ser.in_waiting))
        now = clock()
        if chunk:
            buf.extend(chunk)
            last_data = now
            if on_data:
                on_data(chunk)
        elif last_data is not None and now - last_data >= idle:
            break
        if now - start >= timeout:
            break
    return bytes(buf)


def run_command(
    port: str,
    text: str,
    timeout: float = 5.0,
    idle: float = IDLE_SECONDS,
    opener: Optional[Opener] = None,
    clock: Clock = time.monotonic,
    on_data: Optional[Callable[[bytes], None]] = None,
) -> str:
    """Send one command and return the reply text. Raises NoReplyError if the board stays silent."""
    ser = (opener or open_serial)(port)
    try:
        ser.reset_input_buffer()
        send_line(ser, text)
        data = read_until_idle(ser, idle=idle, timeout=timeout, clock=clock, on_data=on_data)
    finally:
        ser.close()
    reply = data.decode("utf-8", errors="replace")
    if not reply.strip():
        raise NoReplyError(
            f"No reply from the board on {port} within {timeout:g} s",
            "Is DeskBuddy firmware installed? Try 'deskbuddy monitor' or reflash with 'deskbuddy flash'.",
        )
    return reply


def _present_boards(lister: Optional[ports_mod.Lister]) -> list[str]:
    found = ports_mod.list_ports(lister)
    return [p.device for p in ports_mod.board_candidates(found)]


def wait_for_board(
    preferred: Optional[str],
    timeout: float = 20.0,
    lister: Optional[ports_mod.Lister] = None,
    clock: Clock = time.monotonic,
    sleep: Sleeper = time.sleep,
    gone_first: bool = False,
    cancel: Optional[Callable[[], bool]] = None,
) -> Optional[str]:
    """Wait until a board port is present and return its name (None on timeout/cancel).

    `preferred` wins if it is present; otherwise the first board found is returned (the port
    may come back under a new name). With `gone_first`, the port must first disappear (i.e.
    actually re-enumerate); if it never disappears within the timeout it is returned anyway.
    """
    deadline = clock() + timeout
    seen_gone = not gone_first
    while True:
        if cancel and cancel():
            return None
        present = _present_boards(lister)
        if not present or (preferred and preferred not in present):
            seen_gone = True
        if seen_gone and present:
            return preferred if preferred in present else present[0]
        if clock() >= deadline:
            return preferred if present and preferred in present else None
        sleep(POLL_INTERVAL)
