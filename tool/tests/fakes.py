"""Test doubles for serial ports and subprocesses."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from typing import Optional

import serial


class ScriptedSerial:
    """A fake serial port. Each read() returns the next scripted chunk (b"" = nothing arrived).

    `clock`, if given, is advanced by `tick` seconds per read to simulate the port timeout.
    A chunk that is an Exception instance is raised instead (e.g. the board unplugged).
    """

    def __init__(self, chunks: Iterable[object] = (), clock=None, tick: float = 0.1) -> None:
        self.chunks: deque[object] = deque(chunks)
        self.written = bytearray()
        self.clock = clock
        self.tick = tick
        self.is_open = True
        self.dtr: Optional[bool] = None
        self.rts: Optional[bool] = None
        self.reset_calls = 0

    @property
    def in_waiting(self) -> int:
        if self.chunks and isinstance(self.chunks[0], bytes):
            return len(self.chunks[0])  # type: ignore[arg-type]
        return 0

    def read(self, size: int = 1) -> bytes:
        if self.clock is not None:
            self.clock.sleep(self.tick)
        if not self.chunks:
            return b""
        chunk = self.chunks.popleft()
        if isinstance(chunk, BaseException):
            raise chunk
        assert isinstance(chunk, bytes)
        return chunk

    def write(self, data: bytes) -> int:
        if not self.is_open:
            raise serial.SerialException("port closed")
        self.written.extend(data)
        return len(data)

    def flush(self) -> None:
        pass

    def reset_input_buffer(self) -> None:
        self.reset_calls += 1

    def close(self) -> None:
        self.is_open = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
