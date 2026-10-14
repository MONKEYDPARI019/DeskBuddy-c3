#!/usr/bin/env python3
"""On-board regression test: the main loop must never block, whether or not a PC reads the USB port.

    python scripts/board_stress_test.py [--port COM9] [--clicks 50] [--gap 400]

Needs firmware 2.3.0+ (the 'stress' command clicks BTN1 in software, with sound and log lines,
exactly like a real press). Two runs:

1. no reader: 'stress' starts and the port is closed at once, so nobody reads the board's output
   while it clicks. Firmware 2.2.1 froze here (the whole loop, screen included) as soon as the
   256-byte USB send buffer was full: 'status' then reported a longest loop of ~23 s.
2. reader: the port stays open and is read the whole time.

Each run passes if the longest loop since the previous 'status' stays under 50 ms.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tool" / "src"))

from deskbuddy import ports, serial_io  # noqa: E402

LIMIT_MS = 50
_TIMING_RE = re.compile(r"longest loop (\d+) ms")


def longest_loop(port: str) -> int:
    reply = serial_io.run_command(port, "status", timeout=5.0)
    match = _TIMING_RE.search(reply)
    if not match:
        raise SystemExit("error: 'status' has no timing line; this needs firmware 2.3.0 or newer")
    return int(match.group(1))


def run(port: str, clicks: int, gap_ms: int, reader: bool) -> int:
    longest_loop(port)  # resets the maximum
    seconds = clicks * gap_ms / 1000 + 3
    ser = serial_io.open_serial(port)
    serial_io.send_line(ser, f"stress {clicks} {gap_ms}")
    if reader:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            ser.read(4096)
        ser.close()
    else:
        ser.close()  # nobody reads the port from now on
        time.sleep(seconds + 2)
    return longest_loop(port)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", help="serial port (default: the DeskBuddy found)")
    parser.add_argument("--clicks", type=int, default=50)
    parser.add_argument("--gap", type=int, default=400, help="ms between clicks (>= 150)")
    args = parser.parse_args()
    port = args.port or ports.choose_port(None, ports.list_ports())
    failed = False
    for reader in (False, True):
        ms = run(port, args.clicks, args.gap, reader)
        ok = ms < LIMIT_MS
        failed |= not ok
        label = "with a reader" if reader else "no reader   "
        print(f"{'PASS' if ok else 'FAIL'}  {label}  {args.clicks} clicks: longest loop {ms} ms (limit {LIMIT_MS})")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
